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
            # Results endpoints 404 unless the search's live config is public
            # (or the caller is owner/admin) — default to a public config.
            fc.load_search_config.return_value = {"search_name": "wax_coat", "visibility": "public"}
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
    base = {"title": "", "visibility": "public", "owned": False, "created_at": None}
    assert data[0] == {"name": "wax_coat", "active": True, **base}
    assert data[1] == {"name": "wool_jacket", "active": False, **base}


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


def test_get_searches_hides_private_from_non_admin(client):
    c, fc = client
    fc.list_searches.return_value = [
        {"search_name": "wax_coat", "active": True, "visibility": "public"},
        {"search_name": "secret_search", "active": True, "visibility": "private"},
    ]
    r = c.get("/api/searches")
    names = [s["name"] for s in r.json()]
    assert "wax_coat" in names
    assert "secret_search" not in names


def test_get_searches_shows_private_to_admin(client):
    import hashlib

    c, fc = client
    fc.list_searches.return_value = [
        {"search_name": "wax_coat", "active": True, "visibility": "public"},
        {"search_name": "secret_search", "active": True, "visibility": "private"},
    ]
    token = hashlib.sha256(b"sa:hunter2").hexdigest()
    r = c.get("/api/searches", cookies={"sa_admin": token})
    names = [s["name"] for s in r.json()]
    assert "wax_coat" in names
    assert "secret_search" in names


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


def test_get_run_returns_live_pinned_finds_not_frozen_snapshot(client):
    """A pin/unpin made after this run was saved (or on a different run entirely)
    must show up immediately — pinned_finds must come from the live search config,
    not whatever config_snapshot happened to hold when this run executed.
    Pinned finds are personal signal, so this is asserted as the OWNER."""
    from core.auth import create_session_token

    c, fc = client
    fc.load_run.return_value = {
        "search_name": "wax_coat",
        "run_date": "2026-06-21",
        "matches": [],
        "partial_matches": [],
        "config_snapshot": {"pinned_finds": [{"url": "https://stale.example.com"}]},
    }
    fc.load_search_config.return_value = {
        "owner_id": "owner@x.com",
        "pinned_finds": [{"url": "https://example.com/pinned-after-run"}],
    }
    with patch.object(main_module._settings, "session_secret", "test-secret"):
        token = create_session_token({"email": "owner@x.com", "role": "free"}, "test-secret")
        r = c.get("/api/results/wax_coat/2026-06-21", cookies={"sa_session": token})
    assert r.status_code == 200
    assert r.json()["pinned_finds"] == [{"url": "https://example.com/pinned-after-run"}]


def test_get_run_pinned_finds_empty_when_no_live_config(client):
    # A run whose search config is gone is orphaned data: admin-only now,
    # and the live merge must degrade to an empty list.
    import hashlib

    c, fc = client
    fc.load_search_config.return_value = None
    token = hashlib.sha256(b"sa:hunter2").hexdigest()
    r = c.get("/api/results/wax_coat/2026-06-21", cookies={"sa_admin": token})
    assert r.status_code == 200
    assert r.json()["pinned_finds"] == []


def test_get_run_redacts_feedback_from_anonymous_caller(client):
    c, fc = client
    fc.load_run.return_value = {
        "search_name": "wax_coat",
        "run_date": "2026-06-21",
        "matches": [],
        "partial_matches": [],
        "feedback": {"https://example.com/a": "great fit"},
    }
    r = c.get("/api/results/wax_coat/2026-06-21")
    assert r.status_code == 200
    assert r.json()["feedback"] == {}


def test_get_run_shows_feedback_to_admin(client):
    import hashlib

    c, fc = client
    fc.load_run.return_value = {
        "search_name": "wax_coat",
        "run_date": "2026-06-21",
        "matches": [],
        "partial_matches": [],
        "feedback": {"https://example.com/a": "great fit"},
    }
    token = hashlib.sha256(b"sa:hunter2").hexdigest()
    r = c.get("/api/results/wax_coat/2026-06-21", cookies={"sa_admin": token})
    assert r.json()["feedback"] == {"https://example.com/a": "great fit"}


