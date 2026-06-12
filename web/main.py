from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

import core.firestore_client as fc

app = FastAPI(title="Shop Assistant")
app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")

_HTML = (Path(__file__).parent / "templates" / "index.html").read_text()


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
