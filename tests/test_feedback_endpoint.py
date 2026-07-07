import hashlib
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

import web.main as main_module
from core.auth import create_session_token
from web.main import app

PASSWORD = "testpass"
SECRET = "test-secret"
TOKEN = hashlib.sha256(f"sa:{PASSWORD}".encode()).hexdigest()

_OWNER = {"email": "owner@x.com", "display_name": "Owner", "photo_url": "", "role": "free"}
_OTHER_USER = {"email": "other@x.com", "display_name": "Other", "photo_url": "", "role": "free"}


def _tok(user_dict: dict) -> str:
    return create_session_token(user_dict, SECRET)


@pytest.fixture()
def client():
    with patch.object(main_module, "_settings") as s:
        s.admin_password = PASSWORD
        s.session_secret = SECRET
        with patch("web.main.fc") as fc:
            fc.list_searches.return_value = []
            fc.get_user.return_value = None
            with TestClient(app, raise_server_exceptions=True) as c:
                yield c


@pytest.fixture()
def authed_client(client):
    r = client.post("/api/admin/login", json={"password": PASSWORD})
    assert r.status_code == 200
    return client


# ── PUT /api/feedback/{search_name}/{run_date}/batch ─────────────────────────


def test_feedback_batch_requires_auth(client):
    r = client.put(
        "/api/feedback/wax_coat/2026-06-19/batch",
        json={"items": [{"url": "https://example.com/a", "text": "good"}]},
    )
    assert r.status_code == 401


def test_feedback_batch_requires_auth_even_with_malformed_body(client):
    """Auth must be checked via a Depends() dependency, not inline in the endpoint body —
    otherwise FastAPI validates (and 422s on) the request body before auth ever runs,
    leaking a 422 to an anonymous caller instead of 401."""
    r = client.put("/api/feedback/wax_coat/2026-06-19/batch", json={})
    assert r.status_code == 401


def test_feedback_batch_owner_session_allowed(client):
    client.cookies.set("sa_session", _tok(_OWNER))
    with patch("web.main.fc") as mock_fc:
        mock_fc.load_search_config.return_value = {"search_name": "wax_coat", "owner_id": "owner@x.com"}
        r = client.put(
            "/api/feedback/wax_coat/2026-06-19/batch",
            json={"items": [{"url": "https://example.com/a", "text": "good"}]},
        )
    assert r.status_code == 200
    mock_fc.save_feedback_batch.assert_called_once()


def test_feedback_batch_non_owner_session_rejected(client):
    client.cookies.set("sa_session", _tok(_OTHER_USER))
    with patch("web.main.fc") as mock_fc:
        mock_fc.load_search_config.return_value = {"search_name": "wax_coat", "owner_id": "owner@x.com"}
        r = client.put(
            "/api/feedback/wax_coat/2026-06-19/batch",
            json={"items": [{"url": "https://example.com/a", "text": "good"}]},
        )
    assert r.status_code == 403


def test_feedback_batch_saves_all_items(authed_client):
    items = [
        {"url": "https://example.com/a", "text": "good"},
        {"url": "https://example.com/b", "text": "  bad  "},
    ]
    with patch("web.main.fc") as mock_fc:
        r = authed_client.put(
            "/api/feedback/wax_coat/2026-06-19/batch",
            json={"items": items},
        )
    assert r.status_code == 200
    assert r.json() == {"ok": True}
    mock_fc.save_feedback_batch.assert_called_once_with(
        "wax_coat",
        "2026-06-19",
        [("https://example.com/a", "good"), ("https://example.com/b", "bad")],
    )


def test_feedback_batch_strips_whitespace(authed_client):
    with patch("web.main.fc") as mock_fc:
        authed_client.put(
            "/api/feedback/wax_coat/2026-06-19/batch",
            json={"items": [{"url": "https://example.com/a", "text": "  hello  "}]},
        )
    mock_fc.save_feedback_batch.assert_called_once_with("wax_coat", "2026-06-19", [("https://example.com/a", "hello")])


def test_feedback_batch_rejects_invalid_item(authed_client):
    r = authed_client.put(
        "/api/feedback/wax_coat/2026-06-19/batch",
        json={"items": [{"url": "https://example.com/a", "text": "x" * 257}]},
    )
    assert r.status_code == 422


# ── Pinning via "Perfect match" feedback ──────────────────────────────────────

_MATCH = {
    "url": "https://example.com/a",
    "title": "Waxed Cotton Jacket",
    "price": 199.0,
    "score": 9.0,
    "matched": ["waxed cotton"],
    "unmatched": [],
    "notes": "Great fit.",
    "is_new": False,
}


def test_perfect_match_feedback_pins_the_result(authed_client):
    with patch("web.main.fc") as mock_fc:
        mock_fc.load_run.return_value = {"matches": [_MATCH], "partial_matches": []}
        r = authed_client.put(
            "/api/feedback/wax_coat/2026-06-19/batch",
            json={"items": [{"url": "https://example.com/a", "text": "Perfect match"}]},
        )
    assert r.status_code == 200
    mock_fc.pin_results.assert_called_once()
    called_name, called_finds = mock_fc.pin_results.call_args[0]
    assert called_name == "wax_coat"
    assert len(called_finds) == 1
    assert called_finds[0]["url"] == "https://example.com/a"
    assert called_finds[0]["title"] == "Waxed Cotton Jacket"
    assert "pinned_at" in called_finds[0]


