from __future__ import annotations

from pathlib import Path

from core.db import DEFAULT_DB_PATH, connect, ensure_account_identities, initialize_database


def account_identity_detail(db_path: Path | str = DEFAULT_DB_PATH, account_id: str = "") -> dict[str, object]:
    if not account_id:
        raise ValueError("account_id is required")

    initialize_database(db_path)
    with connect(db_path) as conn:
        ensure_account_identities(conn)
        selected = conn.execute(
            """
            SELECT a.account_id, a.platform, a.platform_user_id, a.source_record_id,
                   a.username, a.nickname, a.profile_url, a.avatar_url,
                   a.avatar_local_path, a.bio, a.location, a.gender, a.is_target,
                   a.crawl_level, a.source,
                   COALESCE(ct.status, 'pending') AS crawl_status,
                   COALESCE(ct.crawl_count, 0) AS crawl_count,
                   ct.last_crawled_at,
                   COALESCE(ns.pagerank, 0) AS pagerank,
                   COALESCE(ns.weighted_degree, 0) AS weighted_degree
            FROM accounts a
            LEFT JOIN crawl_targets ct ON ct.target_id = a.account_id
            LEFT JOIN node_scores ns ON ns.account_id = a.account_id
            WHERE a.account_id = ?
              AND a.hidden_at IS NULL
            """,
            (account_id,),
        ).fetchone()
        if selected is None:
            raise ValueError(f"Account not found: {account_id}")

        identity = conn.execute(
            """
            SELECT i.identity_id, i.legal_name, i.phone, i.email,
                   i.osge_account, i.display_name, i.notes, i.source,
                   i.created_at, i.updated_at,
                   ia.link_type, ia.confidence, ia.is_primary
            FROM identity_accounts ia
            JOIN identities i ON i.identity_id = ia.identity_id
            WHERE ia.account_id = ?
            ORDER BY ia.is_primary DESC, ia.created_at ASC
            LIMIT 1
            """,
            (account_id,),
        ).fetchone()
        if identity is None:
            raise ValueError(f"Identity not found for account: {account_id}")

        linked = conn.execute(
            """
            SELECT a.account_id, a.platform, a.platform_user_id, a.source_record_id,
                   a.username, a.nickname, a.profile_url, a.avatar_url,
                   a.avatar_local_path, a.bio, a.location, a.gender, a.is_target,
                   a.crawl_level, a.source,
                   COALESCE(ct.status, 'pending') AS crawl_status,
                   COALESCE(ct.crawl_count, 0) AS crawl_count,
                   ct.last_crawled_at,
                   COALESCE(ns.pagerank, 0) AS pagerank,
                   COALESCE(ns.weighted_degree, 0) AS weighted_degree,
                   ia.link_type, ia.confidence, ia.is_primary
            FROM identity_accounts ia
            JOIN accounts a ON a.account_id = ia.account_id
            LEFT JOIN crawl_targets ct ON ct.target_id = a.account_id
            LEFT JOIN node_scores ns ON ns.account_id = a.account_id
            WHERE ia.identity_id = ?
              AND a.hidden_at IS NULL
            ORDER BY ia.is_primary DESC, a.platform ASC, a.nickname ASC, a.account_id ASC
            """,
            (identity["identity_id"],),
        ).fetchall()

    return {
        "identity": dict(identity),
        "selected_account": dict(selected),
        "linked_accounts": [dict(row) for row in linked],
    }
