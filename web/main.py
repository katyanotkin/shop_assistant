import hashlib
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
_MANIFEST = _inject_brand((Path(__file__).parent / "static" / "manifest.json").read_text())


def _admin_token() -> str:
    return hashlib.sha256(f"sa:{_settings.admin_password}".encode()).hexdigest()


def _require_admin(sa_admin: str | None = Cookie(default=None)) -> None:
    if not _settings.admin_password or sa_admin != _admin_token():
        raise HTTPException(status_code=401, detail="Unauthorized")


def _oauth_redirect_uri(request: Request) -> str:
    if _settings.base_url:
        return _settings.base_url.rstrip("/") + "/auth/callback"
    proto = request.headers.get("x-forwarded-proto", request.url.scheme)
    host = request.headers.get("host", request.url.netloc)
    return f"{proto}://{host}/auth/callback"


def _is_https(request: Request) -> bool:
    return request.headers.get("x-forwarded-proto") == "https" or request.url.scheme == "https"


@app.get("/manifest.json")
def manifest():
    return Response(content=_MANIFEST, media_type="application/manifest+json")


@app.get("/", response_class=HTMLResponse)
def index():
    return _HTML


@app.get("/admin")
def admin_page():
    return RedirectResponse(url="/", status_code=302)


@app.get("/privacy", response_class=HTMLResponse)
def privacy_page():
    return _PRIVACY_HTML


@app.get("/terms", response_class=HTMLResponse)
def terms_page():
    return _TERMS_HTML


@app.get("/auth/login")
def auth_login(request: Request):
    if not _settings.google_client_id:
        raise HTTPException(status_code=503, detail="Google OAuth not configured")
    state = new_state()
    url = google_auth_url(_settings.google_client_id, _oauth_redirect_uri(request), state)
    resp = RedirectResponse(url=url)
    resp.set_cookie("sa_oauth_state", state, httponly=True, samesite="lax", secure=_is_https(request), max_age=300)
    return resp


@app.get("/auth/callback")
def auth_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    sa_oauth_state: str | None = Cookie(default=None),
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
    resp = RedirectResponse(url="/", status_code=302)
    resp.delete_cookie("sa_oauth_state", samesite="lax")
    resp.set_cookie(
        "sa_session", token, httponly=True, samesite="lax", secure=_is_https(request), max_age=60 * 60 * 24 * 30
    )
    return resp


@app.post("/auth/logout")
def auth_logout_user(response: Response):
    response.delete_cookie("sa_session", samesite="lax")
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
    if _settings.admin_password and sa_admin == _admin_token():
        return {"role": "admin", "anonymous": False}
    if sa_session:
        user = verify_session_token(sa_session, _settings.session_secret)
        if user:
            return {"role": user["role"], "anonymous": False, "name": user.get("name"), "email": user.get("sub")}
    return {"role": "free", "anonymous": True}


@app.get("/api/searches")
def get_searches():
    configs = fc.list_searches(active_only=False)
    return [
        {
            "name": c["search_name"],
            "active": c.get("active", True),
            "visibility": c.get("visibility", "public"),
        }
        for c in configs
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


@app.get("/api/results/{search_name}/{run_date}")
def get_run(search_name: str, run_date: str):
    run = fc.load_run(search_name, run_date)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return run


class FeedbackBody(BaseModel):
    url: str = Field(max_length=2048)
    text: str = Field(max_length=256)


class FeedbackBatch(BaseModel):
    items: list[FeedbackBody] = Field(max_length=200)


@app.put("/api/feedback/{search_name}/{run_date}/batch", dependencies=[Depends(_require_admin)])
def put_feedback_batch(search_name: str, run_date: str, body: FeedbackBatch):
    fc.save_feedback_batch(search_name, run_date, [(i.url, i.text.strip()) for i in body.items])
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
def admin_logout(response: Response):
    response.delete_cookie("sa_admin", httponly=True, samesite="strict")
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
    config = await request.json()
    config["search_name"] = name
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
    return config


class RunOptions(BaseModel):
    learn: bool = True


@app.post("/api/admin/run/{name}", dependencies=[Depends(_require_admin)])
def admin_run_search(name: str, options: RunOptions = RunOptions()):
    result = run_search(name, _settings, learn=options.learn)
    return {"ok": True, "matches": len(result.matches), "partial": len(result.partial_matches)}
