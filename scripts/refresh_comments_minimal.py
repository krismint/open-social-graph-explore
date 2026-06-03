from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from adapters.minimal_platform import MinimalAdapterConfig
from adapters.registry import get_platform, supported_platform_ids
from core.db import DEFAULT_DB_PATH, connect, initialize_database
from core.minicrawler import known_comment_ids, sync_comment_records


def main() -> None:
    parser = argparse.ArgumentParser(description="Refresh one post's comments through OSGE minimal platform adapter.")
    parser.add_argument("--platform", required=True, choices=supported_platform_ids())
    parser.add_argument("--post-id", required=True, help="Platform post id.")
    parser.add_argument("--comment-context", action="append", default=[], metavar="KEY=VALUE", help="Optional platform comment context; repeat for multiple values.")
    parser.add_argument("--db-path", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--max-comments", type=int, default=10)
    parser.add_argument("--get-sub-comments", action="store_true")
    parser.add_argument("--crawl-interval", type=float, default=1.0)
    args = parser.parse_args()

    initialize_database(args.db_path)
    platform = get_platform(args.platform)
    comment_context = _parse_context_args(args.comment_context)
    if platform.requires_comment_context and not comment_context:
        comment_context = _comment_context_from_osge_post(args.db_path, platform.platform_id, args.post_id)
    target_account_id = _post_author_account_id(args.db_path, platform.platform_id, args.post_id)
    existing = known_comment_ids(args.db_path, platform=platform.platform_id, platform_post_ids=[args.post_id])
    adapter_config = MinimalAdapterConfig(
        crawl_interval=args.crawl_interval,
    )
    adapter = platform.create_adapter(adapter_config)
    result = asyncio.run(
        adapter.fetch_comments(
            args.post_id,
            args.max_comments,
            platform_context=comment_context,
            get_sub_comments=args.get_sub_comments,
            known_comment_ids=existing,
        )
    )
    written = sync_comment_records(
        args.db_path,
        platform.platform_id,
        result.comments,
        target_account_id=target_account_id,
    )
    print(
        "minimal_comment_refresh "
        f"platform={platform.platform_id} post_id={args.post_id} "
        f"known_before={len(existing)} fetched={len(result.comments)} "
        f"written_interactions={written} pages_seen={result.pages_seen} "
        f"stopped_on_known={result.stopped_on_known}"
    )


def _post_author_account_id(db_path: Path, platform: str, platform_post_id: str) -> str:
    with connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT author_account_id
            FROM posts
            WHERE platform = ?
              AND platform_post_id = ?
            LIMIT 1
            """,
            (platform, platform_post_id),
        ).fetchone()
    return str(row["author_account_id"]) if row else ""


def _parse_context_args(values: list[str]) -> dict[str, str]:
    context: dict[str, str] = {}
    for raw in values:
        if "=" not in raw:
            raise SystemExit(f"Invalid --comment-context value: {raw}. Expected KEY=VALUE.")
        key, value = raw.split("=", 1)
        key = key.strip()
        if not key:
            raise SystemExit(f"Invalid --comment-context value: {raw}. Key cannot be empty.")
        context[key] = value
    return context


def _comment_context_from_osge_post(db_path: Path, platform: str, post_id: str) -> dict[str, str]:
    with connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT url
            FROM posts
            WHERE platform = ?
              AND platform_post_id = ?
            LIMIT 1
            """,
            (platform, post_id),
        ).fetchone()
    if not row:
        return {}
    definition = get_platform(platform)
    return definition.context_from_url(str(row["url"] or ""))


if __name__ == "__main__":
    main()
