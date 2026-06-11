import json
from unittest.mock import MagicMock, patch
from core.searcher import _plan_queries, _grounded_search, search_products
from core.models import SearchCriteria


CRITERIA = SearchCriteria(category="jacket", gender="women", sizes=["M"])


def _mock_model_response(text: str) -> MagicMock:
    response = MagicMock()
    response.text = text
    return response


def _make_model(text: str) -> MagicMock:
    model = MagicMock()
    model.generate_content.return_value = _mock_model_response(text)
    return model


# --- _plan_queries ---

def test_plan_queries_parses_valid_json_array():
    queries = ["women jacket buy", "jacket women M shop", "women jacket for sale"]
    model = _make_model(json.dumps(queries))
    result = _plan_queries(CRITERIA, model)
    assert result == queries


def test_plan_queries_strips_markdown_fences():
    queries = ["query one", "query two", "query three"]
    fenced = f"```json\n{json.dumps(queries)}\n```"
    model = _make_model(fenced)
    result = _plan_queries(CRITERIA, model)
    assert result == queries


def test_plan_queries_strips_plain_code_fences():
    queries = ["query one", "query two", "query three"]
    fenced = f"```\n{json.dumps(queries)}\n```"
    model = _make_model(fenced)
    result = _plan_queries(CRITERIA, model)
    assert result == queries


# --- _grounded_search ---

def _make_grounding_chunk(uri: str, title: str) -> MagicMock:
    chunk = MagicMock()
    chunk.web.uri = uri
    chunk.web.title = title
    return chunk


def test_grounded_search_extracts_urls_from_chunks():
    chunk1 = _make_grounding_chunk("https://shop.com/jacket", "Jacket Shop")
    chunk2 = _make_grounding_chunk("https://store.com/coat", "Coat Store")

    response = MagicMock()
    response.candidates[0].grounding_metadata.grounding_chunks = [chunk1, chunk2]

    model = MagicMock()
    model.generate_content.return_value = response

    result = _grounded_search("women jacket buy", model)
    assert len(result) == 2
    assert result[0] == {"link": "https://shop.com/jacket", "title": "Jacket Shop"}
    assert result[1] == {"link": "https://store.com/coat", "title": "Coat Store"}


def test_grounded_search_returns_empty_when_grounding_metadata_missing():
    response = MagicMock()
    response.candidates[0].grounding_metadata = None

    model = MagicMock()
    model.generate_content.return_value = response

    result = _grounded_search("women jacket buy", model)
    assert result == []


def test_grounded_search_returns_empty_when_candidates_empty():
    response = MagicMock()
    response.candidates = []

    model = MagicMock()
    model.generate_content.return_value = response

    result = _grounded_search("women jacket buy", model)
    assert result == []


def test_grounded_search_returns_empty_when_chunks_raise():
    response = MagicMock()
    # Make iterating grounding_chunks raise to exercise the bare except
    response.candidates[0].grounding_metadata.grounding_chunks = MagicMock(
        __iter__=MagicMock(side_effect=AttributeError("no chunks"))
    )

    model = MagicMock()
    model.generate_content.return_value = response

    result = _grounded_search("women jacket buy", model)
    assert result == []


# --- search_products ---

def test_search_products_deduplicates_urls():
    queries = ["query one", "query two"]
    shared_url = "https://shop.com/jacket"

    chunk = _make_grounding_chunk(shared_url, "Jacket")
    response = MagicMock()
    response.candidates[0].grounding_metadata.grounding_chunks = [chunk]

    plan_response = MagicMock()
    plan_response.text = json.dumps(queries)

    with patch("vertexai.init"), \
         patch("core.searcher.GenerativeModel") as MockModel, \
         patch("core.searcher.Tool"), \
         patch("core.searcher.grounding"):

        planner = MagicMock()
        planner.generate_content.return_value = plan_response

        searcher = MagicMock()
        searcher.generate_content.return_value = response

        MockModel.side_effect = [planner, searcher]

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

    call_count = 0

    def make_search_response(*args, **kwargs):
        nonlocal call_count
        resp = MagicMock()
        resp.candidates[0].grounding_metadata.grounding_chunks = chunks_per_query[call_count]
        call_count += 1
        return resp

    with patch("vertexai.init"), \
         patch("core.searcher.GenerativeModel") as MockModel, \
         patch("core.searcher.Tool"), \
         patch("core.searcher.grounding"):

        planner = MagicMock()
        planner.generate_content.return_value = plan_response

        searcher = MagicMock()
        searcher.generate_content.side_effect = make_search_response

        MockModel.side_effect = [planner, searcher]

        result = search_products(CRITERIA, "my-project", max_results=4)

    assert len(result) == 4
