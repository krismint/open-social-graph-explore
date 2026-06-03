#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from adapters.registry import DEFAULT_PLATFORM_ID, supported_platform_ids  # noqa: E402
from core.db import DEFAULT_DB_PATH  # noqa: E402
from core.platform_expansion_runner import DEFAULT_GRAPH, prepare_platform_expansion, run_prepared_platform_expansion  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Expand one platform account through the OSGE platform registry.")
    parser.add_argument("--platform", default=DEFAULT_PLATFORM_ID, choices=supported_platform_ids(), help="Registered platform id")
    parser.add_argument("--account", required=True, help="Platform account id, profile URL, or share URL")
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH), help="OSGE overlay SQLite database path")
    parser.add_argument("--graph-output", default=str(DEFAULT_GRAPH), help="Rendered graph HTML path")
    parser.add_argument("--max-notes", type=int, default=5)
    parser.add_argument("--max-comments", type=int, default=10)
    parser.add_argument("--get-sub-comments", action="store_true")
    parser.add_argument("--force", action="store_true", help="Run even if the account was already crawled")
    parser.add_argument("--dry-run", action="store_true", help="Show what would happen without starting the OSGE adapter")
    args = parser.parse_args()

    try:
        prepared = prepare_platform_expansion(
            args.platform,
            account=args.account,
            db_path=args.db,
            graph_output=args.graph_output,
            max_notes=args.max_notes,
            max_comments=args.max_comments,
            get_sub_comments=args.get_sub_comments,
            force=args.force,
            requested_by="cli",
            create_job=not args.dry_run,
        )
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc

    print(f"Platform: {prepared.platform}")
    print(f"Target: {prepared.target_id}")
    print(f"Profile URL: {prepared.profile_url}")
    print(f"OSGE DB: {prepared.db_path}")
    print(f"Incremental plan: {prepared.incremental_plan}")

    if prepared.skipped:
        print(f"Skipped: {prepared.reason}")
        return
    if args.dry_run:
        print("Dry run only; no crawl job was created.")
        return

    result = run_prepared_platform_expansion(prepared)
    print(f"Completed job: {result['job_id']}")
    print(f"Source: {result['source']}")
    print(f"Edges: {result['edges']}")
    print(f"Graph: {result['graph']}")
    print(f"Minimal sync: {result['minimal']}")
    print(f"Rendered: {result['rendered']}")
    print(f"OSGE counts: notes/comments -> {result['notes_after']}/{result['comments_after']}")
    print(f"Log: {result['log_path']}")


if __name__ == "__main__":
    main()
