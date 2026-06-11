import json
from unittest.mock import MagicMock
from core.ranker import rank_candidate
from core.models import SearchCriteria


CRITERIA = SearchCriteria(
    category="jacket",
    gender="women",
    outer_material=["waxed cotton"],
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


def _make_model(text: str) -> MagicMock:
    model = MagicMock()
    response = MagicMock()
    response.text = text
    model.generate_content.return_value = response
    return model


def test_rank_candidate_parses_valid_response():
    model = _make_model(json.dumps(VALID_RESPONSE))
    result = rank_candidate("https://example.com", "some page text", CRITERIA, model)
    assert result["score"] == 9
    assert result["title"] == "Barbour Waxed Cotton Jacket"
    assert result["price"] == 249.99
    assert "waxed cotton" in result["matched"]
    assert result["unmatched"] == []


def test_rank_candidate_strips_markdown_fences():
    fenced = f"```json\n{json.dumps(VALID_RESPONSE)}\n```"
    model = _make_model(fenced)
    result = rank_candidate("https://example.com", "some page text", CRITERIA, model)
    assert result["score"] == 9


def test_rank_candidate_strips_plain_code_fences():
    fenced = f"```\n{json.dumps(VALID_RESPONSE)}\n```"
    model = _make_model(fenced)
    result = rank_candidate("https://example.com", "some page text", CRITERIA, model)
    assert result["score"] == 9


def test_rank_candidate_returns_score_zero_on_empty_text():
    model = MagicMock()
    result = rank_candidate("https://example.com", "", CRITERIA, model)
    assert result["score"] == 0
    assert result["notes"] == "could not fetch page"
    model.generate_content.assert_not_called()


def test_rank_candidate_returns_score_zero_on_malformed_json():
    model = _make_model("this is not json at all {{{")
    result = rank_candidate("https://example.com", "some page text", CRITERIA, model)
    assert result["score"] == 0
    assert "analysis error" in result["notes"]


def test_rank_candidate_returns_score_zero_on_partial_json():
    model = _make_model('{"score": 8, "title":')
    result = rank_candidate("https://example.com", "some page text", CRITERIA, model)
    assert result["score"] == 0
    assert "analysis error" in result["notes"]


def test_rank_candidate_handles_api_exception():
    model = MagicMock()
    model.generate_content.side_effect = Exception("API unavailable")
    result = rank_candidate("https://example.com", "some page text", CRITERIA, model)
    assert result["score"] == 0
    assert "analysis error" in result["notes"]
    assert "API unavailable" in result["notes"]


def test_rank_candidate_zero_score_has_empty_defaults():
    model = _make_model("not json")
    result = rank_candidate("https://example.com", "some text", CRITERIA, model)
    assert result["title"] == ""
    assert result["price"] is None
    assert result["matched"] == []
    assert result["unmatched"] == []
