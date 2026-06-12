#!/usr/bin/env python3
"""
Shop Assistant entry point.

Usage:
  python run.py add searches/wax_coat.json   # save search config to Firestore
  python run.py list                          # list all saved searches
  python run.py run                           # run all active searches
  python run.py run --search wax_coat         # run one search
  python run.py run --search wax_coat --dry-run  # run without saving or notifying
"""

import argparse
import json
import sys

from core import firestore_client as fc
from core.runner import print_result, run_search
from core.settings import Settings


def cmd_add(args, _settings: Settings) -> None:
    with open(args.file) as f:
        config = json.load(f)
    if "search_name" not in config:
        print("ERROR: config must have 'search_name'", file=sys.stderr)
        sys.exit(1)
    fc.save_search_config(config)
    print(f"Saved: {config['search_name']}")


def cmd_list(_args, _settings: Settings) -> None:
    searches = fc.list_searches(active_only=False)
    if not searches:
        print("No searches found.")
        return
    for s in searches:
        status = "active" if s.get("active") else "inactive"
        print(f"  {s['search_name']}  [{status}]")


def cmd_run(args, settings: Settings) -> None:
    if args.search:
        names = [args.search]
    else:
        names = [s["search_name"] for s in fc.list_searches(active_only=True)]
    if not names:
        print("No active searches. Add one with: run.py add <file>")
        return
    for name in names:
        print(f"\nRunning: {name}")
        result = run_search(name, settings, dry_run=args.dry_run)
        print_result(result)


def main() -> None:
    parser = argparse.ArgumentParser(description="Shop Assistant")
    sub = parser.add_subparsers(dest="command", required=True)

    p_add = sub.add_parser("add", help="Add or update a search config from a JSON file")
    p_add.add_argument("file", help="Path to search config JSON")

    sub.add_parser("list", help="List all searches in Firestore")

    p_run = sub.add_parser("run", help="Run searches and report matches")
    p_run.add_argument("--search", help="Search name (default: all active)")
    p_run.add_argument("--dry-run", action="store_true", help="Don't save results or send notifications")

    args = parser.parse_args()
    # Settings (requires .env) only needed for run
    settings = Settings() if args.command == "run" else None

    dispatch = {"add": cmd_add, "list": cmd_list, "run": cmd_run}
    dispatch[args.command](args, settings)


if __name__ == "__main__":
    main()
