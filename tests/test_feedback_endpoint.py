import hashlib
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

import web.main as main_module
from web.main import app

PASSWORD = "testpass"
TOKEN = hashlib.sha256(f"sa:{PASSWORD}".encode()).hexdigest()


@pytest.fixture()
def client():
    with patch.object(main_module, "_settings") as s:
        s.admin_password = PASSWORD
        with patch("web.main.fc") as fc:
            fc.list_searches.return_value = []
            with TestClient(app, raise_server_exceptions=True) as c:
                yield c


@pytest.fixture()
def authed_client(client):
    r = client.post("/api/admin/login", json={"password": PASSWORD})
    assert r.status_code == 200
    return client


# ── PUT /api/feedback/{search_name}/{run_date} ────────────────────────────────


def test_feedback_put_requires_auth(client):
    r = client.put(
        "/api/feedback/wax_coat/2026-06-19",
        json={"url": "https://example.com/product/1", "text": "nice coat"},
    )
    assert r.status_code == 401


def test_feedback_put_saves_correctly(authed_client):
    url = "https://example.com/product/1"
    text = "nice coat"

    with patch("web.main.submit_feedback") as mock_submit:
        r = authed_client.put(
            "/api/feedback/wax_coat/2026-06-19",
            json={"url": url, "text": text},
        )

    assert r.status_code == 200
    assert r.json() == {"ok": True}
    mock_submit.assert_called_once_with("wax_coat", "2026-06-19", url, text)


def test_feedback_put_bad_date_format_still_passes(authed_client):
    with patch("web.main.submit_feedback") as mock_submit:
        r = authed_client.put(
            "/api/feedback/wax_coat/2026-06-15",
            json={"url": "https://example.com/x", "text": "fine"},
        )

    assert r.status_code == 200
    mock_submit.assert_called_once_with("wax_coat", "2026-06-15", "https://example.com/x", "fine")


def test_feedback_put_strips_whitespace(authed_client):
    with patch("web.main.submit_feedback") as mock_submit:
        r = authed_client.put(
            "/api/feedback/wax_coat/2026-06-19",
            json={"url": "https://example.com/x", "text": "  nice coat  "},
        )

    assert r.status_code == 200
    mock_submit.assert_called_once_with("wax_coat", "2026-06-19", "https://example.com/x", "nice coat")


def test_feedback_put_rejects_text_over_256_chars(authed_client):
    with patch("web.main.submit_feedback"):
        r = authed_client.put(
            "/api/feedback/wax_coat/2026-06-19",
            json={"url": "https://example.com/x", "text": "x" * 257},
        )

    assert r.status_code == 422


def test_feedback_put_rejects_url_over_2048_chars(authed_client):
    with patch("web.main.submit_feedback"):
        r = authed_client.put(
            "/api/feedback/wax_coat/2026-06-19",
            json={"url": "https://example.com/" + "x" * 2030, "text": "ok"},
        )

    assert r.status_code == 422
