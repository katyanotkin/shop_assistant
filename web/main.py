import hashlib
import re
from datetime import date, datetime, timezone
from pathlib import Path

from fastapi import Cookie, Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import core.firestore_client as fc
from core.auth import (
    create_session_token,
    exchange_code,
    fetch_userinfo,
    google_auth_url,
    new_state,
    verify_session_token,
)
from core.brand import APP_MOTTO, APP_NAME
from core.generator import generate_search_config
from core.models import validate_example_urls
from core.runner import run_search
from core.settings import Settings

_settings = Settings()
app = FastAPI(title=APP_NAME)
app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")


def _inject_brand(html: str) -> str:
    return html.replace("__APP_NAME__", APP_NAME).replace("__APP_MOTTO__", APP_MOTTO)


_HTML = _inject_brand((Path(__file__).parent / "templates" / "index.html").read_text())
_ADMIN_HTML = _inject_brand((Path(__file__).parent / "templates" / "admin.html").read_text())
_PRIVACY_HTML = _inject_brand((Path(__file__).parent / "templates" / "privacy.html").read_text())
_TERMS_HTML = _inject_brand((Path(__file__).parent / "templates" / "terms.html").read_text())
_FEEDBACK_HTML = _inject_brand((Path(__file__).parent / "templates" / "feedback.html").read_text())
_MANIFEST = _inject_brand((Path(__file__).parent / "static" / "manifest.json").read_text())


def _admin_token() -> str:
    return hashlib.sha256(f"sa:{_settings.admin_password}".encode()).hexdigest()


def _require_admin(
    sa_admin: str | None = Cookie(default=None),
    sa_session: str | None = Cookie(default=None),
) -> None:
    if not _is_admin(sa_admin, sa_session):
        raise HTTPException(status_code=401, detail="Unauthorized")


def _oauth_redirect_uri(request: Request) -> str:
    if _settings.base_url:
        return _settings.base_url.rstrip("/") + "/auth/callback"
    proto = request.headers.get("x-forwarded-proto", request.url.scheme)
    host = request.headers.get("host", request.url.netloc)
    return f"{proto}://{host}/auth/callback"


def _is_https(request: Request) -> bool:
    return request.headers.get("x-forwarded-proto") == "https" or request.url.scheme == "https"


def _is_admin(sa_admin: str | None, sa_session: str | None) -> bool:
    # Re-reads role from Firestore via _session_user (not just the JWT claim) so an
    # admin demotion takes effect on the demoted user's very next request, rather than
    # only once their existing session cookie expires or they explicitly log out.
    if _settings.admin_password and sa_admin == _admin_token():
        return True
    user = _session_user(sa_session)
    return bool(user and user.get("role") == "admin")


_ADMIN_LOGIN_HTML = _inject_brand((Path(__file__).parent / "templates" / "admin_login.html").read_text())


@app.get("/manifest.json")
def manifest():
    return Response(content=_MANIFEST, media_type="application/manifest+json")


@app.get("/", response_class=HTMLResponse)
def index():
    return _HTML


@app.get("/admin/login", response_class=HTMLResponse)
def admin_login_page():
    return HTMLResponse(_ADMIN_LOGIN_HTML)


@app.post("/admin/login")
async def admin_login_form(request: Request):
    form = await request.form()
    password = form.get("password", "")
    if not _settings.admin_password or password != _settings.admin_password:
        return RedirectResponse(url="/admin/login?error=1", status_code=303)
    resp = RedirectResponse(url="/admin", status_code=303)
    resp.set_cookie("sa_admin", _admin_token(), httponly=True, samesite="strict", secure=_is_https(request))
    return resp


@app.get("/admin")
def admin_page(
    sa_admin: str | None = Cookie(default=None),
    sa_session: str | None = Cookie(default=None),
):
    if not _is_admin(sa_admin, sa_session):
        return RedirectResponse(url="/admin/login", status_code=302)
    return HTMLResponse(_ADMIN_HTML)


@app.get("/privacy", response_class=HTMLResponse)
def privacy_page():
    return _PRIVACY_HTML


@app.get("/terms", response_class=HTMLResponse)
def terms_page():
    return _TERMS_HTML


@app.get("/feedback", response_class=HTMLResponse)
def feedback_page():
    return _FEEDBACK_HTML


class ProductFeedbackBody(BaseModel):
    text: str = Field(min_length=1, max_length=2000)


