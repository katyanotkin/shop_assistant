from typing import Optional
from pydantic import BaseModel


class SearchCriteria(BaseModel):
    category: str
    gender: str
    outer_material: list[str] = []
    lining: list[str] = []
    exclude: list[str] = []
    sizes: list[str] = []
    max_price: Optional[float] = None
    extra_notes: Optional[str] = None


class SearchConfig(BaseModel):
    search_name: str
    active: bool = True
    criteria: SearchCriteria


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
