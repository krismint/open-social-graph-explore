from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path

from adapters.registry import DEFAULT_PLATFORM_ID
from core.db import DEFAULT_DB_PATH, connect


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def stable_id(*parts: object) -> str:
    raw = "|".join("" if part is None else str(part) for part in parts)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def target_id(platform: str, platform_user_id: str) -> str:
    return f"{platform}:{platform_user_id}"


def ensure_crawl_target(
    db_path: Path | str = DEFAULT_DB_PATH,
    platform: str = DEFAULT_PLATFORM_ID,
    platform_user_id: str = "",
    profile_url: str = "",
    status: str = "pending",
) -> str:
    tid = target_id(platform, platform_user_id)
    with connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO crawl_targets (
                target_id, platform, platform_user_id, profile_url,
                status, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ON CONFLICT(target_id) DO UPDATE SET
                profile_url=COALESCE(NULLIF(excluded.profile_url, ''), crawl_targets.profile_url),
                updated_at=CURRENT_TIMESTAMP
            """,
            (tid, platform, platform_user_id, profile_url, status),
        )
    return tid


def get_crawl_target(db_path: Path | str, tid: str) -> dict[str, object] | None:
    with connect(db_path) as conn:
        row = conn.execute("SELECT * FROM crawl_targets WHERE target_id = ?", (tid,)).fetchone()
    return dict(row) if row else None


def should_skip_crawl(db_path: Path | str, tid: str, force: bool = False) -> tuple[bool, str]:
    if force:
        return False, "force requested"
    target = get_crawl_target(db_path, tid)
    if not target:
        return False, "target not registered"
    if target["status"] == "running":
        return True, "target already has a running job"
    if int(target["crawl_count"] or 0) > 0 or target["status"] == "crawled":
        timestamp = target["last_crawled_at"] or target["last_imported_at"] or "unknown time"
        return True, f"target already crawled/imported at {timestamp}"
    return False, "target has not been crawled"


def begin_crawl_job(
    db_path: Path | str,
    tid: str,
    platform: str,
    profile_url: str,
    source_db: str,
    output_db: str,
    graph_output: str,
    log_path: str,
    max_notes: int,
    max_comments: int,
    get_sub_comments: bool,
    force: bool,
    notes_before: int,
    comments_before: int,
    requested_by: str = "cli",
) -> str:
    job_id = stable_id("crawl_job", tid, now_iso())
    with connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO crawl_jobs (
                job_id, target_id, platform, profile_url, status, requested_by,
                force, max_notes, max_comments, get_sub_comments, source_db,
                output_db, graph_output, log_path, notes_before, comments_before
            )
            VALUES (?, ?, ?, ?, 'running', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                job_id,
                tid,
                platform,
                profile_url,
                requested_by,
                1 if force else 0,
                max_notes,
                max_comments,
                1 if get_sub_comments else 0,
                source_db,
                output_db,
                graph_output,
                log_path,
                notes_before,
                comments_before,
            ),
        )
        conn.execute(
            """
            UPDATE crawl_targets
            SET status='running', last_job_id=?, updated_at=CURRENT_TIMESTAMP
            WHERE target_id=?
            """,
            (job_id, tid),
        )
        _history(conn, job_id, tid, "job_started", f"max_notes={max_notes}; max_comments={max_comments}; sub={get_sub_comments}")
    return job_id


def finish_crawl_job(
    db_path: Path | str,
    job_id: str,
    tid: str,
    status: str,
    notes_after: int,
    comments_after: int,
    error: str = "",
) -> None:
    with connect(db_path) as conn:
        conn.execute(
            """
            UPDATE crawl_jobs
            SET status=?, finished_at=CURRENT_TIMESTAMP, notes_after=?,
                comments_after=?, error=?
            WHERE job_id=?
            """,
            (status, notes_after, comments_after, error, job_id),
        )
        if status == "completed":
            conn.execute(
                """
                UPDATE crawl_targets
                SET status='crawled',
                    crawl_count=crawl_count + 1,
                    notes_seen=?,
                    comments_seen=?,
                    last_crawled_at=CURRENT_TIMESTAMP,
                    last_imported_at=CURRENT_TIMESTAMP,
                    updated_at=CURRENT_TIMESTAMP
                WHERE target_id=?
                """,
                (notes_after, comments_after, tid),
            )
        else:
            conn.execute(
                """
                UPDATE crawl_targets
                SET status='failed', updated_at=CURRENT_TIMESTAMP
                WHERE target_id=?
                """,
                (tid,),
            )
        _history(conn, job_id, tid, f"job_{status}", error)


def mark_targets_from_accounts(db_path: Path | str = DEFAULT_DB_PATH, platform: str = "") -> int:
    with connect(db_path) as conn:
        platform_clause = "WHERE platform = ?" if platform else ""
        params: tuple[str, ...] = (platform,) if platform else ()
        rows = conn.execute(
            f"""
            SELECT account_id, platform, platform_user_id, profile_url
            FROM accounts
            {platform_clause}
            """,
            params,
        ).fetchall()
        count = 0
        for row in rows:
            conn.execute(
                """
                INSERT INTO crawl_targets (
                    target_id, platform, platform_user_id, profile_url,
                    status, crawl_count, last_imported_at, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                ON CONFLICT(target_id) DO UPDATE SET
                    profile_url=COALESCE(NULLIF(excluded.profile_url, ''), crawl_targets.profile_url),
                    status=CASE
                        WHEN crawl_targets.status = 'crawled' THEN crawl_targets.status
                        WHEN excluded.status = 'crawled' THEN excluded.status
                        ELSE crawl_targets.status
                    END,
                    crawl_count=MAX(crawl_targets.crawl_count, excluded.crawl_count),
                    last_imported_at=CURRENT_TIMESTAMP,
                    updated_at=CURRENT_TIMESTAMP
                """,
                (
                    row["account_id"],
                    row["platform"],
                    row["platform_user_id"],
                    row["profile_url"],
                    "pending",
                    0,
                ),
            )
            count += 1
    return count


def _history(conn, job_id: str, tid: str, event_type: str, event_value: str = "") -> None:
    history_id = stable_id("crawl_history", job_id, tid, event_type, now_iso())
    conn.execute(
        """
        INSERT INTO crawl_history (
            history_id, job_id, target_id, event_type, event_value
        )
        VALUES (?, ?, ?, ?, ?)
        """,
        (history_id, job_id, tid, event_type, event_value),
    )
