#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from core.db import DEFAULT_DB_PATH
from core.reporting import format_report, target_report


def main() -> None:
    parser = argparse.ArgumentParser(description="Print a one-hop relationship report for an account.")
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH), help="SQLite database path")
    parser.add_argument("--account", required=True, help="Account id, platform:user id, or username")
    parser.add_argument("--limit", type=int, default=10, help="Maximum relations and evidence rows")
    args = parser.parse_args()

    try:
        report = target_report(args.db, args.account, args.limit)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    print(format_report(report))


if __name__ == "__main__":
    main()