@app.post("/api/product-feedback")
def submit_product_feedback(
    body: ProductFeedbackBody,
    sa_session: str | None = Cookie(default=None),
):
    text = body.text.strip()
    if not text:
        raise HTTPException(status_code=422, detail="Feedback text cannot be empty")
    user = _session_user(sa_session)
    if not user and len(text) > 500:
        raise HTTPException(status_code=422, detail="Anonymous feedback is limited to 500 characters")
    owner_id = user["sub"] if user else None
    owner_name = user.get("name") if user else None
    fc.save_product_feedback(text, owner_id=owner_id, owner_name=owner_name)
    return {"ok": True}


@app.get("/auth/login")
def auth_login(request: Request, next: str = "/"):
    if not _settings.google_client_id:
        raise HTTPException(status_code=503, detail="Google OAuth not configured")
    # Validate next is a safe relative path (no protocol, no open redirect).
    # Reject //evil.com (protocol-relative), ://evil.com, and anything not starting with /.
    if not next.startswith("/") or next.startswith("//") or "://" in next:
        next = "/"
    state = new_state()
    url = google_auth_url(_settings.google_client_id, _oauth_redirect_uri(request), state)
    resp = RedirectResponse(url=url)
    https = _is_https(request)
    resp.set_cookie("sa_oauth_state", state, httponly=True, samesite="lax", secure=https, max_age=300)
    resp.set_cookie("sa_oauth_next", next, httponly=True, samesite="lax", secure=https, max_age=300)
    return resp


@app.get("/auth/callback")
def auth_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    sa_oauth_state: str | None = Cookie(default=None),
    sa_oauth_next: str | None = Cookie(default=None),
):
    if error or not code or not state or not sa_oauth_state or state != sa_oauth_state:
        return RedirectResponse(url="/?auth_error=1", status_code=302)
    try:
        tokens = exchange_code(
            _settings.google_client_id, _settings.google_client_secret, code, _oauth_redirect_uri(request)
        )
        userinfo = fetch_userinfo(tokens["access_token"])
    except Exception:
        return RedirectResponse(url="/?auth_error=1", status_code=302)
    email = userinfo.get("email")
    if not email:
        return RedirectResponse(url="/?auth_error=1", status_code=302)
    user = fc.upsert_user(
        email=email,
        display_name=userinfo.get("name", ""),
        photo_url=userinfo.get("picture", ""),
        bootstrap_admin_email=_settings.bootstrap_admin_email,
    )
    token = create_session_token(user, _settings.session_secret)
    next_url = (
        sa_oauth_next
        if (
            sa_oauth_next
            and sa_oauth_next.startswith("/")
            and not sa_oauth_next.startswith("//")
            and "://" not in sa_oauth_next
        )
        else "/"
    )
    resp = RedirectResponse(url=next_url, status_code=302)
    resp.delete_cookie("sa_oauth_state", samesite="lax")
    resp.delete_cookie("sa_oauth_next", samesite="lax")
    resp.set_cookie(
        "sa_session", token, httponly=True, samesite="lax", secure=_is_https(request), max_age=60 * 60 * 24 * 30
    )
    return resp


@app.post("/auth/logout")
def auth_logout_user(request: Request, response: Response):
    https = _is_https(request)
    response.delete_cookie("sa_session", samesite="lax", secure=https)
    response.delete_cookie("sa_admin", httponly=True, samesite="strict", secure=https)
    return {"ok": True}


@app.delete("/api/me")
def delete_me(response: Response, sa_session: str | None = Cookie(default=None)):
    if not sa_session:
        raise HTTPException(status_code=401, detail="Not signed in")
    user = verify_session_token(sa_session, _settings.session_secret)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid session")
    fc.delete_user(user["sub"])
    response.delete_cookie("sa_session", samesite="lax")
    return {"ok": True}


@app.get("/{search_name}", response_class=HTMLResponse)
def search_page(search_name: str):
    return _HTML


@app.get("/api/me")
def get_me(sa_admin: str | None = Cookie(default=None), sa_session: str | None = Cookie(default=None)):
    if _settings.admin_password and sa_admin == _admin_token() and not sa_session:
        # Password-only admin: role is admin but no Google identity yet.
        # Return anonymous so the topbar shows "Sign in" rather than an empty name badge.
        return {"role": "admin", "anonymous": True}
    if sa_session:
        user = verify_session_token(sa_session, _settings.session_secret)
        if user:
            # Re-read role from Firestore so admin promotions take effect without re-login.
            db_user = fc.get_user(user["sub"])
            role = db_user["role"] if (isinstance(db_user, dict) and "role" in db_user) else user["role"]
            return {"role": role, "anonymous": False, "name": user.get("name"), "email": user.get("sub")}
    return {"role": "free", "anonymous": True}


