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
