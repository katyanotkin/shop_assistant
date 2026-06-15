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
