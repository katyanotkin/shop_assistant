import json
from urllib.parse import urlparse

import google.genai as genai
from google.genai import types

from . import models
from .feedback import format_feedback_section

GEMINI_MODEL = "gemini-2.5-flash"
GEMINI_LOCATION = "us-central1"

_PLAN_PROMPT = """\
You are a shopping search strategist. Given product search criteria, generate exactly 3 Google search queries.

Criteria (JSON):
{criteria}
{feedback_section}

Strategy — follow this order:
1. Discovery query: "who sells [key criteria] [all category terms]?" \
— pick the most distinctive criteria to narrow results
2. Specific query: key criteria + ALL category terms joined by "or" + buying intent (buy/shop/for sale)
3. Specific query: key criteria + ALL category terms + additional constraints + for sale

Extract the most important search terms from the criteria. Prioritise:
- category (always use ALL values)
- materials, colours, finishes, or physical attributes that narrow the field
- size, dimensions, or capacity constraints if present
- gender (only for clothing/fashion)
- price range if specified (e.g. "under £500")
- exclude any values from fields ending in `_exclude` or named `exclude`

Examples:

Women's waxed cotton coat/jacket/trench M/L:
[
  "who sells women waxed cotton coat jacket trench?",
  "waxed cotton coat or jacket or trench women buy",
  "waxed cotton coat jacket trench women size M L for sale"
]

Bathroom cabinet not white with shelves max 60 cm wide:
[
  "who sells bathroom cabinet with shelves not white?",
  "bathroom cabinet or bathroom storage unit shelves not white buy",
  "bathroom storage cabinet shelves dark colour max 60cm for sale"
]

Return ONLY a JSON array of 3 strings, no markdown, no extra text."""


def _plan_queries(criteria: models.SearchCriteria, client: genai.Client, feedback_notes: str = "") -> list[str]:
    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=_PLAN_PROMPT.format(
            criteria=criteria.model_dump_json(indent=2, exclude_defaults=True),
            feedback_section=format_feedback_section(feedback_notes),
        ),
        config=types.GenerateContentConfig(temperature=0),
    )
    raw = response.text.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return json.loads(raw)


def _search_shop(shop_url: str, criteria: models.SearchCriteria, client: genai.Client) -> list[dict]:
    """Grounded search scoped to one preferred shop."""
    domain = urlparse(shop_url).netloc.removeprefix("www.")
    cats = " OR ".join(criteria.category)
    parts = [f"({cats})"]
    if criteria.material:
        parts.append(criteria.material[0])
    if criteria.gender:
        parts.append(criteria.gender)
    query = f"site:{domain} " + " ".join(parts)
    return _grounded_search(query, client)


def _grounded_search(query: str, client: genai.Client) -> list[dict]:
    from bs4 import BeautifulSoup

    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=(
            f"Find direct product detail pages (each showing a single specific product for sale) "
            f"matching: {query}. Prefer individual product pages over category, collection, "
            f"or search-results pages."
        ),
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
    criteria: models.SearchCriteria,
    project: str,
    max_results: int = 20,
    shops: list[str] | None = None,
    feedback_notes: str = "",
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
    queries = _plan_queries(criteria, client, feedback_notes=feedback_notes)
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
