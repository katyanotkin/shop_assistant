import json
from urllib.parse import urlparse
import google.genai as genai
from google.genai import types
from .models import SearchCriteria

GEMINI_MODEL = "gemini-2.5-flash-lite"
GEMINI_LOCATION = "us-central1"

_PLAN_PROMPT = """\
You are a shopping search strategist. Given product search criteria, generate exactly 3 Google search queries.

Criteria (JSON):
{criteria}

Query format — follow this order strictly:
1. Discovery query: "who sells {{gender}} {{category}}?" — broad, finds brands and shops
2. Specific query: product + key material + gender + buying intent (buy/shop/for sale)
3. Specific query: product + material + sizes + gender + for sale

Example for women's waxed cotton coat M/L:
[
  "who sells women waxed cotton coats?",
  "waxed cotton coat women buy",
  "waxed cotton coat women size M L for sale"
]

Return ONLY a JSON array of 3 strings, no markdown, no extra text."""


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


def _shop_queries(criteria: SearchCriteria, shops: list[str]) -> list[str]:
    keywords = " ".join(criteria.category[:1] + criteria.outer_material[:1] + [criteria.gender])
    queries = []
    for shop_url in shops:
        domain = urlparse(shop_url).netloc.removeprefix("www.")
        queries.append(f"site:{domain} {keywords}")
    return queries


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


def search_products(
    criteria: SearchCriteria,
    project: str,
    max_results: int = 20,
    shops: list[str] | None = None,
) -> list[dict]:
    """Two-stage AI search: planner generates queries, grounded Gemini returns URLs."""
    client = genai.Client(vertexai=True, project=project, location=GEMINI_LOCATION)

    queries = _plan_queries(criteria, client)
    if shops:
        queries += _shop_queries(criteria, shops)
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
