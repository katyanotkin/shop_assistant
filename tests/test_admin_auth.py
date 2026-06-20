import hashlib
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

import web.main as main_module
from web.main import app

PASSWORD = "hunter2"
TOKEN = hashlib.sha256(f"sa:{PASSWORD}".encode()).hexdigest()


@pytest.fixture()
def client():
    with patch.object(main_module, "_settings") as s:
        s.admin_password = PASSWORD
        with patch("web.main.fc") as fc:
            fc.list_searches.return_value = [{"search_name": "wax_coat", "active": True}]
            fc.load_search_config.return_value = {"search_name": "wax_coat"}
            fc.save_search_config.return_value = None
            with TestClient(app, raise_server_exceptions=True) as c:
                yield c


@pytest.fixture()
def authed_client(client):
    r = client.post("/api/admin/login", json={"password": PASSWORD})
    assert r.status_code == 200
    return client


# ── Login ─────────────────────────────────────────────────────────────────────


def test_login_correct_password_returns_200(client):
    r = client.post("/api/admin/login", json={"password": PASSWORD})
    assert r.status_code == 200
    assert r.json() == {"ok": True}


def test_login_sets_cookie(client):
    r = client.post("/api/admin/login", json={"password": PASSWORD})
    assert "sa_admin" in r.cookies
    assert r.cookies["sa_admin"] == TOKEN


def test_login_wrong_password_returns_401(client):
    r = client.post("/api/admin/login", json={"password": "wrong"})
    assert r.status_code == 401


def test_login_empty_password_returns_401(client):
    r = client.post("/api/admin/login", json={"password": ""})
    assert r.status_code == 401


def test_login_no_admin_password_configured_returns_401():
    with patch.object(main_module, "_settings") as s:
        s.admin_password = None
        with TestClient(app) as c:
            r = c.post("/api/admin/login", json={"password": PASSWORD})
            assert r.status_code == 401


def test_login_sets_secure_cookie_on_https(client):
    r = client.post(
        "/api/admin/login",
        json={"password": PASSWORD},
        headers={"x-forwarded-proto": "https"},
    )
    assert r.status_code == 200
    set_cookie = r.headers.get("set-cookie", "")
    assert "Secure" in set_cookie


def test_login_no_secure_flag_on_http(client):
    r = client.post("/api/admin/login", json={"password": PASSWORD})
    set_cookie = r.headers.get("set-cookie", "")
    assert "Secure" not in set_cookie


# ── Protected endpoints ────────────────────────────────────────────────────────


def test_admin_searches_requires_auth(client):
    r = client.get("/api/admin/searches")
    assert r.status_code == 401


def test_admin_searches_with_valid_cookie(authed_client):
    r = authed_client.get("/api/admin/searches")
    assert r.status_code == 200
    assert r.json()[0]["search_name"] == "wax_coat"


def test_admin_searches_with_wrong_cookie(client):
    client.cookies.set("sa_admin", "deadbeef")
    r = client.get("/api/admin/searches")
    assert r.status_code == 401


def test_admin_get_search_requires_auth(client):
    r = client.get("/api/admin/search/wax_coat")
    assert r.status_code == 401


def test_admin_get_search_with_valid_cookie(authed_client):
    r = authed_client.get("/api/admin/search/wax_coat")
    assert r.status_code == 200


def test_admin_save_search_requires_auth(client):
    r = client.put("/api/admin/search/wax_coat", json={"search_name": "wax_coat"})
    assert r.status_code == 401


def test_admin_save_search_with_valid_cookie(authed_client):
    r = authed_client.put("/api/admin/search/wax_coat", json={"search_name": "wax_coat", "active": True})
    assert r.status_code == 200


# ── GET /api/admin/me ─────────────────────────────────────────────────────────


def test_admin_me_returns_false_when_not_logged_in(client):
    r = client.get("/api/admin/me")
    assert r.status_code == 200
    assert r.json() == {"admin": False}


def test_admin_me_returns_true_when_logged_in(authed_client):
    r = authed_client.get("/api/admin/me")
    assert r.status_code == 200
    assert r.json() == {"admin": True}


def test_admin_me_returns_false_with_wrong_cookie(client):
    client.cookies.set("sa_admin", "deadbeef")
    r = client.get("/api/admin/me")
    assert r.status_code == 200
    assert r.json() == {"admin": False}


# ── POST /api/admin/search/generate ──────────────────────────────────────────


def test_generate_search_requires_auth(client):
    r = client.post(
        "/api/admin/search/generate",
        json={"search_name": "wool_coat", "description": "a warm wool coat for women"},
    )
    assert r.status_code == 401


def test_generate_search_returns_config(authed_client):
    fake_config = {
        "search_name": "wool_coat",
        "active": True,
        "criteria": {
            "category": ["coat"],
            "gender": "women",
            "material": ["wool"],
            "lining": [],
            "length": [],
            "exclude": [],
            "sizes": [],
            "max_price": None,
            "extra_notes": "",
        },
        "preferred_shops": [],
    }
    with patch("web.main.generate_search_config", return_value=fake_config) as mock_gen:
        r = authed_client.post(
            "/api/admin/search/generate",
            json={"search_name": "wool_coat", "description": "a warm wool coat for women"},
        )
    assert r.status_code == 200
    assert r.json()["search_name"] == "wool_coat"
    mock_gen.assert_called_once()


def test_generate_search_rejects_invalid_name(authed_client):
    r = authed_client.post(
        "/api/admin/search/generate",
        json={"search_name": "Wool Coat!", "description": "a warm wool coat for women"},
    )
    assert r.status_code == 422


def test_generate_search_rejects_short_description(authed_client):
    r = authed_client.post(
        "/api/admin/search/generate",
        json={"search_name": "wool_coat", "description": "coat"},
    )
    assert r.status_code == 422
