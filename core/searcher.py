from googleapiclient.discovery import build
from .models import SearchCriteria


def build_query(criteria: SearchCriteria) -> str:
    parts = [criteria.gender, criteria.category]
    parts.extend(criteria.outer_material)
    if criteria.sizes:
        parts.append(" ".join(criteria.sizes))
    parts.append("buy")
    return " ".join(parts)


def search_google(
    query: str, api_key: str, engine_id: str, num: int = 20
) -> list[dict]:
    service = build("customsearch", "v1", developerKey=api_key)
    results: list[dict] = []
    for start in range(1, num + 1, 10):
        batch = min(10, num - len(results))
        response = (
            service.cse()
            .list(q=query, cx=engine_id, start=start, num=batch)
            .execute()
        )
        results.extend(response.get("items", []))
        if len(results) >= num or "nextPage" not in response.get("queries", {}):
            break
    return results[:num]
