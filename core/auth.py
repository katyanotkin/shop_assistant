import hashlib
import secrets as _secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import httpx
import jwt

_ALGORITHM = "HS256"
_SESSION_DAYS = 30
_GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
_GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
_GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"
_SCOPES = "openid email profile"


def user_doc_id(email: str) -> str:
    return hashlib.md5(email.lower().encode()).hexdigest()


def new_state() -> str:
    return _secrets.token_urlsafe(16)


def google_auth_url(client_id: str, redirect_uri: str, state: str) -> str:
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": _SCOPES,
        "state": state,
        "access_type": "online",
    }
    return f"{_GOOGLE_AUTH_URL}?{urlencode(params)}"


def exchange_code(client_id: str, client_secret: str, code: str, redirect_uri: str) -> dict:
    resp = httpx.post(
        _GOOGLE_TOKEN_URL,
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "code": code,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        },
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()


def fetch_userinfo(access_token: str) -> dict:
    resp = httpx.get(
        _GOOGLE_USERINFO_URL,
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()


def create_session_token(user: dict, secret: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user["email"],
        "name": user.get("display_name", ""),
        "picture": user.get("photo_url", ""),
        "role": user["role"],
        "iat": now,
        "exp": now + timedelta(days=_SESSION_DAYS),
    }
    return jwt.encode(payload, secret, algorithm=_ALGORITHM)


def verify_session_token(token: str, secret: str) -> dict | None:
    try:
        return jwt.decode(token, secret, algorithms=[_ALGORITHM])
    except jwt.PyJWTError:
        return None
