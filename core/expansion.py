from __future__ import annotations

from pathlib import Path

from adapters.registry import DEFAULT_PLATFORM_ID, platform_display_name
from core.db import DEFAULT_DB_PATH, connect


def expansion_candidates(
    platform: str,
    db_path: Path | str = DEFAULT_DB_PATH,
    target_account_id: str = "",
    limit: int = 20,
    min_interactions: int = 1,
) -> list[dict[str, object]]:
    with connect(db_path) as conn:
        target_clause = ""
        params: list[object] = []
        if target_account_id:
            target_clause = "AND (i.source_account_id = ? OR i.target_account_id = ?)"
            params.extend([target_account_id, target_account_id])

        rows = conn.execute(
            f"""
            WITH related AS (
                SELECT
                    CASE
                        WHEN i.source_account_id = ? THEN i.target_account_id
                        ELSE i.source_account_id
                    END AS account_id,
                    COUNT(*) AS interaction_count,
                    SUM(CASE WHEN i.interaction_type = 'reply' THEN 1 ELSE 0 END) AS reply_count,
                    SUM(CASE WHEN i.interaction_type = 'comment' THEN 1 ELSE 0 END) AS comment_count
                FROM interactions i
                WHERE i.platform = ?
                  AND i.source_account_id != i.target_account_id
                  {target_clause}
                GROUP BY account_id
            )
            SELECT a.account_id, a.platform_user_id, a.nickname, a.profile_url,
                   a.crawl_level, a.source, related.interaction_count,
                   related.comment_count, related.reply_count,
                   COALESCE(n.weighted_degree, 0) AS weighted_degree,
                   COALESCE(n.pagerank, 0) AS pagerank
            FROM related
            JOIN accounts a ON a.account_id = related.account_id
            LEFT JOIN node_scores n ON n.account_id = a.account_id
            WHERE a.platform = ?
              AND a.is_target = 0
              AND related.interaction_count >= ?
            ORDER BY related.interaction_count DESC,
                     related.reply_count DESC,
                     weighted_degree DESC,
                     a.nickname
            LIMIT ?
            """,
            [target_account_id, platform, *params, platform, min_interactions, limit],
        ).fetchall()

    return [dict(row) for row in rows]


def write_candidate_urls(candidates: list[dict[str, object]], output_path: Path | str) -> None:
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    lines = [str(row["profile_url"]) for row in candidates if row.get("profile_url")]
    output.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def format_candidates(candidates: list[dict[str, object]], platform: str = DEFAULT_PLATFORM_ID) -> str:
    if not candidates:
        return "No expansion candidates found."
    lines = [f"{platform_display_name(platform)} expansion candidates:"]
    for index, row in enumerate(candidates, start=1):
        lines.append(
            f"{index}. {row['nickname'] or row['platform_user_id']} "
            f"user_id={row['platform_user_id']} "
            f"interactions={row['interaction_count']} "
            f"comments={row['comment_count']} replies={row['reply_count']} "
            f"profile={row['profile_url']}"
        )
    return "\n".join(lines)
