import json
from unittest.mock import MagicMock, patch

import pytest

from core.models import SearchCriteria
from core.ranker import _example_section, fetch_example_refs, is_listing_url, rank_all, rank_candidate

CRITERIA = SearchCriteria(
    category="jacket",
    gender="women",
    material=["waxed cotton"],
    sizes=["M", "L"],
)

VALID_RESPONSE = {
    "title": "Barbour Waxed Cotton Jacket",
    "price": 249.99,
    "score": 9,
    "matched": ["waxed cotton", "women", "size M"],
    "unmatched": [],
    "notes": "Excellent match across all criteria.",
}


def _make_client(text: str) -> MagicMock:
    client = MagicMock()
    response = MagicMock()
    response.text = text
    client.models.generate_content.return_value = response
    return client


def test_rank_candidate_parses_valid_response():
    client = _make_client(json.dumps(VALID_RESPONSE))
    result = rank_candidate("https://example.com", "some page text", CRITERIA, client)
    assert result["score"] == 9
    assert result["title"] == "Barbour Waxed Cotton Jacket"
    assert result["price"] == 249.99
    assert "waxed cotton" in result["matched"]
    assert result["unmatched"] == []


def test_rank_candidate_strips_markdown_fences():
    fenced = f"```json\n{json.dumps(VALID_RESPONSE)}\n```"
    client = _make_client(fenced)
    result = rank_candidate("https://example.com", "some page text", CRITERIA, client)
    assert result["score"] == 9


def test_rank_candidate_strips_plain_code_fences():
    fenced = f"```\n{json.dumps(VALID_RESPONSE)}\n```"
    client = _make_client(fenced)
    result = rank_candidate("https://example.com", "some page text", CRITERIA, client)
    assert result["score"] == 9


def test_rank_candidate_returns_score_zero_on_empty_text():
    client = MagicMock()
    result = rank_candidate("https://example.com", "", CRITERIA, client)
    assert result["score"] == 0
    assert result["notes"] == "could not fetch page"
    client.models.generate_content.assert_not_called()


def test_rank_candidate_falls_back_to_title_only_when_text_empty_but_title_present():
    """A blocked fetch (see core/fetcher.py) shouldn't zero out a candidate we
    actually have a title for — it should still get scored, just conservatively
    and capped so it can never register as a full Match, only a Partial."""
    title_only_response = {
        "title": "Barbour Waxed Cotton Jacket",
        "price": None,
        "score": 9,
        "matched": ["waxed cotton"],
        "unmatched": [],
        "notes": "Title clearly matches.",
    }
    client = _make_client(json.dumps(title_only_response))
    result = rank_candidate("https://example.com", "", CRITERIA, client, title="Barbour Waxed Cotton Jacket")
    assert result["score"] == 6  # capped below match_score_threshold despite model returning 9
    assert result["price"] is None
    assert "Unverified" in result["notes"]
    assert "Title clearly matches" in result["notes"]
    client.models.generate_content.assert_called_once()


def test_rank_candidate_title_only_respects_low_model_score():
    """The cap only ever lowers a score, never raises one — a poor title-only
    match should still score below the cap, not get inflated to it."""
    title_only_response = {
        "title": "Some Other Product",
        "price": None,
        "score": 2,
        "matched": [],
        "unmatched": ["category"],
        "notes": "Doesn't look related.",
    }
    client = _make_client(json.dumps(title_only_response))
    result = rank_candidate("https://example.com", "", CRITERIA, client, title="Some Other Product")
    assert result["score"] == 2


def test_rank_candidate_title_only_handles_malformed_json():
    client = _make_client("not valid json {{{")
    result = rank_candidate("https://example.com", "", CRITERIA, client, title="Some Title")
    assert result["score"] == 0
    assert "analysis error" in result["notes"]


def test_rank_candidate_returns_score_zero_on_malformed_json():
    client = _make_client("this is not json at all {{{")
    result = rank_candidate("https://example.com", "some page text", CRITERIA, client)
    assert result["score"] == 0
    assert "analysis error" in result["notes"]


def test_rank_candidate_returns_score_zero_on_partial_json():
    client = _make_client('{"score": 8, "title":')
    result = rank_candidate("https://example.com", "some page text", CRITERIA, client)
    assert result["score"] == 0
    assert "analysis error" in result["notes"]


