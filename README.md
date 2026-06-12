# Shop Assistant

CLI + web UI that monitors online shops for products matching saved search criteria. Uses Gemini (Vertex AI) to plan queries, search the web via Google Search grounding, and score each product page against your criteria. New matches are saved to Firestore and optionally emailed.

## How it works

1. **Plan** — Gemini generates 3 optimised search queries from your criteria
2. **Search** — Gemini with Google Search grounding returns product URLs (no API key needed)
3. **Fetch** — each URL is fetched and stripped to plain text
4. **Rank** — Gemini scores each page 0–10 against your criteria
5. **Save & notify** — results written to CSV + Firestore; email sent on new matches

A lightweight web UI reads results from Firestore and displays them by search and date.

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
| `gender` | yes | `"women"`, `"men"`, `"unisex"` |
| `material` | no | Accepted outer materials |
| `lining` | no | Accepted lining materials |
| `length` | no | Accepted lengths — any match satisfies (e.g. `"thigh"`, `"midi"`, `"long"`, `"maxi"`) |
| `exclude` | no | Materials that cap score at 3 if detected |
| `sizes` | no | Accepted sizes |
| `max_price` | no | Upper price limit |
| `extra_notes` | no | Free-text hints passed to the Gemini ranker |
| `preferred_shops` | no | Shop URLs to target directly with `site:` queries |

### List / run / dry-run

```bash
make list                       # list all searches in Firestore
make run                        # run all active searches
make run-one SEARCH=wax_coat    # run one search
make dry-run SEARCH=wax_coat    # print results, skip save and email
```

### Update or disable a search

Edit the JSON file (change criteria or set `"active": false`) and re-add:

```bash
make add FILE=searches/wax_coat.json
```

This overwrites the Firestore document in place.

## Web UI

### Run locally

```bash
make local-run    # installs fastapi + uvicorn into .venv, starts on http://localhost:8000
```

The UI reads directly from Firestore — no CLI run needed. Select a search from the sidebar, pick a date (defaults to latest), and browse scored results.

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
| `results/<name>_<date>.csv` | Tab-separated: score, title, URL, price, matched/unmatched criteria |
| Firestore `shop_searches/<name>` | Search config (source of truth at runtime) |
| Firestore `shop_results/<name>/runs/<date>` | Full run result with all matches |
| Email | Sent only when new matches appear (requires `NOTIFY_EMAIL` + `GMAIL_APP_PASSWORD`) |

## GCP services & permissions

| Service | IAM role |
|---|---|
| Vertex AI (Gemini 2.5 Flash Lite) | `roles/aiplatform.user` |
| Firestore | `roles/datastore.user` |

No Google Custom Search API key is required — search uses Gemini's built-in Google Search grounding.

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
web/
  main.py              # FastAPI app — serves UI and REST API
  static/app.css       # Styles (vanilla CSS, no framework)
  static/app.js        # Client logic (vanilla JS, no framework)
  templates/index.html # Single-page shell
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
| `code-reviewer` | After any code change — quality, security, performance, prompt fragility |
| `qa-engineer` | Adding or fixing tests; always mocks Vertex AI and Firestore |
| `ui-ux-engineer` | Web UI design critiques, CSS changes, layout decisions |