def test_get_run_shows_feedback_to_owner(client):
    from core.auth import create_session_token

    c, fc = client
    fc.load_search_config.return_value = {"search_name": "wax_coat", "owner_id": "owner@x.com"}
    fc.load_run.return_value = {
        "search_name": "wax_coat",
        "run_date": "2026-06-21",
        "matches": [],
        "partial_matches": [],
        "feedback": {"https://example.com/a": "great fit"},
    }
    with patch.object(main_module._settings, "session_secret", "test-secret"):
        token = create_session_token({"email": "owner@x.com", "role": "free"}, "test-secret")
        r = c.get("/api/results/wax_coat/2026-06-21", cookies={"sa_session": token})
    assert r.json()["feedback"] == {"https://example.com/a": "great fit"}


def test_get_run_redacts_feedback_from_non_owner_session(client):
    from core.auth import create_session_token

    c, fc = client
    fc.load_search_config.return_value = {"search_name": "wax_coat", "owner_id": "owner@x.com"}
    fc.load_run.return_value = {
        "search_name": "wax_coat",
        "run_date": "2026-06-21",
        "matches": [],
        "partial_matches": [],
        "feedback": {"https://example.com/a": "great fit"},
    }
    with patch.object(main_module._settings, "session_secret", "test-secret"):
        token = create_session_token({"email": "other@x.com", "role": "free"}, "test-secret")
        r = c.get("/api/results/wax_coat/2026-06-21", cookies={"sa_session": token})
    assert r.json()["feedback"] == {}


def test_get_run_returns_live_example_urls_sanitized(client):
    """example_urls must be live-merged from the search config (like pinned_finds),
    sanitized via validate_example_urls, and independent of the run's frozen
    config_snapshot. Reference products are personal signal, so asserted as OWNER."""
    from core.auth import create_session_token

    c, fc = client
    fc.load_run.return_value = {
        "search_name": "wax_coat",
        "run_date": "2026-06-21",
        "matches": [],
        "partial_matches": [],
        "config_snapshot": {"example_urls": ["https://stale.example.com/snapshot-only"]},
    }
    fc.load_search_config.return_value = {
        "owner_id": "owner@x.com",
        "example_urls": ["not a url", "https://ok.example/x"],
    }
    with patch.object(main_module._settings, "session_secret", "test-secret"):
        token = create_session_token({"email": "owner@x.com", "role": "free"}, "test-secret")
        r = c.get("/api/results/wax_coat/2026-06-21", cookies={"sa_session": token})
    assert r.status_code == 200
    assert r.json()["example_urls"] == ["https://ok.example/x"]


def test_get_run_redacts_personal_layers_from_non_owner_on_public_search(client):
    """Public showcase keeps scores/criteria visible, but personal signal —
    pinned finds, reference products, learn-mode notes (incl. the frozen
    config_snapshot copies) — is owner/admin-only."""
    c, fc = client
    fc.load_run.return_value = {
        "search_name": "wax_coat",
        "run_date": "2026-06-21",
        "matches": [{"url": "https://example.com/coat", "score": 9}],
        "partial_matches": [],
        "config_snapshot": {
            "criteria": {"category": ["coat"]},
            "feedback_notes": "prefers unlined",
            "avoid_shops": ["bad.example"],
            "example_urls": ["https://ref.example/coat"],
            "pinned_finds": [{"url": "https://pin.example/coat"}],
        },
    }
    fc.load_search_config.return_value = {
        "search_name": "wax_coat",
        "visibility": "public",
        "owner_id": "owner@x.com",
        "pinned_finds": [{"url": "https://pin.example/coat"}],
        "example_urls": ["https://ref.example/coat"],
    }
    r = c.get("/api/results/wax_coat/2026-06-21")
    assert r.status_code == 200
    data = r.json()
    assert data["pinned_finds"] == []
    assert data["example_urls"] == []
    snap = data["config_snapshot"]
    assert snap["criteria"] == {"category": ["coat"]}  # objective spec stays public
    assert snap["feedback_notes"] is None
    assert snap["avoid_shops"] == []
    assert snap["example_urls"] == []
    assert snap["pinned_finds"] == []


