from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from collections.abc import Sequence

from adapters.registry import DEFAULT_PLATFORM_ID, supported_platform_ids
from core.db import DEFAULT_DB_PATH, connect, initialize_database
from core.graph_render_data import attach_overlay_evidence_items, merge_display_edges


SUPPORTED_RENDER_PLATFORMS = set(supported_platform_ids())


@dataclass(frozen=True)
class RenderGraphData:
    nodes: Sequence[object]
    edges: list[dict[str, object]]
    source_platform: str


def normalized_render_platform(source_platform: str) -> str:
    platform = source_platform.strip().lower()
    return platform if platform in SUPPORTED_RENDER_PLATFORMS else DEFAULT_PLATFORM_ID


def load_render_graph_data(
    db_path: Path | str = DEFAULT_DB_PATH,
    source_platform: str = DEFAULT_PLATFORM_ID,
) -> RenderGraphData:
    initialize_database(db_path)
    platform = normalized_render_platform(source_platform)
    nodes, edges = _load_overlay_graph(db_path, platform)
    return RenderGraphData(
        nodes=nodes,
        edges=merge_display_edges(edges),
        source_platform=platform,
    )


def _load_overlay_graph(db_path: Path | str, platform: str) -> tuple[Sequence[object], list[dict[str, object]]]:
    with connect(db_path) as conn:
        nodes = conn.execute(
            """
            SELECT a.account_id, a.platform, a.platform_user_id, a.source_record_id,
                   a.username, a.nickname, a.profile_url, a.avatar_url,
                   a.avatar_local_path, a.bio, a.location, a.gender,
                   a.is_target, a.crawl_level, a.source,
                   COALESCE(ct.status, 'pending') AS crawl_status,
                   COALESCE(ct.crawl_count, 0) AS crawl_count,
                   ct.last_crawled_at,
                   COALESCE(n.pagerank, 0) AS pagerank,
                   COALESCE(n.weighted_degree, 0) AS weighted_degree,
                   COALESCE(n.community_id, -1) AS community_id
            FROM accounts a
            LEFT JOIN node_scores n ON n.account_id = a.account_id
            LEFT JOIN crawl_targets ct ON ct.target_id = a.account_id
            WHERE a.platform = ?
              AND a.hidden_at IS NULL
              AND a.account_id IN (
                SELECT source_node FROM edges
                UNION
                SELECT target_node FROM edges
            )
            """,
            (platform,),
        ).fetchall()
        edges = [
            dict(row)
            for row in conn.execute(
                """
                SELECT e.edge_id, e.source_node, e.target_node, e.relation_type, e.weight,
                       e.confidence, e.interaction_count, e.first_seen, e.last_seen,
                       e.evidence_count,
                       s.nickname AS source_name,
                       t.nickname AS target_name
                FROM edges e
                JOIN accounts s ON s.account_id = e.source_node
                JOIN accounts t ON t.account_id = e.target_node
                WHERE s.platform = ?
                  AND t.platform = ?
                  AND s.hidden_at IS NULL
                  AND t.hidden_at IS NULL
                """,
                (platform, platform),
            ).fetchall()
        ]
        attach_overlay_evidence_items(conn, edges, platform)
    return nodes, edges
