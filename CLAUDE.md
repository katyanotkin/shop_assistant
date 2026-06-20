# Shop Assistant

CLI tool that monitors online shops for products matching saved search criteria, scores candidates with Gemini, and sends email notifications.

See [ARCHITECTURE.md](ARCHITECTURE.md) for the full pipeline, module roles, Firestore data model, API endpoints, and infrastructure details.
See [PRODUCT.md](PRODUCT.md) for the user-facing feature guide.

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
