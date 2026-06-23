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
            fc.list_searches.return_value = [
                {"search_name": "wax_coat", "active": True},
                {"search_name": "wool_jacket", "active": False},
            ]
            fc.list_runs.return_value = ["2026-06-20", "2026-06-21"]
            fc.load_run.return_value = {
                "search_name": "wax_coat",
                "run_date": "2026-06-21",
                "matches": [],
                "partial_matches": [],
            }
            with TestClient(app, raise_server_exceptions=True) as c:
                yield c, fc


# ── GET /api/searches ─────────────────────────────────────────────────────────


def test_get_searches_returns_list(client):
    c, _ = client
    r = c.get("/api/searches")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)


def test_get_searches_contains_name_and_active(client):
    c, _ = client
    r = c.get("/api/searches")
    data = r.json()
    assert len(data) == 2
    assert data[0] == {"name": "wax_coat", "active": True}
    assert data[1] == {"name": "wool_jacket", "active": False}


def test_get_searches_returns_empty_list_when_no_searches(client):
    c, fc = client
    fc.list_searches.return_value = []
    r = c.get("/api/searches")
    assert r.status_code == 200
    assert r.json() == []


def test_get_searches_uses_active_only_false(client):
    c, fc = client
    c.get("/api/searches")
    fc.list_searches.assert_called_with(active_only=False)


# ── GET /api/results/{search_name} ───────────────────────────────────────────


def test_get_run_dates_returns_list_of_dates(client):
    c, _ = client
    r = c.get("/api/results/wax_coat")
    assert r.status_code == 200
    data = r.json()
    assert data == ["2026-06-20", "2026-06-21"]


def test_get_run_dates_404_when_no_runs(client):
    c, fc = client
    fc.list_runs.return_value = []
    r = c.get("/api/results/wax_coat")
    assert r.status_code == 404


def test_get_run_dates_404_detail_message(client):
    c, fc = client
    fc.list_runs.return_value = []
    r = c.get("/api/results/wax_coat")
    assert "No runs found" in r.json()["detail"]


def test_get_run_dates_calls_fc_with_search_name(client):
    c, fc = client
    c.get("/api/results/wool_jacket")
    fc.list_runs.assert_called_with("wool_jacket")


# ── GET /api/results/{search_name}/{run_date} ─────────────────────────────────


def test_get_run_returns_run_data(client):
    c, _ = client
    r = c.get("/api/results/wax_coat/2026-06-21")
    assert r.status_code == 200
    data = r.json()
    assert data["search_name"] == "wax_coat"
    assert data["run_date"] == "2026-06-21"


def test_get_run_404_when_not_found(client):
    c, fc = client
    fc.load_run.return_value = None
    r = c.get("/api/results/wax_coat/1999-01-01")
    assert r.status_code == 404


def test_get_run_404_detail_message(client):
    c, fc = client
    fc.load_run.return_value = None
    r = c.get("/api/results/wax_coat/1999-01-01")
    assert "Run not found" in r.json()["detail"]


def test_get_run_calls_fc_with_correct_args(client):
    c, fc = client
    c.get("/api/results/wax_coat/2026-06-21")
    fc.load_run.assert_called_with("wax_coat", "2026-06-21")


def test_get_run_returns_matches_field(client):
    c, fc = client
    fc.load_run.return_value = {
        "search_name": "wax_coat",
        "run_date": "2026-06-21",
        "matches": [{"url": "https://example.com/coat", "score": 9}],
        "partial_matches": [],
    }
    r = c.get("/api/results/wax_coat/2026-06-21")
    assert r.status_code == 200
    assert len(r.json()["matches"]) == 1
