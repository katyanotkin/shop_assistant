import pytest
from pydantic import ValidationError

from core.models import ProductMatch, RunResult, SearchCriteria


def test_search_criteria_valid():
    c = SearchCriteria(category="jacket", gender="women")
    assert c.category == ["jacket"]
    assert c.gender == "women"
    assert c.material == []
    assert c.lining == []
    assert c.exclude == []
    assert c.sizes == []
    assert c.max_price is None
    assert c.extra_notes is None


def test_search_criteria_full():
    c = SearchCriteria(
        category=["coat", "trench"],
        gender="women",
        material=["waxed cotton"],
        lining=["cotton"],
        exclude=["polyester"],
        sizes=["M", "L"],
        max_price=300.0,
        extra_notes="must be waterproof",
    )
    assert c.material == ["waxed cotton"]
    assert c.max_price == 300.0
    assert c.extra_notes == "must be waterproof"


def test_search_criteria_missing_required_fields():
    with pytest.raises(ValidationError):
        SearchCriteria(category="jacket")


def test_product_match_defaults_is_new_false():
    m = ProductMatch(url="https://example.com", title="Test Jacket", score=8.0)
    assert m.is_new is False


def test_product_match_is_new_can_be_set():
    m = ProductMatch(url="https://example.com", title="Test Jacket", score=8.0, is_new=True)
    assert m.is_new is True


def test_product_match_optional_fields():
    m = ProductMatch(url="https://example.com", title="", score=0.0)
    assert m.price is None
    assert m.matched == []
    assert m.unmatched == []
    assert m.notes == ""


def test_run_result_defaults():
    r = RunResult(search_name="test", run_date="2024-01-01")
    assert r.matches == []
    assert r.partial_matches == []
    assert r.no_match is False
    assert r.total_candidates == 0
    assert r.config_snapshot is None


def test_run_result_config_snapshot_roundtrip():
    from core.models import SearchConfig, SearchCriteria

    cfg = SearchConfig(
        search_name="test",
        criteria=SearchCriteria(category="coat", gender="women"),
    )
    r = RunResult(search_name="test", run_date="2024-01-01", config_snapshot=cfg)
    assert r.config_snapshot is not None
    assert r.config_snapshot.search_name == "test"
    assert r.config_snapshot.criteria.gender == "women"
    # Serialization must not raise and must preserve the snapshot
    data = r.model_dump()
    assert data["config_snapshot"]["search_name"] == "test"
