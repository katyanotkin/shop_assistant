import json
import vertexai
from vertexai.generative_models import GenerationConfig, GenerativeModel, Tool, grounding
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


def _plan_queries(criteria: SearchCriteria, model: GenerativeModel) -> list[str]:
    response = model.generate_content(
        _PLAN_PROMPT.format(criteria=criteria.model_dump_json(indent=2)),
        generation_config=GenerationConfig(temperature=0),
    )
    raw = response.text.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return json.loads(raw)


def _grounded_search(query: str, model: GenerativeModel) -> list[dict]:
    response = model.generate_content(f"Find product pages for sale matching: {query}")
    results = []
    try:
        for chunk in response.candidates[0].grounding_metadata.grounding_chunks:
            if chunk.web.uri:
                results.append({"link": chunk.web.uri, "title": chunk.web.title})
    except Exception:
        pass
    return results


def search_products(criteria: SearchCriteria, project: str, max_results: int = 20) -> list[dict]:
    """Two-stage AI search: planner generates queries, grounded Gemini returns URLs."""
    vertexai.init(project=project, location=GEMINI_LOCATION)

    queries = _plan_queries(criteria, GenerativeModel(GEMINI_MODEL))
    print(f"Queries: {queries}")

    search_tool = Tool.from_google_search_retrieval(grounding.GoogleSearchRetrieval())
    searcher = GenerativeModel(GEMINI_MODEL, tools=[search_tool])

    seen: set[str] = set()
    results: list[dict] = []
    for query in queries:
        for item in _grounded_search(query, searcher):
            url = item["link"]
            if url not in seen:
                seen.add(url)
                results.append(item)
            if len(results) >= max_results:
                return results

    return results
