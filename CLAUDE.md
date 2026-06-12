# Shop Assistant

CLI tool that monitors online shops for products matching saved search criteria, scores candidates with Gemini, and sends email notifications.

## Architecture

```
SearchCriteria (Firestore)
        │
        ▼
┌───────────────────┐
│  Planner (Gemini) │  — generates 3 optimized search queries from criteria
└────────┬──────────┘
         │ queries[]
         ▼
┌────────────────────────────┐
│  Searcher (Gemini +        │  — Google Search grounding returns URLs per query
│  GoogleSearchRetrieval)    │    no Custom Search API key needed
└────────┬───────────────────┘
         │ candidates [{"link", "title"}]
         ▼
┌────────────────────────────┐
│  Fetcher (httpx + BS4)     │  — fetches page text, strips nav/footer/scripts
└────────┬───────────────────┘
         │ page text (≤3500 chars)
         ▼
┌────────────────────────────┐
│  Ranker (Gemini)           │  — scores 0-10, extracts title/price, matched/unmatched
└────────┬───────────────────┘
         │ ProductMatch[]
         ▼
  Firestore + CSV + Email
         │
         ▼
┌────────────────────────────┐
│  Web UI (FastAPI)          │  — reads Firestore, serves results by search + date
└────────────────────────────┘
```

### Key modules

| File | Role |
|------|------|
| `core/searcher.py` | Two-stage AI search: planner → grounded searcher |
| `core/fetcher.py` | HTTP fetch + HTML → plain text |
| `core/ranker.py` | Gemini scoring of individual product pages |
| `core/runner.py` | Orchestrator: search → fetch → rank → save → notify |
| `core/firestore_client.py` | Load search configs, persist run results |
| `core/notifier.py` | Gmail notification on new matches |
| `core/models.py` | Pydantic models: SearchCriteria, ProductMatch, RunResult |
| `core/settings.py` | Env-based config via pydantic-settings |
| `web/main.py` | FastAPI app: REST API + static file serving |
| `web/static/app.js` | Vanilla JS: sidebar, date picker, result cards |
| `web/static/app.css` | Styles — no framework, CSS custom properties |

### Gemini model

All three AI steps use `gemini-2.5-flash-lite` (`us-central1`) via Vertex AI.

### Search flow (searcher.py)

1. **Planner** — `_plan_queries(criteria)`: calls Gemini (no grounding) with criteria JSON, returns 3 search query strings optimized for buying intent.
2. **Grounded searcher** — `_grounded_search(query)`: calls Gemini with `GoogleSearchRetrieval` tool. URLs are extracted from `response.candidates[0].grounding_metadata.grounding_chunks[*].web.uri`.
3. Deduplicates URLs across queries, caps at `max_candidates` (default 20).

## Setup

```bash
gcloud auth application-default login
cp .env.sample .env
# edit .env — only GOOGLE_CLOUD_PROJECT is required
```

Required GCP APIs: Vertex AI, Firestore, Gmail (optional).

## Usage

```bash
# add a search config
python run.py add searches/wax_coat.json

# run a search
python run.py run wax_coat

# dry run (no Firestore write, no email)
python run.py run wax_coat --dry-run

# list saved searches
python run.py list
```

## Search config format

`searches/*.json`:
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
  "preferred_shops": ["https://www.houseofbruar.com"]
}
```
