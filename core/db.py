from __future__ import annotations

import sqlite3
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "database" / "osge_overlay.db"


SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS platforms (
    platform_id TEXT PRIMARY KEY,
    platform_name TEXT NOT NULL,
    base_url TEXT,
    adapter_name TEXT,
    enabled INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS accounts (
    account_id TEXT PRIMARY KEY,
    platform TEXT NOT NULL,
    platform_user_id TEXT NOT NULL,
    source_record_id TEXT,
    username TEXT,
    nickname TEXT,
    profile_url TEXT,
    avatar_url TEXT,
    avatar_local_path TEXT,
    avatar_cached_at TEXT,
    avatar_cache_checked_at TEXT,
    avatar_cache_error TEXT,
    bio TEXT,
    location TEXT,
    gender TEXT,
    is_target INTEGER NOT NULL DEFAULT 0,
    crawl_level INTEGER NOT NULL DEFAULT 1,
    first_seen TEXT,
    last_seen TEXT,
    source TEXT,
    hidden_reason TEXT,
    hidden_at TEXT,
    UNIQUE(platform, platform_user_id)
);

CREATE TABLE IF NOT EXISTS identities (
    identity_id TEXT PRIMARY KEY,
    legal_name TEXT,
    phone TEXT,
    email TEXT,
    osge_account TEXT,
    display_name TEXT,
    notes TEXT,
    source TEXT NOT NULL DEFAULT 'auto',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS identity_accounts (
    identity_id TEXT NOT NULL,
    account_id TEXT NOT NULL UNIQUE,
    link_type TEXT NOT NULL DEFAULT 'auto_platform_account',
    confidence REAL NOT NULL DEFAULT 1.0,
    is_primary INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY(identity_id, account_id),
    FOREIGN KEY(identity_id) REFERENCES identities(identity_id) ON DELETE CASCADE,
    FOREIGN KEY(account_id) REFERENCES accounts(account_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS posts (
    post_id TEXT PRIMARY KEY,
    platform TEXT NOT NULL,
    platform_post_id TEXT NOT NULL,
    author_account_id TEXT NOT NULL,
    content TEXT,
    url TEXT,
    created_at TEXT,
    like_count INTEGER NOT NULL DEFAULT 0,
    comment_count INTEGER NOT NULL DEFAULT 0,
    repost_count INTEGER NOT NULL DEFAULT 0,
    source TEXT,
    UNIQUE(platform, platform_post_id),
    FOREIGN KEY(author_account_id) REFERENCES accounts(account_id)
);

CREATE TABLE IF NOT EXISTS interactions (
    interaction_id TEXT PRIMARY KEY,
    platform TEXT NOT NULL,
    source_account_id TEXT NOT NULL,
    target_account_id TEXT NOT NULL,
    post_id TEXT,
    interaction_type TEXT NOT NULL,
    source_record_id TEXT,
    parent_interaction_id TEXT,
    parent_source_record_id TEXT,
    content TEXT,
    created_at TEXT,
    first_seen TEXT,
    last_seen TEXT,
    like_count INTEGER NOT NULL DEFAULT 0,
    weight_raw REAL NOT NULL DEFAULT 1,
    crawl_job_id TEXT,
    deleted_at TEXT,
    source TEXT,
    FOREIGN KEY(source_account_id) REFERENCES accounts(account_id),
    FOREIGN KEY(target_account_id) REFERENCES accounts(account_id),
    FOREIGN KEY(post_id) REFERENCES posts(post_id)
);

CREATE TABLE IF NOT EXISTS edges (
    edge_id TEXT PRIMARY KEY,
    source_node TEXT NOT NULL,
    target_node TEXT NOT NULL,
    source_type TEXT NOT NULL DEFAULT 'account',
    target_type TEXT NOT NULL DEFAULT 'account',
    relation_type TEXT NOT NULL,
    weight REAL NOT NULL,
    confidence REAL NOT NULL,
    interaction_count INTEGER NOT NULL DEFAULT 0,
    first_seen TEXT,
    last_seen TEXT,
    is_inferred INTEGER NOT NULL DEFAULT 1,
    evidence_count INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(source_node, target_node, relation_type),
    FOREIGN KEY(source_node) REFERENCES accounts(account_id),
    FOREIGN KEY(target_node) REFERENCES accounts(account_id)
);

CREATE TABLE IF NOT EXISTS evidences (
    evidence_id TEXT PRIMARY KEY,
    subject_node TEXT NOT NULL,
    object_node TEXT NOT NULL,
    evidence_type TEXT NOT NULL,
    evidence_value TEXT NOT NULL,
    score REAL NOT NULL,
    source_table TEXT,
    source_id TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(subject_node) REFERENCES accounts(account_id),
    FOREIGN KEY(object_node) REFERENCES accounts(account_id)
);

CREATE TABLE IF NOT EXISTS node_scores (
    node_score_id TEXT PRIMARY KEY,
    account_id TEXT NOT NULL,
    degree_centrality REAL NOT NULL DEFAULT 0,
    betweenness_centrality REAL NOT NULL DEFAULT 0,
    pagerank REAL NOT NULL DEFAULT 0,
    community_id INTEGER,
    weighted_degree REAL NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(account_id),
    FOREIGN KEY(account_id) REFERENCES accounts(account_id)
);

CREATE TABLE IF NOT EXISTS crawl_targets (
    target_id TEXT PRIMARY KEY,
    platform TEXT NOT NULL,
    platform_user_id TEXT NOT NULL,
    profile_url TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    crawl_count INTEGER NOT NULL DEFAULT 0,
    notes_seen INTEGER NOT NULL DEFAULT 0,
    comments_seen INTEGER NOT NULL DEFAULT 0,
    last_job_id TEXT,
    last_crawled_at TEXT,
    last_imported_at TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(platform, platform_user_id)
);

CREATE TABLE IF NOT EXISTS crawl_jobs (
    job_id TEXT PRIMARY KEY,
    target_id TEXT NOT NULL,
    platform TEXT NOT NULL,
    profile_url TEXT,
    status TEXT NOT NULL,
    requested_by TEXT,
    force INTEGER NOT NULL DEFAULT 0,
    max_notes INTEGER NOT NULL DEFAULT 10,
    max_comments INTEGER NOT NULL DEFAULT 20,
    get_sub_comments INTEGER NOT NULL DEFAULT 0,
    started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    finished_at TEXT,
    source_db TEXT,
    output_db TEXT,
    graph_output TEXT,
    log_path TEXT,
    notes_before INTEGER NOT NULL DEFAULT 0,
    notes_after INTEGER NOT NULL DEFAULT 0,
    comments_before INTEGER NOT NULL DEFAULT 0,
    comments_after INTEGER NOT NULL DEFAULT 0,
    error TEXT,
    FOREIGN KEY(target_id) REFERENCES crawl_targets(target_id)
);

CREATE TABLE IF NOT EXISTS crawl_history (
    history_id TEXT PRIMARY KEY,
    job_id TEXT,
    target_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    event_value TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(job_id) REFERENCES crawl_jobs(job_id),
    FOREIGN KEY(target_id) REFERENCES crawl_targets(target_id)
);

CREATE TABLE IF NOT EXISTS minimal_crawl_state (
    platform TEXT NOT NULL,
    scope_type TEXT NOT NULL,
    scope_id TEXT NOT NULL,
    known_posts INTEGER NOT NULL DEFAULT 0,
    known_comments INTEGER NOT NULL DEFAULT 0,
    newest_item_at TEXT,
    last_checked_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY(platform, scope_type, scope_id)
);

CREATE INDEX IF NOT EXISTS idx_accounts_platform_user
    ON accounts(platform, platform_user_id);
CREATE INDEX IF NOT EXISTS idx_posts_platform_post
    ON posts(platform, platform_post_id);
CREATE INDEX IF NOT EXISTS idx_identity_accounts_identity
    ON identity_accounts(identity_id);
CREATE INDEX IF NOT EXISTS idx_identity_accounts_account
    ON identity_accounts(account_id);
CREATE INDEX IF NOT EXISTS idx_interactions_source
    ON interactions(source_account_id);
CREATE INDEX IF NOT EXISTS idx_interactions_target
    ON interactions(target_account_id);
CREATE INDEX IF NOT EXISTS idx_interactions_post
    ON interactions(post_id);
CREATE INDEX IF NOT EXISTS idx_edges_source
    ON edges(source_node);
CREATE INDEX IF NOT EXISTS idx_edges_target
    ON edges(target_node);
CREATE INDEX IF NOT EXISTS idx_crawl_targets_status
    ON crawl_targets(status);
CREATE INDEX IF NOT EXISTS idx_crawl_jobs_target
    ON crawl_jobs(target_id);
"""


class ClosingConnection(sqlite3.Connection):
    def __exit__(self, exc_type, exc_value, traceback) -> bool:
        try:
            return super().__exit__(exc_type, exc_value, traceback)
        finally:
            self.close()


def connect(db_path: Path | str = DEFAULT_DB_PATH) -> sqlite3.Connection:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=30, factory=ClosingConnection)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 30000")
    return conn


def initialize_database(db_path: Path | str = DEFAULT_DB_PATH) -> None:
    with connect(db_path) as conn:
        conn.executescript(SCHEMA_SQL)
        conn.executemany(
            """
            INSERT OR IGNORE INTO platforms
                (platform_id, platform_name, base_url, adapter_name, enabled)
            VALUES (?, ?, ?, ?, ?)
            """,
            _platform_seed_rows(),
        )
        migrate_account_schema(conn)
        migrate_minimal_crawl_schema(conn)
        migrate_hidden_account_schema(conn)
        migrate_identity_schema(conn)
        ensure_account_identities(conn)


def _platform_seed_rows() -> list[tuple[str, str, str, str, int]]:
    from adapters.registry import PLATFORMS

    return [
        (platform.platform_id, platform.display_name, platform.base_url, platform.platform_id, 1)
        for platform in PLATFORMS
    ]


def migrate_account_schema(conn: sqlite3.Connection) -> None:
    columns = {
        row["name"]
        for row in conn.execute("PRAGMA table_info(accounts)").fetchall()
    }
    additions = {
        "source_record_id": "ALTER TABLE accounts ADD COLUMN source_record_id TEXT",
        "gender": "ALTER TABLE accounts ADD COLUMN gender TEXT",
        "hidden_reason": "ALTER TABLE accounts ADD COLUMN hidden_reason TEXT",
        "hidden_at": "ALTER TABLE accounts ADD COLUMN hidden_at TEXT",
        "avatar_local_path": "ALTER TABLE accounts ADD COLUMN avatar_local_path TEXT",
        "avatar_cached_at": "ALTER TABLE accounts ADD COLUMN avatar_cached_at TEXT",
        "avatar_cache_checked_at": "ALTER TABLE accounts ADD COLUMN avatar_cache_checked_at TEXT",
        "avatar_cache_error": "ALTER TABLE accounts ADD COLUMN avatar_cache_error TEXT",
    }
    for column, statement in additions.items():
        if column not in columns:
            conn.execute(statement)


def migrate_minimal_crawl_schema(conn: sqlite3.Connection) -> None:
    interaction_columns = {
        row["name"]
        for row in conn.execute("PRAGMA table_info(interactions)").fetchall()
    }
    interaction_additions = {
        "source_record_id": "ALTER TABLE interactions ADD COLUMN source_record_id TEXT",
        "parent_interaction_id": "ALTER TABLE interactions ADD COLUMN parent_interaction_id TEXT",
        "parent_source_record_id": "ALTER TABLE interactions ADD COLUMN parent_source_record_id TEXT",
        "first_seen": "ALTER TABLE interactions ADD COLUMN first_seen TEXT",
        "last_seen": "ALTER TABLE interactions ADD COLUMN last_seen TEXT",
        "like_count": "ALTER TABLE interactions ADD COLUMN like_count INTEGER NOT NULL DEFAULT 0",
        "crawl_job_id": "ALTER TABLE interactions ADD COLUMN crawl_job_id TEXT",
        "deleted_at": "ALTER TABLE interactions ADD COLUMN deleted_at TEXT",
    }
    for column, statement in interaction_additions.items():
        if column not in interaction_columns:
            conn.execute(statement)
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_interactions_source_record
        ON interactions(platform, source_record_id)
        """
    )


def migrate_hidden_account_schema(conn: sqlite3.Connection) -> None:
    tables = {
        row["name"]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    }
    if "hidden_accounts" not in tables:
        return
    conn.execute(
        """
        UPDATE accounts
        SET hidden_reason = COALESCE(
                (SELECT reason FROM hidden_accounts WHERE hidden_accounts.account_id = accounts.account_id),
                hidden_reason
            ),
            hidden_at = COALESCE(
                (SELECT hidden_at FROM hidden_accounts WHERE hidden_accounts.account_id = accounts.account_id),
                hidden_at
            )
        WHERE account_id IN (SELECT account_id FROM hidden_accounts)
        """
    )
    conn.execute("DROP TABLE hidden_accounts")


def migrate_identity_schema(conn: sqlite3.Connection) -> None:
    columns = {
        row["name"]
        for row in conn.execute("PRAGMA table_info(identities)").fetchall()
    }
    additions = {
        "legal_name": "ALTER TABLE identities ADD COLUMN legal_name TEXT",
        "phone": "ALTER TABLE identities ADD COLUMN phone TEXT",
        "email": "ALTER TABLE identities ADD COLUMN email TEXT",
        "osge_account": "ALTER TABLE identities ADD COLUMN osge_account TEXT",
    }
    for column, statement in additions.items():
        if column not in columns:
            conn.execute(statement)
    conn.execute(
        """
        UPDATE identities
        SET display_name = NULL
        WHERE source = 'auto_platform_account'
        """
    )
    conn.execute(
        """
        UPDATE identities
        SET osge_account = COALESCE(NULLIF(osge_account, ''), substr(identity_id, 10))
        WHERE source = 'auto_platform_account'
          AND identity_id LIKE 'identity:%'
        """
    )


def ensure_account_identities(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        INSERT OR IGNORE INTO identities (identity_id, display_name, osge_account, source)
        SELECT
            'identity:' || account_id,
            NULL,
            account_id,
            'auto_platform_account'
        FROM accounts
        """
    )
    conn.execute(
        """
        INSERT OR IGNORE INTO identity_accounts (
            identity_id, account_id, link_type, confidence, is_primary
        )
        SELECT
            'identity:' || account_id,
            account_id,
            'auto_platform_account',
            1.0,
            1
        FROM accounts
        """
    )
