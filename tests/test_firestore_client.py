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


# ── save_feedback_batch ───────────────────────────────────────────────────────


def test_save_feedback_batch_single_update_call():
    url1 = "https://shop.example.com/a"
    url2 = "https://shop.example.com/b"

    mock_db, mock_doc_ref = _make_doc_ref_mock()
    with patch("core.firestore_client.get_db", return_value=mock_db):
        fc.save_feedback_batch("wax_coat", "2026-06-19", [(url1, "good"), (url2, "bad")])

    mock_doc_ref.update.assert_called_once()
    updates = mock_doc_ref.update.call_args[0][0]
    assert f"feedback.{_url_key(url1)}" in updates
    assert f"feedback.{_url_key(url2)}" in updates
    assert updates[f"feedback.{_url_key(url1)}"] == {"url": url1, "text": "good"}
    assert updates[f"feedback.{_url_key(url2)}"] == {"url": url2, "text": "bad"}


def test_save_feedback_batch_falls_back_to_set_when_doc_missing():
    url = "https://shop.example.com/a"

    mock_db, mock_doc_ref = _make_doc_ref_mock(update_raises=NotFound("not found"))
    with patch("core.firestore_client.get_db", return_value=mock_db):
        fc.save_feedback_batch("wax_coat", "2026-06-19", [(url, "nice")])

    mock_doc_ref.set.assert_called_once()
    call_kwargs = mock_doc_ref.set.call_args
    assert call_kwargs[1].get("merge") is True


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


# ── generate_unique_search_name ──────────────────────────────────────────────


def test_generate_unique_search_name_no_collision():
    with patch("core.firestore_client.load_search_config", return_value=None):
        assert fc.generate_unique_search_name("Bathroom Cabinet") == "bathroom_cabinet"


def test_generate_unique_search_name_appends_numeric_suffix_on_collision():
    taken = {"bathroom_cabinet", "bathroom_cabinet_2"}
    with patch("core.firestore_client.load_search_config", side_effect=lambda n: {} if n in taken else None):
        assert fc.generate_unique_search_name("Bathroom Cabinet") == "bathroom_cabinet_3"


def test_generate_unique_search_name_falls_back_to_uuid_when_attempts_exhausted():
    with patch("core.firestore_client.load_search_config", return_value={}):
        result = fc.generate_unique_search_name("Bathroom Cabinet")
    assert result.startswith("bathroom_cabinet"[:57])
    assert result != "bathroom_cabinet"


def test_generate_unique_search_name_avoids_reserved_route_names():
    with patch("core.firestore_client.load_search_config", return_value=None):
        assert fc.generate_unique_search_name("Admin") == "admin_2"


# ── save_search_config ───────────────────────────────────────────────────────


def test_save_search_config_defaults_title_from_search_name():
    mock_db = MagicMock()
    config = {"search_name": "wool_coat"}
    with patch("core.firestore_client.get_db", return_value=mock_db):
        fc.save_search_config(config)
    assert config["title"] == "Wool Coat"


def test_save_search_config_preserves_explicit_title():
    mock_db = MagicMock()
    config = {"search_name": "wool_coat", "title": "My Cozy Coat"}
    with patch("core.firestore_client.get_db", return_value=mock_db):
        fc.save_search_config(config)
    assert config["title"] == "My Cozy Coat"


# ── pin_result / unpin_result ────────────────────────────────────────────────

_FIND = {
    "url": "https://example.com/a",
    "title": "Waxed Cotton Jacket",
    "score": 9.0,
    "matched": [],
    "unmatched": [],
    "notes": "",
    "pinned_at": "2026-07-01",
}


def test_pin_result_appends_to_empty_list():
    mock_db = MagicMock()
    with (
        patch("core.firestore_client.load_search_config", return_value={"search_name": "wax_coat"}),
        patch("core.firestore_client.get_db", return_value=mock_db),
    ):
        fc.pin_result("wax_coat", _FIND)
    saved = mock_db.collection.return_value.document.return_value.set.call_args[0][0]
    assert len(saved["pinned_finds"]) == 1
    assert saved["pinned_finds"][0]["url"] == _FIND["url"]
    assert saved["pinned_finds"][0]["title"] == _FIND["title"]
    assert saved["pinned_finds"][0]["pinned_at"] == _FIND["pinned_at"]


def test_pin_result_dedupes_existing_url():
    mock_db = MagicMock()
    stale = {**_FIND, "score": 3.0}
    config = {"search_name": "wax_coat", "pinned_finds": [stale]}
    with (
        patch("core.firestore_client.load_search_config", return_value=config),
        patch("core.firestore_client.get_db", return_value=mock_db),
    ):
        fc.pin_result("wax_coat", _FIND)
    saved = mock_db.collection.return_value.document.return_value.set.call_args[0][0]
    assert len(saved["pinned_finds"]) == 1
    assert saved["pinned_finds"][0]["score"] == 9.0


