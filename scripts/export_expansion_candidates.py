#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from adapters.registry import DEFAULT_PLATFORM_ID, supported_platform_ids
from core.db import DEFAULT_DB_PATH
from core.expansion import expansion_candidates, format_candidates, write_candidate_urls


DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "processed" / "expansion_candidates.txt"


def main() -> None:
    parser = argparse.ArgumentParser(description="Export platform accounts worth expanding into second-hop crawls.")
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH), help="OSGE SQLite database path")
    parser.add_argument("--platform", default=DEFAULT_PLATFORM_ID, choices=supported_platform_ids())
    parser.add_argument("--target-account", default="", help="Optional target account_id, e.g. platform:<user_id>")
    parser.add_argument("--limit", type=int, default=20, help="Maximum candidates")
    parser.add_argument("--min-interactions", type=int, default=1, help="Minimum interactions with the current graph")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="Output text file of profile URLs")
    args = parser.parse_args()

    candidates = expansion_candidates(
        args.platform,
        db_path=args.db,
        target_account_id=args.target_account,
        limit=args.limit,
        min_interactions=args.min_interactions,
    )
    write_candidate_urls(candidates, args.output)
    print(format_candidates(candidates, args.platform))
    print(f"\nWrote {len(candidates)} profile URL(s) to {args.output}")


if __name__ == "__main__":
    main()
