"""Tests for premium-tier gating added on top of the free/premium/admin roles:

  - Premium daily creation cap (2 new searches/clones per UTC calendar day),
    enforced on POST /api/user/search/generate (soft pre-check) and the
    persisting PUT /api/user/search/{name} (authoritative), plus the clone
    endpoint below.
  - POST /api/user/search/{source_name}/clone — premium-only, copies a public
    search's objective spec (criteria + preferred_shops) into a new private
    search owned by the caller.
  - Per-role run window (free: 30 days, premium: 90 days) on
    POST /api/user/search/{name}/run.
  - Per-role monthly run cap (free: 20/month, premium: 100/month), tracked via
    fc.get_user_run_count / fc.increment_user_run_count.
  - GET /api/searches now includes created_at (ISO string) for the caller's
    own rows only; null otherwise.

Follows the client fixture pattern from tests/test_user_and_admin_endpoints.py:
settings + fc fully mocked, quota counters default to 0 so gates stay open
unless a test overrides them.
"""

import hashlib
from datetime import datetime, timedelta, timezone
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
_PREMIUM_USER = {
    "email": "premium@x.com",
    "display_name": "Premium User",
    "photo_url": "",
    "role": "premium",
}

_FAKE_CONFIG = {
    "search_name": "wool_coat",
    "title": "Wool Coat",
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

_GENERATE_BODY = {
    "title": "Wool Coat",
    "description": "a warm wool coat for winter use in the city",
}


def _tok(user_dict: dict) -> str:
    return create_session_token(user_dict, SECRET)


class _FakeRunResult:
    matches = [{"url": "https://example.com/coat", "score": 9}]
    partial_matches = []


@pytest.fixture()
def client():
    """TestClient with settings + fc fully mocked (mirrors
    tests/test_user_and_admin_endpoints.py's client fixture)."""
    with patch.object(main_module, "_settings") as s:
        s.admin_password = PASSWORD
        s.session_secret = SECRET
        s.google_client_id = "fake-client-id"
        s.google_client_secret = "fake-secret"
        s.base_url = None
        s.google_cloud_project = "fake-project"
        with patch("web.main.fc") as mock_fc:
            mock_fc.get_user.return_value = None
            mock_fc.list_searches.return_value = []
            mock_fc.load_search_config.return_value = None
            mock_fc.save_search_config.return_value = None
            mock_fc.list_users.return_value = []
            mock_fc.list_user_searches.return_value = []
            mock_fc.count_searches_created_since.return_value = 0
            mock_fc.get_user_run_count.return_value = 0
            mock_fc.increment_user_run_count.return_value = None
            mock_fc.generate_unique_search_name.return_value = "wool_coat"
            mock_fc.update_user_role.return_value = None
            mock_fc.update_search_visibility.return_value = None
            mock_fc.delete_search_config.return_value = None
            with TestClient(app, raise_server_exceptions=True) as c:
                yield c, mock_fc


# ── 1. Premium daily creation limit ──────────────────────────────────────────
# PUT /api/user/search/{name}


def test_save_new_search_premium_succeeds_at_zero_created_today(client):
    c, mock_fc = client
    mock_fc.load_search_config.return_value = None
    mock_fc.count_searches_created_since.return_value = 0
    c.cookies.set("sa_session", _tok(_PREMIUM_USER))
    r = c.put("/api/user/search/wool_coat", json={"title": "Wool Coat", "criteria": {"category": ["coat"]}})
    assert r.status_code == 200


def test_save_new_search_premium_succeeds_at_one_created_today(client):
    c, mock_fc = client
    mock_fc.load_search_config.return_value = None
    mock_fc.count_searches_created_since.return_value = 1
    c.cookies.set("sa_session", _tok(_PREMIUM_USER))
    r = c.put("/api/user/search/wool_coat", json={"title": "Wool Coat", "criteria": {"category": ["coat"]}})
    assert r.status_code == 200


def test_save_new_search_premium_403_at_two_created_today(client):
    c, mock_fc = client
    mock_fc.load_search_config.return_value = None
    mock_fc.count_searches_created_since.return_value = 2
    c.cookies.set("sa_session", _tok(_PREMIUM_USER))
    r = c.put("/api/user/search/wool_coat", json={"title": "Wool Coat", "criteria": {"category": ["coat"]}})
    assert r.status_code == 403
    assert "limit of 2 new searches" in r.json()["detail"]


def test_save_existing_search_premium_edit_not_gated_by_daily_limit(client):
    """Editing (not creating) must never be blocked by the daily creation cap."""
    c, mock_fc = client
    mock_fc.load_search_config.return_value = {
        "search_name": "wool_coat",
        "owner_id": _PREMIUM_USER["email"],
        "created_at": datetime.now(timezone.utc) - timedelta(days=5),
    }
    mock_fc.count_searches_created_since.return_value = 2
    c.cookies.set("sa_session", _tok(_PREMIUM_USER))
    r = c.put("/api/user/search/wool_coat", json={"title": "Wool Coat", "criteria": {"category": ["coat"]}})
    assert r.status_code == 200


def test_generate_premium_403_at_daily_creation_quota(client):
    c, mock_fc = client
    mock_fc.count_searches_created_since.return_value = 2
    c.cookies.set("sa_session", _tok(_PREMIUM_USER))
    with patch("web.main.generate_search_config") as gen:
        r = c.post("/api/user/search/generate", json=_GENERATE_BODY)
    assert r.status_code == 403
    assert "limit of 2 new searches" in r.json()["detail"]
    gen.assert_not_called()


def test_generate_free_user_unaffected_by_premium_daily_counter(client):
    """A free user with no existing search is unaffected by
    count_searches_created_since — the free 1-search rule is the only gate
    that applies to them."""
    c, mock_fc = client
    mock_fc.list_user_searches.return_value = []
    mock_fc.count_searches_created_since.return_value = 2
    c.cookies.set("sa_session", _tok(_FREE_USER))
    with patch("web.main.generate_search_config", return_value=dict(_FAKE_CONFIG)):
        r = c.post("/api/user/search/generate", json=_GENERATE_BODY)
    assert r.status_code == 200


def test_generate_free_at_one_search_gets_unchanged_message_not_premium_message(client):
    """The free 1-search rule takes precedence and its message must stay
    unchanged, even when the premium daily counter is also at quota."""
    c, mock_fc = client
    mock_fc.list_user_searches.return_value = [{"search_name": "existing_search"}]
    mock_fc.count_searches_created_since.return_value = 2
    c.cookies.set("sa_session", _tok(_FREE_USER))
    r = c.post("/api/user/search/generate", json=_GENERATE_BODY)
    assert r.status_code == 403
    assert r.json()["detail"] == "Free plan allows one search. Contact us to upgrade."


def test_save_new_search_free_unaffected_by_premium_daily_counter(client):
    c, mock_fc = client
    mock_fc.load_search_config.return_value = None
    mock_fc.list_user_searches.return_value = []
    mock_fc.count_searches_created_since.return_value = 2
    c.cookies.set("sa_session", _tok(_FREE_USER))
    r = c.put("/api/user/search/wool_coat", json={"title": "Wool Coat", "criteria": {"category": ["coat"]}})
    assert r.status_code == 200


def test_save_new_search_admin_ungated_by_daily_limit(client):
    c, mock_fc = client
    mock_fc.load_search_config.return_value = None
    mock_fc.count_searches_created_since.return_value = 2
    c.cookies.set("sa_session", _tok(_ADMIN_USER))
    r = c.put("/api/user/search/wool_coat", json={"title": "Wool Coat", "criteria": {"category": ["coat"]}})
    assert r.status_code == 200


def test_generate_admin_ungated_by_daily_limit(client):
    c, mock_fc = client
    mock_fc.count_searches_created_since.return_value = 2
    c.cookies.set("sa_session", _tok(_ADMIN_USER))
    with patch("web.main.generate_search_config", return_value=dict(_FAKE_CONFIG)):
        r = c.post("/api/user/search/generate", json=_GENERATE_BODY)
    assert r.status_code == 200


# ── 2. Clone endpoint ─────────────────────────────────────────────────────────
# POST /api/user/search/{source_name}/clone

_PUBLIC_SOURCE = {
    "search_name": "source_search",
    "title": "Source Title",
    "visibility": "public",
    "owner_id": "someone_else@x.com",
    "criteria": {"category": ["coat"], "material": ["wool"]},
    "preferred_shops": ["https://example.com"],
    "example_urls": ["https://example.com/reference"],
    "pinned_finds": [{"url": "https://example.com/pinned", "pinned_at": "2026-01-01"}],
    "feedback_notes": "prefers longer length",
}


def test_clone_requires_session(client):
    c, _ = client
    r = c.post("/api/user/search/source_search/clone")
    assert r.status_code == 401


def test_clone_free_returns_403(client):
    c, mock_fc = client
    mock_fc.load_search_config.return_value = dict(_PUBLIC_SOURCE)
    c.cookies.set("sa_session", _tok(_FREE_USER))
    r = c.post("/api/user/search/source_search/clone")
    assert r.status_code == 403
    assert "Premium" in r.json()["detail"]


def test_clone_404_when_source_private(client):
    c, mock_fc = client
    mock_fc.load_search_config.return_value = dict(_PUBLIC_SOURCE, visibility="private")
    c.cookies.set("sa_session", _tok(_PREMIUM_USER))
    r = c.post("/api/user/search/source_search/clone")
    assert r.status_code == 404


def test_clone_404_when_source_missing(client):
    c, mock_fc = client
    mock_fc.load_search_config.return_value = None
    c.cookies.set("sa_session", _tok(_PREMIUM_USER))
    r = c.post("/api/user/search/nonexistent/clone")
    assert r.status_code == 404


def test_clone_404_detail_identical_for_private_and_missing_source(client):
    """A private search must be indistinguishable from a nonexistent one."""
    c, mock_fc = client
    c.cookies.set("sa_session", _tok(_PREMIUM_USER))

    mock_fc.load_search_config.return_value = dict(_PUBLIC_SOURCE, visibility="private")
    r_private = c.post("/api/user/search/source_search/clone")

    mock_fc.load_search_config.return_value = None
    r_missing = c.post("/api/user/search/nonexistent/clone")

    assert r_private.status_code == r_missing.status_code == 404
    assert r_private.json()["detail"] == r_missing.json()["detail"]


def test_clone_success_premium_public_source(client):
    c, mock_fc = client
    mock_fc.load_search_config.return_value = dict(_PUBLIC_SOURCE)
    mock_fc.generate_unique_search_name.return_value = "source_title_copy"
    c.cookies.set("sa_session", _tok(_PREMIUM_USER))
    r = c.post("/api/user/search/source_search/clone")
    assert r.status_code == 200
    data = r.json()
    assert data["search_name"] == "source_title_copy"
    assert data["title"] == "Source Title (copy)"
    assert data["visibility"] == "private"
    assert data["owner_id"] == _PREMIUM_USER["email"]
    assert data["criteria"] == _PUBLIC_SOURCE["criteria"]
    assert data["preferred_shops"] == _PUBLIC_SOURCE["preferred_shops"]
    assert isinstance(data["created_at"], str)
    datetime.fromisoformat(data["created_at"])  # must parse as ISO

    mock_fc.save_search_config.assert_called_once()
    saved = mock_fc.save_search_config.call_args[0][0]
    assert "example_urls" not in saved
    assert "pinned_finds" not in saved
    assert "feedback_notes" not in saved


def test_clone_explicit_title_respected(client):
    c, mock_fc = client
    mock_fc.load_search_config.return_value = dict(_PUBLIC_SOURCE)
    c.cookies.set("sa_session", _tok(_PREMIUM_USER))
    r = c.post("/api/user/search/source_search/clone", json={"title": "My Custom Title"})
    assert r.status_code == 200
    assert r.json()["title"] == "My Custom Title"


def test_clone_403_at_daily_quota(client):
    c, mock_fc = client
    mock_fc.load_search_config.return_value = dict(_PUBLIC_SOURCE)
    mock_fc.count_searches_created_since.return_value = 2
    c.cookies.set("sa_session", _tok(_PREMIUM_USER))
    r = c.post("/api/user/search/source_search/clone")
    assert r.status_code == 403
    assert "limit of 2 new searches" in r.json()["detail"]
    mock_fc.save_search_config.assert_not_called()


def test_clone_admin_bypasses_daily_quota(client):
    c, mock_fc = client
    mock_fc.load_search_config.return_value = dict(_PUBLIC_SOURCE)
    mock_fc.count_searches_created_since.return_value = 99
    c.cookies.set("sa_session", _tok(_ADMIN_USER))
    r = c.post("/api/user/search/source_search/clone")
    assert r.status_code == 200


def test_clone_works_with_no_request_body(client):
    """No JSON body at all (not even `{}`) must not 422."""
    c, mock_fc = client
    mock_fc.load_search_config.return_value = dict(_PUBLIC_SOURCE)
    c.cookies.set("sa_session", _tok(_PREMIUM_USER))
    r = c.post("/api/user/search/source_search/clone")
    assert r.status_code == 200


# ── 3. Run window ─────────────────────────────────────────────────────────────
# POST /api/user/search/{name}/run


def test_run_premium_owner_succeeds_at_89_days(client):
    c, mock_fc = client
    created_at = datetime.now(timezone.utc) - timedelta(days=89)
    mock_fc.load_search_config.return_value = {
        "search_name": "wool_coat",
        "owner_id": _PREMIUM_USER["email"],
        "created_at": created_at,
    }
    c.cookies.set("sa_session", _tok(_PREMIUM_USER))
    with patch("web.main.run_search", return_value=_FakeRunResult()):
        r = c.post("/api/user/search/wool_coat/run")
    assert r.status_code == 200


def test_run_premium_owner_403_at_91_days(client):
    c, mock_fc = client
    created_at = datetime.now(timezone.utc) - timedelta(days=91)
    mock_fc.load_search_config.return_value = {
        "search_name": "wool_coat",
        "owner_id": _PREMIUM_USER["email"],
        "created_at": created_at,
    }
    c.cookies.set("sa_session", _tok(_PREMIUM_USER))
    with patch("web.main.run_search", return_value=_FakeRunResult()) as run_mock:
        r = c.post("/api/user/search/wool_coat/run")
    assert r.status_code == 403
    assert "90-day run window" in r.json()["detail"]
    run_mock.assert_not_called()


def test_run_free_owner_still_403_after_31_days_with_unchanged_message(client):
    c, mock_fc = client
    created_at = datetime.now(timezone.utc) - timedelta(days=31)
    mock_fc.load_search_config.return_value = {
        "search_name": "wool_coat",
        "owner_id": _FREE_USER["email"],
        "created_at": created_at,
    }
    c.cookies.set("sa_session", _tok(_FREE_USER))
    with patch("web.main.run_search", return_value=_FakeRunResult()) as run_mock:
        r = c.post("/api/user/search/wool_coat/run")
    assert r.status_code == 403
    assert r.json()["detail"] == "Free plan: 30-day run window has expired. Contact us to upgrade."
    run_mock.assert_not_called()


# ── 4. Monthly run limit ──────────────────────────────────────────────────────


def test_run_free_403_at_monthly_limit_of_20(client):
    c, mock_fc = client
    mock_fc.load_search_config.return_value = {
        "search_name": "wool_coat",
        "owner_id": _FREE_USER["email"],
        "created_at": datetime.now(timezone.utc) - timedelta(days=5),
    }
    mock_fc.get_user_run_count.return_value = 20
    c.cookies.set("sa_session", _tok(_FREE_USER))
    with patch("web.main.run_search", return_value=_FakeRunResult()) as run_mock:
        r = c.post("/api/user/search/wool_coat/run")
    assert r.status_code == 403
    assert "all 20 runs" in r.json()["detail"]
    run_mock.assert_not_called()
    mock_fc.increment_user_run_count.assert_not_called()


def test_run_premium_403_at_monthly_limit_of_100(client):
    c, mock_fc = client
    mock_fc.load_search_config.return_value = {
        "search_name": "wool_coat",
        "owner_id": _PREMIUM_USER["email"],
        "created_at": datetime.now(timezone.utc) - timedelta(days=5),
    }
    mock_fc.get_user_run_count.return_value = 100
    c.cookies.set("sa_session", _tok(_PREMIUM_USER))
    with patch("web.main.run_search", return_value=_FakeRunResult()) as run_mock:
        r = c.post("/api/user/search/wool_coat/run")
    assert r.status_code == 403
    assert "all 100 runs" in r.json()["detail"]
    run_mock.assert_not_called()
    mock_fc.increment_user_run_count.assert_not_called()


def test_run_premium_ok_at_99_and_increments_run_count(client):
    c, mock_fc = client
    mock_fc.load_search_config.return_value = {
        "search_name": "wool_coat",
        "owner_id": _PREMIUM_USER["email"],
        "created_at": datetime.now(timezone.utc) - timedelta(days=5),
    }
    mock_fc.get_user_run_count.return_value = 99
    c.cookies.set("sa_session", _tok(_PREMIUM_USER))
    with patch("web.main.run_search", return_value=_FakeRunResult()):
        r = c.post("/api/user/search/wool_coat/run")
    assert r.status_code == 200
    current_month = datetime.now(timezone.utc).strftime("%Y-%m")
    mock_fc.increment_user_run_count.assert_called_once_with(_PREMIUM_USER["email"], current_month)


def test_run_admin_no_monthly_check_and_no_increment(client):
    c, mock_fc = client
    mock_fc.load_search_config.return_value = {
        "search_name": "wool_coat",
        "owner_id": "someone_else@x.com",
        "created_at": datetime.now(timezone.utc) - timedelta(days=500),
    }
    mock_fc.get_user_run_count.return_value = 999
    c.cookies.set("sa_session", _tok(_ADMIN_USER))
    with patch("web.main.run_search", return_value=_FakeRunResult()):
        r = c.post("/api/user/search/wool_coat/run")
    assert r.status_code == 200
    mock_fc.get_user_run_count.assert_not_called()
    mock_fc.increment_user_run_count.assert_not_called()


def test_run_failed_run_search_does_not_increment_run_count(client):
    c, mock_fc = client
    mock_fc.load_search_config.return_value = {
        "search_name": "wool_coat",
        "owner_id": _PREMIUM_USER["email"],
        "created_at": datetime.now(timezone.utc) - timedelta(days=5),
    }
    mock_fc.get_user_run_count.return_value = 0
    c.cookies.set("sa_session", _tok(_PREMIUM_USER))
    with patch("web.main.run_search", side_effect=Exception("boom")):
        with pytest.raises(Exception, match="boom"):
            c.post("/api/user/search/wool_coat/run")
    mock_fc.increment_user_run_count.assert_not_called()


# ── 5. GET /api/searches created_at ───────────────────────────────────────────


def test_searches_created_at_present_for_own_search(client):
    c, mock_fc = client
    created_at = datetime(2026, 6, 1, tzinfo=timezone.utc)
    mock_fc.list_searches.return_value = [
        {
            "search_name": "wool_coat",
            "active": True,
            "visibility": "private",
            "owner_id": _PREMIUM_USER["email"],
            "created_at": created_at,
        }
    ]
    c.cookies.set("sa_session", _tok(_PREMIUM_USER))
    r = c.get("/api/searches")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 1
    assert data[0]["created_at"] == created_at.isoformat()


def test_searches_created_at_null_for_non_owned_search(client):
    c, mock_fc = client
    created_at = datetime(2026, 6, 1, tzinfo=timezone.utc)
    mock_fc.list_searches.return_value = [
        {
            "search_name": "someone_elses_search",
            "active": True,
            "visibility": "public",
            "owner_id": "other@x.com",
            "created_at": created_at,
        }
    ]
    c.cookies.set("sa_session", _tok(_PREMIUM_USER))
    r = c.get("/api/searches")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 1
    assert data[0]["created_at"] is None
