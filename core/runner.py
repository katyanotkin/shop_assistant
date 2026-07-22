import csv
import pathlib
from datetime import date
from urllib.parse import urlparse

from . import firestore_client as fc
from . import models
from .feedback import learn_from_feedback
from .notifier import send_run_notification
from .ranker import rank_all
from .searcher import search_products
from .settings import Settings

_RESULTS_DIR = pathlib.Path("results")
_CSV_FIELDS = [
    "run_date",
    "search_name",
    "match_type",
    "score",
    "is_new",
    "carried_over",
    "title",
    "url",
    "price",
    "matched",
    "unmatched",
    "notes",
    "total_candidates",
]


def _link(url: str) -> str:
    """OSC 8 hyperlink — renders as clickable in iTerm2, GNOME Terminal, Kitty, Windows Terminal."""
    return f"\033]8;;{url}\033\\{url}\033]8;;\033\\"


def save_csv(result: models.RunResult) -> pathlib.Path:
    _RESULTS_DIR.mkdir(exist_ok=True)
    path = _RESULTS_DIR / f"{result.search_name}_{result.run_date}.csv"
    rows = []
    for m in result.matches:
        rows.append(_to_row(m, "match", result))
    for m in result.partial_matches:
        rows.append(_to_row(m, "partial", result))
    if not rows:
        rows.append(
            {f: "" for f in _CSV_FIELDS}
            | {
                "run_date": result.run_date,
                "search_name": result.search_name,
                "match_type": "no_match",
                "score": "",
                "total_candidates": result.total_candidates,
            }
        )
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=_CSV_FIELDS, delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)
    return path


def _to_row(m: models.ProductMatch, match_type: str, result: models.RunResult) -> dict:
    return {
        "run_date": result.run_date,
        "search_name": result.search_name,
        "match_type": match_type,
        "score": m.score,
        "is_new": m.is_new,
        "carried_over": m.carried_over,
        "title": m.title,
        "url": m.url,
        "price": m.price if m.price is not None else "",
        "matched": "; ".join(m.matched),
        "unmatched": "; ".join(m.unmatched),
        "notes": m.notes,
    }


