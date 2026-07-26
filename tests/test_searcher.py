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


def test_grounded_search_falls_back_to_rendered_content_when_chunks_none():
    """Regression: grounding_chunks comes back as None (not []) whenever Gemini
    finds nothing worth explicitly citing — common for narrow site:-scoped
    preferred-shop queries. `for chunk in None` used to raise TypeError,
    caught by the outer except, which meant the secondary rendered-HTML
    fallback below it never even ran — silently zeroing out that shop's
    results even when the rendered search page had real links."""
    response = MagicMock()
    response.candidates[0].grounding_metadata.grounding_chunks = None
    response.candidates[
        0
    ].grounding_metadata.search_entry_point.rendered_content = '<a href="https://dillards.com/product/dress">Dress</a>'

    client = MagicMock()
    client.models.generate_content.return_value = response

    result = _grounded_search("site:dillards.com dresses", client)
    assert result == [{"link": "https://dillards.com/product/dress", "title": "Dress"}]


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
    # search_products now runs the discovery queries concurrently, so the mock
    # must dispatch by the CONTENT of each call (which query it's for) rather
    # than call order — a call-order-based side_effect isn't safe once calls
    # can arrive from multiple threads in any order.
    queries = ["query one", "query two", "query three"]

    def make_chunk(i):
        return _make_grounding_chunk(f"https://shop.com/item{i}", f"Item {i}")

    chunks_by_query = {
        "query one": [make_chunk(1), make_chunk(2), make_chunk(3)],
        "query two": [make_chunk(4), make_chunk(5), make_chunk(6)],
        "query three": [make_chunk(7), make_chunk(8), make_chunk(9)],
    }

    plan_response = MagicMock()
    plan_response.text = json.dumps(queries)

    def side_effect(*args, **kwargs):
        contents = kwargs.get("contents") or args[1]
        if isinstance(contents, str) and contents.startswith("You are a shopping search strategist"):
            return plan_response
        for query, chunks in chunks_by_query.items():
            if query in contents:
                resp = MagicMock()
                resp.candidates[0].grounding_metadata.grounding_chunks = chunks
                return resp
        raise AssertionError(f"unexpected call contents: {contents!r}")

    with patch("core.searcher.genai.Client") as MockClient:
        mock_client = MagicMock()
        MockClient.return_value = mock_client
        mock_client.models.generate_content.side_effect = side_effect

        result = search_products(CRITERIA, "my-project", max_results=4)

    assert len(result) == 4


# --- _search_shop: gender handling ---


def test_search_shop_gender_none_no_none_in_query():
    from core.searcher import _search_shop

    criteria = SearchCriteria(category=["bathroom cabinet"])
    client = MagicMock()
    # _grounded_search catches all errors internally; an unspecced MagicMock response is fine
    _search_shop("https://www.somestore.com/", criteria, client)

    call_args = client.models.generate_content.call_args
    contents = call_args[1]["contents"] if "contents" in call_args[1] else call_args[0][1]
    # gender=None must not produce the literal string "None" in the search query
    assert "None" not in contents


def test_search_shop_gender_set_includes_gender_in_query():
    from core.searcher import _search_shop

    criteria = SearchCriteria(category=["jacket"], gender="women")
    client = MagicMock()
    _search_shop("https://www.somestore.com/", criteria, client)

    call_args = client.models.generate_content.call_args
    contents = call_args[1]["contents"] if "contents" in call_args[1] else call_args[0][1]
    assert "women" in contents


def test_search_shop_bare_domain_no_scheme_still_scopes_query():
    """A shop entered without http(s):// (e.g. "nordstrom.com") must still produce
    a site:-scoped query — urlparse() puts a schemeless string entirely in .path,
    not .netloc, so this previously silently produced an unscoped site: query."""
    from core.searcher import _search_shop

    criteria = SearchCriteria(category=["dress"])
    client = MagicMock()
    _search_shop("nordstrom.com", criteria, client)

    call_args = client.models.generate_content.call_args
    contents = call_args[1]["contents"] if "contents" in call_args[1] else call_args[0][1]
    assert "site:nordstrom.com" in contents


# --- _plan_queries: exclude_defaults removes empty clothing fields ---


def test_plan_queries_furniture_empty_clothing_fields_absent():
    criteria = SearchCriteria(category=["bathroom cabinet"], dimensions="max 60cm")
    queries = ["query one", "query two", "query three"]
    client = _make_client(json.dumps(queries))

    _plan_queries(criteria, client)

    call_args = client.models.generate_content.call_args
    prompt = call_args[1]["contents"] if "contents" in call_args[1] else call_args[0][1]

    # Empty clothing list fields must be excluded from the criteria JSON in the prompt.
    # Check JSON-key form to avoid false matches against the static prompt text
    # (which uses plain English like "materials" and "gender").
    assert '"material"' not in prompt
    assert '"lining"' not in prompt
    # Category value and extra field must be present
    assert "bathroom cabinet" in prompt
    assert '"dimensions"' in prompt
