# TailoredLoop

Web app that monitors online shops for products matching saved search criteria. Uses Gemini (Vertex AI) to plan queries, search the web via Google Search grounding, and score each product page against your criteria. Results are saved to Firestore and displayed in the browser UI.

## How it works

1. **Plan** — Gemini generates 3 optimised search queries from your criteria
2. **Search** — Gemini with Google Search grounding returns product URLs (no API key needed)
3. **Fetch** — each URL is fetched and stripped to plain text
4. **Rank** — Gemini scores each page 0–10 against your criteria
5. **Save** — results saved to Firestore; the web UI updates automatically

A lightweight web UI reads results from Firestore and displays them by search and date. An admin panel (password-protected) lets you create and edit searches, trigger runs, and leave feedback on results.

## Prerequisites

- Python 3.12+
- GCP project with **Vertex AI API** and **Firestore (Native mode)** enabled
- `gcloud` CLI installed and authenticated

```bash
gcloud auth application-default login
```

## Setup

```bash
git clone <repo> && cd shop_assistant

# create virtualenv and install
python3.12 -m venv .venv && source .venv/bin/activate && pip install -e .

cp .env.sample .env
# edit .env — only GOOGLE_CLOUD_PROJECT is required
```

**`.env` reference:**

```ini
# Required
GOOGLE_CLOUD_PROJECT=your-gcp-project-id

# Admin UI (optional — omit to disable the /admin panel)
ADMIN_PASSWORD=choose-a-strong-password

# Scoring thresholds (optional, shown with defaults)
MATCH_SCORE_THRESHOLD=7.0     # score >= this → full match
PARTIAL_SCORE_THRESHOLD=4.0   # score >= this → partial match
MAX_CANDIDATES=20             # max URLs to evaluate per run
```

## Daily operation

### Add a search

Go to `/admin`, log in, and click **+ New search** in the sidebar. Enter a short search name (lowercase, underscores) and describe what you want in plain text — material, style, size, price ceiling, preferred shops. Click **Generate config**: Gemini produces a structured config populated only with fields mentioned or implied by the description — `category` is always present, everything else is conditional. The config appears in an editable form. Optional fields can be added using the chip buttons in the **Add:** row, or removed with the × button on each field. Review the populated fields, then click **Save** or **Save & Run**.

### Create a search (signed-in users)

Signed-in users on the main page (`/`) can create one private search without admin access.

After signing in, a **+ New search** button appears in the sidebar. Free-plan users with one search already saved see no button. Admin-role users see an **Admin panel** link instead and use `/admin`.

Click **+ New search**: enter a title (free text) and describe what you want. Click **Generate**: Gemini produces a structured config identical to the admin flow; the search's Firestore ID is derived from the title. A JSON preview appears. Click **Save** to store it; a **Run** button then appears. Click **Run** to execute the search immediately.

The search appears under **My searches** in the sidebar. A **Run** button also appears in the toolbar when an owned search is selected.

Free-plan searches can be run for 30 days from the date they were created. After 30 days the Run endpoint returns an error message ("contact us to upgrade").

### Dev / bulk import (CLI)

```bash
make add FILE=searches/wax_coat.json
```

**Search config format:**

```json
{
  "search_name": "wax_coat",
  "active": true,
  "criteria": {
    "category": ["coat", "trenchcoat"],
    "gender": "women",
    "material": ["waxed cotton"],
    "lining": ["none", "cotton", "viscose"],
    "length": ["thigh", "midi", "long"],
    "exclude": ["polyester", "nylon", "synthetic"],
    "sizes": ["M", "L"],
    "max_price": 500,
    "extra_notes": "natural fabric lining preferred, or unlined"
  },
  "preferred_shops": [
    "https://www.houseofbruar.com"
  ]
}
```

| Field | Required | Description |
|---|---|---|
| `search_name` | yes | Unique ID — used in file names and Firestore |
| `active` | yes | `false` skips this search on batch runs |
| `category` | yes | Product type keyword(s) |
| `gender` | no | `"women"`, `"men"`, `"unisex"` |
| `material` | no | Accepted outer materials |
| `lining` | no | Accepted lining materials |
| `length` | no | Accepted lengths — any match satisfies (e.g. `"thigh"`, `"midi"`, `"long"`, `"maxi"`) |
| `exclude` | no | Materials that cap score at 3 if detected |
| `sizes` | no | Accepted sizes |
| `max_price` | no | Upper price limit |
| `extra_notes` | no | Free-text hints passed to the Gemini ranker |
| `preferred_shops` | no | Shop URLs to target directly with `site:` queries |

### Dev commands

```bash
make list                       # list all searches in Firestore
make run                        # run all active searches
make run-one SEARCH=wax_coat    # run one search
make dry-run SEARCH=wax_coat    # print results without saving
```

### Update or disable a search

Edit directly in the admin UI, or via CLI:

```bash
make add FILE=searches/wax_coat.json
```

This overwrites the Firestore document in place. You can also edit directly in the admin UI.

### Toggle visibility (admin)

When viewing any search config in `/admin`, a **Make public** / **Make private** button appears in the config header. Clicking it switches the search's visibility immediately. Private searches are visible only to their owner and admins. Public searches appear on the main page for everyone. Admins can toggle visibility on any search regardless of owner.

### Manage users (admin)

In `/admin`, click **Users** in the sidebar to see a table of all registered users with their name, email, and current role. Change the role dropdown (`free` / `premium` / `admin`) to update a user's role immediately — no re-login required for the user. There is no payment integration; qualifying for premium is decided outside the product.

## Feedback & learning