def test_unpin_result_removes_matching_url():
    mock_db = MagicMock()
    other = {**_FIND, "url": "https://example.com/b"}
    config = {"search_name": "wax_coat", "pinned_finds": [_FIND, other]}
    with (
        patch("core.firestore_client.load_search_config", return_value=config),
        patch("core.firestore_client.get_db", return_value=mock_db),
    ):
        fc.unpin_result("wax_coat", "https://example.com/a")
    saved = mock_db.collection.return_value.document.return_value.set.call_args[0][0]
    assert saved["pinned_finds"] == [other]


def test_unpin_result_noop_when_url_not_pinned():
    mock_db = MagicMock()
    config = {"search_name": "wax_coat", "pinned_finds": [_FIND]}
    with (
        patch("core.firestore_client.load_search_config", return_value=config),
        patch("core.firestore_client.get_db", return_value=mock_db),
    ):
        fc.unpin_result("wax_coat", "https://not-pinned.example.com")


def test_pin_results_noop_on_empty_list():
    mock_db = MagicMock()
    with (
        patch("core.firestore_client.load_search_config") as mock_load,
        patch("core.firestore_client.get_db", return_value=mock_db),
    ):
        fc.pin_results("wax_coat", [])
    mock_load.assert_not_called()
    mock_db.collection.return_value.document.return_value.set.assert_not_called()


def test_pin_results_single_round_trip_for_multiple_finds():
    mock_db = MagicMock()
    other = {**_FIND, "url": "https://example.com/b", "title": "Another Jacket"}
    with (
        patch("core.firestore_client.load_search_config", return_value={"search_name": "wax_coat"}),
        patch("core.firestore_client.get_db", return_value=mock_db),
    ):
        fc.pin_results("wax_coat", [_FIND, other])
    # Exactly one load and one save, regardless of how many finds are pinned
    mock_db.collection.return_value.document.return_value.set.assert_called_once()
    saved = mock_db.collection.return_value.document.return_value.set.call_args[0][0]
    assert {f["url"] for f in saved["pinned_finds"]} == {_FIND["url"], other["url"]}


def test_pin_result_skips_malformed_existing_entry():
    """A legacy/corrupted pinned_finds entry (e.g. missing required fields) must not
    crash the whole pin — it should be dropped, mirroring _decode_feedback's handling
    of malformed feedback entries elsewhere in this module."""
    mock_db = MagicMock()
    malformed = {"url": "https://bad.example.com"}  # missing required "score"/"title"/"pinned_at"
    with (
        patch(
            "core.firestore_client.load_search_config",
            return_value={"search_name": "wax_coat", "pinned_finds": [malformed]},
        ),
        patch("core.firestore_client.get_db", return_value=mock_db),
    ):
        fc.pin_result("wax_coat", _FIND)
    saved = mock_db.collection.return_value.document.return_value.set.call_args[0][0]
    assert len(saved["pinned_finds"]) == 1
    assert saved["pinned_finds"][0]["url"] == _FIND["url"]


# ── delete_user ───────────────────────────────────────────────────────────────


def test_delete_user_reassigns_owned_searches_to_admin():
    """Account deletion only erases identity data; the user's searches and results
    are retained (see privacy.html) by reassigning owner_id to the "admin" sentinel
    rather than being deleted or left pointing at a nonexistent user."""
    mock_db = MagicMock()
    doc1, doc2 = MagicMock(), MagicMock()
    mock_db.collection.return_value.where.return_value.stream.return_value = [doc1, doc2]
    mock_batch = MagicMock()
    mock_db.batch.return_value = mock_batch
    with patch("core.firestore_client.get_db", return_value=mock_db):
        fc.delete_user("user@example.com")
    mock_batch.update.assert_any_call(doc1.reference, {"owner_id": "admin"})
    mock_batch.update.assert_any_call(doc2.reference, {"owner_id": "admin"})
    mock_batch.commit.assert_called_once()
    mock_db.collection.return_value.document.return_value.delete.assert_called_once()


def test_delete_user_skips_batch_when_no_owned_searches():
    mock_db = MagicMock()
    mock_db.collection.return_value.where.return_value.stream.return_value = []
    with patch("core.firestore_client.get_db", return_value=mock_db):
        fc.delete_user("user@example.com")
    mock_db.batch.assert_not_called()
    mock_db.collection.return_value.document.return_value.delete.assert_called_once()
