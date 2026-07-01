from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

import web.main as main_module
from core.auth import create_session_token
from web.main import app

SECRET = "test-secret"

FREE_USER = {"email": "user@example.com", "display_name": "Test User", "photo_url": "", "role": "free"}
PREMIUM_USER = {"email": "vip@example.com", "display_name": "VIP User", "photo_url": "", "role": "premium"}


@pytest.fixture()
def client():
    with patch.object(main_module, "_settings") as s:
        s.admin_password = "hunter2"
        s.session_secret = SECRET
        s.google_client_id = "fake-client-id"
        s.google_client_secret = "fake-secret"
        s.base_url = None
        s.bootstrap_admin_email = None
        with patch("web.main.fc"):
            with TestClient(app, raise_server_exceptions=True, follow_redirects=False) as c:
                yield c


def _session_cookie(user: dict) -> str:
    return create_session_token(user, SECRET)


# ── GET /api/me ───────────────────────────────────────────────────────────────


def test_me_anonymous_when_no_cookies(client):
    r = client.get("/api/me")
    assert r.status_code == 200
    assert r.json() == {"role": "free", "anonymous": True}


def test_me_returns_free_role_from_session(client):
    token = _session_cookie(FREE_USER)
    client.cookies.set("sa_session", token)
    r = client.get("/api/me")
    assert r.status_code == 200
    data = r.json()
    assert data["role"] == "free"
    assert data["anonymous"] is False
    assert data["name"] == "Test User"
    assert data["email"] == "user@example.com"


def test_me_returns_premium_role_from_session(client):
    token = _session_cookie(PREMIUM_USER)
    client.cookies.set("sa_session", token)
    r = client.get("/api/me")
    data = r.json()
    assert data["role"] == "premium"
    assert data["anonymous"] is False


def test_me_ignores_tampered_session(client):
    client.cookies.set("sa_session", "not.a.valid.jwt")
    r = client.get("/api/me")
    assert r.json() == {"role": "free", "anonymous": True}


def test_me_returns_admin_when_admin_cookie_set(client):
    import hashlib

    token = hashlib.sha256(b"sa:hunter2").hexdigest()
    client.cookies.set("sa_admin", token)
    r = client.get("/api/me")
    data = r.json()
    assert data["role"] == "admin"
    # Password-only admin has no Google identity — anonymous=True so the
    # topbar shows "Sign in" rather than an empty name badge.
    assert data["anonymous"] is True


def test_me_admin_cookie_with_session_returns_session_identity(client):
    import hashlib

    admin_token = hashlib.sha256(b"sa:hunter2").hexdigest()
    session_token = _session_cookie(FREE_USER)
    client.cookies.set("sa_admin", admin_token)
    client.cookies.set("sa_session", session_token)
    r = client.get("/api/me")
    # When both cookies are present the OAuth session resolves the identity.
    # The admin role comes from the session user's Firestore role, not sa_admin.
    data = r.json()
    assert data["anonymous"] is False
    assert data["role"] == FREE_USER["role"]


# ── GET /auth/login ───────────────────────────────────────────────────────────


def test_auth_login_redirects_to_google(client):
    r = client.get("/auth/login")
    assert r.status_code in (302, 307)
    assert "accounts.google.com" in r.headers["location"]


def test_auth_login_sets_state_cookie(client):
    r = client.get("/auth/login")
    assert "sa_oauth_state" in r.cookies


def test_auth_login_503_when_not_configured(client):
    with patch.object(main_module, "_settings") as s:
        s.google_client_id = None
        with TestClient(app, raise_server_exceptions=True) as c:
            r = c.get("/auth/login")
            assert r.status_code == 503


def test_auth_login_includes_client_id_in_redirect(client):
    r = client.get("/auth/login")
    assert "fake-client-id" in r.headers["location"]


# ── POST /auth/logout ─────────────────────────────────────────────────────────


def test_auth_logout_returns_ok(client):
    r = client.post("/auth/logout")
    assert r.status_code == 200
    assert r.json() == {"ok": True}


def test_auth_logout_deletes_session_cookie(client):
    token = _session_cookie(FREE_USER)
    client.cookies.set("sa_session", token)
    r = client.post("/auth/logout")
    set_cookie = r.headers.get("set-cookie", "")
    assert "sa_session" in set_cookie
    assert "Max-Age=0" in set_cookie or "max-age=0" in set_cookie.lower() or "expires" in set_cookie.lower()


# ── GET /auth/callback ────────────────────────────────────────────────────────


def test_auth_callback_missing_code_redirects_with_error(client):
    r = client.get("/auth/callback?state=abc")
    assert r.status_code in (302, 307)
    assert "auth_error=1" in r.headers["location"]


def test_auth_callback_state_mismatch_redirects_with_error(client):
    client.cookies.set("sa_oauth_state", "correct-state")
    r = client.get("/auth/callback?code=mycode&state=wrong-state")
    assert r.status_code in (302, 307)
    assert "auth_error=1" in r.headers["location"]


def test_auth_callback_error_param_redirects_with_error(client):
    r = client.get("/auth/callback?error=access_denied")
    assert r.status_code in (302, 307)
    assert "auth_error=1" in r.headers["location"]


def test_auth_callback_sets_session_cookie_on_success(client):
    client.cookies.set("sa_oauth_state", "mystate")
    with patch("web.main.exchange_code", return_value={"access_token": "tok"}):
        with patch(
            "web.main.fetch_userinfo",
            return_value={"email": "user@example.com", "name": "Test", "picture": ""},
        ):
            with patch("web.main.fc") as fc:
                fc.upsert_user.return_value = FREE_USER
                r = client.get("/auth/callback?code=mycode&state=mystate")
    assert r.status_code in (302, 307)
    assert r.headers["location"] == "/"
    assert "sa_session" in r.cookies


# ── DELETE /api/me ────────────────────────────────────────────────────────────


def test_delete_me_no_session_returns_401(client):
    r = client.request("DELETE", "/api/me")
    assert r.status_code == 401


def test_delete_me_invalid_session_returns_401(client):
    client.cookies.set("sa_session", "not.a.valid.jwt")
    r = client.request("DELETE", "/api/me")
    assert r.status_code == 401


def test_delete_me_valid_session_deletes_user_and_clears_cookie(client):
    token = _session_cookie(FREE_USER)
    client.cookies.set("sa_session", token)
    with patch("web.main.fc") as fc:
        r = client.request("DELETE", "/api/me")
    assert r.status_code == 200
    assert r.json() == {"ok": True}
    fc.delete_user.assert_called_once_with("user@example.com")
    set_cookie = r.headers.get("set-cookie", "")
    assert "sa_session" in set_cookie
    assert "Max-Age=0" in set_cookie or "max-age=0" in set_cookie.lower() or "expires" in set_cookie.lower()
