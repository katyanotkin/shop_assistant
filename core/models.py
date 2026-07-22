from typing import Optional
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

_MAX_EXAMPLE_URL_LENGTH = 2000


def validate_example_urls(urls: list[str]) -> list[str]:
    """Keep only well-formed http(s) URLs, capped at 3.

    Reference URLs are interpolated as raw text into the Gemini scoring prompt
    (see core/ranker.py `_example_section`), so anything that isn't actually a
    URL is a prompt-injection vector rather than a benchmark product.
    """
    out = []
    for u in urls:
        if not isinstance(u, str) or len(u) > _MAX_EXAMPLE_URL_LENGTH:
            continue
        parsed = urlparse(u)
        if parsed.scheme in ("http", "https") and parsed.netloc:
            out.append(u)
    return out[:3]


# gender/exclude are already enforced elsewhere in the ranker prompt as hard
# (gender) or near-hard (exclude) rules, so allowing them as deal_breakers too
# would just be a confusing no-op instruction alongside the existing one.
_DEAL_BREAKER_INELIGIBLE = frozenset({"category", "gender", "exclude"})


class SearchCriteria(BaseModel):
    model_config = ConfigDict(extra="allow")

    category: list[str]

    @field_validator("category", mode="before")
    @classmethod
    def coerce_category(cls, v: object) -> list[str]:
        if isinstance(v, str):
            return [v]
        return v

    gender: Optional[str] = None
    material: list[str] = []
    length: list[str] = []
    lining: list[str] = []
    exclude: list[str] = []
    deal_breakers: list[str] = []
    sizes: list[str] = []
    max_price: Optional[float] = None
    extra_notes: Optional[str] = None

    @model_validator(mode="after")
    def _drop_stale_deal_breakers(self) -> "SearchCriteria":
        dumped = self.model_dump(exclude_defaults=True, exclude={"deal_breakers"})
        present = set()
        for key, value in dumped.items():
            if isinstance(value, (list, str)) and len(value) == 0:
                continue
            present.add(key)
        self.deal_breakers = [d for d in self.deal_breakers if d in present and d not in _DEAL_BREAKER_INELIGIBLE]
        return self


class ProductMatch(BaseModel):
    url: str
    title: str
    price: Optional[float] = None
    score: float
    matched: list[str] = []
    unmatched: list[str] = []
    notes: str = ""
    is_new: bool = False
    carried_over: bool = False


_MAX_PINNED_FINDS = 3


class PinnedFind(ProductMatch):
    pinned_at: str  # ISO date, same format as RunResult.run_date


def add_pinned_find(existing: list[PinnedFind], new_find: PinnedFind, cap: int = _MAX_PINNED_FINDS) -> list[PinnedFind]:
    """De-dupe by URL (re-pinning refreshes the snapshot) and FIFO-evict the oldest over cap.

    Unlike validate_example_urls' truncate-on-add, dropping the newest pin here
    would silently discard the very find the user just said they loved.
    """
    kept = [f for f in existing if f.url != new_find.url]
    kept.append(new_find)
    return kept[-cap:]


class SearchConfig(BaseModel):
    search_name: str
    title: str
    active: bool = True
    owner_id: str = "admin"
    visibility: str = "public"  # "public" | "private"
    description: Optional[str] = None  # original freeform text used to generate this config
    criteria: SearchCriteria
    preferred_shops: list[str] = []
    feedback_notes: Optional[str] = None
    avoid_shops: list[str] = []
    example_urls: list[str] = []
    pinned_finds: list[PinnedFind] = []

    @field_validator("example_urls")
    @classmethod
    def cap_example_urls(cls, v: list[str]) -> list[str]:
        return validate_example_urls(v)


class RunResult(BaseModel):
    search_name: str
    run_date: str
    matches: list[ProductMatch] = []
    partial_matches: list[ProductMatch] = []
    no_match: bool = False
    total_candidates: int = 0
    feedback: dict[str, str] = {}
    config_snapshot: Optional[SearchConfig] = None
