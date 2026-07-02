#!/usr/bin/env python3
"""
Title backfill: stamp a human-readable `title` on every existing shop_searches
document that is missing one, derived from search_name (underscores -> spaces,
title-cased). `title` became a required SearchConfig field alongside the
search_name/slug split (2026-07-01).

Run once before deploying that change:
    python scripts/migrate_add_titles.py

Requires application-default credentials with Firestore read/write access:
    gcloud auth application-default login
"""

import os
import sys

from google.cloud import firestore


def main() -> None:
    project = os.environ.get("GOOGLE_CLOUD_PROJECT")
    db = firestore.Client(project=project)
    col = db.collection("shop_searches")
    docs = list(col.stream())

    if not docs:
        print("No documents found in shop_searches — nothing to migrate.")
        return

    print(f"Found {len(docs)} searches.")
    updated = skipped = 0

    for doc in docs:
        data = doc.to_dict() or {}
        if not data.get("title"):
            title = data["search_name"].replace("_", " ").title()
            doc.reference.update({"title": title})
            print(f"  ✓ {doc.id}: set title={title!r}")
            updated += 1
        else:
            print(f"  – {doc.id}: already has title, skipped")
            skipped += 1

    print(f"\nDone. {updated} updated, {skipped} skipped.")


if __name__ == "__main__":
    sys.exit(main())
