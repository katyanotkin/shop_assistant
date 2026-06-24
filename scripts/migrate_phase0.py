#!/usr/bin/env python3
"""
Phase 0 migration: stamp owner_id="admin" and visibility="common" on every
existing shop_searches document that is missing those fields.

Run once before deploying Phase 1 auth:
    python scripts/migrate_phase0.py

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
        patch: dict = {}
        if "owner_id" not in data:
            patch["owner_id"] = "admin"
        if "visibility" not in data:
            patch["visibility"] = "common"

        if patch:
            doc.reference.update(patch)
            print(f"  ✓ {doc.id}: set {patch}")
            updated += 1
        else:
            print(f"  – {doc.id}: already stamped, skipped")
            skipped += 1

    print(f"\nDone. {updated} updated, {skipped} skipped.")


if __name__ == "__main__":
    sys.exit(main())
