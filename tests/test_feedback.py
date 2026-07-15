import json
from unittest.mock import MagicMock, patch

from core.feedback import format_feedback_section, learn_from_feedback


def _mock_response(text: str) -> MagicMock:
    resp = MagicMock()
    resp.text = text
    return resp


# ── format_feedback_section ──────────────────────────────────────────────────


def test_format_feedback_section_empty_notes_returns_empty_string():
    assert format_feedback_section("") == ""


def test_format_feedback_section_wraps_notes():
    section = format_feedback_section("prefers wool over polyester")
    assert "prefers wool over polyester" in section


# ── learn_from_feedback ───────────────────────────────────────────────────────

_ONE_ENTRY = [
    {
        "url": "https://shop.example.com/a",
        "domain": "shop.example.com",
        "title": "Waxed Coat",
        "score": 9,
        "matched": ["material"],
        "unmatched": [],
        "feedback": "loved the fit",
    }
]

_LEARNED = {"feedback_notes": "prefers a tailored fit", "avoid_shops": []}


def test_learn_from_feedback_runs_with_a_single_entry():
    """_MIN_FEEDBACK_ITEMS == 1: a single feedback item is now enough to learn from,
    unlike the old threshold of 3."""
    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = _mock_response(json.dumps(_LEARNED))

    with (
        patch("core.feedback.fc.load_feedback_entries", return_value=_ONE_ENTRY),
        patch("core.feedback.genai.Client", return_value=mock_client),
    ):
        result = learn_from_feedback("wax_coat", "test-project")

    assert result == {"feedback_notes": "prefers a tailored fit", "avoid_shops": []}
    mock_client.models.generate_content.assert_called_once()


def test_learn_from_feedback_returns_none_with_zero_entries():
    with patch("core.feedback.fc.load_feedback_entries", return_value=[]):
        result = learn_from_feedback("wax_coat", "test-project")

    assert result is None


def test_learn_from_feedback_returns_none_on_malformed_json():
    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = _mock_response("not json at all {{{")

    with (
        patch("core.feedback.fc.load_feedback_entries", return_value=_ONE_ENTRY),
        patch("core.feedback.genai.Client", return_value=mock_client),
    ):
        result = learn_from_feedback("wax_coat", "test-project")

    assert result is None


def test_learn_from_feedback_strips_markdown_fences():
    fenced = f"```json\n{json.dumps(_LEARNED)}\n```"
    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = _mock_response(fenced)

    with (
        patch("core.feedback.fc.load_feedback_entries", return_value=_ONE_ENTRY),
        patch("core.feedback.genai.Client", return_value=mock_client),
    ):
        result = learn_from_feedback("wax_coat", "test-project")

    assert result == {"feedback_notes": "prefers a tailored fit", "avoid_shops": []}


def test_learn_from_feedback_defaults_missing_fields():
    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = _mock_response(json.dumps({}))

    with (
        patch("core.feedback.fc.load_feedback_entries", return_value=_ONE_ENTRY),
        patch("core.feedback.genai.Client", return_value=mock_client),
    ):
        result = learn_from_feedback("wax_coat", "test-project")

    assert result == {"feedback_notes": "", "avoid_shops": []}


def test_learn_from_feedback_includes_overall_note_entries_in_prompt():
    entries = [
        {"type": "overall_note", "run_date": "2026-07-10", "feedback": "always skip synthetic fabrics"},
    ]
    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = _mock_response(json.dumps(_LEARNED))

    with (
        patch("core.feedback.fc.load_feedback_entries", return_value=entries),
        patch("core.feedback.genai.Client", return_value=mock_client),
    ):
        result = learn_from_feedback("wax_coat", "test-project")

    assert result is not None
    call_args = mock_client.models.generate_content.call_args
    contents = call_args.kwargs["contents"] if "contents" in call_args.kwargs else call_args.args[1]
    assert "always skip synthetic fabrics" in contents
    assert "overall_note" in contents
