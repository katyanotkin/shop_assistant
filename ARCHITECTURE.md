# Architecture

## System overview

Shop Assistant monitors online shops for products matching saved search criteria. On each run it: generates optimized search queries from structured criteria, uses Gemini with Google Search grounding to find candidate product URLs, fetches and strips each page, scores each candidate against the criteria, persists results to Firestore, writes a local CSV, and optionally sends an email notification for new matches. A FastAPI web app reads from Firestore and serves results to a browser UI.

---

## Pipeline

```
SearchCriteria (Firestore)
        │
        ▼
┌───────────────────┐
│  Planner          │  Gemini, no grounding — generates 3 search query strings
└────────┬──────────┘
         │ queries[]
         ▼
┌────────────────────────────┐
│  Searcher                  │  Gemini + GoogleSearch grounding — returns URLs
└────────┬───────────────────┘
         │ candidates [{link, title}]
         ▼
┌────────────────────────────┐
│  Fetcher                   │  httpx + BeautifulSoup — page text ≤ 3500 chars
└────────┬───────────────────┘
         │ page text
         ▼
┌────────────────────────────┐
│  Ranker                    │  Gemini, no grounding — score 0–10 + structured output
└────────┬───────────────────┘
         │ ProductMatch[]
         ▼
  Firestore + CSV + Email
```

### Stage 1 — Planner (`core/searcher.py: _plan_queries`)

- **Input:** `SearchCriteria` serialized as JSON, plus optional `feedback_notes` string from prior learn cycle.
- **Model:** `gemini-2.5-flash-lite`, `us-central1`, temperature 0, no grounding.
- **Output:** JSON array of exactly 3 query strings. Queries follow a fixed format: discovery ("who sells…?"), material+category buying intent, material+category+sizes.
- The feedback section is injected into the prompt only when `feedback_notes` is non-empty.

### Stage 2 — Searcher (`core/searcher.py: _grounded_search`, `_search_shop`)

- **Input:** one query string.
- **Model:** `gemini-2.5-flash-lite`, `us-central1`, `GoogleSearch` tool (Gemini native grounding — no Custom Search API key needed).
- **Output:** list of `{link, title}` dicts, extracted from two sources:
  1. `response.candidates[0].grounding_metadata.grounding_chunks[*].web` — URLs Gemini explicitly cited.
  2. `grounding_metadata.search_entry_point.rendered_content` — all `<a href>` links in the rendered Google SERP HTML (secondary fallback, parsed with BeautifulSoup).
- For each configured `preferred_shop`, a separate `site:<domain>` scoped query is issued first (`_search_shop`), so preferred-shop results appear at the top of the candidate list.
- URLs are deduplicated across all queries; the candidate list is capped at `max_candidates` (default 40, configurable via `MAX_CANDIDATES` env var).

### Stage 3 — Fetcher (`core/fetcher.py`)

- **Input:** candidate URL.
- **Output:** `(final_url, text)` — `final_url` is the URL after following redirects; `text` is page content stripped of `script`, `style`, `nav`, `footer`, `header`, `aside` tags, truncated to 3500 characters.
- Uses `httpx` with a Chrome-like `User-Agent` and `Accept-Language: en-US` header.
- Timeout configurable via `FETCH_TIMEOUT` env var (default 12 s). On any error, returns `(url, "")`.
- The fetcher is called inside `rank_all` rather than as a separate batch step, so fetch and rank are interleaved with a 1 s delay between candidates to avoid hammering shops.

### Stage 4 — Ranker (`core/ranker.py`)

- **Input:** page text + `SearchCriteria` + optional `feedback_notes`.
- **Model:** `gemini-2.5-flash-lite`, `us-central1`, temperature 0, no grounding.
- **Output:** JSON object `{title, price, score, matched[], unmatched[], notes}`.
- Scoring rules injected in the system prompt:
  - **Hard rules (score → 0):** not a product page; wrong category; wrong gender.
  - **Soft rules:** `exclude` match → cap at 3; price >50% over `max_price` → cap at 3; price ≤50% over → cap at 6; material/lining/sizes/length satisfied if any value matches.
  - `matched[]` / `unmatched[]` are concise 2–5-word labels, not raw field names.

### Stage 5 — Classify & Persist (`core/runner.py`)

- Scores are compared against two thresholds (env-configurable):
  - `score >= MATCH_SCORE_THRESHOLD` (default 7.0) → `matches[]`
  - `score >= PARTIAL_SCORE_THRESHOLD` (default 4.0) → `partial_matches[]`
  - Below partial threshold → discarded.
- `is_new = True` for any URL not present in the previous run's combined matches+partial_matches.
- Previous run is loaded from Firestore with `load_last_run`.
- Both lists are sorted descending by score.
- **Outputs:** Firestore run document, local TSV file at `results/<name>_<date>.csv`, email notification (if configured and new matches exist).

