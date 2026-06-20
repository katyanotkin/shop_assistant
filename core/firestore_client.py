import hashlib
from urllib.parse import urlparse

from google.cloud import firestore

_db: firestore.Client | None = None


def get_db() -> firestore.Client:
    global _db
    if _db is None:
        _db = firestore.Client()
    return _db


def load_search_config(search_name: str) -> dict | None:
    doc = get_db().collection("shop_searches").document(search_name).get()
    return doc.to_dict() if doc.exists else None


def save_search_config(config: dict) -> None:
    get_db().collection("shop_searches").document(config["search_name"]).set(config)


def list_searches(active_only: bool = True) -> list[dict]:
    q = get_db().collection("shop_searches")
    if active_only:
        q = q.where(filter=firestore.FieldFilter("active", "==", True))
    return [d.to_dict() for d in q.stream()]


def load_last_run(search_name: str) -> dict | None:
    runs = (
        get_db()
        .collection("shop_results")
        .document(search_name)
        .collection("runs")
        .order_by("run_date", direction=firestore.Query.DESCENDING)
        .limit(1)
        .stream()
    )
    docs = list(runs)
    return docs[0].to_dict() if docs else None


def list_runs(search_name: str, limit: int = 30) -> list[str]:
    docs = (
        get_db()
        .collection("shop_results")
        .document(search_name)
        .collection("runs")
        .order_by("run_date", direction=firestore.Query.DESCENDING)
        .limit(limit)
        .stream()
    )
    return [d.id for d in docs]


def _decode_feedback(raw: dict) -> dict:
    """Convert {md5_hash: {url, text}} back to {url: text} for frontend consumption."""
    result = {}
    for v in raw.values():
        if isinstance(v, dict) and "url" in v:
            result[v["url"]] = v.get("text", "")
        # skip legacy malformed entries
    return result


def load_run(search_name: str, run_date: str) -> dict | None:
    doc = get_db().collection("shop_results").document(search_name).collection("runs").document(run_date).get()
    if not doc.exists:
        return None
    data = doc.to_dict()
    if data.get("feedback"):
        data["feedback"] = _decode_feedback(data["feedback"])
    return data


def save_run(search_name: str, run_date: str, result: dict) -> None:
    (get_db().collection("shop_results").document(search_name).collection("runs").document(run_date).set(result))


def _url_key(url: str) -> str:
    """Safe Firestore field name for a URL (URLs contain '/' which is invalid in field paths)."""
    return hashlib.md5(url.encode()).hexdigest()


def save_feedback(search_name: str, run_date: str, url: str, text: str) -> None:
    doc_ref = get_db().collection("shop_results").document(search_name).collection("runs").document(run_date)
    doc_ref.update({f"feedback.{_url_key(url)}": {"url": url, "text": text}})


def save_learned_feedback(search_name: str, feedback_notes: str, avoid_shops: list[str]) -> None:
    get_db().collection("shop_searches").document(search_name).update(
        {"feedback_notes": feedback_notes, "avoid_shops": avoid_shops}
    )


def load_feedback_entries(search_name: str, limit: int = 10) -> list[dict]:
    """Collect rated items across the last `limit` runs, with the Gemini context they were scored with."""
    runs = (
        get_db()
        .collection("shop_results")
        .document(search_name)
        .collection("runs")
        .order_by("run_date", direction=firestore.Query.DESCENDING)
        .limit(limit)
        .stream()
    )
    entries = []
    for doc in runs:
        data = doc.to_dict()
        raw_feedback = data.get("feedback") or {}
        if not raw_feedback:
            continue
        feedback = _decode_feedback(raw_feedback)
        items_by_url = {m["url"]: m for m in data.get("matches", []) + data.get("partial_matches", [])}
        for url, text in feedback.items():
            item = items_by_url.get(url, {})
            entries.append(
                {
                    "url": url,
                    "domain": urlparse(url).netloc.removeprefix("www."),
                    "title": item.get("title", ""),
                    "score": item.get("score"),
                    "matched": item.get("matched", []),
                    "unmatched": item.get("unmatched", []),
                    "feedback": text,
                }
            )
    return entries