def test_get_run_example_urls_empty_when_no_live_config(client):
    # Orphaned run (no config): admin-only, live example_urls merge degrades to [].
    import hashlib

    c, fc = client
    fc.load_search_config.return_value = None
    token = hashlib.sha256(b"sa:hunter2").hexdigest()
    r = c.get("/api/results/wax_coat/2026-06-21", cookies={"sa_admin": token})
    assert r.status_code == 200
    assert r.json()["example_urls"] == []


# ── Private search visibility gate ────────────────────────────────────────────
#
# A search config with visibility "private" (or a missing/orphaned config) must
# 404 for anonymous callers and non-owner sessions, and stay indistinguishable
# from a truly nonexistent search — while remaining visible to its owner and to
# admins. Legacy configs saved before visibility existed default to "public".

_PRIVATE_CONFIG = {"search_name": "secret_search", "owner_id": "owner@x.com", "visibility": "private"}


def _admin_cookie() -> dict:
    import hashlib

    return {"sa_admin": hashlib.sha256(b"sa:hunter2").hexdigest()}


def _session_cookie(email: str) -> dict:
    from core.auth import create_session_token

    with patch.object(main_module._settings, "session_secret", "test-secret"):
        token = create_session_token({"email": email, "role": "free"}, "test-secret")
    return {"sa_session": token}


# GET /api/search/{name} ------------------------------------------------------


def test_get_search_private_404_anonymous(client):
    c, fc = client
    fc.load_search_config.return_value = _PRIVATE_CONFIG
    r = c.get("/api/search/secret_search")
    assert r.status_code == 404


def test_get_search_private_404_non_owner_session(client):
    c, fc = client
    fc.load_search_config.return_value = _PRIVATE_CONFIG
    with patch.object(main_module._settings, "session_secret", "test-secret"):
        r = c.get("/api/search/secret_search", cookies=_session_cookie("other@x.com"))
    assert r.status_code == 404


def test_get_search_private_200_owner(client):
    c, fc = client
    fc.load_search_config.return_value = _PRIVATE_CONFIG
    with patch.object(main_module._settings, "session_secret", "test-secret"):
        r = c.get("/api/search/secret_search", cookies=_session_cookie("owner@x.com"))
    assert r.status_code == 200


def test_get_search_private_200_admin(client):
    c, fc = client
    fc.load_search_config.return_value = _PRIVATE_CONFIG
    r = c.get("/api/search/secret_search", cookies=_admin_cookie())
    assert r.status_code == 200


# GET /api/results/{search_name} ----------------------------------------------


def test_get_run_dates_private_404_anonymous(client):
    c, fc = client
    fc.load_search_config.return_value = _PRIVATE_CONFIG
    fc.list_runs.return_value = ["2026-06-21"]
    r = c.get("/api/results/secret_search")
    assert r.status_code == 404


def test_get_run_dates_private_200_owner(client):
    c, fc = client
    fc.load_search_config.return_value = _PRIVATE_CONFIG
    fc.list_runs.return_value = ["2026-06-21"]
    with patch.object(main_module._settings, "session_secret", "test-secret"):
        r = c.get("/api/results/secret_search", cookies=_session_cookie("owner@x.com"))
    assert r.status_code == 200


def test_get_run_dates_private_200_admin(client):
    c, fc = client
    fc.load_search_config.return_value = _PRIVATE_CONFIG
    fc.list_runs.return_value = ["2026-06-21"]
    r = c.get("/api/results/secret_search", cookies=_admin_cookie())
    assert r.status_code == 200


def test_get_run_dates_private_404_matches_nonexistent_search_detail(client):
    """A private search must be indistinguishable from one that doesn't exist at all."""
    c, fc = client
    fc.load_search_config.return_value = _PRIVATE_CONFIG
    fc.list_runs.return_value = ["2026-06-21"]
    r_private = c.get("/api/results/secret_search")
    assert r_private.status_code == 404

    fc.load_search_config.return_value = None
    fc.list_runs.return_value = []
    r_missing = c.get("/api/results/does_not_exist")
    assert r_missing.status_code == 404

    assert r_private.json()["detail"] == r_missing.json()["detail"] == "No runs found"


# GET /api/results/{search_name}/{run_date} ------------------------------------

