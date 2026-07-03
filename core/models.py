from typing import Optional
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, field_validator

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
    sizes: list[str] = []
    max_price: Optional[float] = None
    extra_notes: Optional[str] = None


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

    @field_validator("example_urls")
    @classmethod
    def cap_example_urls(cls, v: list[str]) -> list[str]:
        return validate_example_urls(v)


class ProductMatch(BaseModel):
    url: str
    title: str
    price: Optional[float] = None
    score: float
    matched: list[str] = []
    unmatched: list[str] = []
    notes: str = ""
    is_new: bool = False


class RunResult(BaseModel):
    search_name: str
    run_date: str
    matches: list[ProductMatch] = []
    partial_matches: list[ProductMatch] = []
    no_match: bool = False
    total_candidates: int = 0
    feedback: dict[str, str] = {}
    config_snapshot: Optional[SearchConfig] = None
