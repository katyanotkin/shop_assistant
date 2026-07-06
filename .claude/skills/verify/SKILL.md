---
name: verify
description: Launch TailoredLoop's web app and drive the admin UI end-to-end for verification (not unit tests).
---

# Verifying TailoredLoop changes live

## Launch

```bash
PYTHONPATH=. .venv/bin/python -m uvicorn web.main:app --port 8000 &
```

Requires `.env` with `GOOGLE_CLOUD_PROJECT` and `ADMIN_PASSWORD` set, and `gcloud auth application-default login` already done (real Firestore + Vertex AI, no mocks/emulator in this repo). Check `.env` for `ADMIN_PASSWORD` before scripting a login.

## Driving the admin UI (no Playwright installed by default)

`pip install playwright` then use `channel="chrome"` to reuse the system Chrome already present (`/usr/bin/google-chrome`) — skips the slow Playwright browser download:

```python
b = p.chromium.launch(channel="chrome", headless=True)
```

Log in through the real form (don't hand-roll cookie files — Netscape cookie-jar parsing from curl is fragile to get right):

```python
page.goto("http://localhost:8000/admin/login")
page.fill('input[name="password"]', pw)  # from .env ADMIN_PASSWORD
page.click('button[type="submit"]')
ctx.storage_state(path="authstate.json")  # reuse across script runs
```

## API surface for fast round-trip checks

Once logged in (curl with `-c/-b cookies.txt` against `/admin/login` also works for pure-API checks, no browser needed):

- `PUT /api/admin/search/{name}` — saves raw JSON straight to Firestore, **no pydantic validation on this path**. Validation (`SearchCriteria`'s validators) only runs when a search actually executes (`run_search` in `core/runner.py` constructs `SearchCriteria(**config["criteria"])`). If you need to see a model validator fire, you must trigger a real run or construct the model directly in a script — saving via the API alone won't do it.
- `GET /api/admin/search/{name}` — read back saved state.
- No `DELETE /api/admin/search/{name}` endpoint exists (only `DELETE /api/user/search/{name}`, owner-scoped). To clean up a test search created as admin, delete it directly:
  ```python
  from core import firestore_client as fc
  fc.delete_search_config("test_search_name")
  ```

## Exercising the ranker prompt/scoring behavior for real

Don't run the full pipeline (Google Search grounding + page fetch) just to check a prompt change — it's slow and costs real API quota. Instead call `core.ranker.rank_candidate` directly with a real (unmocked) `genai.Client` and synthetic product text — this is a real Gemini call through the actual changed prompt, without the search/fetch overhead:

```python
import google.genai as genai
from core.models import SearchCriteria
from core.ranker import rank_candidate

client = genai.Client(vertexai=True, project="<GOOGLE_CLOUD_PROJECT>", location="us-central1")
result = rank_candidate("https://example.com/x", "<synthetic product page text>", criteria, client)
```

## Gotchas

- Button text collisions in the edit form: "Save", "Save & Run", and "Save references" all match loose text selectors — use `page.get_by_role("button", name="Save", exact=True)`.
- Kill the dev server when done: `pkill -f "uvicorn web.main:app"`, then confirm with `curl --max-time 2 localhost:8000` failing, not `pgrep` (which matches its own grep invocation).