### Learn cycle (`core/feedback.py`, `core/generator.py`)

Runs at the start of each `run_search` call (unless `learn=False` or `dry_run`):

1. `load_feedback_entries(search_name, limit=10)` collects all feedback-tagged items from the last 10 runs.
2. If ≥ 3 feedback items exist, `learn_from_feedback` calls Gemini with the items and extracts:
   - `feedback_notes` — up to 2 sentences of product-attribute preferences.
   - `avoid_shops` — list of domains with shop-level complaints.
3. `save_learned_feedback` writes both back to the `shop_searches` document.
4. On the next run, `feedback_notes` is injected into Planner and Ranker prompts; candidate URLs from `avoid_shops` domains are filtered out before ranking.

---

## Gemini model calls — summary

| Stage | Function | Grounding | Temperature | Notes |
|-------|----------|-----------|-------------|-------|
| Planner | `_plan_queries` | None | 0 | Injects `feedback_notes` if present |
| Searcher | `_grounded_search` | `GoogleSearch` | (default) | Called once per query + once per preferred shop |
| Ranker | `rank_candidate` | None | 0 | Injects `feedback_notes` if present |
| Learn | `learn_from_feedback` | None | 0 | Only when ≥ 3 feedback items exist |
| Generate config | `generate_search_config` | None | 0 | Admin and user "generate" flows; converts free text → `SearchConfig` JSON |

All calls use `gemini-2.5-flash-lite` on Vertex AI in `us-central1`. Auth is Application Default Credentials.

---

## Firestore data model

### Collection: `shop_searches`

Document ID = `search_name` (e.g. `wax_coat`).

| Field | Type | Description |
|-------|------|-------------|
| `search_name` | string | Primary key, matches document ID. URL slug, `^[a-z0-9_]{1,64}$`. For free users this is server-derived from `title` (see below); admins still type it directly |
| `title` | string | Required. Free-form human-readable name. Free users type this directly; `search_name` is derived from it via `core/slug.py: slugify()` + `core/firestore_client.py: generate_unique_search_name()` (numeric-suffix dedup `_2`, `_3`, ... against a reserved-word blocklist, falling back to a uuid suffix after 50 attempts). Defaulted from `search_name` (title-cased) by `save_search_config` if not set, so CLI- and admin-created docs also get one |
| `active` | bool | Included in results UI; inactive searches still appear in admin |
| `visibility` | string | `"public"` (default) or `"private"` |
| `owner_id` | string | `"admin"` or a user email; controls who sees private searches |
| `description` | string | Original free-text description used to generate the config; preserved across edits |
| `criteria` | map | `SearchCriteria` fields: `category[]` (required) plus any product-appropriate fields (`gender`, `material[]`, `lining[]`, `length[]`, `exclude[]`, `sizes[]`, `max_price`, `extra_notes`, or custom fields for non-clothing categories) |
| `preferred_shops` | string[] | URLs of preferred retailers; searched first each run |
| `example_urls` | string[] | Up to 3 product URLs the admin marked as ideal matches; fed to the ranker for calibration |
| `feedback_notes` | string | Distilled product preferences from learn cycle; injected into prompts |
| `avoid_shops` | string[] | Domains filtered from candidates; written by learn cycle |

### Collection: `shop_results/{search_name}/runs`

Document ID = `run_date` (ISO date string, e.g. `2026-06-20`).

| Field | Type | Description |
|-------|------|-------------|
| `search_name` | string | Redundant with parent path; kept for query convenience |
| `run_date` | string | ISO date |
| `matches` | ProductMatch[] | Score ≥ match threshold |
| `partial_matches` | ProductMatch[] | Score ≥ partial threshold |
| `no_match` | bool | True when both lists are empty |
| `total_candidates` | int | Number of URLs fetched and ranked |
| `config_snapshot` | SearchConfig | Full copy of the search config at the time of the run — preserved even if the live config is later edited |
| `feedback` | map | Keyed by MD5 hex of URL; each value is `{url: string, text: string}` |

**Why MD5 keys for feedback:** Firestore field paths use `/` as a path separator, and product URLs contain slashes. Storing them raw as field names would break Firestore's nested-field update syntax. MD5 hex strings are safe field names. The `_decode_feedback` helper converts back to `{url: text}` before serving the frontend.

`ProductMatch` fields: `url`, `title`, `price` (float|null), `score` (float), `matched[]`, `unmatched[]`, `notes`, `is_new` (bool).

---

## Web API

Base URL: `https://shopassistant.verbboard.com`

