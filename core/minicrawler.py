from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

from adapters.base import AccountRecord, CommentRecord, PostRecord
from adapters.registry import DEFAULT_PLATFORM_ID, get_platform
from core.avatar_cache import cache_avatar_url
from core.db import DEFAULT_DB_PATH, connect, initialize_database
from core.normalizer import account_id, post_id


AVATAR_RETRY_AFTER = timedelta(hours=24)


@dataclass(frozen=True)
class IncrementalCrawlPlan:
    platform: str
    target_account_id: str
    should_get_comments: bool
    known_posts: int
    planned_posts: int
    posts_with_enough_comments: int
    max_comments: int
    reason: str

    def as_dict(self) -> dict[str, int | str | bool]:
        return {
            "platform": self.platform,
            "target_account_id": self.target_account_id,
            "should_get_comments": self.should_get_comments,
            "known_posts": self.known_posts,
            "planned_posts": self.planned_posts,
            "posts_with_enough_comments": self.posts_with_enough_comments,
            "max_comments": self.max_comments,
            "reason": self.reason,
        }


def build_incremental_crawl_plan(
    overlay_db_path: Path | str = DEFAULT_DB_PATH,
    platform: str = DEFAULT_PLATFORM_ID,
    target_account_id: str = "",
    max_notes: int = 5,
    max_comments: int = 10,
    get_sub_comments: bool = False,
) -> IncrementalCrawlPlan:
    initialize_database(overlay_db_path)
    if not target_account_id:
        return IncrementalCrawlPlan(platform, target_account_id, True, 0, 0, 0, max_comments, "no target account id")
    with connect(overlay_db_path) as conn:
        rows = conn.execute(
            """
            SELECT p.post_id, p.platform_post_id, COALESCE(s.known_comments, 0) AS known_comments
            FROM posts p
            LEFT JOIN minimal_crawl_state s
              ON s.platform = p.platform
             AND s.scope_type = 'post'
             AND s.scope_id = p.post_id
            WHERE p.platform = ?
              AND p.author_account_id = ?
            ORDER BY COALESCE(p.created_at, '') DESC, p.platform_post_id DESC
            LIMIT ?
            """,
            (platform, target_account_id, max_notes),
        ).fetchall()
    known_posts = len(rows)
    if not rows:
        return IncrementalCrawlPlan(platform, target_account_id, True, 0, 0, 0, max_comments, "no known posts for target")
    enough = sum(1 for row in rows if int(row["known_comments"] or 0) >= max_comments)
    if enough == len(rows) and not get_sub_comments:
        return IncrementalCrawlPlan(
            platform,
            target_account_id,
            True,
            known_posts,
            len(rows),
            enough,
            max_comments,
            "known first-level comments satisfy budget; run lightweight incremental check",
        )
    if enough == len(rows) and get_sub_comments:
        return IncrementalCrawlPlan(
            platform,
            target_account_id,
            True,
            known_posts,
            len(rows),
            enough,
            max_comments,
            "sub-comments requested; keep comment crawl enabled",
        )
    return IncrementalCrawlPlan(
        platform,
        target_account_id,
        True,
        known_posts,
        len(rows),
        enough,
        max_comments,
        "some planned posts are below comment budget",
    )


def known_comment_ids(
    overlay_db_path: Path | str = DEFAULT_DB_PATH,
    platform: str = DEFAULT_PLATFORM_ID,
    platform_post_ids: Iterable[str] | None = None,
) -> set[str]:
    initialize_database(overlay_db_path)
    with connect(overlay_db_path) as conn:
        params: list[object] = [platform]
        post_filter = ""
        if platform_post_ids:
            post_ids = [post_id(platform, str(value)) for value in platform_post_ids if value]
            if post_ids:
                placeholders = ",".join("?" for _ in post_ids)
                post_filter = f" AND post_id IN ({placeholders})"
                params.extend(post_ids)
        rows = conn.execute(
            f"""
            SELECT DISTINCT source_record_id
            FROM interactions
            WHERE platform = ?
              AND source_record_id IS NOT NULL
              AND source_record_id != ''
              AND interaction_type IN ('comment', 'reply')
              {post_filter}
            """,
            params,
        ).fetchall()
    return {str(row["source_record_id"]) for row in rows}


