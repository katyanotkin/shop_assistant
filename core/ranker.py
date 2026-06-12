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
  "matched": ["brief label per satisfied requirement, e.g. 'waxed cotton', 'size M', 'price ok'"],
  "unmatched": ["brief label per unsatisfied requirement, e.g. 'lining unclear', 'size not listed'"],
  "notes": "one sentence explanation"
}}

Hard rules (violations → score 0):
- Product must match at least one value in `category`
- Product must match `gender` (or be unisex)
- Score 0 if not a product page at all

Soft rules (violations reduce score, do not zero it):
- material / lining / sizes / length: satisfied if ANY listed value matches
- exclude: if ANY excluded material is detected, cap score at 3
- max_price: up to 50% over limit → score ≤ 6, note "price over budget"; more than 50% over → score ≤ 3

Keep matched/unmatched labels concise (2-5 words) — no raw JSON field names.
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
