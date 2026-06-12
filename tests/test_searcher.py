import json
from unittest.mock import MagicMock, patch

from core.models import SearchCriteria
from core.searcher import _grounded_search, _plan_queries, search_products

CRITERIA = SearchCriteria(category="jacket", gender="women", sizes=["M"])


def _make_client(text: str) -> MagicMock:
    client = MagicMock()
    response = MagicMock()
    response.text = text
    client.models.generate_content.return_value = response
    return client


def _make_grounding_chunk(uri: str, title: str) -> MagicMock:
    chunk = MagicMock()
    chunk.web.uri = uri
    chunk.web.title = title
    return chunk


# --- _plan_queries ---


def test_plan_queries_parses_valid_json_array():
    queries = ["women jacket buy", "jacket women M shop", "women jacket for sale"]
    client = _make_client(json.dumps(queries))
    result = _plan_queries(CRITERIA, client)
    assert result == queries


def test_plan_queries_strips_markdown_fences():
    queries = ["query one", "query two", "query three"]
    fenced = f"```json\n{json.dumps(queries)}\n```"
    client = _make_client(fenced)
    result = _plan_queries(CRITERIA, client)
    assert result == queries


def test_plan_queries_strips_plain_code_fences():
    queries = ["query one", "query two", "query three"]
    fenced = f"```\n{json.dumps(queries)}\n```"
    client = _make_client(fenced)
    result = _plan_queries(CRITERIA, client)
    assert result == queries


# --- _grounded_search ---


def test_grounded_search_extracts_urls_from_chunks():
    chunk1 = _make_grounding_chunk("https://shop.com/jacket", "Jacket Shop")
    chunk2 = _make_grounding_chunk("https://store.com/coat", "Coat Store")

    response = MagicMock()
    response.candidates[0].grounding_metadata.grounding_chunks = [chunk1, chunk2]

    client = MagicMock()
    client.models.generate_content.return_value = response

    result = _grounded_search("women jacket buy", client)
    assert len(result) == 2
    assert result[0] == {"link": "https://shop.com/jacket", "title": "Jacket Shop"}
    assert result[1] == {"link": "https://store.com/coat", "title": "Coat Store"}


def test_grounded_search_returns_empty_when_grounding_metadata_missing():
    response = MagicMock()
    response.candidates[0].grounding_metadata = None

    client = MagicMock()
    client.models.generate_content.return_value = response

    result = _grounded_search("women jacket buy", client)
    assert result == []


def test_grounded_search_returns_empty_when_candidates_empty():
    response = MagicMock()
    response.candidates = []

    client = MagicMock()
    client.models.generate_content.return_value = response

    result = _grounded_search("women jacket buy", client)
    assert result == []


def test_grounded_search_returns_empty_when_chunks_raise():
    response = MagicMock()
    response.candidates[0].grounding_metadata.grounding_chunks = MagicMock(
        __iter__=MagicMock(side_effect=AttributeError("no chunks"))
    )

    client = MagicMock()
    client.models.generate_content.return_value = response

    result = _grounded_search("women jacket buy", client)
    assert result == []


# --- search_products ---


def test_search_products_deduplicates_urls():
    queries = ["query one", "query two"]
    shared_url = "https://shop.com/jacket"
    chunk = _make_grounding_chunk(shared_url, "Jacket")

    plan_response = MagicMock()
    plan_response.text = json.dumps(queries)

    search_response = MagicMock()
    search_response.candidates[0].grounding_metadata.grounding_chunks = [chunk]

    with patch("core.searcher.genai.Client") as MockClient:
        mock_client = MagicMock()
        MockClient.return_value = mock_client
        mock_client.models.generate_content.side_effect = [plan_response, search_response, search_response]

        result = search_products(CRITERIA, "my-project", max_results=20)

    assert len(result) == 1
    assert result[0]["link"] == shared_url


def test_search_products_respects_max_results():
    queries = ["query one", "query two", "query three"]

    def make_chunk(i):
        return _make_grounding_chunk(f"https://shop.com/item{i}", f"Item {i}")

    chunks_per_query = [
        [make_chunk(1), make_chunk(2), make_chunk(3)],
        [make_chunk(4), make_chunk(5), make_chunk(6)],
        [make_chunk(7), make_chunk(8), make_chunk(9)],
    ]

    plan_response = MagicMock()
    plan_response.text = json.dumps(queries)

    call_idx = 0

    def side_effect(*args, **kwargs):
        nonlocal call_idx
        if call_idx == 0:
            call_idx += 1
            return plan_response
        resp = MagicMock()
        resp.candidates[0].grounding_metadata.grounding_chunks = chunks_per_query[call_idx - 1]
        call_idx += 1
        return resp

    with patch("core.searcher.genai.Client") as MockClient:
        mock_client = MagicMock()
        MockClient.return_value = mock_client
        mock_client.models.generate_content.side_effect = side_effect

        result = search_products(CRITERIA, "my-project", max_results=4)

    assert len(result) == 4
