import hashlib
from unittest.mock import MagicMock, patch

from google.api_core.exceptions import NotFound

import core.firestore_client as fc
from core.firestore_client import _decode_feedback, _url_key

# ── _url_key ──────────────────────────────────────────────────────────────────


def test_url_key_no_slashes():
    key = _url_key("https://example.com/product/1")
    assert "/" not in key
    assert ":" not in key
    assert "." not in key


def test_url_key_is_deterministic():
    url = "https://example.com/product/1"
    assert _url_key(url) == _url_key(url)


def test_url_key_is_md5_hex():
    url = "https://example.com/product/1"
    expected = hashlib.md5(url.encode()).hexdigest()
    assert _url_key(url) == expected


# ── save_feedback ─────────────────────────────────────────────────────────────


def _make_doc_ref_mock(update_raises=None):
    mock_doc_ref = MagicMock()
    if update_raises:
        mock_doc_ref.update.side_effect = update_raises
    mock_db = MagicMock()
    (mock_db.collection.return_value.document.return_value.collection.return_value.document.return_value) = mock_doc_ref
    return mock_db, mock_doc_ref


def test_save_feedback_uses_hash_key():
    url = "https://shop.example.com/items/coat/42"
    text = "great fit"
    expected_key = _url_key(url)

    mock_db, mock_doc_ref = _make_doc_ref_mock()
    with patch("core.firestore_client.get_db", return_value=mock_db):
        fc.save_feedback("wax_coat", "2026-06-19", url, text)

    mock_doc_ref.update.assert_called_once()
    call_args = mock_doc_ref.update.call_args[0][0]

    field_path = f"feedback.{expected_key}"
    assert field_path in call_args
    assert "/" not in field_path
    assert call_args[field_path] == {"url": url, "text": text}


def test_save_feedback_falls_back_to_set_when_doc_missing():
    url = "https://shop.example.com/items/coat/42"
    text = "great fit"
    expected_key = _url_key(url)

    mock_db, mock_doc_ref = _make_doc_ref_mock(update_raises=NotFound("document not found"))
    with patch("core.firestore_client.get_db", return_value=mock_db):
        fc.save_feedback("wax_coat", "2026-06-19", url, text)

    mock_doc_ref.set.assert_called_once_with({"feedback": {expected_key: {"url": url, "text": text}}}, merge=True)


# ── _decode_feedback ──────────────────────────────────────────────────────────


def test_decode_feedback_roundtrip():
    url = "https://shop.example.com/items/coat/42"
    raw = {_url_key(url): {"url": url, "text": "hello"}}
    result = _decode_feedback(raw)
    assert result == {url: "hello"}


def test_decode_feedback_multiple_entries():
    url1 = "https://shop.example.com/a"
    url2 = "https://other.example.com/b"
    raw = {
        _url_key(url1): {"url": url1, "text": "good"},
        _url_key(url2): {"url": url2, "text": "bad"},
    }
    result = _decode_feedback(raw)
    assert result == {url1: "good", url2: "bad"}


def test_decode_feedback_skips_malformed_entries():
    url = "https://shop.example.com/a"
    raw = {
        _url_key(url): {"url": url, "text": "ok"},
        "some_bad_key": "not a dict",
    }
    result = _decode_feedback(raw)
    assert result == {url: "ok"}


# ── load_run ──────────────────────────────────────────────────────────────────


def _make_doc(data: dict, exists: bool = True) -> MagicMock:
    doc = MagicMock()
    doc.exists = exists
    doc.to_dict.return_value = data
    return doc


def _mock_db_returning_doc(doc: MagicMock) -> MagicMock:
    mock_db = MagicMock()
    (
        mock_db.collection.return_value.document.return_value.collection.return_value.document.return_value.get.return_value
    ) = doc
    return mock_db


def test_load_run_decodes_feedback():
    url = "https://shop.example.com/items/coat/42"
    text = "loved it"
    raw_data = {
        "feedback": {_url_key(url): {"url": url, "text": text}},
        "matches": [],
    }
    doc = _make_doc(raw_data)
    mock_db = _mock_db_returning_doc(doc)

    with patch("core.firestore_client.get_db", return_value=mock_db):
        result = fc.load_run("wax_coat", "2026-06-19")

    assert result is not None
    assert result["feedback"] == {url: text}


def test_load_run_missing_feedback():
    raw_data = {"matches": [{"url": "https://shop.example.com/a", "score": 8}]}
    doc = _make_doc(raw_data)
    mock_db = _mock_db_returning_doc(doc)

    with patch("core.firestore_client.get_db", return_value=mock_db):
        result = fc.load_run("wax_coat", "2026-06-19")

    assert result is not None
    assert "matches" in result
    assert not result.get("feedback")


def test_load_run_not_found():
    doc = _make_doc({}, exists=False)
    mock_db = _mock_db_returning_doc(doc)

    with patch("core.firestore_client.get_db", return_value=mock_db):
        result = fc.load_run("wax_coat", "2026-06-19")

    assert result is None
