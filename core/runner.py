import csv
import pathlib
from datetime import date

from .models import ProductMatch, RunResult, SearchCriteria
from .settings import Settings
from . import firestore_client as fc
from .searcher import search_products
from .ranker import rank_all
from .notifier import send_run_notification

_RESULTS_DIR = pathlib.Path("results")
_CSV_FIELDS = ["run_date", "search_name", "match_type", "score", "is_new", "title", "url", "price", "matched", "unmatched", "notes"]


def save_csv(result: RunResult) -> pathlib.Path:
    _RESULTS_DIR.mkdir(exist_ok=True)
    path = _RESULTS_DIR / f"{result.search_name}_{result.run_date}.csv"
    rows = []
    for m in result.matches:
        rows.append(_to_row(m, "match", result))
    for m in result.partial_matches:
        rows.append(_to_row(m, "partial", result))
    if not rows:
        rows.append({f: "" for f in _CSV_FIELDS} | {
            "run_date": result.run_date, "search_name": result.search_name,
            "match_type": "no_match", "score": "", "total_candidates": result.total_candidates,
        })
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=_CSV_FIELDS, delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)
    return path


def _to_row(m: ProductMatch, match_type: str, result: RunResult) -> dict:
    return {
        "run_date": result.run_date,
        "search_name": result.search_name,
        "match_type": match_type,
        "score": m.score,
        "is_new": m.is_new,
        "title": m.title,
        "url": m.url,
        "price": m.price or "",
        "matched": "; ".join(m.matched),
        "unmatched": "; ".join(m.unmatched),
        "notes": m.notes,
    }


def run_search(search_name: str, settings: Settings, dry_run: bool = False) -> RunResult:
    config = fc.load_search_config(search_name)
    if not config:
        raise ValueError(f"Search '{search_name}' not found in Firestore. Add it first with: run.py add <file>")

    criteria = SearchCriteria(**config["criteria"])

    candidates = search_products(criteria, settings.google_cloud_project, max_results=settings.max_candidates)
    print(f"Candidates: {len(candidates)}")

    ranked = rank_all(candidates, criteria, settings.google_cloud_project)

    matches: list[ProductMatch] = []
    partial_matches: list[ProductMatch] = []

    for r in ranked:
        score = float(r.get("score", 0))
        m = ProductMatch(
            url=r.get("url", ""),
            title=r.get("title", ""),
            price=r.get("price"),
            score=score,
            matched=r.get("matched", []),
            unmatched=r.get("unmatched", []),
            notes=r.get("notes", ""),
        )
        if score >= settings.match_score_threshold:
            matches.append(m)
        elif score >= settings.partial_score_threshold:
            partial_matches.append(m)

    matches.sort(key=lambda x: x.score, reverse=True)
    partial_matches.sort(key=lambda x: x.score, reverse=True)

    last_run = fc.load_last_run(search_name) if not dry_run else None
    prev_urls: set[str] = set()
    if last_run:
        prev_urls = {
            m["url"]
            for m in last_run.get("matches", []) + last_run.get("partial_matches", [])
        }

    for m in matches + partial_matches:
        if m.url not in prev_urls:
            m.is_new = True

    result = RunResult(
        search_name=search_name,
        run_date=str(date.today()),
        matches=matches,
        partial_matches=partial_matches,
        no_match=(not matches and not partial_matches),
        total_candidates=len(candidates),
    )

    csv_path = save_csv(result)
    print(f"  CSV: {csv_path}")

    if not dry_run:
        fc.save_run(search_name, result.run_date, result.model_dump())
        send_run_notification(result, settings)

    return result


def print_result(result: RunResult) -> None:
    print(f"\n=== {result.search_name} | {result.run_date} | {result.total_candidates} candidates ===")

    if result.no_match:
        print("  No matches today.")
        return

    if result.matches:
        print(f"\nMatches ({len(result.matches)}):")
        for m in result.matches:
            new_tag = " [NEW]" if m.is_new else ""
            print(f"  [{m.score:.0f}/10]{new_tag} {m.title or '(no title)'}")
            print(f"    {m.url}")
            if m.price:
                print(f"    Price: {m.price}")
            if m.matched:
                print(f"    OK: {', '.join(m.matched)}")
            if m.unmatched:
                print(f"    Missing: {', '.join(m.unmatched)}")

    if result.partial_matches:
        print(f"\nPartial matches ({len(result.partial_matches)}):")
        for m in result.partial_matches:
            new_tag = " [NEW]" if m.is_new else ""
            print(f"  [{m.score:.0f}/10]{new_tag} {m.title or '(no title)'}")
            print(f"    {m.url}")
            if m.unmatched:
                print(f"    Missing: {', '.join(m.unmatched)}")