def write_known_comment_ids_file(
    overlay_db_path: Path | str,
    platform: str,
    output_path: Path | str,
) -> int:
    ids = sorted(known_comment_ids(overlay_db_path, platform=platform))
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(ids) + ("\n" if ids else ""), encoding="utf-8")
    return len(ids)


def sync_comment_records(
    overlay_db_path: Path | str,
    platform: str,
    comments: Iterable[CommentRecord],
    target_account_id: str = "",
    crawl_job_id: str = "",
) -> int:
    records = [comment for comment in comments if comment.platform == platform and comment.comment_id]
    if not records:
        return 0
    initialize_database(overlay_db_path)
    with connect(overlay_db_path) as conn:
        post_authors = _post_authors_by_platform_post_id(conn, platform)
        comments_by_id = {record.comment_id: record for record in records}
        written = 0
        touched_posts: set[str] = set()
        for record in records:
            post_author = post_authors.get(record.platform_post_id, "")
            if not post_author or not record.author_platform_user_id:
                continue
            _upsert_account(
                conn,
                platform=platform,
                platform_user_id=record.author_platform_user_id,
                username=_first_non_empty(record.author_username, record.author_platform_user_id),
                nickname=record.author_nickname,
                avatar_url=record.author_avatar_url,
                source=f"adapter:{platform}:comment",
                crawl_level=1,
            )
            created_at = _timestamp_to_iso(record.created_at)
            _upsert_interaction(
                conn,
                platform=platform,
                interaction_id=f"{platform}:comment:{record.comment_id}:author",
                source_platform_user_id=record.author_platform_user_id,
                target_platform_user_id=post_author,
                platform_post_id=record.platform_post_id,
                interaction_type="comment",
                source_record_id=record.comment_id,
                parent_source_record_id=record.parent_comment_id,
                content=record.content,
                created_at=created_at,
                like_count=record.like_count,
                crawl_job_id=crawl_job_id,
                source=f"adapter:{platform}:comment",
            )
            written += 1
            parent_id = record.parent_comment_id
            parent = comments_by_id.get(parent_id)
            if parent and parent.author_platform_user_id and parent.author_platform_user_id != record.author_platform_user_id:
                _upsert_interaction(
                    conn,
                    platform=platform,
                    interaction_id=f"{platform}:comment:{record.comment_id}:parent:{parent_id}",
                    source_platform_user_id=record.author_platform_user_id,
                    target_platform_user_id=parent.author_platform_user_id,
                    platform_post_id=record.platform_post_id,
                    interaction_type="reply",
                    source_record_id=record.comment_id,
                    parent_source_record_id=parent_id,
                    content=record.content,
                    created_at=created_at,
                    like_count=record.like_count,
                    crawl_job_id=crawl_job_id,
                    source=f"adapter:{platform}:reply",
                )
                written += 1
            touched_posts.add(record.platform_post_id)
        _refresh_minimal_state_for_posts(conn, platform, touched_posts, target_account_id)
    return written


def sync_profile_post_records(
    overlay_db_path: Path | str,
    platform: str,
    profile: AccountRecord,
    posts: Iterable[PostRecord],
    target_account_id: str = "",
) -> dict[str, int]:
    records = [post for post in posts if post.platform == platform and post.platform_post_id]
    initialize_database(overlay_db_path)
    with connect(overlay_db_path) as conn:
        if profile.platform == platform and profile.platform_user_id:
            _upsert_account(
                conn,
                platform=platform,
                platform_user_id=profile.platform_user_id,
                username=_first_non_empty(profile.username, profile.platform_user_id),
                nickname=profile.nickname,
                avatar_url=profile.avatar_url,
                bio=profile.bio,
                source=f"adapter:{platform}:profile",
                crawl_level=0,
            )
            conn.execute(
                """
                UPDATE accounts
                SET is_target = 1,
                    profile_url = COALESCE(NULLIF(?, ''), profile_url),
                    location = COALESCE(NULLIF(?, ''), location)
                WHERE account_id = ?
                """,
                (profile.profile_url, profile.location, account_id(platform, profile.platform_user_id)),
            )
        valid_posts: list[PostRecord] = []
        for record in records:
            if not record.author_platform_user_id:
                continue
            valid_posts.append(record)
            if record.author_platform_user_id != profile.platform_user_id:
                _upsert_account(
                    conn,
                    platform=platform,
                    platform_user_id=record.author_platform_user_id,
                    username=record.author_platform_user_id,
                    nickname="",
                    avatar_url="",
                    source=f"adapter:{platform}:post_author",
                    crawl_level=0,
                )
            _upsert_post(
                conn,
                platform=platform,
                platform_post_id=record.platform_post_id,
                author_platform_user_id=record.author_platform_user_id,
                content=record.content,
                url=record.url,
                created_at=record.created_at,
                like_count=record.like_count,
                comment_count=record.comment_count,
                repost_count=record.repost_count,
                source=f"adapter:{platform}:post",
            )
        _refresh_minimal_state_for_posts(conn, platform, {record.platform_post_id for record in valid_posts}, target_account_id)
    return {"accounts": 1 if profile.platform_user_id else 0, "posts": len(valid_posts)}