@app.get("/api/searches")
def get_searches(
    sa_admin: str | None = Cookie(default=None),
    sa_session: str | None = Cookie(default=None),
):
    configs = fc.list_searches(active_only=False)
    is_admin = _is_admin(sa_admin, sa_session)
    user = verify_session_token(sa_session, _settings.session_secret) if sa_session else None
    user_email = user["sub"] if user else None
    return [
        {
            "name": c["search_name"],
            "title": c.get("title", ""),
            "active": c.get("active", True),
            "visibility": c.get("visibility", "public"),
            "owned": c.get("owner_id") == user_email if user_email else False,
        }
        for c in configs
        if is_admin or c.get("visibility", "public") == "public" or (user_email and c.get("owner_id") == user_email)
    ]


@app.get("/api/search/{name}")
def get_search_public(name: str):
    config = fc.load_search_config(name)
    if not config:
        raise HTTPException(status_code=404, detail="Not found")
    return {
        "search_name": config["search_name"],
        "criteria": config.get("criteria", {}),
        "preferred_shops": config.get("preferred_shops", []),
    }


@app.get("/api/results/{search_name}")
def get_run_dates(search_name: str):
    dates = fc.list_runs(search_name)
    if not dates:
        raise HTTPException(status_code=404, detail="No runs found")
    return dates


def _is_owner_or_admin(
    search_name: str,
    sa_admin: str | None,
    sa_session: str | None,
) -> bool:
    if _is_admin(sa_admin, sa_session):
        return True
    user = _session_user(sa_session)
    if not user:
        return False
    config = fc.load_search_config(search_name)
    return bool(config and config.get("owner_id") == user["sub"])


@app.get("/api/results/{search_name}/{run_date}")
def get_run(
    search_name: str,
    run_date: str,
    sa_admin: str | None = Cookie(default=None),
    sa_session: str | None = Cookie(default=None),
):
    run = fc.load_run(search_name, run_date)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    # pinned_finds must reflect the LIVE search config, not this run's frozen
    # config_snapshot — a pin/unpin made after this run was saved (or on an
    # entirely different run) must show up immediately, regardless of which
    # run's results the caller happens to be viewing.
    live_config = fc.load_search_config(search_name)
    run["pinned_finds"] = (live_config or {}).get("pinned_finds", [])
    if not _is_owner_or_admin(search_name, sa_admin, sa_session):
        run = {**run, "feedback": {}}
    return run


class FeedbackBody(BaseModel):
    url: str = Field(max_length=2048)
    text: str = Field(max_length=256)


class FeedbackBatch(BaseModel):
    items: list[FeedbackBody] = Field(max_length=200)


def _require_feedback_access(
    search_name: str,
    sa_admin: str | None = Cookie(default=None),
    sa_session: str | None = Cookie(default=None),
) -> None:
    # A Depends()-based check (not inline in the endpoint body) is required here: FastAPI
    # resolves dependencies before validating the request body, so this fires 401/403 even
    # when the body is malformed/empty — an inline check would let a bad body 422 first,
    # leaking whether a search exists to an unauthenticated caller.
    if _is_admin(sa_admin, sa_session):
        return
    if not _is_owner_or_admin(search_name, sa_admin, sa_session):
        if not _session_user(sa_session):
            raise HTTPException(status_code=401, detail="Sign in required")
        raise HTTPException(status_code=403, detail="Not your search")


@app.put("/api/feedback/{search_name}/{run_date}/batch", dependencies=[Depends(_require_feedback_access)])
def put_feedback_batch(search_name: str, run_date: str, body: FeedbackBatch):
    fc.save_feedback_batch(search_name, run_date, [(i.url, i.text.strip()) for i in body.items])

    run = fc.load_run(search_name, run_date) or {}
    by_url = {m["url"]: m for m in run.get("matches", []) + run.get("partial_matches", [])}
    to_pin = []
    for item in body.items:
        if item.url.startswith("_"):  # skip the synthetic "_overall_" entry
            continue
        segments = [s.strip().lower() for s in item.text.split(";")]
        if "perfect match" in segments and item.url in by_url:
            to_pin.append({**by_url[item.url], "pinned_at": str(date.today())})
    if to_pin:
        try:
            fc.pin_results(search_name, to_pin)
        except Exception:
            # Feedback itself already saved above — a pinning failure (e.g. a
            # corrupted existing pinned_finds entry) must not fail the request
            # the user is waiting on for their feedback save.
            pass

    return {"ok": True}


class UnpinBody(BaseModel):
    url: str = Field(max_length=2048)