def test_rank_candidate_handles_api_exception():
    client = MagicMock()
    client.models.generate_content.side_effect = Exception("API unavailable")
    result = rank_candidate("https://example.com", "some page text", CRITERIA, client)
    assert result["score"] == 0
    assert "analysis error" in result["notes"]
    assert "API unavailable" in result["notes"]


def test_rank_candidate_zero_score_has_empty_defaults():
    client = _make_client("not json")
    result = rank_candidate("https://example.com", "some text", CRITERIA, client)
    assert result["title"] == ""
    assert result["price"] is None
    assert result["matched"] == []
    assert result["unmatched"] == []


# --- exclude_defaults=True in ranker prompt ---

_FURNITURE_CRITERIA = SearchCriteria(
    category=["bathroom cabinet"],
    dimensions="max 60cm",
    has_shelves=True,
)

_FURNITURE_RESPONSE = {
    "title": "Bathroom Cabinet",
    "price": 199.99,
    "score": 8,
    "matched": ["shelves"],
    "unmatched": [],
    "notes": "Good match.",
}


def _get_ranker_prompt(criteria: SearchCriteria, client_response: dict) -> str:
    """Call rank_candidate and return the full prompt string sent to the model."""
    client = _make_client(json.dumps(client_response))
    rank_candidate("https://example.com", "some product text", criteria, client)
    call_args = client.models.generate_content.call_args
    return call_args[1]["contents"] if "contents" in call_args[1] else call_args[0][1]


def test_furniture_criteria_extra_fields_appear_in_prompt():
    prompt = _get_ranker_prompt(_FURNITURE_CRITERIA, _FURNITURE_RESPONSE)
    # The extra field "dimensions" must be present as a JSON key in the criteria section
    assert '"dimensions"' in prompt
    # "material" is at its default ([]) so exclude_defaults=True must have dropped it
    assert '"material"' not in prompt


def test_furniture_criteria_gender_absent_from_prompt():
    prompt = _get_ranker_prompt(_FURNITURE_CRITERIA, _FURNITURE_RESPONSE)
    # gender=None is the default; exclude_defaults=True must have dropped it.
    # Static prompt text uses `gender` in backticks, not "gender" as a JSON key,
    # so checking for the JSON-key form '"gender"' is unambiguous.
    assert '"gender"' not in prompt


# --- deal_breakers ---


def test_deal_breakers_rule_present_in_static_prompt():
    from core.ranker import _PROMPT

    assert "deal_breakers" in _PROMPT
    assert "cap score at 3" in _PROMPT


def test_deal_breakers_appear_in_prompt_when_set():
    criteria = SearchCriteria(category=["bathroom cabinet"], dimensions="max 60cm", deal_breakers=["dimensions"])
    prompt = _get_ranker_prompt(criteria, _FURNITURE_RESPONSE)
    assert '"deal_breakers"' in prompt
    assert '"dimensions"' in prompt


def test_deal_breakers_absent_from_prompt_when_unset():
    prompt = _get_ranker_prompt(_FURNITURE_CRITERIA, _FURNITURE_RESPONSE)
    # _FURNITURE_CRITERIA has no deal_breakers set, so exclude_defaults=True must drop it
    assert '"deal_breakers"' not in prompt


# --- listing-page hard rule ---


def test_listing_page_hard_rule_present_in_static_prompt():
    from core.ranker import _PROMPT

    assert "category, collection, search-results" in _PROMPT


# --- is_listing_url ---


@pytest.mark.parametrize(
    "url",
    [
        # word segments flag at any depth
        "https://www.ikea.com/us/en/cat/bathroom-shelving-units-20804/",
        "https://thebradiva.com/collections/size-30g-bras",
        # single-letter prefix only counts in shallow paths (<=2 segments)
        "https://www.worldmarket.com/c/bath",
    ],
)
def test_is_listing_url_true(url):
    assert is_listing_url(url) is True


@pytest.mark.parametrize(
    "url",
    [
        # single-letter prefix "b" but 3 segments deep -> shallow-prefix rule doesn't fire
        "https://www.ebay.com/b/Metal-Bathroom-Shelves/31385/bn_123",
        # Shopify product nested under a collection -> product marker wins
        "https://shop.com/collections/coats/products/waxed-coat",
        "https://www.amazon.com/HCIOAN/dp/B0FSZ",
        "https://www.target.com/p/fantasie-bra",
        # grounding redirect URL has no recognizable markers at all
        "https://vertexaisearch.cloud.google.com/grounding-api-redirect/AbCdEf",
        "https://example.com/waxed-coat-12345",
    ],
)
def test_is_listing_url_false(url):
    assert is_listing_url(url) is False


