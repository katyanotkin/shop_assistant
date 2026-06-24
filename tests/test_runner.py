from contextlib import ExitStack
from unittest.mock import patch

from core.runner import run_search
from core.settings import Settings

_FAKE_CONFIG = {
    "search_name": "test_search",
    "active": True,
    "owner_id": "admin",
    "visibility": "public",
    "criteria": {"category": ["coat"], "gender": "women"},
    "preferred_shops": ["https://example.com"],
}

_FAKE_CANDIDATE = {"link": "https://example.com/p1", "title": "Nice Coat", "price": "120"}
_FAKE_RANKED = [
    {
        "url": "https://example.com/p1",
        "title": "Nice Coat",
        "score": 9.0,
        "matched": [],
        "unmatched": [],
        "notes": "",
    }
]


def _run(dry_run=True):
    with ExitStack() as stack:
        stack.enter_context(patch("core.runner.fc.load_search_config", return_value=_FAKE_CONFIG))
        stack.enter_context(patch("core.runner.fc.load_feedback_entries", return_value=[]))
        stack.enter_context(patch("core.runner.learn_from_feedback"))
        stack.enter_context(patch("core.runner.search_products", return_value=[_FAKE_CANDIDATE]))
        stack.enter_context(patch("core.runner.rank_all", return_value=_FAKE_RANKED))
        stack.enter_context(patch("core.runner.fc.load_last_run", return_value=None))
        stack.enter_context(patch("core.runner.save_csv", return_value="results/test.csv"))
        stack.enter_context(patch("core.runner.fc.save_run"))
        stack.enter_context(patch("core.runner.send_run_notification"))
        return run_search("test_search", Settings(google_cloud_project="test", admin_password=None), dry_run=dry_run)


def test_config_snapshot_is_attached():
    result = _run()
    assert result.config_snapshot is not None
    snap = result.config_snapshot
    assert snap.search_name == "test_search"
    assert snap.owner_id == "admin"
    assert snap.visibility == "public"
    assert snap.criteria.gender == "women"
    assert snap.preferred_shops == ["https://example.com"]


def test_config_snapshot_serializes():
    data = _run().model_dump()
    snap = data["config_snapshot"]
    assert isinstance(snap, dict)
    assert snap["search_name"] == "test_search"
    assert snap["criteria"]["gender"] == "women"