def _upsert_account(
    conn: sqlite3.Connection,
    platform: str,
    platform_user_id: str,
    username: str,
    nickname: str,
    avatar_url: str,
    source: str,
    crawl_level: int,
    bio: str = "",
) -> None:
    acc_id = account_id(platform, platform_user_id)
    profile_url = _profile_url(platform, platform_user_id)
    avatar_state = _cache_avatar_for_minimal_account(conn, acc_id, platform, avatar_url)
    conn.execute(
        """
        INSERT INTO accounts (
            account_id, platform, platform_user_id, username, nickname,
            profile_url, avatar_url, avatar_local_path, avatar_cached_at,
            avatar_cache_checked_at, avatar_cache_error, bio, is_target,
            crawl_level, first_seen, last_seen, source
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, ?)
        ON CONFLICT(account_id) DO UPDATE SET
            username=COALESCE(NULLIF(excluded.username, ''), accounts.username),
            nickname=COALESCE(NULLIF(excluded.nickname, ''), accounts.nickname),
            profile_url=COALESCE(NULLIF(excluded.profile_url, ''), accounts.profile_url),
            avatar_url=COALESCE(NULLIF(excluded.avatar_url, ''), accounts.avatar_url),
            avatar_local_path=COALESCE(NULLIF(excluded.avatar_local_path, ''), accounts.avatar_local_path),
            avatar_cached_at=COALESCE(NULLIF(excluded.avatar_cached_at, ''), accounts.avatar_cached_at),
            avatar_cache_checked_at=COALESCE(NULLIF(excluded.avatar_cache_checked_at, ''), accounts.avatar_cache_checked_at),
            avatar_cache_error=excluded.avatar_cache_error,
            bio=COALESCE(NULLIF(excluded.bio, ''), accounts.bio),
            crawl_level=MIN(accounts.crawl_level, excluded.crawl_level),
            last_seen=CURRENT_TIMESTAMP,
            source=excluded.source
        """,
        (
            acc_id,
            platform,
            platform_user_id,
            username,
            nickname,
            profile_url,
            avatar_url,
            avatar_state["local_path"],
            avatar_state["cached_at"],
            avatar_state["checked_at"],
            avatar_state["error"],
            bio,
            crawl_level,
            source,
        ),
    )


def _cache_avatar_for_minimal_account(
    conn: sqlite3.Connection,
    account_id_value: str,
    platform: str,
    avatar_url: str,
) -> dict[str, str]:
    url = avatar_url.strip()
    state = {
        "local_path": "",
        "cached_at": "",
        "checked_at": "",
        "error": "",
    }
    if not url:
        return state

    existing = conn.execute(
        """
        SELECT avatar_url, avatar_local_path, avatar_cached_at,
               avatar_cache_checked_at, avatar_cache_error
        FROM accounts
        WHERE account_id = ?
        """,
        (account_id_value,),
    ).fetchone()
    if existing and existing["avatar_url"] == url:
        local_path = str(existing["avatar_local_path"] or "")
        if local_path and Path(local_path).exists():
            return {
                "local_path": local_path,
                "cached_at": str(existing["avatar_cached_at"] or ""),
                "checked_at": str(existing["avatar_cache_checked_at"] or ""),
                "error": str(existing["avatar_cache_error"] or ""),
            }
        if existing["avatar_cache_error"] and not _avatar_retry_due(str(existing["avatar_cache_checked_at"] or "")):
            return {
                "local_path": "",
                "cached_at": "",
                "checked_at": str(existing["avatar_cache_checked_at"] or ""),
                "error": str(existing["avatar_cache_error"] or ""),
            }

    checked_at = datetime.now(timezone.utc).isoformat()
    result = cache_avatar_url(url, platform=platform)
    state["local_path"] = result.local_path
    state["checked_at"] = checked_at
    state["error"] = result.error
    if result.local_path:
        state["cached_at"] = checked_at
    elif existing and existing["avatar_url"] == url and existing["avatar_local_path"]:
        local_path = str(existing["avatar_local_path"] or "")
        if local_path and Path(local_path).exists():
            state["local_path"] = local_path
            state["cached_at"] = str(existing["avatar_cached_at"] or "")
    return state