@app.post("/api/feedback/{search_name}/pinned/remove", dependencies=[Depends(_require_feedback_access)])
def remove_pinned_find(search_name: str, body: UnpinBody):
    fc.unpin_result(search_name, body.url)
    return {"ok": True}


# ── Admin ────────────────────────────────────────────────────────────────────


@app.get("/api/admin/me")
def admin_me(sa_admin: str | None = Cookie(default=None)):
    return {"admin": bool(_settings.admin_password and sa_admin == _admin_token())}


@app.post("/api/admin/login")
async def admin_login(request: Request):
    body = await request.json()
    if not _settings.admin_password or body.get("password") != _settings.admin_password:
        raise HTTPException(status_code=401, detail="Wrong password")
    resp = JSONResponse({"ok": True})
    is_https = request.headers.get("x-forwarded-proto") == "https" or request.url.scheme == "https"
    resp.set_cookie("sa_admin", _admin_token(), httponly=True, samesite="strict", secure=is_https)
    return resp


@app.post("/api/admin/logout")
def admin_logout(request: Request, response: Response):
    https = _is_https(request)
    response.delete_cookie("sa_admin", httponly=True, samesite="strict", secure=https)
    response.delete_cookie("sa_session", samesite="lax", secure=https)
    return {"ok": True}


@app.get("/api/admin/searches", dependencies=[Depends(_require_admin)])
def admin_list_searches():
    return fc.list_searches(active_only=False)


@app.get("/api/admin/search/{name}", dependencies=[Depends(_require_admin)])
def admin_get_search(name: str):
    config = fc.load_search_config(name)
    if not config:
        raise HTTPException(status_code=404, detail="Not found")
    return config


@app.put("/api/admin/search/{name}", dependencies=[Depends(_require_admin)])
async def admin_save_search(name: str, request: Request):
    existing = fc.load_search_config(name) or {}
    config = {**existing, **(await request.json())}
    config["search_name"] = name
    config["example_urls"] = validate_example_urls(config.get("example_urls") or [])
    fc.save_search_config(config)
    return {"ok": True}


class GenerateBody(BaseModel):
    search_name: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9_]+$")
    description: str = Field(min_length=10, max_length=2000)


@app.post("/api/admin/search/generate", dependencies=[Depends(_require_admin)])
def admin_generate_search(body: GenerateBody):
    try:
        config = generate_search_config(body.description, body.search_name, _settings.google_cloud_project)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    config["description"] = body.description
    config["title"] = body.search_name.replace("_", " ").title()
    return config


class RunOptions(BaseModel):
    learn: bool = True


@app.post("/api/admin/run/{name}", dependencies=[Depends(_require_admin)])
def admin_run_search(name: str, options: RunOptions = RunOptions()):
    result = run_search(name, _settings, learn=options.learn)
    return {"ok": True, "matches": len(result.matches), "partial": len(result.partial_matches)}


# ── Admin: users + search visibility ─────────────────────────────────────────


class UpdateRoleBody(BaseModel):
    role: str = Field(pattern=r"^(free|premium|admin)$")


class UpdateVisibilityBody(BaseModel):
    visibility: str = Field(pattern=r"^(public|private)$")


@app.get("/api/admin/users", dependencies=[Depends(_require_admin)])
def admin_list_users():
    return fc.list_users()


@app.patch("/api/admin/user/{uid}/role", dependencies=[Depends(_require_admin)])
def admin_update_user_role(uid: str, body: UpdateRoleBody):
    try:
        fc.update_user_role(uid, body.role)
    except ValueError:
        raise HTTPException(status_code=404, detail="User not found")
    return {"ok": True}


@app.patch("/api/admin/search/{name}/visibility", dependencies=[Depends(_require_admin)])
def admin_update_search_visibility(name: str, body: UpdateVisibilityBody):
    config = fc.load_search_config(name)
    if not config:
        raise HTTPException(status_code=404, detail="Search not found")
    fc.update_search_visibility(name, body.visibility)
    return {"ok": True}


# ── User (authenticated, non-admin) ──────────────────────────────────────────


_SEARCH_NAME_RE = re.compile(r"^[a-z0-9_]{1,64}$")


def _session_user(sa_session: str | None) -> dict | None:
    """Decode session JWT and refresh role from Firestore so promotions take effect without re-login."""
    if not sa_session:
        return None
    user = verify_session_token(sa_session, _settings.session_secret)
    if not user:
        return None
    db_user = fc.get_user(user["sub"])
    if isinstance(db_user, dict) and "role" in db_user:
        user = {**user, "role": db_user["role"]}
    return user


