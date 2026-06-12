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
1. Discovery query: "who sells {{gender}} {{material}} {{category terms}}?" — use ALL category values
2. Specific query: material + ALL category terms joined by "or" + gender + buying intent (buy/shop/for sale)
3. Specific query: material + ALL category terms + sizes + gender + for sale

Example for women's waxed cotton coat/jacket/trench M/L:
[
  "who sells women waxed cotton coat jacket trench?",
  "waxed cotton coat or jacket or trench women buy",
  "waxed cotton coat jacket trench women size M L for sale"
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


def _search_shop(shop_url: str, criteria: SearchCriteria, client: genai.Client) -> list[dict]:
    """Grounded search scoped to one preferred shop."""
    domain = urlparse(shop_url).netloc.removeprefix("www.")
    cats = " OR ".join(criteria.category)
    material = criteria.material[0] if criteria.material else ""
    query = f"site:{domain} ({cats}) {material} {criteria.gender}"
    return _grounded_search(query, client)


def _grounded_search(query: str, client: genai.Client) -> list[dict]:
    from bs4 import BeautifulSoup

    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=f"Find product pages for sale matching: {query}",
        config=types.GenerateContentConfig(tools=[types.Tool(google_search=types.GoogleSearch())]),
    )
    seen: set[str] = set()
    results: list[dict] = []

    try:
        meta = response.candidates[0].grounding_metadata

        # Primary: chunks Gemini explicitly cited
        for chunk in meta.grounding_chunks:
            if chunk.web and chunk.web.uri:
                url = chunk.web.uri
                if url not in seen:
                    seen.add(url)
                    results.append({"link": url, "title": chunk.web.title or ""})

        # Secondary: all URLs in the rendered Google search results page
        rendered = getattr(getattr(meta, "search_entry_point", None), "rendered_content", None)
        if rendered:
            soup = BeautifulSoup(rendered, "html.parser")
            for a in soup.find_all("a", href=True):
                href = a["href"]
                if href.startswith("http") and href not in seen:
                    seen.add(href)
                    results.append({"link": href, "title": a.get_text(strip=True)})
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

    seen: set[str] = set()
    results: list[dict] = []

    # Preferred shops first
    for shop_url in shops or []:
        for item in _search_shop(shop_url, criteria, client):
            url = item["link"]
            if url not in seen:
                seen.add(url)
                results.append(item)

    # General discovery queries fill remaining slots
    queries = _plan_queries(criteria, client)
    print(f"Queries: {queries}")
    for query in queries:
        for item in _grounded_search(query, client):
            url = item["link"]
            if url not in seen:
                seen.add(url)
                results.append(item)
            if len(results) >= max_results:
                return results

    return results