def run_search(search_name: str, settings: Settings, dry_run: bool = False, learn: bool = True) -> models.RunResult:
    config = fc.load_search_config(search_name)
    if not config:
        raise ValueError(f"Search '{search_name}' not found in Firestore. Add it first with: run.py add <file>")

    feedback_notes: str = config.get("feedback_notes") or ""
    avoid_shops: set[str] = set(config.get("avoid_shops") or [])
    example_urls: list[str] = models.validate_example_urls(config.get("example_urls") or [])
    # Reuse the same sanitizer as example_urls — these are interpolated raw into
    # the same Gemini prompt section (core/ranker.py _example_section), so a
    # malformed/legacy pinned_finds.url must not reach it unfiltered either.
    pinned_urls: list[str] = models.validate_example_urls([f["url"] for f in config.get("pinned_finds", [])])

    if learn and not dry_run:
        learned = learn_from_feedback(search_name, settings.google_cloud_project)
        if learned is not None:
            feedback_notes = learned["feedback_notes"]
            avoid_shops = set(learned["avoid_shops"])
            fc.save_learned_feedback(search_name, feedback_notes, learned["avoid_shops"])

    criteria = models.SearchCriteria(**config["criteria"])
    shops: list[str] = config.get("preferred_shops", [])

    candidates = search_products(
        criteria,
        settings.google_cloud_project,
        max_results=settings.max_candidates,
        shops=shops or None,
        feedback_notes=feedback_notes,
    )

    if avoid_shops:
        before = len(candidates)
        candidates = [
            c for c in candidates if urlparse(c.get("link", "")).netloc.removeprefix("www.") not in avoid_shops
        ]
        if before > len(candidates):
            print(f"  Filtered {before - len(candidates)} candidates from avoided shops")

    # Carry forward Matches + Partial matches from the last 2 runs so a good
    # result isn't silently lost just because this run's fresh queries don't
    # resurface it. Re-verified fresh below (fetch + score), not redisplayed
    # with a stale score — shares the same max_candidates cap as new discovery
    # and is given priority within it (prepended) since avoiding loss is the
    # whole point.
    carried_forward_urls: set[str] = set()
    if not dry_run:
        recent = fc.load_recent_matches(search_name, limit=2)
        if avoid_shops:
            recent = [c for c in recent if urlparse(c.get("link", "")).netloc.removeprefix("www.") not in avoid_shops]
        existing_urls = {c.get("link", "") for c in candidates}
        new_recent = [c for c in recent if c.get("link", "") not in existing_urls]
        carried_forward_urls = {c["link"] for c in new_recent}
        candidates = (new_recent + candidates)[: settings.max_candidates]

    print(f"Candidates: {len(candidates)}")

    ranked = rank_all(
        candidates,
        criteria,
        settings.google_cloud_project,
        feedback_notes=feedback_notes,
        example_urls=example_urls + pinned_urls,
        fetch_timeout=settings.fetch_timeout,
    )

    matches: list[models.ProductMatch] = []
    partial_matches: list[models.ProductMatch] = []

    for r in ranked:
        score = float(r.get("score", 0))
        m = models.ProductMatch(
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
        prev_urls = {m["url"] for m in last_run.get("matches", []) + last_run.get("partial_matches", [])}

    for m in matches + partial_matches:
        if m.url in carried_forward_urls:
            m.carried_over = True
        elif m.url not in prev_urls:
            m.is_new = True

    effective_config = models.SearchConfig(
        search_name=search_name,
        title=config.get("title", ""),
        active=config.get("active", True),
        owner_id=config.get("owner_id", "admin"),
        visibility=config.get("visibility", "public"),
        description=config.get("description"),
        criteria=criteria,
        preferred_shops=shops,
        feedback_notes=feedback_notes or None,
        avoid_shops=list(avoid_shops),
        example_urls=example_urls,
        pinned_finds=config.get("pinned_finds", []),
    )

    result = models.RunResult(
        search_name=search_name,
        run_date=str(date.today()),
        matches=matches,
        partial_matches=partial_matches,
        no_match=(not matches and not partial_matches),
        total_candidates=len(candidates),
        config_snapshot=effective_config,
    )

    csv_path = save_csv(result)
    print(f"  CSV: {csv_path}")

    if not dry_run:
        fc.save_run(search_name, result.run_date, result.model_dump())
        send_run_notification(result, settings)

    return result


def print_result(result: models.RunResult) -> None:
    print(f"\n=== {result.search_name} | {result.run_date} | {result.total_candidates} candidates ===")

    if result.no_match:
        print("  No matches today.")
        return

    if result.matches:
        print(f"\nMatches ({len(result.matches)}):")
        for m in result.matches:
            new_tag = " [NEW]" if m.is_new else " [CARRIED OVER]" if m.carried_over else ""
            print(f"  [{m.score:.0f}/10]{new_tag} {m.title or '(no title)'}")
            print(f"    {_link(m.url)}")
            if m.price:
                print(f"    Price: {m.price}")
            if m.matched:
                print(f"    OK: {', '.join(m.matched)}")
            if m.unmatched:
                print(f"    Missing: {', '.join(m.unmatched)}")

    if result.partial_matches:
        print(f"\nPartial matches ({len(result.partial_matches)}):")
        for m in result.partial_matches:
            new_tag = " [NEW]" if m.is_new else " [CARRIED OVER]" if m.carried_over else ""
            print(f"  [{m.score:.0f}/10]{new_tag} {m.title or '(no title)'}")
            print(f"    {_link(m.url)}")
            if m.unmatched:
                print(f"    Missing: {', '.join(m.unmatched)}")