# --- fetch_example_refs / _example_section ---


def test_fetch_example_refs_truncates_text_to_example_text_chars():
    from core.ranker import _EXAMPLE_TEXT_CHARS

    long_text = "x" * (_EXAMPLE_TEXT_CHARS + 500)
    with patch("core.ranker.fetch_page", return_value=("https://example.com/ref", long_text, [])):
        refs = fetch_example_refs(["https://example.com/ref"])
    assert len(refs) == 1
    assert refs[0]["url"] == "https://example.com/ref"
    assert len(refs[0]["text"]) == _EXAMPLE_TEXT_CHARS


def test_fetch_example_refs_empty_list_does_not_fetch():
    with patch("core.ranker.fetch_page") as mock_fetch:
        refs = fetch_example_refs([])
    assert refs == []
    mock_fetch.assert_not_called()


def test_example_section_empty_refs_returns_empty_string():
    assert _example_section([]) == ""


def test_example_section_wraps_excerpt_in_untrusted_delimiters():
    refs = [{"url": "https://example.com/ref", "text": "some scraped text"}]
    section = _example_section(refs)
    assert "https://example.com/ref" in section
    assert "<untrusted_page_text>" in section
    assert "some scraped text" in section
    assert "</untrusted_page_text>" in section


def test_example_section_empty_text_has_url_only_no_delimiter_block():
    refs = [{"url": "https://example.com/ref", "text": ""}]
    section = _example_section(refs)
    assert "https://example.com/ref" in section
    assert "<untrusted_page_text>" not in section
    assert "</untrusted_page_text>" not in section


# --- rank_all ---


def _client_returning(response_dict: dict) -> MagicMock:
    client = MagicMock()
    response = MagicMock()
    response.text = json.dumps(response_dict)
    client.models.generate_content.return_value = response
    return client


def test_rank_all_skips_listing_url_before_fetching():
    candidates = [
        {"link": "https://shop.com/collections/coats"},
        {"link": "https://example.com/product/waxed-coat"},
    ]
    with (
        patch("core.ranker.fetch_page") as mock_fetch,
        patch("core.ranker.genai.Client") as MockClient,
    ):
        mock_fetch.return_value = ("https://example.com/product/waxed-coat", "some product text", [])
        MockClient.return_value = _client_returning(VALID_RESPONSE)

        results = rank_all(candidates, CRITERIA, project="test-project")

    assert len(results) == 1
    fetched_urls = [c.args[0] for c in mock_fetch.call_args_list]
    assert "https://shop.com/collections/coats" not in fetched_urls
    assert fetched_urls == ["https://example.com/product/waxed-coat"]


def test_rank_all_scores_from_title_when_fetch_returns_empty_text():
    """A candidate whose page couldn't be fetched (blocked shop, see
    core/fetcher.py) must still reach the ranker via its title, not get
    silently dropped — end-to-end through rank_all, not just rank_candidate."""
    candidates = [{"link": "https://blocked-shop.com/product/coat", "title": "Barbour Waxed Cotton Jacket"}]
    title_only_response = {
        "title": "Barbour Waxed Cotton Jacket",
        "price": None,
        "score": 9,
        "matched": ["waxed cotton"],
        "unmatched": [],
        "notes": "Title matches.",
    }
    with (
        patch(
            "core.ranker.fetch_page",
            return_value=("https://blocked-shop.com/product/coat", "", []),
        ),
        patch("core.ranker.genai.Client") as MockClient,
    ):
        MockClient.return_value = _client_returning(title_only_response)

        results = rank_all(candidates, CRITERIA, project="test-project")

    assert len(results) == 1
    assert results[0]["score"] == 6  # capped, never a full Match from title alone
    assert "Unverified" in results[0]["notes"]


def test_rank_all_dedupes_candidates_resolving_to_the_same_final_url():
    candidates = [
        {"link": "https://vertexaisearch.cloud.google.com/grounding-api-redirect/AAA"},
        {"link": "https://vertexaisearch.cloud.google.com/grounding-api-redirect/BBB"},
    ]
    with (
        patch(
            "core.ranker.fetch_page",
            return_value=("https://shop.com/product/coat-123", "product text", []),
        ) as mock_fetch,
        patch("core.ranker.genai.Client") as MockClient,
    ):
        client = _client_returning(VALID_RESPONSE)
        MockClient.return_value = client

        results = rank_all(candidates, CRITERIA, project="test-project")

    assert mock_fetch.call_count == 2
    assert len(results) == 1
    assert client.models.generate_content.call_count == 1