def _avatar_retry_due(checked_at: str) -> bool:
    if not checked_at:
        return True
    try:
        last_checked = datetime.fromisoformat(checked_at)
    except ValueError:
        return True
    if last_checked.tzinfo is None:
        last_checked = last_checked.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - last_checked >= AVATAR_RETRY_AFTER


def _upsert_post(
    conn: sqlite3.Connection,
    platform: str,
    platform_post_id: str,
    author_platform_user_id: str,
    content: str,
    url: str,
    created_at: str,
    like_count: int,
    comment_count: int,
    repost_count: int,
    source: str,
) -> None:
    if not platform_post_id or not author_platform_user_id:
        return
    conn.execute(
        """
        INSERT INTO posts (
            post_id, platform, platform_post_id, author_account_id, content,
            url, created_at, like_count, comment_count, repost_count, source
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(post_id) DO UPDATE SET
            content=COALESCE(NULLIF(excluded.content, ''), posts.content),
            url=COALESCE(NULLIF(excluded.url, ''), posts.url),
            created_at=COALESCE(NULLIF(excluded.created_at, ''), posts.created_at),
            like_count=excluded.like_count,
            comment_count=excluded.comment_count,
            repost_count=excluded.repost_count,
            source=excluded.source
        """,
        (
            post_id(platform, platform_post_id),
            platform,
            platform_post_id,
            account_id(platform, author_platform_user_id),
            content,
            url,
            created_at,
            like_count,
            comment_count,
            repost_count,
            source,
        ),
    )


def _upsert_interaction(
    conn: sqlite3.Connection,
    platform: str,
    interaction_id: str,
    source_platform_user_id: str,
    target_platform_user_id: str,
    platform_post_id: str,
    interaction_type: str,
    source_record_id: str,
    parent_source_record_id: str,
    content: str,
    created_at: str,
    like_count: int,
    crawl_job_id: str,
    source: str,
) -> None:
    parent_interaction_id = ""
    if parent_source_record_id and parent_source_record_id != "0":
        parent_interaction_id = f"{platform}:comment:{parent_source_record_id}:author"
    conn.execute(
        """
        INSERT INTO interactions (
            interaction_id, platform, source_account_id, target_account_id,
            post_id, interaction_type, source_record_id, parent_interaction_id,
            parent_source_record_id, content, created_at, first_seen, last_seen,
            like_count, weight_raw, crawl_job_id, deleted_at, source
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, ?, 1, ?, NULL, ?)
        ON CONFLICT(interaction_id) DO UPDATE SET
            source_record_id=COALESCE(NULLIF(excluded.source_record_id, ''), interactions.source_record_id),
            content=COALESCE(NULLIF(excluded.content, ''), interactions.content),
            created_at=COALESCE(NULLIF(excluded.created_at, ''), interactions.created_at),
            parent_interaction_id=COALESCE(NULLIF(excluded.parent_interaction_id, ''), interactions.parent_interaction_id),
            parent_source_record_id=COALESCE(NULLIF(excluded.parent_source_record_id, ''), interactions.parent_source_record_id),
            like_count=excluded.like_count,
            last_seen=CURRENT_TIMESTAMP,
            crawl_job_id=excluded.crawl_job_id,
            deleted_at=NULL,
            source=excluded.source
        """,
        (
            interaction_id,
            platform,
            account_id(platform, source_platform_user_id),
            account_id(platform, target_platform_user_id),
            post_id(platform, platform_post_id),
            interaction_type,
            source_record_id,
            parent_interaction_id,
            parent_source_record_id,
            content,
            created_at,
            like_count,
            crawl_job_id,
            source,
        ),
    )