class GenerateByTitleBody(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=10, max_length=2000)


@app.post("/api/user/search/generate")
def user_generate_search(body: GenerateByTitleBody, sa_session: str | None = Cookie(default=None)):
    user = _session_user(sa_session)
    if not user:
        raise HTTPException(status_code=401, detail="Sign in required")
    if user.get("role") == "free" and fc.list_user_searches(user["sub"]):
        raise HTTPException(status_code=403, detail="Free plan allows one search. Contact us to upgrade.")
    title = body.title.strip()
    search_name = fc.generate_unique_search_name(title)
    try:
        config = generate_search_config(body.description, search_name, _settings.google_cloud_project)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    config["search_name"] = search_name
    config["title"] = title
    config["description"] = body.description
    config["visibility"] = "private"
    config["owner_id"] = user["sub"]
    return config


@app.get("/api/user/search/{name}")
def user_get_search(
    name: str,
    sa_admin: str | None = Cookie(default=None),
    sa_session: str | None = Cookie(default=None),
):
    user = _session_user(sa_session)
    if not user and not _is_admin(sa_admin, sa_session):
        raise HTTPException(status_code=401, detail="Sign in required")
    config = fc.load_search_config(name)
    if not config:
        raise HTTPException(status_code=404, detail="Search not found")
    if not _is_admin(sa_admin, sa_session) and config.get("owner_id") != (user or {}).get("sub"):
        raise HTTPException(status_code=403, detail="Not your search")
    return config


@app.put("/api/user/search/{name}")
async def user_save_search(name: str, request: Request, sa_session: str | None = Cookie(default=None)):
    if not _SEARCH_NAME_RE.match(name):
        raise HTTPException(
            status_code=422, detail="Invalid search name: lowercase letters, digits, underscores only (max 64 chars)"
        )
    user = _session_user(sa_session)
    if not user:
        raise HTTPException(status_code=401, detail="Sign in required")
    config = await request.json()
    title = (config.get("title") or "").strip()
    if not title:
        raise HTTPException(status_code=422, detail="Title is required")
    if len(title) > 200:
        raise HTTPException(status_code=422, detail="Title must be 200 characters or fewer")
    existing = fc.load_search_config(name)
    if existing and existing.get("owner_id") != user["sub"]:
        raise HTTPException(status_code=403, detail="Not your search")
    if not existing and user.get("role") == "free":
        if fc.list_user_searches(user["sub"]):
            raise HTTPException(status_code=403, detail="Free plan allows one search. Contact us to upgrade.")
    config["search_name"] = name
    config["title"] = title
    config["owner_id"] = user["sub"]
    config["visibility"] = existing.get("visibility", "private") if existing else "private"
    config["created_at"] = (
        existing["created_at"] if existing and "created_at" in existing else datetime.now(timezone.utc)
    )
    config["example_urls"] = validate_example_urls(config.get("example_urls") or [])
    fc.save_search_config(config)
    return {"ok": True}


@app.delete("/api/user/search/{name}")
def user_delete_search(name: str, sa_session: str | None = Cookie(default=None)):
    user = _session_user(sa_session)
    if not user:
        raise HTTPException(status_code=401, detail="Sign in required")
    config = fc.load_search_config(name)
    if not config:
        raise HTTPException(status_code=404, detail="Search not found")
    if config.get("owner_id") != user["sub"]:
        raise HTTPException(status_code=403, detail="Not your search")
    fc.delete_search_config(name)
    return {"ok": True}


@app.post("/api/user/search/{name}/run")
def user_run_search(name: str, sa_session: str | None = Cookie(default=None)):
    user = _session_user(sa_session)
    if not user:
        raise HTTPException(status_code=401, detail="Sign in required")
    config = fc.load_search_config(name)
    if not config:
        raise HTTPException(status_code=404, detail="Search not found")
    is_owner = config.get("owner_id") == user["sub"]
    if not is_owner and user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Not your search")
    if user.get("role") == "free" and is_owner:
        created_at = config.get("created_at")
        if created_at:
            if not isinstance(created_at, datetime):
                created_at = datetime.fromisoformat(str(created_at))
            if not created_at.tzinfo:
                created_at = created_at.replace(tzinfo=timezone.utc)
            if (datetime.now(timezone.utc) - created_at).days > 30:
                raise HTTPException(
                    status_code=403,
                    detail="Free plan: 30-day run window has expired. Contact us to upgrade.",
                )
    result = run_search(name, _settings, learn=True)
    return {"ok": True, "matches": len(result.matches), "partial": len(result.partial_matches)}