def test_rank_all_dedupes_locale_mirrors_via_hreflang_alternates():
    """Some shops (Rydale among them) serve the same product at several
    locale-prefixed paths with no redirect between them and a
    self-referencing canonical tag on each — final_url alone can't catch
    this, but the hreflang alternates each page declares can."""
    candidates = [
        {"link": "https://shop.com/products/coat"},
        {"link": "https://shop.com/us/products/coat"},
    ]

    def fake_fetch_page(url, *args, **kwargs):
        if url == "https://shop.com/products/coat":
            return url, "product text (GB)", ["https://shop.com/us/products/coat"]
        return url, "product text (US)", ["https://shop.com/products/coat"]

    with (
        patch("core.ranker.fetch_page", side_effect=fake_fetch_page) as mock_fetch,
        patch("core.ranker.genai.Client") as MockClient,
    ):
        client = _client_returning(VALID_RESPONSE)
        MockClient.return_value = client

        results = rank_all(candidates, CRITERIA, project="test-project")

    assert mock_fetch.call_count == 2  # both still fetched — dedup only decides which get ranked
    assert len(results) == 1
    assert results[0]["url"] == "https://shop.com/products/coat"  # first occurrence wins
    assert client.models.generate_content.call_count == 1


def test_rank_all_dedupes_locale_mirrors_regardless_of_which_variant_is_first():
    """Same fixture as above with candidate order reversed — confirms
    "first occurrence wins" holds in either direction, not just the one
    where the GB/bare variant happens to come first."""
    candidates = [
        {"link": "https://shop.com/us/products/coat"},
        {"link": "https://shop.com/products/coat"},
    ]

    def fake_fetch_page(url, *args, **kwargs):
        if url == "https://shop.com/products/coat":
            return url, "product text (GB)", ["https://shop.com/us/products/coat"]
        return url, "product text (US)", ["https://shop.com/products/coat"]

    with (
        patch("core.ranker.fetch_page", side_effect=fake_fetch_page) as mock_fetch,
        patch("core.ranker.genai.Client") as MockClient,
    ):
        client = _client_returning(VALID_RESPONSE)
        MockClient.return_value = client

        results = rank_all(candidates, CRITERIA, project="test-project")

    assert mock_fetch.call_count == 2
    assert len(results) == 1
    assert results[0]["url"] == "https://shop.com/us/products/coat"  # first occurrence wins
    assert client.models.generate_content.call_count == 1


def test_rank_all_skips_candidate_resolving_to_listing_url():
    candidates = [{"link": "https://vertexaisearch.cloud.google.com/grounding-api-redirect/AbCdEf"}]
    with (
        patch(
            "core.ranker.fetch_page",
            return_value=("https://shop.com/collections/coats", "listing page text", []),
        ),
        patch("core.ranker.genai.Client") as MockClient,
    ):
        client = _client_returning(VALID_RESPONSE)
        MockClient.return_value = client

        results = rank_all(candidates, CRITERIA, project="test-project")

    assert results == []
    client.models.generate_content.assert_not_called()


def test_rank_all_fetches_example_refs_once_and_includes_in_every_prompt():
    candidates = [
        {"link": "https://example.com/product/a"},
        {"link": "https://example.com/product/b"},
    ]

    def fake_fetch_page(url, *args, **kwargs):
        if "reference" in url:
            return url, "reference product text", []
        return url, "candidate product text", []

    with (
        patch("core.ranker.fetch_page", side_effect=fake_fetch_page),
        patch("core.ranker.fetch_example_refs", wraps=fetch_example_refs) as mock_refs,
        patch("core.ranker.genai.Client") as MockClient,
    ):
        client = _client_returning(VALID_RESPONSE)
        MockClient.return_value = client

        rank_all(
            candidates,
            CRITERIA,
            project="test-project",
            example_urls=["https://example.com/reference/coat"],
        )

    mock_refs.assert_called_once_with(["https://example.com/reference/coat"], fetch_timeout=8.0)
    assert client.models.generate_content.call_count == 2
    for call in client.models.generate_content.call_args_list:
        contents = call.kwargs["contents"] if "contents" in call.kwargs else call.args[1]
        assert "https://example.com/reference/coat" in contents
        assert "reference product text" in contents
