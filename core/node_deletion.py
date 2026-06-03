from __future__ import annotations

from pathlib import Path

from core.db import DEFAULT_DB_PATH, connect, ensure_account_identities, initialize_database
from core.edge_builder import build_edges


def delete_platform_account_node(db_path: Path | str = DEFAULT_DB_PATH, account_id: str = "") -> dict[str, object]:
    if not account_id:
        raise ValueError("account_id is required")

    initialize_database(db_path)
    with connect(db_path) as conn:
        ensure_account_identities(conn)
        account = conn.execute("SELECT * FROM accounts WHERE account_id = ? AND hidden_at IS NULL", (account_id,)).fetchone()
        if account is None:
            raise ValueError(f"Account not found: {account_id}")
        neighbor_ids = _incident_neighbors(conn, account_id)
        _hide_accounts(conn, [account_id], "user_hidden")
        orphan_ids = _find_deletable_orphans(conn, neighbor_ids)
        _hide_accounts(conn, orphan_ids, "adjacent_orphan")
        _delete_empty_auto_identities(conn)

    edge_result = build_edges(db_path)
    return {
        "deleted_account_id": account_id,
        "deleted_accounts": [account_id, *orphan_ids],
        "hidden_account_id": account_id,
        "hidden_accounts": [account_id, *orphan_ids],
        "orphan_accounts": orphan_ids,
        "posts_deleted": 0,
        "interactions_deleted": 0,
        "edges": edge_result["edges"],
        "evidences": edge_result["evidences"],
    }


def prune_adjacent_orphan_nodes(db_path: Path | str = DEFAULT_DB_PATH, account_id: str = "") -> dict[str, object]:
    if not account_id:
        raise ValueError("account_id is required")

    initialize_database(db_path)
    with connect(db_path) as conn:
        ensure_account_identities(conn)
        account = conn.execute("SELECT * FROM accounts WHERE account_id = ? AND hidden_at IS NULL", (account_id,)).fetchone()
        if account is None:
            raise ValueError(f"Account not found: {account_id}")
        neighbor_ids = _incident_neighbors(conn, account_id)
        orphan_ids = _find_deletable_leaf_neighbors(conn, account_id, neighbor_ids)
        _hide_accounts(conn, orphan_ids, "adjacent_orphan")
        _delete_empty_auto_identities(conn)

    edge_result = build_edges(db_path)
    return {
        "kept_account_id": account_id,
        "deleted_accounts": orphan_ids,
        "hidden_accounts": orphan_ids,
        "orphan_accounts": orphan_ids,
        "posts_deleted": 0,
        "interactions_deleted": 0,
        "edges": edge_result["edges"],
        "evidences": edge_result["evidences"],
    }


def _incident_neighbors(conn, account_id: str) -> list[str]:
    rows = conn.execute(
        """
        SELECT CASE
            WHEN source_node = ? THEN target_node
            ELSE source_node
        END AS neighbor_id
        FROM edges
        WHERE source_node = ? OR target_node = ?
        """,
        (account_id, account_id, account_id),
    ).fetchall()
    return sorted({row["neighbor_id"] for row in rows if row["neighbor_id"] and row["neighbor_id"] != account_id})


def _find_deletable_leaf_neighbors(conn, center_id: str, candidate_ids: list[str]) -> list[str]:
    deletable: list[str] = []
    for account_id in sorted(set(candidate_ids)):
        account = conn.execute("SELECT is_target, hidden_at FROM accounts WHERE account_id = ?", (account_id,)).fetchone()
        if account is None or account["hidden_at"] or int(account["is_target"] or 0):
            continue
        neighbors = _visible_incident_neighbors(conn, account_id)
        if set(neighbors) != {center_id}:
            continue
        if _has_owned_or_crawled_data(conn, account_id):
            continue
        if _has_multi_account_identity(conn, account_id):
            continue
        deletable.append(account_id)
    return deletable


def _hide_accounts(conn, account_ids: list[str], reason: str) -> None:
    if not account_ids:
        return
    conn.executemany(
        """
        UPDATE accounts
        SET hidden_reason = ?,
            hidden_at = COALESCE(hidden_at, CURRENT_TIMESTAMP)
        WHERE account_id = ?
        """,
        [(reason, account_id) for account_id in sorted(set(account_ids))],
    )


def _visible_incident_neighbors(conn, account_id: str) -> list[str]:
    rows = conn.execute(
        """
        SELECT CASE
            WHEN e.source_node = ? THEN e.target_node
            ELSE e.source_node
        END AS neighbor_id
        FROM edges e
        JOIN accounts other_account
          ON other_account.account_id = CASE
              WHEN e.source_node = ? THEN e.target_node
              ELSE e.source_node
          END
        WHERE (e.source_node = ? OR e.target_node = ?)
          AND other_account.hidden_at IS NULL
        """,
        (account_id, account_id, account_id, account_id),
    ).fetchall()
    return sorted({row["neighbor_id"] for row in rows if row["neighbor_id"] and row["neighbor_id"] != account_id})


def _find_deletable_orphans(conn, candidate_ids: list[str]) -> list[str]:
    if not candidate_ids:
        return []

    deletable: list[str] = []
    for account_id in sorted(set(candidate_ids)):
        account = conn.execute("SELECT is_target, hidden_at FROM accounts WHERE account_id = ?", (account_id,)).fetchone()
        if account is None or account["hidden_at"] or int(account["is_target"] or 0):
            continue
        if _has_visible_incident_edge(conn, account_id):
            continue
        if _has_owned_or_crawled_data(conn, account_id):
            continue
        if _has_multi_account_identity(conn, account_id):
            continue
        deletable.append(account_id)
    return deletable


def _has_visible_incident_edge(conn, account_id: str) -> bool:
    row = conn.execute(
        """
        SELECT 1
        FROM edges e
        JOIN accounts s ON s.account_id = e.source_node
        JOIN accounts t ON t.account_id = e.target_node
        WHERE (e.source_node = ? OR e.target_node = ?)
          AND s.hidden_at IS NULL
          AND t.hidden_at IS NULL
        LIMIT 1
        """,
        (account_id, account_id),
    ).fetchone()
    return row is not None


def _has_owned_or_crawled_data(conn, account_id: str) -> bool:
    checks = [
        ("SELECT 1 FROM posts WHERE author_account_id = ? LIMIT 1", (account_id,)),
        (
            "SELECT 1 FROM crawl_targets WHERE target_id = ? AND (status = 'crawled' OR crawl_count > 0) LIMIT 1",
            (account_id,),
        ),
    ]
    return any(conn.execute(sql, params).fetchone() is not None for sql, params in checks)


def _has_multi_account_identity(conn, account_id: str) -> bool:
    row = conn.execute(
        """
        SELECT COUNT(*) AS account_count
        FROM identity_accounts ia
        JOIN identity_accounts selected ON selected.identity_id = ia.identity_id
        WHERE selected.account_id = ?
        """,
        (account_id,),
    ).fetchone()
    return int(row["account_count"] or 0) > 1 if row else False


def _delete_empty_auto_identities(conn) -> None:
    conn.execute(
        """
        DELETE FROM identities
        WHERE source = 'auto_platform_account'
          AND identity_id NOT IN (SELECT DISTINCT identity_id FROM identity_accounts)
        """
    )
