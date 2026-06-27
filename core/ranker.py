import json
import time

import google.genai as genai
from google.genai import types

from . import models
from .feedback import format_feedback_section
from .fetcher import fetch_page

GEMINI_MODEL = "gemini-2.5-flash-lite"
GEMINI_LOCATION = "us-central1"


def _example_section(urls: list[str]) -> str:
    if not urls:
        return ""
    header = "\nReference products (use as style/quality benchmarks when scoring):\n"
    return header + "\n".join(f"- {u}" for u in urls) + "\n"


_PROMPT = """\
You are a shopping assistant. Score how well this product page matches the search criteria.

Search criteria (JSON):
{criteria}
{feedback_section}{example_section}
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
- Product must match at least one value in `category` — this is always enforced.
- If `gender` is present in criteria: product must match it (or be unisex); otherwise ignore.
- Score 0 if not a product page at all.

Soft rules (violations reduce score, do not zero it):
- For any criteria field that lists acceptable values (arrays), the requirement is satisfied \
if ANY listed value matches the product. If none match, reduce the score.
- Fields ending in `_exclude` or named `exclude`: if ANY excluded value is present in the \
product, cap score at 3.
- `max_price`: up to 50% over limit → score ≤ 6, note "price over budget"; \
more than 50% over → score ≤ 3.
- For non-standard fields (dimensions, features, capacity, color_exclude, etc.): apply \
common-sense matching — treat them as strong requirements and reduce the score \
proportionally if the product does not satisfy them.

Keep matched/unmatched labels concise (2-5 words) — use plain English, not raw JSON field names.
Return only the JSON object, no markdown, no extra text."""


def rank_candidate(
    url: str,
    text: str,
    criteria: models.SearchCriteria,
    client: genai.Client,
    feedback_notes: str = "",
    example_urls: list[str] | None = None,
) -> dict:
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
            contents=_PROMPT.format(
                criteria=criteria.model_dump_json(indent=2, exclude_defaults=True),
                feedback_section=format_feedback_section(feedback_notes),
                example_section=_example_section(example_urls or []),
                text=text,
            ),
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
    criteria: models.SearchCriteria,
    project: str,
    delay: float = 1.0,
    feedback_notes: str = "",
    example_urls: list[str] | None = None,
) -> list[dict]:
    client = genai.Client(vertexai=True, project=project, location=GEMINI_LOCATION)
    results = []
    for item in candidates:
        url = item.get("link", "")
        print(f"  [{len(results) + 1}/{len(candidates)}] {url}")
        final_url, text = fetch_page(url)
        ranked = rank_candidate(
            final_url,
            text,
            criteria,
            client,
            feedback_notes=feedback_notes,
            example_urls=example_urls,
        )
        ranked["url"] = final_url
        results.append(ranked)
        if delay:
            time.sleep(delay)
    return results
