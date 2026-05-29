# Shop Assistant

A Python CLI that runs saved product searches daily, ranks results with Gemini AI, and emails you when new matches appear.

## How it works

1. You define a search (category, materials, sizes, price limit) as a JSON file
2. The tool queries Google Custom Search, fetches each product page, and sends the text to Gemini 2.5 Flash Lite for scoring against your criteria
3. Results are saved to Firestore and written to a local CSV; new matches trigger a Gmail notification

## Setup

```bash
# 1. Create virtualenv and install dependencies
make install

# 2. Copy and fill in credentials
cp .env.sample .env
# Edit .env — required: GOOGLE_CLOUD_PROJECT, GOOGLE_CUSTOM_SEARCH_API_KEY, SEARCH_ENGINE_ID
# Optional: NOTIFY_EMAIL + GMAIL_APP_PASSWORD for email alerts

# 3. Authenticate with GCP (Firestore + Vertex AI)
gcloud auth application-default login
```

## Usage

```bash
# Add a search config to Firestore
make add FILE=searches/wax_coat.json

# List all saved searches
make list

# Run all active searches
make run

# Run one search (dry-run: no save, no email)
make dry-run SEARCH=wax_coat
```

## Search config format

```json
{
  "search_name": "wax_coat",
  "active": true,
  "criteria": {
    "category": "coat",
    "gender": "women",
    "outer_material": ["waxed cotton"],
    "lining": ["none", "cotton", "wool"],
    "exclude": ["polyester", "nylon", "synthetic"],
    "sizes": ["M", "L"],
    "max_price": 300,
    "extra_notes": "natural fabric lining preferred, or unlined"
  }
}
```

## GCP services used

| Service | Purpose |
|---|---|
| Firestore | Stores search configs and run history |
| Vertex AI (Gemini) | Scores product pages against criteria |
| Google Custom Search API | Finds candidate product URLs |

## Output

- `results/<search_name>_<date>.csv` — tab-separated run results
- Email notification (if configured) — only sent when new matches appear
