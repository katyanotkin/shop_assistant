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


def save_run(search_name: str, run_date: str, result: dict) -> None:
    (
        get_db()
        .collection("shop_results")
        .document(search_name)
        .collection("runs")
        .document(run_date)
        .set(result)
    )
