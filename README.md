# Shop Assistant

CLI that monitors online shops for products matching saved search criteria. Uses Gemini (Vertex AI) to plan queries, search the web via Google Search grounding, and score each product page against your criteria. New matches are saved to Firestore and optionally emailed.

## How it works

1. **Plan** — Gemini generates 3 optimised search queries from your criteria
2. **Search** — Gemini with Google Search grounding returns product URLs (no API key needed)
3. **Fetch** — each URL is fetched and stripped to plain text
4. **Rank** — Gemini scores each page 0–10 against your criteria
5. **Save & notify** — results written to CSV + Firestore; email sent on new matches

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
make install        # uses uv if available
# or manually:
python3.12 -m venv .venv && source .venv/bin/activate && pip install -e .

cp .env.sample .env
# edit .env — only GOOGLE_CLOUD_PROJECT is required
```

**`.env` reference:**

```ini
# Required
GOOGLE_CLOUD_PROJECT=your-gcp-project-id

# Email notifications (optional — omit both to use CSV output only)
NOTIFY_EMAIL=you@gmail.com
GMAIL_APP_PASSWORD=xxxx_xxxx_xxxx_xxxx   # 16-char App Password from myaccount.google.com/apppasswords
GMAIL_FROM=you@gmail.com                  # defaults to NOTIFY_EMAIL if omitted

# Scoring thresholds (optional, shown with defaults)
MATCH_SCORE_THRESHOLD=7.0     # score >= this → full match
PARTIAL_SCORE_THRESHOLD=4.0   # score >= this → partial match
MAX_CANDIDATES=20             # max URLs to evaluate per run
```

## Daily operation

### Add a search

Write a JSON file describing what you want, save it under `searches/`, then push to Firestore:

```bash
make add FILE=searches/wax_coat.json
# or: python run.py add searches/wax_coat.json
```

**Search config format** (`searches/wax_coat.json`):

```json
{
  "search_name": "wax_coat",
  "active": true,
  "criteria": {
    "category": "coat",
    "gender": "women",
    "outer_material": ["waxed cotton"],
    "lining": ["none", "cotton", "viscose"],
    "exclude": ["polyester", "nylon", "synthetic"],
    "sizes": ["M", "L"],
    "max_price": 500,
    "extra_notes": "natural fabric lining preferred, or unlined"
  }
}
```

| Field | Required | Description |
|---|---|---|
| `search_name` | yes | Unique ID — used in file names and Firestore |
| `active` | yes | `false` skips this search on batch runs |
| `category` | yes | Product type keyword(s) |
| `gender` | yes | `"women"`, `"men"`, `"unisex"` |
| `outer_material` | no | Accepted outer materials |
| `lining` | no | Accepted lining materials |
| `exclude` | no | Materials that cap score at 3 if detected |
| `sizes` | no | Accepted sizes |
| `max_price` | no | Upper price limit |
| `extra_notes` | no | Free-text hints passed to the Gemini ranker |

### List saved searches

```bash
make list
# or: python run.py list
```

### Run searches

```bash
# run all active searches
make run

# run one specific search
make run-one SEARCH=wax_coat

# dry run — print results, skip Firestore write and email
make dry-run SEARCH=wax_coat
```

**Example output:**

```
Running: wax_coat
Queries: ['women waxed cotton coat buy', 'waxed cotton trench coat women M L shop', ...]
Candidates: 18
  [1/18] https://example.com/waxed-coat
  ...

=== wax_coat | 2026-06-11 | 18 candidates ===

Matches (2):
  [9/10] [NEW] Barbour Beadnell Waxed Cotton Jacket
    https://...
    Price: 349.0
    OK: waxed cotton outer, women, size M, no synthetic lining

Partial matches (3):
  [5/10] ...
```

### Update or disable a search

Edit the JSON file (change criteria or set `"active": false`) and re-add:

```bash
make add FILE=searches/wax_coat.json
```

This overwrites the Firestore document in place.

## Scheduling (cron)

```bash
crontab -e
# run all active searches at 08:00 every day
0 8 * * * cd /path/to/shop_assistant && source .venv/bin/activate && python run.py run >> logs/run.log 2>&1
```

For serverless: deploy `run.py run` to Cloud Run and trigger via Cloud Scheduler.

## Output

| Location | Contents |
|---|---|
| `results/<name>_<date>.csv` | Tab-separated: score, title, URL, price, matched/unmatched criteria |
| Firestore `shop_searches/<name>` | Search config (source of truth at runtime) |
| Firestore `shop_results/<name>/runs/<date>` | Full run result with all matches |
| Email | Sent only when new matches appear (requires `NOTIFY_EMAIL` + `GMAIL_APP_PASSWORD`) |

## GCP services & permissions

| Service | IAM role |
|---|---|
| Vertex AI (Gemini 2.5 Flash Lite) | `roles/aiplatform.user` |
| Firestore | `roles/datastore.user` |

No Google Custom Search API key or Programmable Search Engine is required — search is handled by Gemini's built-in Google Search grounding.

## Project structure

```
core/
  searcher.py          # AI planner + grounded search → candidate URLs
  fetcher.py           # HTTP fetch + HTML → plain text
  ranker.py            # Gemini scoring of individual product pages
  runner.py            # orchestrator: search → fetch → rank → save → notify
  notifier.py          # Gmail notification on new matches
  firestore_client.py  # Firestore read/write helpers
  models.py            # Pydantic models: SearchCriteria, ProductMatch, RunResult
  settings.py          # Env-based config (pydantic-settings)
searches/              # Search config JSON files (commit these)
results/               # CSV output — gitignore this directory
run.py                 # CLI entry point
Makefile               # Convenience targets: install, run, dry-run, list, add
```

## AI agents (Claude Code)

Three sub-agents are available under `.claude/agents/`:

| Agent | When to use |
|---|---|
| `senior-architect` | Reviewing pipeline design, Gemini prompt strategy, GCP cost |
| `code-reviewer` | After any code change — quality, security, performance, prompt fragility |
| `qa-engineer` | Adding or fixing tests; always mocks Vertex AI and Firestore |
