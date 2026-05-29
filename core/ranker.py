import json
import time
import vertexai
from vertexai.generative_models import GenerationConfig, GenerativeModel
from .models import SearchCriteria

GEMINI_MODEL = "gemini-2.5-flash-lite"
GEMINI_LOCATION = "us-central1"

_PROMPT = """\
You are a shopping assistant. Analyze this product page and score how well it matches the search criteria.

Search criteria (JSON):
{criteria}

Product page text:
{text}

Return ONLY a JSON object with these fields:
{{
  "title": "product name, or empty string if not a product page",
  "price": null or numeric price in USD/EUR/GBP,
  "score": integer 0-10,
  "matched": ["criteria that are satisfied"],
  "unmatched": ["criteria that are not satisfied or unknown"],
  "notes": "one sentence explanation"
}}

Scoring guide:
- 9-10: all criteria met
- 7-8: most criteria met, minor gaps
- 4-6: partial match, notable gaps
- 1-3: poor fit
- 0: not a product page or completely off

Be strict about material exclusions (exclude list). If excluded materials are present, cap score at 3.
Return only the JSON object, no markdown, no extra text."""


def rank_candidate(url: str, text: str, criteria: SearchCriteria, model: GenerativeModel) -> dict:
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
        response = model.generate_content(
            _PROMPT.format(criteria=criteria.model_dump_json(indent=2), text=text),
            generation_config=GenerationConfig(temperature=0),
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
    vertexai.init(project=project, location=GEMINI_LOCATION)
    model = GenerativeModel(GEMINI_MODEL)

    from .fetcher import fetch_page_text

    results = []
    for item in candidates:
        url = item.get("link", "")
        print(f"  [{len(results) + 1}/{len(candidates)}] {url}")
        text = fetch_page_text(url)
        ranked = rank_candidate(url, text, criteria, model)
        ranked["url"] = url
        results.append(ranked)
        if delay:
            time.sleep(delay)
    return results
