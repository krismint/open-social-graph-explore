from __future__ import annotations

import csv
from pathlib import Path

from core.normalizer import account_id, interaction_id, post_id
from core.scoring import relation_rule


ACCOUNT_REQUIRED_FIELDS = {"platform", "platform_user_id"}
POST_REQUIRED_FIELDS = {"platform", "platform_post_id", "author_platform_user_id"}
INTERACTION_REQUIRED_FIELDS = {
    "platform",
    "source_platform_user_id",
    "target_platform_user_id",
    "platform_post_id",
    "interaction_type",
}


class ImportValidationError(ValueError):
    pass


def _int(value: str | None, default: int = 0) -> int:
    if value is None or value == "":
        return default
    return int(value)


def _float(value: str | None, default: float = 1.0) -> float:
    if value is None or value == "":
        return default
    return float(value)


def _read_rows(csv_path: Path, required_fields: set[str]) -> list[dict[str, str]]:
    if not csv_path.exists():
        raise ImportValidationError(f"Missing CSV file: {csv_path}")
    with csv_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        fieldnames = set(reader.fieldnames or [])
        missing = sorted(required_fields - fieldnames)
        if missing:
            raise ImportValidationError(f"{csv_path.name} is missing required columns: {', '.join(missing)}")
        rows = list(reader)

    for index, row in enumerate(rows, start=2):
        empty = [field for field in sorted(required_fields) if not row.get(field)]
        if empty:
            raise ImportValidationError(
                f"{csv_path.name}:{index} has empty required values: {', '.join(empty)}"
            )
    return rows


def import_accounts(conn, csv_path: Path) -> int:
    count = 0
    for row in _read_rows(csv_path, ACCOUNT_REQUIRED_FIELDS):
        acc_id = row.get("account_id") or account_id(row["platform"], row["platform_user_id"])
        conn.execute(
            """
            INSERT INTO accounts (
                account_id, platform, platform_user_id, username, nickname,
                profile_url, avatar_url, bio, location, is_target,
                crawl_level, first_seen, last_seen, source
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(account_id) DO UPDATE SET
                username=excluded.username,
                nickname=excluded.nickname,
                profile_url=excluded.profile_url,
                avatar_url=excluded.avatar_url,
                bio=excluded.bio,
                location=excluded.location,
                is_target=excluded.is_target,
                crawl_level=excluded.crawl_level,
                last_seen=excluded.last_seen,
                source=excluded.source
            """,
            (
                acc_id,
                row["platform"],
                row["platform_user_id"],
                row.get("username", ""),
                row.get("nickname", ""),
                row.get("profile_url", ""),
                row.get("avatar_url", ""),
                row.get("bio", ""),
                row.get("location", ""),
                _int(row.get("is_target")),
                _int(row.get("crawl_level"), 1),
                row.get("first_seen", ""),
                row.get("last_seen", ""),
                row.get("source", "manual_csv"),
            ),
        )
        count += 1
    return count


def import_posts(conn, csv_path: Path) -> int:
    count = 0
    for row in _read_rows(csv_path, POST_REQUIRED_FIELDS):
        pid = row.get("post_id") or post_id(row["platform"], row["platform_post_id"])
        author_id = row.get("author_account_id") or account_id(row["platform"], row["author_platform_user_id"])
        if not _account_exists(conn, author_id):
            raise ImportValidationError(f"{csv_path.name} references missing author account: {author_id}")
        conn.execute(
            """
            INSERT INTO posts (
                post_id, platform, platform_post_id, author_account_id,
                content, url, created_at, like_count, comment_count,
                repost_count, source
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(post_id) DO UPDATE SET
                content=excluded.content,
                url=excluded.url,
                created_at=excluded.created_at,
                like_count=excluded.like_count,
                comment_count=excluded.comment_count,
                repost_count=excluded.repost_count,
                source=excluded.source
            """,
            (
                pid,
                row["platform"],
                row["platform_post_id"],
                author_id,
                row.get("content", ""),
                row.get("url", ""),
                row.get("created_at", ""),
                _int(row.get("like_count")),
                _int(row.get("comment_count")),
                _int(row.get("repost_count")),
                row.get("source", "manual_csv"),
            ),
        )
        count += 1
    return count


def import_interactions(conn, csv_path: Path) -> int:
    count = 0
    for row in _read_rows(csv_path, INTERACTION_REQUIRED_FIELDS):
        if relation_rule(row["interaction_type"]) is None:
            raise ImportValidationError(f"{csv_path.name} has unsupported interaction_type: {row['interaction_type']}")

        source_id = row.get("source_account_id") or account_id(row["platform"], row["source_platform_user_id"])
        target_id = row.get("target_account_id") or account_id(row["platform"], row["target_platform_user_id"])
        pid = row.get("post_id") or post_id(row["platform"], row["platform_post_id"])

        for referenced_id, label in [(source_id, "source account"), (target_id, "target account")]:
            if not _account_exists(conn, referenced_id):
                raise ImportValidationError(f"{csv_path.name} references missing {label}: {referenced_id}")
        if not _post_exists(conn, pid):
            raise ImportValidationError(f"{csv_path.name} references missing post: {pid}")

        iid = row.get("interaction_id") or interaction_id(
            row["platform"],
            source_id,
            target_id,
            pid,
            row["interaction_type"],
            row.get("created_at", ""),
        )
        conn.execute(
            """
            INSERT INTO interactions (
                interaction_id, platform, source_account_id, target_account_id,
                post_id, interaction_type, content, created_at, weight_raw, source
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(interaction_id) DO UPDATE SET
                content=excluded.content,
                created_at=excluded.created_at,
                weight_raw=excluded.weight_raw,
                source=excluded.source
            """,
            (
                iid,
                row["platform"],
                source_id,
                target_id,
                pid,
                row["interaction_type"],
                row.get("content", ""),
                row.get("created_at", ""),
                _float(row.get("weight_raw")),
                row.get("source", "manual_csv"),
            ),
        )
        count += 1
    return count


def import_directory(conn, raw_dir: Path) -> dict[str, int]:
    accounts = import_accounts(conn, raw_dir / "accounts.csv")
    posts = import_posts(conn, raw_dir / "posts.csv")
    interactions = import_interactions(conn, raw_dir / "interactions.csv")
    return {"accounts": accounts, "posts": posts, "interactions": interactions}


def _account_exists(conn, acc_id: str) -> bool:
    return conn.execute("SELECT 1 FROM accounts WHERE account_id = ?", (acc_id,)).fetchone() is not None


def _post_exists(conn, pid: str) -> bool:
    return conn.execute("SELECT 1 FROM posts WHERE post_id = ?", (pid,)).fetchone() is not None
