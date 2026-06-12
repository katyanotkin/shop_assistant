import json
from unittest.mock import MagicMock

from core.models import SearchCriteria
from core.ranker import rank_candidate

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
