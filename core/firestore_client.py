import hashlib
import os
import uuid
from urllib.parse import urlparse

from google.api_core.exceptions import NotFound
from google.cloud import firestore

from core import models
from core.slug import slugify

_db: firestore.Client | None = None
_MAX_SLUG_ATTEMPTS = 50
_RESERVED_SEARCH_NAMES = {"admin", "privacy", "terms", "feedback", "manifest.json", "static", "api", "auth"}

# TailoredLoop has its own named Firestore database, separate from the
# project's (default) database (which other apps in this GCP project use) —
# see FIRESTORE_DATABASE in .env.sample.
_DEFAULT_DATABASE = "tailoredloop"


def get_db() -> firestore.Client:
    global _db
    if _db is None:
        _db = firestore.Client(database=os.environ.get("FIRESTORE_DATABASE", _DEFAULT_DATABASE))
    return _db


def load_search_config(search_name: str) -> dict | None:
    doc = get_db().collection("shop_searches").document(search_name).get()
    return doc.to_dict() if doc.exists else None


def save_search_config(config: dict) -> None:
    config.setdefault("owner_id", "admin")
    config.setdefault("visibility", "public")
    if not config.get("title"):
        config["title"] = config["search_name"].replace("_", " ").title()
    get_db().collection("shop_searches").document(config["search_name"]).set(config)


def generate_unique_search_name(title: str, max_length: int = 64) -> str:
    base = slugify(title, max_length)
    candidate = base
    for n in range(2, _MAX_SLUG_ATTEMPTS + 2):
        if candidate not in _RESERVED_SEARCH_NAMES and load_search_config(candidate) is None:
            return candidate
        suffix = f"_{n}"
        candidate = f"{base[: max_length - len(suffix)]}{suffix}"
    return f"{base[:57]}_{uuid.uuid4().hex[:6]}"


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
    save_feedback_batch(search_name, run_date, [(url, text)])


def save_feedback_batch(search_name: str, run_date: str, items: list[tuple[str, str]]) -> None:
    doc_ref = get_db().collection("shop_results").document(search_name).collection("runs").document(run_date)
    updates = {f"feedback.{_url_key(url)}": {"url": url, "text": text} for url, text in items}
    try:
        doc_ref.update(updates)
    except NotFound:
        doc_ref.set({"feedback": {_url_key(url): {"url": url, "text": text} for url, text in items}}, merge=True)


def pin_results(search_name: str, finds: list[dict]) -> None:
    """Pin one or more finds in a single load/save round trip (avoids N Firestore
    writes when a feedback batch marks several results "Perfect match" at once)."""
    if not finds:
        return
    config = load_search_config(search_name) or {}
    existing = []
    for f in config.get("pinned_finds", []):
        try:
            existing.append(models.PinnedFind(**f))
        except Exception:
            continue  # skip a malformed/legacy entry rather than fail the whole save
    for find in finds:
        existing = models.add_pinned_find(existing, models.PinnedFind(**find))
    config["pinned_finds"] = [f.model_dump() for f in existing]
    save_search_config(config)


def pin_result(search_name: str, find: dict) -> None:
    pin_results(search_name, [find])


def unpin_result(search_name: str, url: str) -> None:
    config = load_search_config(search_name) or {}
    config["pinned_finds"] = [f for f in config.get("pinned_finds", []) if f.get("url") != url]
    save_search_config(config)


def get_user(email: str) -> dict | None:
    from core.auth import user_doc_id

    doc = get_db().collection("users").document(user_doc_id(email)).get()
    return doc.to_dict() if doc.exists else None


def list_users() -> list[dict]:
    docs = get_db().collection("users").stream()
    return [d.to_dict() | {"uid": d.id} for d in docs]


def update_user_role(uid: str, role: str) -> None:
    try:
        get_db().collection("users").document(uid).update({"role": role})
    except NotFound:
        raise ValueError(f"User {uid} not found")


def list_user_searches(owner_id: str) -> list[dict]:
    return [
        d.to_dict()
        for d in get_db()
        .collection("shop_searches")
        .where(filter=firestore.FieldFilter("owner_id", "==", owner_id))
        .limit(1)
        .stream()
    ]


def update_search_visibility(search_name: str, visibility: str) -> None:
    get_db().collection("shop_searches").document(search_name).update({"visibility": visibility})


def delete_search_config(search_name: str) -> None:
    get_db().collection("shop_searches").document(search_name).delete()


def upsert_user(email: str, display_name: str, photo_url: str, bootstrap_admin_email: str | None = None) -> dict:
    from datetime import datetime, timezone

    from core.auth import user_doc_id

    doc_id = user_doc_id(email)
    ref = get_db().collection("users").document(doc_id)
    doc = ref.get()

    if doc.exists:
        data = doc.to_dict()
        updates: dict = {"display_name": display_name, "photo_url": photo_url}
        if bootstrap_admin_email and email.lower() == bootstrap_admin_email.lower() and data.get("role") == "free":
            updates["role"] = "admin"
        ref.update(updates)
        data.update(updates)
        return data

    role = "admin" if (bootstrap_admin_email and email.lower() == bootstrap_admin_email.lower()) else "free"
    data = {
        "email": email,
        "display_name": display_name,
        "photo_url": photo_url,
        "role": role,
        "created_at": datetime.now(timezone.utc),
    }
    ref.set(data)
    return data


def delete_user(email: str) -> None:
    from core.auth import user_doc_id

    get_db().collection("users").document(user_doc_id(email)).delete()


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
            if url.startswith("_"):
                continue
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


def save_product_feedback(text: str, owner_id: str | None, owner_name: str | None) -> None:
    from datetime import datetime, timezone

    get_db().collection("product_feedback").add(
        {
            "text": text,
            "owner_id": owner_id,  # the user's email, matching owner_id semantics elsewhere in this codebase
            "owner_name": owner_name,
            "created_at": datetime.now(timezone.utc),
        }
    )
