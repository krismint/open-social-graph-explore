#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from core.db import DEFAULT_DB_PATH, connect


DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "processed" / "graph.json"


def export_graph(db_path: str, output_path: Path) -> dict[str, int]:
    with connect(db_path) as conn:
        account_rows = conn.execute(
            """
            SELECT a.account_id, a.platform, a.username, a.nickname, a.is_target,
                   COALESCE(n.pagerank, 0) AS pagerank,
                   COALESCE(n.community_id, -1) AS community_id
            FROM accounts a
            LEFT JOIN node_scores n ON n.account_id = a.account_id
            WHERE a.account_id IN (
                SELECT source_node FROM edges
                UNION
                SELECT target_node FROM edges
            )
            """
        ).fetchall()
        edge_rows = conn.execute(
            """
            SELECT source_node, target_node, relation_type, weight,
                   confidence, evidence_count
            FROM edges
            """
        ).fetchall()

    payload = {
        "nodes": [dict(row) for row in account_rows],
        "edges": [dict(row) for row in edge_rows],
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"nodes": len(payload["nodes"]), "edges": len(payload["edges"])}


def main() -> None:
    parser = argparse.ArgumentParser(description="Export the graph as JSON for future visualization.")
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH), help="SQLite database path")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="Output JSON path")
    args = parser.parse_args()

    result = export_graph(args.db, Path(args.output))
    print(f"Exported nodes={result['nodes']}, edges={result['edges']} to {args.output}")


if __name__ == "__main__":
    main()
