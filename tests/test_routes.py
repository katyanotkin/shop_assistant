from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

import web.main as main_module
from web.main import app


@pytest.fixture()
def client():
    with patch.object(main_module, "_settings") as s:
        s.admin_password = "hunter2"
        with patch("web.main.fc") as fc:
            fc.list_searches.return_value = []
            with TestClient(app, raise_server_exceptions=True, follow_redirects=False) as c:
                yield c


# ── GET / ─────────────────────────────────────────────────────────────────────


def test_index_returns_200(client):
    r = client.get("/")
    assert r.status_code == 200


def test_index_returns_html(client):
    r = client.get("/")
    assert "text/html" in r.headers["content-type"]


def test_index_contains_app_name(client):
    r = client.get("/")
    assert "TailoredLoop" in r.text


# ── GET /admin ────────────────────────────────────────────────────────────────


def test_admin_redirects_when_unauthenticated(client):
    r = client.get("/admin")
    assert r.status_code == 302


def test_admin_redirect_location_is_login_page(client):
    r = client.get("/admin")
    assert r.headers["location"] == "/admin/login"


# ── GET /{search_name} (catch-all) ───────────────────────────────────────────


def test_search_page_returns_200(client):
    r = client.get("/wax_coat")
    assert r.status_code == 200


def test_search_page_returns_html(client):
    r = client.get("/wax_coat")
    assert "text/html" in r.headers["content-type"]


def test_search_page_arbitrary_name_returns_200(client):
    r = client.get("/some_other_search")
    assert r.status_code == 200


# ── GET /manifest.json ────────────────────────────────────────────────────────


def test_manifest_returns_200(client):
    r = client.get("/manifest.json")
    assert r.status_code == 200


def test_manifest_content_type(client):
    r = client.get("/manifest.json")
    assert "manifest" in r.headers["content-type"]


def test_manifest_body_is_valid_json(client):
    import json

    r = client.get("/manifest.json")
    data = json.loads(r.text)
    assert "name" in data


def test_manifest_contains_app_name(client):
    r = client.get("/manifest.json")
    assert "TailoredLoop" in r.text