def test_perfect_match_is_case_and_whitespace_insensitive(authed_client):
    with patch("web.main.fc") as mock_fc:
        mock_fc.load_run.return_value = {"matches": [_MATCH], "partial_matches": []}
        authed_client.put(
            "/api/feedback/wax_coat/2026-06-19/batch",
            json={"items": [{"url": "https://example.com/a", "text": "  PERFECT MATCH  "}]},
        )
    mock_fc.pin_results.assert_called_once()


def test_combined_phrase_still_pins_if_perfect_match_present(authed_client):
    with patch("web.main.fc") as mock_fc:
        mock_fc.load_run.return_value = {"matches": [_MATCH], "partial_matches": []}
        authed_client.put(
            "/api/feedback/wax_coat/2026-06-19/batch",
            json={"items": [{"url": "https://example.com/a", "text": "Perfect match; loved the fit"}]},
        )
    mock_fc.pin_results.assert_called_once()


def test_other_phrases_do_not_pin(authed_client):
    with patch("web.main.fc") as mock_fc:
        mock_fc.load_run.return_value = {"matches": [_MATCH], "partial_matches": []}
        authed_client.put(
            "/api/feedback/wax_coat/2026-06-19/batch",
            json={"items": [{"url": "https://example.com/a", "text": "Not a perfect match at all"}]},
        )
    mock_fc.pin_results.assert_not_called()


def test_overall_entry_never_pinned_even_if_text_says_perfect_match(authed_client):
    with patch("web.main.fc") as mock_fc:
        mock_fc.load_run.return_value = {"matches": [_MATCH], "partial_matches": []}
        authed_client.put(
            "/api/feedback/wax_coat/2026-06-19/batch",
            json={"items": [{"url": "_overall_", "text": "Perfect match"}]},
        )
    mock_fc.pin_results.assert_not_called()


def test_perfect_match_on_url_not_in_this_run_is_skipped(authed_client):
    with patch("web.main.fc") as mock_fc:
        mock_fc.load_run.return_value = {"matches": [], "partial_matches": []}
        r = authed_client.put(
            "/api/feedback/wax_coat/2026-06-19/batch",
            json={"items": [{"url": "https://example.com/unknown", "text": "Perfect match"}]},
        )
    assert r.status_code == 200
    mock_fc.pin_results.assert_not_called()


def test_perfect_match_matches_from_partial_matches_too(authed_client):
    with patch("web.main.fc") as mock_fc:
        mock_fc.load_run.return_value = {"matches": [], "partial_matches": [_MATCH]}
        authed_client.put(
            "/api/feedback/wax_coat/2026-06-19/batch",
            json={"items": [{"url": "https://example.com/a", "text": "Perfect match"}]},
        )
    mock_fc.pin_results.assert_called_once()


def test_multiple_perfect_matches_in_one_batch_pin_in_a_single_call(authed_client):
    """Marking several results Perfect match in one Save click must be one
    Firestore round trip (fc.pin_results with all finds), not N."""
    match_b = {**_MATCH, "url": "https://example.com/b", "title": "Another Jacket"}
    with patch("web.main.fc") as mock_fc:
        mock_fc.load_run.return_value = {"matches": [_MATCH, match_b], "partial_matches": []}
        authed_client.put(
            "/api/feedback/wax_coat/2026-06-19/batch",
            json={
                "items": [
                    {"url": "https://example.com/a", "text": "Perfect match"},
                    {"url": "https://example.com/b", "text": "Perfect match"},
                ]
            },
        )
    mock_fc.pin_results.assert_called_once()
    called_name, called_finds = mock_fc.pin_results.call_args[0]
    assert called_name == "wax_coat"
    assert {f["url"] for f in called_finds} == {"https://example.com/a", "https://example.com/b"}


def test_pin_failure_does_not_fail_the_feedback_save(authed_client):
    with patch("web.main.fc") as mock_fc:
        mock_fc.load_run.return_value = {"matches": [_MATCH], "partial_matches": []}
        mock_fc.pin_results.side_effect = Exception("boom")
        r = authed_client.put(
            "/api/feedback/wax_coat/2026-06-19/batch",
            json={"items": [{"url": "https://example.com/a", "text": "Perfect match"}]},
        )
    assert r.status_code == 200
    mock_fc.save_feedback_batch.assert_called_once()


# ── POST /api/feedback/{search_name}/pinned/remove ────────────────────────────


def test_unpin_requires_auth(client):
    r = client.post("/api/feedback/wax_coat/pinned/remove", json={"url": "https://example.com/a"})
    assert r.status_code == 401


def test_unpin_owner_session_allowed(client):
    client.cookies.set("sa_session", _tok(_OWNER))
    with patch("web.main.fc") as mock_fc:
        mock_fc.load_search_config.return_value = {"search_name": "wax_coat", "owner_id": "owner@x.com"}
        r = client.post("/api/feedback/wax_coat/pinned/remove", json={"url": "https://example.com/a"})
    assert r.status_code == 200
    mock_fc.unpin_result.assert_called_once_with("wax_coat", "https://example.com/a")


def test_unpin_non_owner_session_rejected(client):
    client.cookies.set("sa_session", _tok(_OTHER_USER))
    with patch("web.main.fc") as mock_fc:
        mock_fc.load_search_config.return_value = {"search_name": "wax_coat", "owner_id": "owner@x.com"}
        r = client.post("/api/feedback/wax_coat/pinned/remove", json={"url": "https://example.com/a"})
    assert r.status_code == 403
