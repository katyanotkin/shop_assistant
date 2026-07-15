import json

import google.genai as genai
from google.genai import types

from . import firestore_client as fc

GEMINI_MODEL = "gemini-2.5-flash"
GEMINI_LOCATION = "us-central1"

_MIN_FEEDBACK_ITEMS = 1

_LEARN_PROMPT = """\
You are analyzing user feedback on shopping search results to extract durable signal for \
future searches.

Feedback items (JSON). Two kinds appear:
- Per-product items: the product's URL/domain, the Gemini-assigned score/matched/unmatched, \
and the user's free-text feedback on why the product was or wasn't right for them.
- Overall run notes (type "overall_note"): the user's direct statement about the run as a \
whole — what future runs should look for or avoid. Treat these as explicit, high-signal \
instructions.
{items}

Distinguish two kinds of signal:
1. Product-attribute preferences (material, lining, fit, dimensions, price expectations, etc.) \
— about the *product*, generalizable beyond any one shop.
2. Shop-level complaints (e.g. doesn't ship to the user, unreliable, poor quality control, \
repeatedly out of stock) — about the *seller/site*, not the product itself.

Return ONLY a JSON object:
{{
  "feedback_notes": "max 2 sentences distilling product-attribute preferences, or empty string if none",
  "avoid_shops": ["domain.com", ...]
}}
Extract only what the feedback explicitly supports — with few items, do not over-generalize. \
Do not restate the search criteria; capture only what the feedback ADDS to them. \
Only include a domain in avoid_shops if there's a clear shop-level complaint pattern for it \
(not a one-off). Return only the JSON object, no markdown, no extra text."""


def format_feedback_section(feedback_notes: str) -> str:
    if not feedback_notes:
        return ""
    return f"\nLearned preference from user feedback on past results:\n{feedback_notes}\n"


def learn_from_feedback(search_name: str, project: str) -> dict | None:
    """Distill accumulated free-text feedback into reusable signal, or None if too little feedback exists.

    Returns {"feedback_notes": str, "avoid_shops": list[str]}.
    """
    entries = fc.load_feedback_entries(search_name)
    if len(entries) < _MIN_FEEDBACK_ITEMS:
        return None

    client = genai.Client(vertexai=True, project=project, location=GEMINI_LOCATION)
    try:
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=_LEARN_PROMPT.format(items=json.dumps(entries, indent=2)),
            config=types.GenerateContentConfig(temperature=0),
        )
        raw = response.text.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.strip()
        parsed = json.loads(raw)
    except Exception:
        return None

    return {
        "feedback_notes": parsed.get("feedback_notes") or "",
        "avoid_shops": parsed.get("avoid_shops") or [],
    }


def submit_feedback(search_name: str, run_date: str, url: str, text: str) -> None:
    fc.save_feedback(search_name, run_date, url, text)
