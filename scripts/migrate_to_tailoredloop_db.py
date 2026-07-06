#!/usr/bin/env python3
"""
One-time migration: copy TailoredLoop's data out of the project's (default)
Firestore database into its own named database ("tailoredloop"), since
(default) is shared with an unrelated app (verbboard) whose collections
(verbs, user_practice, analytics_*, etc.) — and even `users` docs, keyed by
Firebase UID instead of TailoredLoop's md5(email) — lived in the same
database (2026-07-05).

Copies:
  - shop_searches (all docs)
  - shop_results/{search_name}/runs/{run_date} (subcollections — the parent
    shop_results/{search_name} doc never actually exists in Firestore, so a
    plain top-level collection scan misses these; must be enumerated per
    known search_name)
  - users docs that have a `role` field (TailoredLoop's shape); verbboard's
    users docs are left untouched
  - product_feedback (all docs)

Does NOT delete anything from (default) — safe to re-run (idempotent, uses
.set() which overwrites), and leaves the old copies in place as a rollback
safety net until the new database is confirmed stable.

Run once, after creating the destination database:
    gcloud firestore databases create --database=tailoredloop --location=us-east1 --type=firestore-native
    python scripts/migrate_to_tailoredloop_db.py

Requires application-default credentials with Firestore read/write access:
    gcloud auth application-default login
"""

import os
import sys

from google.cloud import firestore

PROJECT = os.environ.get("GOOGLE_CLOUD_PROJECT", "knotmem26")
SOURCE_DATABASE = "(default)"
DEST_DATABASE = "tailoredloop"


def migrate() -> None:
    src = firestore.Client(project=PROJECT, database=SOURCE_DATABASE)
    dst = firestore.Client(project=PROJECT, database=DEST_DATABASE)

    search_names = [d.id for d in src.collection("shop_searches").stream()]
    print(f"shop_searches: {len(search_names)} docs")
    for search_name in search_names:
        doc = src.collection("shop_searches").document(search_name).get()
        dst.collection("shop_searches").document(search_name).set(doc.to_dict())
        print(f"  copied {search_name}")

    run_count = 0
    for search_name in search_names:
        runs = src.collection("shop_results").document(search_name).collection("runs").stream()
        for run_doc in runs:
            dst.collection("shop_results").document(search_name).collection("runs").document(run_doc.id).set(
                run_doc.to_dict()
            )
            run_count += 1
    print(f"shop_results runs: {run_count} docs")

    user_count = 0
    for doc in src.collection("users").stream():
        data = doc.to_dict()
        if "role" not in data:
            continue  # not TailoredLoop's shape (verbboard user doc) — skip
        dst.collection("users").document(doc.id).set(data)
        user_count += 1
        print(f"  copied user {doc.id} ({data.get('email')})")
    print(f"users: {user_count} docs")

    feedback_count = 0
    for doc in src.collection("product_feedback").stream():
        dst.collection("product_feedback").document(doc.id).set(doc.to_dict())
        feedback_count += 1
    print(f"product_feedback: {feedback_count} docs")


if __name__ == "__main__":
    if "--yes" not in sys.argv:
        print(f"This copies TailoredLoop data from '{SOURCE_DATABASE}' to '{DEST_DATABASE}' in project '{PROJECT}'.")
        print("Re-run with --yes to proceed.")
        sys.exit(1)
    migrate()
