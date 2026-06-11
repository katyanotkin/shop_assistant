import json
import google.genai as genai
from google.genai import types
from .models import SearchCriteria

GEMINI_MODEL = "gemini-2.5-flash-lite"
GEMINI_LOCATION = "us-central1"

_PLAN_PROMPT = """\
You are a shopping search strategist. Given product search criteria, generate 3 effective Google search queries to find matching products for sale online.

Criteria (JSON):
{criteria}

Return ONLY a JSON array of 3 query strings. Example:
["women waxed cotton coat buy", "waxed cotton trench coat women M shop", "waxed cotton jacket women size M L for sale"]

Focus on: product category, materials, gender, sizes. Include buying-intent words (buy, shop, for sale).
Return only the JSON array, no markdown, no extra text."""


def _plan_queries(criteria: SearchCriteria, client: genai.Client) -> list[str]:
    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=_PLAN_PROMPT.format(criteria=criteria.model_dump_json(indent=2)),
        config=types.GenerateContentConfig(temperature=0),
    )
    raw = response.text.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return json.loads(raw)


def _grounded_search(query: str, client: genai.Client) -> list[dict]:
    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=f"Find product pages for sale matching: {query}",
        config=types.GenerateContentConfig(
            tools=[types.Tool(google_search=types.GoogleSearch())]
        ),
    )
    results = []
    try:
        for chunk in response.candidates[0].grounding_metadata.grounding_chunks:
            if chunk.web and chunk.web.uri:
                results.append({"link": chunk.web.uri, "title": chunk.web.title or ""})
    except Exception:
        pass
    return results


def search_products(criteria: SearchCriteria, project: str, max_results: int = 20) -> list[dict]:
    """Two-stage AI search: planner generates queries, grounded Gemini returns URLs."""
    client = genai.Client(vertexai=True, project=project, location=GEMINI_LOCATION)

    queries = _plan_queries(criteria, client)
    print(f"Queries: {queries}")

    seen: set[str] = set()
    results: list[dict] = []
    for query in queries:
        for item in _grounded_search(query, client):
            url = item["link"]
            if url not in seen:
                seen.add(url)
                results.append(item)
            if len(results) >= max_results:
                return results

    return results
