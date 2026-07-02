from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

import web.main as main_module
from core.auth import create_session_token
from web.main import app

SECRET = "test-secret"
_USER = {"email": "user@x.com", "display_name": "User", "photo_url": "", "role": "free"}


def _tok(user_dict: dict) -> str:
    return create_session_token(user_dict, SECRET)


@pytest.fixture()
def client():
    with patch.object(main_module, "_settings") as s:
        s.admin_password = "hunter2"
        s.session_secret = SECRET
        with patch("web.main.fc") as fc:
            fc.get_user.return_value = None
            fc.save_product_feedback.return_value = None
            with TestClient(app, raise_server_exceptions=True) as c:
                yield c, fc


# ── GET /feedback ─────────────────────────────────────────────────────────────


def test_feedback_page_serves_without_auth(client):
    c, _ = client
    r = c.get("/feedback")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]


# ── POST /api/product-feedback ─────────────────────────────────────────────────


def test_product_feedback_anonymous_success(client):
    c, mock_fc = client
    r = c.post("/api/product-feedback", json={"text": "Love the app, would like dark mode."})
    assert r.status_code == 200
    assert r.json() == {"ok": True}
    mock_fc.save_product_feedback.assert_called_once_with(
        "Love the app, would like dark mode.", owner_id=None, owner_name=None
    )


def test_product_feedback_logged_in_attaches_owner(client):
    c, mock_fc = client
    c.cookies.set("sa_session", _tok(_USER))
    r = c.post("/api/product-feedback", json={"text": "Please add CSV export."})
    assert r.status_code == 200
    mock_fc.save_product_feedback.assert_called_once_with(
        "Please add CSV export.", owner_id="user@x.com", owner_name="User"
    )


def test_product_feedback_rejects_empty_text(client):
    c, _ = client
    r = c.post("/api/product-feedback", json={"text": "   "})
    assert r.status_code == 422


def test_product_feedback_rejects_missing_text(client):
    c, _ = client
    r = c.post("/api/product-feedback", json={})
    assert r.status_code == 422


def test_product_feedback_anonymous_over_500_chars_rejected(client):
    c, _ = client
    r = c.post("/api/product-feedback", json={"text": "x" * 501})
    assert r.status_code == 422


def test_product_feedback_anonymous_exactly_500_chars_allowed(client):
    c, mock_fc = client
    r = c.post("/api/product-feedback", json={"text": "x" * 500})
    assert r.status_code == 200
    mock_fc.save_product_feedback.assert_called_once()


def test_product_feedback_logged_in_over_500_chars_allowed(client):
    c, mock_fc = client
    c.cookies.set("sa_session", _tok(_USER))
    r = c.post("/api/product-feedback", json={"text": "x" * 1500})
    assert r.status_code == 200
    mock_fc.save_product_feedback.assert_called_once()


def test_product_feedback_over_2000_chars_rejected_even_logged_in(client):
    c, _ = client
    c.cookies.set("sa_session", _tok(_USER))
    r = c.post("/api/product-feedback", json={"text": "x" * 2001})
    assert r.status_code == 422
