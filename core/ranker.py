import json
import time
import google.genai as genai
from google.genai import types
from .models import SearchCriteria

GEMINI_MODEL = "gemini-2.5-flash-lite"
GEMINI_LOCATION = "us-central1"

_PROMPT = """\
You are a shopping assistant. Score how well this product page matches the search criteria.

Search criteria (JSON):
{criteria}

Product page text:
{text}

Return ONLY a JSON object:
{{
  "title": "product name, or empty string if not a product page",
  "price": null or numeric price in USD/EUR/GBP,
  "score": integer 0-10,
  "matched": ["brief human-readable label per satisfied requirement, e.g. 'waxed cotton outer', 'size M available', 'price within budget'"],
  "unmatched": ["brief label per unsatisfied or unknown requirement, e.g. 'lining unclear', 'size not listed', 'price too high'"],
  "notes": "one sentence explanation"
}}

Scoring:
- 9-10: all criteria met
- 7-8: most criteria met, minor gaps
- 4-6: partial match, notable gaps
- 1-3: poor fit
- 0: not a product page

Rules:
- outer_material / lining / sizes: satisfied if ANY listed value matches
- exclude: if ANY excluded material is detected, cap score at 3
- max_price: satisfied if listed price is at or below the limit
- Keep matched/unmatched labels concise (2-5 words each) — no raw JSON field names or array indices
Return only the JSON object, no markdown, no extra text."""


def rank_candidate(url: str, text: str, criteria: SearchCriteria, client: genai.Client) -> dict:
    if not text:
        return {
            "title": "",
            "price": None,
            "score": 0,
            "matched": [],
            "unmatched": [],
            "notes": "could not fetch page",
        }
    try:
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=_PROMPT.format(criteria=criteria.model_dump_json(indent=2), text=text),
            config=types.GenerateContentConfig(temperature=0),
        )
        raw = response.text.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        return json.loads(raw)
    except Exception as e:
        return {
            "title": "",
            "price": None,
            "score": 0,
            "matched": [],
            "unmatched": [],
            "notes": f"analysis error: {e}",
        }


def rank_all(
    candidates: list[dict],
    criteria: SearchCriteria,
    project: str,
    delay: float = 1.0,
) -> list[dict]:
    client = genai.Client(vertexai=True, project=project, location=GEMINI_LOCATION)

    from .fetcher import fetch_page

    results = []
    for item in candidates:
        url = item.get("link", "")
        print(f"  [{len(results) + 1}/{len(candidates)}] {url}")
        final_url, text = fetch_page(url)
        ranked = rank_candidate(final_url, text, criteria, client)
        ranked["url"] = final_url
        results.append(ranked)
        if delay:
            time.sleep(delay)
    return results