When logged in as admin, or as the owner of the search being viewed, each result card on the results page shows a feedback textarea with quick-phrase buttons ("Wrong material", "Doesn't ship to me", etc.). Click **Save all feedback** to write all non-empty fields in one batch.

On the next run, if at least 3 feedback items exist across the last 10 runs, Gemini distils product-attribute preferences and any shop-level complaints into reusable signal. That signal is injected into the planning and scoring prompts for the next run, and shops with a clear pattern of complaints are filtered out automatically. You can disable this per-run with the **Learn from feedback** checkbox in the admin edit view.

See PRODUCT.md for the full user journey including feedback details.

## Web UI

### Run locally

```bash
make local-run    # installs fastapi + uvicorn into .venv, starts on http://localhost:8000
```

The UI reads directly from Firestore — no CLI run needed. Select a search from the sidebar, pick a date (defaults to latest), and browse scored results.

The results page (`/`) is public. Signed-in users see their own private searches listed above the public searches in the sidebar and can create and run them from the main page. The admin panel (`/admin`) is accessible via `ADMIN_PASSWORD` or via Google sign-in for accounts with the `admin` role.

Google sign-in requires `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `SESSION_SECRET`, and optionally `BOOTSTRAP_ADMIN_EMAIL` in `.env` (see `.env.sample`). The sign-in flow always prompts the Google account chooser on every login.

### Host on Cloud Run

```bash
PROJECT=your-gcp-project-id
REGION=us-east1
IMAGE=us-east1-docker.pkg.dev/$PROJECT/shop-assistant/web

# build and push
docker build -f Dockerfile.web -t $IMAGE .
docker push $IMAGE

# deploy
gcloud run deploy shop-assistant-web \
  --image=$IMAGE \
  --region=$REGION \
  --platform=managed \
  --allow-unauthenticated \
  --set-env-vars=GOOGLE_CLOUD_PROJECT=$PROJECT
```

### Map a custom subdomain (e.g. shopassistant.verbboard.com)

Cloud Run domain mappings require the domain to be verified in your GCP project. If verbboard.com is already verified:

```bash
gcloud run domain-mappings create \
  --service=shop-assistant-web \
  --domain=shopassistant.verbboard.com \
  --region=$REGION
```

Then add the CNAME record shown in the output to your DNS (Cloudflare / Google Domains / etc.):

```
shopassistant   CNAME   ghs.googlehosted.com.
```

Propagation takes a few minutes; HTTPS is provisioned automatically by Cloud Run.

> If verbboard.com is **not** already verified in this GCP project, first run:
> `gcloud domains verify verbboard.com` and follow the TXT record prompt.

## Scheduling

```bash
crontab -e
# run all active searches at 08:00 every day
0 8 * * * cd /path/to/shop_assistant && source .venv/bin/activate && python run.py run >> logs/run.log 2>&1
```

For serverless: deploy `run.py run` to Cloud Run Jobs and trigger via Cloud Scheduler.

## Output

| Location | Contents |
|---|---|
| `results/<name>_<date>.csv` | CLI runs only — tab-separated: score, title, URL, price, matched/unmatched criteria |
| Firestore `shop_searches/<name>` | Search config (source of truth at runtime) |
| Firestore `shop_results/<name>/runs/<date>` | Full run result with all matches |

## GCP services & permissions

| Service | IAM role |
|---|---|
| Vertex AI (Gemini 2.5 Flash Lite) | `roles/aiplatform.user` |
| Firestore | `roles/datastore.user` |

No Google Custom Search API key is required — search uses Gemini's built-in Google Search grounding.

## Project structure

```
core/
  auth.py              # Google OAuth helpers and JWT session management
  brand.py             # App name/motto constants
  searcher.py          # AI planner + grounded search → candidate URLs
  fetcher.py           # HTTP fetch + HTML → plain text
  ranker.py            # Gemini scoring of individual product pages
  runner.py            # orchestrator: search → fetch → rank → save → notify
  notifier.py          # Gmail notifier — optional, not active in production
  firestore_client.py  # Firestore read/write helpers
  generator.py         # generate structured search config from free-text description
  feedback.py          # learn cycle: distil feedback → signal for next run
  models.py            # Pydantic models: SearchCriteria, ProductMatch, RunResult
  settings.py          # Env-based config (pydantic-settings)
web/
  main.py              # FastAPI app — serves UI and REST API
  static/app.css       # Styles (vanilla CSS, no framework)
  static/app.js        # Client logic for the public results page and user search creation
  static/admin.css     # Admin panel styles
  static/admin.js      # Admin panel logic: new search, generate, run, feedback, users tab, visibility toggle
  templates/index.html # Public results page shell
  templates/admin.html # Admin panel shell
  templates/admin_login.html # Password login form for /admin/login
  templates/privacy.html     # Privacy policy page
  templates/terms.html       # Terms of service page
searches/              # Search config JSON files (commit these)
results/               # CSV output — gitignore this directory
run.py                 # CLI entry point
Dockerfile.web         # Container for the web UI (Cloud Run)
Makefile               # Convenience targets
```

## Claude Code agents

| Agent | When to use |
|---|---|
| `senior-architect` | Reviewing pipeline design, Gemini prompt strategy, GCP cost |
| `senior-web-engineer` | JS/CSS/HTML correctness, FastAPI routing, auth/cookie mechanics, XSS; can review and implement |
| `code-reviewer` | After any code change — quality, security, performance, prompt fragility |
| `qa-engineer` | Adding or fixing tests; always mocks Vertex AI and Firestore |
| `ui-ux-engineer` | Web UI design critiques, CSS changes, layout decisions |
| `product-manager` | Role/permission decisions, feature gating, user journey questions, user-facing copy |
| `writer` | After significant feature additions or removals, update README.md |