_PRIVATE_RUN = {
    "search_name": "secret_search",
    "run_date": "2026-06-21",
    "matches": [],
    "partial_matches": [],
    "feedback": {"https://example.com/a": "great fit"},
}


def test_get_run_private_404_anonymous(client):
    c, fc = client
    fc.load_search_config.return_value = _PRIVATE_CONFIG
    fc.load_run.return_value = _PRIVATE_RUN
    r = c.get("/api/results/secret_search/2026-06-21")
    assert r.status_code == 404


def test_get_run_private_404_non_owner_session(client):
    c, fc = client
    fc.load_search_config.return_value = _PRIVATE_CONFIG
    fc.load_run.return_value = _PRIVATE_RUN
    with patch.object(main_module._settings, "session_secret", "test-secret"):
        r = c.get("/api/results/secret_search/2026-06-21", cookies=_session_cookie("other@x.com"))
    assert r.status_code == 404


def test_get_run_private_200_owner_sees_feedback(client):
    c, fc = client
    fc.load_search_config.return_value = _PRIVATE_CONFIG
    fc.load_run.return_value = _PRIVATE_RUN
    with patch.object(main_module._settings, "session_secret", "test-secret"):
        r = c.get("/api/results/secret_search/2026-06-21", cookies=_session_cookie("owner@x.com"))
    assert r.status_code == 200
    assert r.json()["feedback"] == {"https://example.com/a": "great fit"}


def test_get_run_private_200_admin(client):
    c, fc = client
    fc.load_search_config.return_value = _PRIVATE_CONFIG
    fc.load_run.return_value = _PRIVATE_RUN
    r = c.get("/api/results/secret_search/2026-06-21", cookies=_admin_cookie())
    assert r.status_code == 200


def test_get_run_private_404_matches_nonexistent_run_detail(client):
    """A private search's run must be indistinguishable from a nonexistent run."""
    c, fc = client
    fc.load_search_config.return_value = _PRIVATE_CONFIG
    fc.load_run.return_value = _PRIVATE_RUN
    r_private = c.get("/api/results/secret_search/2026-06-21")
    assert r_private.status_code == 404

    fc.load_search_config.return_value = None
    fc.load_run.return_value = None
    r_missing = c.get("/api/results/wax_coat/1999-01-01")
    assert r_missing.status_code == 404

    assert r_private.json()["detail"] == r_missing.json()["detail"] == "Run not found"


def test_get_run_orphaned_config_404_anonymous(client):
    # A run whose search config is gone (orphaned data) must 404 for anonymous
    # callers, not just fall through to a 200 (it's admin-only, see
    # test_get_run_pinned_finds_empty_when_no_live_config above).
    c, fc = client
    fc.load_search_config.return_value = None
    r = c.get("/api/results/wax_coat/2026-06-21")
    assert r.status_code == 404


def test_get_run_orphaned_config_404_non_admin_session(client):
    c, fc = client
    fc.load_search_config.return_value = None
    with patch.object(main_module._settings, "session_secret", "test-secret"):
        r = c.get("/api/results/wax_coat/2026-06-21", cookies=_session_cookie("someone@x.com"))
    assert r.status_code == 404


# Legacy configs (no "visibility" key) default to public -----------------------

_LEGACY_CONFIG = {"search_name": "wax_coat", "owner_id": "owner@x.com"}


def test_get_search_legacy_config_public_by_default(client):
    c, fc = client
    fc.load_search_config.return_value = _LEGACY_CONFIG
    r = c.get("/api/search/wax_coat")
    assert r.status_code == 200


def test_get_run_dates_legacy_config_public_by_default(client):
    c, fc = client
    fc.load_search_config.return_value = _LEGACY_CONFIG
    fc.list_runs.return_value = ["2026-06-21"]
    r = c.get("/api/results/wax_coat")
    assert r.status_code == 200


def test_get_run_legacy_config_public_by_default(client):
    c, fc = client
    fc.load_search_config.return_value = _LEGACY_CONFIG
    fc.load_run.return_value = {
        "search_name": "wax_coat",
        "run_date": "2026-06-21",
        "matches": [],
        "partial_matches": [],
    }
    r = c.get("/api/results/wax_coat/2026-06-21")
    assert r.status_code == 200
