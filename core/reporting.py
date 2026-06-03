from __future__ import annotations

from pathlib import Path

from core.db import DEFAULT_DB_PATH, connect


def resolve_account(conn, account_ref: str) -> str:
    row = conn.execute(
        """
        SELECT account_id
        FROM accounts
        WHERE account_id = ?
           OR platform || ':' || platform_user_id = ?
           OR username = ?
        """,
        (account_ref, account_ref, account_ref),
    ).fetchone()
    if row is None:
        raise ValueError(f"Account not found: {account_ref}")
    return row["account_id"]


def target_report(db_path: Path | str = DEFAULT_DB_PATH, account_ref: str = "", limit: int = 10) -> dict[str, object]:
    with connect(db_path) as conn:
        account_id = resolve_account(conn, account_ref)
        account = dict(
            conn.execute(
                """
                SELECT account_id, platform, username, nickname, profile_url, bio,
                       location, is_target, crawl_level
                FROM accounts
                WHERE account_id = ?
                """,
                (account_id,),
            ).fetchone()
        )
        relation_rows = conn.execute(
            """
            SELECT e.relation_type, e.weight, e.confidence, e.interaction_count,
                   e.first_seen, e.last_seen, e.evidence_count,
                   other.account_id AS other_account_id,
                   other.platform AS other_platform,
                   other.username AS other_username,
                   other.nickname AS other_nickname,
                   CASE WHEN e.source_node = ? THEN 'outgoing' ELSE 'incoming' END AS direction
            FROM edges e
            JOIN accounts other
              ON other.account_id = CASE
                    WHEN e.source_node = ? THEN e.target_node
                    ELSE e.source_node
                 END
            WHERE e.source_node = ? OR e.target_node = ?
            ORDER BY e.weight DESC, e.interaction_count DESC, other.nickname
            LIMIT ?
            """,
            (account_id, account_id, account_id, account_id, limit),
        ).fetchall()
        evidence_rows = conn.execute(
            """
            SELECT ev.evidence_type, ev.evidence_value, ev.score,
                   other.nickname AS other_nickname
            FROM evidences ev
            JOIN accounts other
              ON other.account_id = CASE
                    WHEN ev.subject_node = ? THEN ev.object_node
                    ELSE ev.subject_node
                 END
            WHERE ev.subject_node = ? OR ev.object_node = ?
            ORDER BY ev.score DESC
            LIMIT ?
            """,
            (account_id, account_id, account_id, limit),
        ).fetchall()
        score = conn.execute(
            """
            SELECT degree_centrality, betweenness_centrality, pagerank,
                   community_id, weighted_degree
            FROM node_scores
            WHERE account_id = ?
            """,
            (account_id,),
        ).fetchone()

    return {
        "account": account,
        "score": dict(score) if score else None,
        "relations": [dict(row) for row in relation_rows],
        "evidences": [dict(row) for row in evidence_rows],
    }


def format_report(report: dict[str, object]) -> str:
    account = report["account"]
    score = report["score"]
    relations = report["relations"]
    evidences = report["evidences"]

    lines = [
        f"Target account: {account['nickname'] or account['username']} ({account['account_id']})",
        f"Platform: {account['platform']}",
    ]
    if account.get("bio"):
        lines.append(f"Bio: {account['bio']}")
    if score:
        lines.append(
            "Scores: "
            f"pagerank={score['pagerank']:.4f}, "
            f"degree={score['degree_centrality']:.4f}, "
            f"weighted_degree={score['weighted_degree']:.2f}, "
            f"community={score['community_id']}"
        )

    lines.append("")
    lines.append("Top one-hop relations:")
    if not relations:
        lines.append("- No generated edges found for this account.")
    for row in relations:
        lines.append(
            f"- {row['direction']} {row['relation_type']} with "
            f"{row['other_nickname'] or row['other_username']} "
            f"weight={row['weight']} confidence={row['confidence']} "
            f"count={row['interaction_count']}"
        )

    lines.append("")
    lines.append("Evidence highlights:")
    if not evidences:
        lines.append("- No evidence rows found for this account.")
    for row in evidences:
        lines.append(
            f"- {row['other_nickname']}: {row['evidence_type']} "
            f"score={row['score']} | {row['evidence_value']}"
        )

    return "\n".join(lines)