def _upsert_state(
    conn: sqlite3.Connection,
    platform: str,
    scope_type: str,
    scope_id: str,
    known_posts: int,
    known_comments_count: int,
    newest_item_at: str,
) -> None:
    conn.execute(
        """
        INSERT INTO minimal_crawl_state (
            platform, scope_type, scope_id, known_posts, known_comments,
            newest_item_at, last_checked_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        ON CONFLICT(platform, scope_type, scope_id) DO UPDATE SET
            known_posts=excluded.known_posts,
            known_comments=excluded.known_comments,
            newest_item_at=COALESCE(NULLIF(excluded.newest_item_at, ''), minimal_crawl_state.newest_item_at),
            last_checked_at=CURRENT_TIMESTAMP,
            updated_at=CURRENT_TIMESTAMP
        """,
        (platform, scope_type, scope_id, known_posts, known_comments_count, newest_item_at),
    )


def _post_authors_by_platform_post_id(conn: sqlite3.Connection, platform: str) -> dict[str, str]:
    rows = conn.execute(
        """
        SELECT p.platform_post_id, a.platform_user_id AS author_platform_user_id
        FROM posts p
        JOIN accounts a ON a.account_id = p.author_account_id
        WHERE p.platform = ?
        """,
        (platform,),
    ).fetchall()
    return {_clean(row["platform_post_id"]): _clean(row["author_platform_user_id"]) for row in rows}


def _refresh_minimal_state_for_posts(
    conn: sqlite3.Connection,
    platform: str,
    platform_post_ids: set[str],
    target_account_id: str,
) -> None:
    for platform_post_id in platform_post_ids:
        pid = post_id(platform, platform_post_id)
        row = conn.execute(
            """
            SELECT COUNT(DISTINCT source_record_id) AS known_comments,
                   MAX(created_at) AS newest_item_at
            FROM interactions
            WHERE platform = ?
              AND post_id = ?
              AND source_record_id IS NOT NULL
              AND source_record_id != ''
              AND interaction_type IN ('comment', 'reply')
            """,
            (platform, pid),
        ).fetchone()
        _upsert_state(
            conn,
            platform,
            "post",
            pid,
            1,
            int(row["known_comments"] or 0),
            _clean(row["newest_item_at"]),
        )
    if not target_account_id:
        return
    row = conn.execute(
        """
        SELECT COUNT(DISTINCT p.post_id) AS known_posts,
               COUNT(DISTINCT i.source_record_id) AS known_comments,
               MAX(i.created_at) AS newest_item_at
        FROM posts p
        LEFT JOIN interactions i
          ON i.platform = p.platform
         AND i.post_id = p.post_id
         AND i.source_record_id IS NOT NULL
         AND i.source_record_id != ''
         AND i.interaction_type IN ('comment', 'reply')
        WHERE p.platform = ?
          AND p.author_account_id = ?
        """,
        (platform, target_account_id),
    ).fetchone()
    _upsert_state(
        conn,
        platform,
        "account",
        target_account_id,
        int(row["known_posts"] or 0),
        int(row["known_comments"] or 0),
        _clean(row["newest_item_at"]),
    )


def _profile_url(platform: str, platform_user_id: str) -> str:
    if not platform_user_id:
        return ""
    try:
        return get_platform(platform).normalize_profile_input(f"{platform}:{platform_user_id}")[1]
    except ValueError:
        return ""


def _timestamp_to_iso(value: object) -> str:
    raw = _clean(value)
    if not raw:
        return ""
    try:
        numeric = float(raw)
    except ValueError:
        return raw
    if numeric > 10_000_000_000:
        numeric = numeric / 1000
    try:
        return datetime.fromtimestamp(numeric, tz=timezone.utc).isoformat()
    except (OverflowError, OSError, ValueError):
        return raw


def _clean(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _first_non_empty(*values: str) -> str:
    for value in values:
        if value:
            return value
    return ""


def stable_id(*parts: object) -> str:
    raw = "|".join("" if part is None else str(part) for part in parts)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()
