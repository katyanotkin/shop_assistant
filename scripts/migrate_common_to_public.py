#!/usr/bin/env python3
"""
Migration: rename visibility="common" → visibility="public" on all shop_searches documents.

Run once after deploying the code change that renames the value:
    python scripts/migrate_common_to_public.py

Requires application-default credentials with Firestore read/write access:
    gcloud auth application-default login
"""

import os
import sys

from google.cloud import firestore


def main() -> None:
    project = os.environ.get("GOOGLE_CLOUD_PROJECT")
    db = firestore.Client(project=project)
    docs = list(db.collection("shop_searches").stream())

    if not docs:
        print("No documents found in shop_searches — nothing to migrate.")
        return

    print(f"Found {len(docs)} searches.")
    updated = skipped = 0

    for doc in docs:
        data = doc.to_dict() or {}
        if data.get("visibility") == "common":
            doc.reference.update({"visibility": "public"})
            print(f"  ✓ {doc.id}: common → public")
            updated += 1
        else:
            print(f"  – {doc.id}: visibility={data.get('visibility')!r}, skipped")
            skipped += 1

    print(f"\nDone. {updated} updated, {skipped} skipped.")


if __name__ == "__main__":
    sys.exit(main())
