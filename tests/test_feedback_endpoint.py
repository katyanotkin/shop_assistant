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
