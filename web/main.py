import hashlib
from pathlib import Path

from fastapi import Cookie, Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

import core.firestore_client as fc
from core.settings import Settings

_settings = Settings()
app = FastAPI(title="Shop Assistant")
app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")

_HTML = (Path(__file__).parent / "templates" / "index.html").read_text()
_ADMIN_HTML = (Path(__file__).parent / "templates" / "admin.html").read_text()


def _admin_token() -> str:
    return hashlib.sha256(f"sa:{_settings.admin_password}".encode()).hexdigest()


def _require_admin(sa_admin: str | None = Cookie(default=None)) -> None:
    if not _settings.admin_password or sa_admin != _admin_token():
        raise HTTPException(status_code=401, detail="Unauthorized")


@app.get("/", response_class=HTMLResponse)
def index():
    return _HTML


@app.get("/api/searches")
def get_searches():
    configs = fc.list_searches(active_only=False)
    return [{"name": c["search_name"], "active": c.get("active", True)} for c in configs]


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


# ── Admin ────────────────────────────────────────────────────────────────────


@app.get("/admin", response_class=HTMLResponse)
def admin_page():
    return _ADMIN_HTML


@app.post("/api/admin/login")
async def admin_login(request: Request):
    body = await request.json()
    if not _settings.admin_password or body.get("password") != _settings.admin_password:
        raise HTTPException(status_code=401, detail="Wrong password")
    resp = JSONResponse({"ok": True})
    is_https = request.headers.get("x-forwarded-proto") == "https" or request.url.scheme == "https"
    resp.set_cookie("sa_admin", _admin_token(), httponly=True, samesite="strict", secure=is_https)
    return resp


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


@app.post("/api/admin/run/{name}", dependencies=[Depends(_require_admin)])
def admin_run_search(name: str):
    from core.runner import run_search

    result = run_search(name, _settings)
    return {"ok": True, "matches": len(result.matches), "partial": len(result.partial_matches)}