### Public endpoints (no auth)

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/` | Main results page (HTML) — read-only, no admin UI |
| `GET` | `/api/searches` | List searches visible to the caller: `[{name, title, active, visibility, owned}]` |
| `GET` | `/api/search/{name}` | Public search config (criteria + preferred_shops only) |
| `GET` | `/api/results/{search_name}` | List run dates for a search (descending), 404 if none |
| `GET` | `/api/results/{search_name}/{run_date}` | Full run document; `feedback` decoded to `{url: text}` |
| `GET` | `/api/me` | `{role, anonymous, name?, email?}` — current user identity from session or admin cookie |

### Auth endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/auth/login` | Redirect to Google OAuth; accepts `?next=<path>` to set post-login destination |
| `GET` | `/auth/callback` | OAuth callback; sets `sa_session` cookie, redirects to `next` (default `/`) |
| `POST` | `/auth/logout` | Clears `sa_session` and `sa_admin` cookies |

### Admin page endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/admin` | Admin panel (HTML); redirects to `/admin/login` if not authenticated |
| `GET` | `/admin/login` | Admin login page (Google sign-in + password form) |
| `POST` | `/admin/login` | Form-based password login; sets `sa_admin` cookie, redirects to `/admin` |

### Admin API endpoints (require `sa_admin` or `sa_session` with `role=admin`)

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/admin/login` | JSON password login: `{password}` → sets `sa_admin` cookie |
| `POST` | `/api/admin/logout` | Clears both `sa_admin` and `sa_session` cookies |
| `GET` | `/api/admin/me` | `{admin: bool}` — checks `sa_admin` cookie |
| `GET` | `/api/admin/searches` | Full search configs including `feedback_notes`, `avoid_shops` |
| `GET` | `/api/admin/search/{name}` | Single search config |
| `PUT` | `/api/admin/search/{name}` | Upsert search config — loads the existing doc and merges the request body on top (`{**existing, **body}`), so fields the admin form doesn't send (`description`, `feedback_notes`, `owner_id`, `visibility`, `title`) are preserved rather than wiped |
| `POST` | `/api/admin/search/generate` | `{search_name, description}` → Gemini config JSON; `description` preserved and `title` set to `search_name` title-cased |
| `POST` | `/api/admin/run/{name}` | Trigger a search run synchronously; returns `{ok, matches, partial}` |
| `PUT` | `/api/feedback/{search_name}/{run_date}/batch` | Save feedback; body: `{items: [{url, text}]}` |

### User API endpoints (require `sa_session`)

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/user/search/generate` | `{title, description}` → Gemini config JSON. `search_name` is server-derived from `title` via `generate_unique_search_name`. Response is the generated config plus `search_name`, `title`, `description`, `visibility: "private"`, `owner_id`. Free-plan users limited to one search |

**Auth mechanisms:**

- **Password (`sa_admin` cookie):** `ADMIN_PASSWORD` env var. Login hashes `"sa:{password}"` with SHA-256 and stores the hex digest as an HttpOnly, SameSite=Strict cookie. Checked by `_require_admin` dependency and `_is_admin()` helper.
- **Google OAuth (`sa_session` cookie):** JWT signed with `SESSION_SECRET`. Set on `/auth/callback` after Google verifies identity. User record stored in Firestore `users` collection; `role` field determines access. `BOOTSTRAP_ADMIN_EMAIL` is promoted to `admin` on first login.
- **Both cookies present:** OAuth session identity wins for `/api/me`. Both are cleared on any logout.

**Feedback batch write:** `save_feedback_batch` issues a single Firestore `update()` call (`feedback.<md5>` per URL). Falls back to `set(..., merge=True)` if the document doesn't exist. Items with empty `text` are excluded by the caller.

---

## Infrastructure

| Component | Detail |
|-----------|--------|
| Runtime | Cloud Run, region `us-east1`, unauthenticated access allowed |
| Image registry | Artifact Registry: `us-east1-docker.pkg.dev/$PROJECT_ID/shop-assistant/web` |
| Build trigger | Cloud Build trigger `main-deploy` — fires on push to `main` branch of `katyanotkin/shop_assistant` (ignores `*.md`, `.gitignore`, `searches/**`) |
| Build steps | `docker build -f Dockerfile.web` → `docker push` → `gcloud run deploy` |
| Secrets | Injected from Secret Manager via `--set-secrets` in `cloudbuild.yaml`: `ADMIN_PASSWORD`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `SESSION_SECRET`, `BOOTSTRAP_ADMIN_EMAIL` |
| Service account | `cloudbuild-deployer@knotmem26.iam.gserviceaccount.com` |
| Vertex AI | `us-central1` (separate from Cloud Run region) |
| Web process | `uvicorn web.main:app --host 0.0.0.0 --port 8080` inside `python:3.12-slim` |
| Live regression | After deploy, run `BASE_URL=https://shopassistant.verbboard.com python -m pytest tests/test_live_qatp.py -v` |

The web image excludes `run.py`, `searches/`, `tests/`, and `results/` — only `core/` and `web/` are copied into the container.
