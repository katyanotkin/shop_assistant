import hashlib
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

import web.main as main_module
from core.auth import create_session_token
from web.main import app

PASSWORD = "hunter2"
SECRET = "test-secret"
TOKEN = hashlib.sha256(f"sa:{PASSWORD}".encode()).hexdigest()

_ADMIN_USER = {
    "email": "admin@x.com",
    "display_name": "Admin",
    "photo_url": "",
    "role": "admin",
}
_FREE_USER = {
    "email": "user@x.com",
    "display_name": "Free User",
    "photo_url": "",
    "role": "free",
}


def _cookie_val(response, name: str) -> str:
    """Return a Set-Cookie value with surrounding RFC 6265 double-quotes stripped.

    Python's http.cookies quotes values that contain '/' (and other special
    chars).  httpx preserves those quotes in response.cookies, so assertions
    that compare cookie values must strip them.
    """
    return response.cookies[name].strip('"')


@pytest.fixture()
def client():
    with patch.object(main_module, "_settings") as s:
        s.admin_password = PASSWORD
        s.session_secret = SECRET
        s.google_client_id = "fake-client-id"
        s.google_client_secret = "fake-secret"
        s.base_url = None
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


@pytest.fixture()
def noredirect_client():
    """Like client but does NOT follow redirects — needed to inspect 302/303 responses."""
    with patch.object(main_module, "_settings") as s:
        s.admin_password = PASSWORD
        s.session_secret = SECRET
        s.google_client_id = "fake-client-id"
        s.google_client_secret = "fake-secret"
        s.base_url = None
        with patch("web.main.fc") as fc:
            fc.list_searches.return_value = [{"search_name": "wax_coat", "active": True}]
            fc.load_search_config.return_value = {"search_name": "wax_coat"}
            fc.save_search_config.return_value = None
            with TestClient(app, raise_server_exceptions=True, follow_redirects=False) as c:
                yield c


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


# ── POST /api/admin/logout ───────────────────────────────────────────────────


def test_admin_logout_returns_200(client):
    r = client.post("/api/admin/logout")
    assert r.status_code == 200
    assert r.json() == {"ok": True}


def test_admin_logout_clears_sa_admin_cookie(authed_client):
    authed_client.post("/api/admin/logout")
    r = authed_client.get("/api/admin/me")
    assert r.json() == {"admin": False}


def test_admin_logout_works_without_auth(client):
    r = client.post("/api/admin/logout")
    assert r.status_code == 200


def test_admin_logout_sets_secure_flag_on_https(client):
    r = client.post("/api/admin/logout", headers={"x-forwarded-proto": "https"})
    set_cookie = r.headers.get("set-cookie", "")
    assert "Secure" in set_cookie


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


# ── GET /admin page auth guard ─────────────────────────────────────────────────


def test_admin_page_redirects_to_login_when_unauthenticated(noredirect_client):
    r = noredirect_client.get("/admin")
    assert r.status_code == 302
    assert r.headers["location"] == "/admin/login"


def test_admin_page_serves_html_with_password_cookie(noredirect_client):
    noredirect_client.cookies.set("sa_admin", TOKEN)
    r = noredirect_client.get("/admin")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]


def test_admin_page_serves_html_with_oauth_admin_session(noredirect_client):
    token = create_session_token(_ADMIN_USER, SECRET)
    noredirect_client.cookies.set("sa_session", token)
    r = noredirect_client.get("/admin")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]


# ── POST /admin/login form handler ────────────────────────────────────────────


def test_admin_login_form_correct_password_redirects_to_admin(noredirect_client):
    r = noredirect_client.post("/admin/login", data={"password": PASSWORD})
    assert r.status_code == 303
    assert r.headers["location"] == "/admin"
    assert "sa_admin" in r.cookies


def test_admin_login_form_wrong_password_redirects_to_login_error(noredirect_client):
    r = noredirect_client.post("/admin/login", data={"password": "wrong"})
    assert r.status_code == 303
    assert r.headers["location"] == "/admin/login?error=1"


# ── _require_admin accepts OAuth session ──────────────────────────────────────


def test_admin_searches_with_oauth_admin_session(client):
    token = create_session_token(_ADMIN_USER, SECRET)
    client.cookies.set("sa_session", token)
    r = client.get("/api/admin/searches")
    assert r.status_code == 200


def test_admin_searches_with_oauth_free_session_returns_401(client):
    token = create_session_token(_FREE_USER, SECRET)
    client.cookies.set("sa_session", token)
    r = client.get("/api/admin/searches")
    assert r.status_code == 401


# ── GET /auth/login next param + open redirect protection ─────────────────────


def test_auth_login_sets_oauth_next_cookie(noredirect_client):
    r = noredirect_client.get("/auth/login?next=/admin")
    assert "sa_oauth_next" in r.cookies
    assert _cookie_val(r, "sa_oauth_next") == "/admin"


def test_auth_login_rejects_double_slash_redirect(noredirect_client):
    r = noredirect_client.get("/auth/login?next=//evil.com")
    assert "sa_oauth_next" in r.cookies
    assert _cookie_val(r, "sa_oauth_next") == "/"


def test_auth_login_rejects_protocol_relative(noredirect_client):
    r = noredirect_client.get("/auth/login?next=https://evil.com")
    assert "sa_oauth_next" in r.cookies
    assert _cookie_val(r, "sa_oauth_next") == "/"


# ── OAuth callback with next ──────────────────────────────────────────────────


def test_auth_callback_redirects_to_next_on_success(noredirect_client):
    noredirect_client.cookies.set("sa_oauth_state", "mystate")
    noredirect_client.cookies.set("sa_oauth_next", "/admin")
    with patch("web.main.exchange_code", return_value={"access_token": "tok"}):
        with patch(
            "web.main.fetch_userinfo",
            return_value={"email": "admin@x.com", "name": "Admin", "picture": ""},
        ):
            with patch("web.main.fc") as fc_mock:
                fc_mock.upsert_user.return_value = _ADMIN_USER
                r = noredirect_client.get("/auth/callback?code=mycode&state=mystate")
    assert r.status_code == 302
    assert r.headers["location"] == "/admin"
