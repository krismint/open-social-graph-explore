#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from core.db import DEFAULT_DB_PATH, connect
from core.graph_analyzer import analyze_graph


def print_top_relations(db_path: str, limit: int) -> None:
    with connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT
                e.relation_type,
                e.weight,
                e.confidence,
                e.interaction_count,
                s.nickname AS source_name,
                t.nickname AS target_name
            FROM edges e
            JOIN accounts s ON s.account_id = e.source_node
            JOIN accounts t ON t.account_id = e.target_node
            ORDER BY e.weight DESC, e.interaction_count DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    print("Top relations:")
    for row in rows:
        print(
            f"- {row['source_name']} -> {row['target_name']} "
            f"{row['relation_type']} weight={row['weight']} "
            f"confidence={row['confidence']} count={row['interaction_count']}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run NetworkX graph analysis and store node scores.")
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH), help="SQLite database path")
    parser.add_argument("--top", type=int, default=10, help="Number of top relations to print")
    args = parser.parse_args()

    result = analyze_graph(args.db)
    print(
        f"Analyzed nodes={result['nodes']}, "
        f"db_edges={result['db_edges']}, graph_edges={result['graph_edges']}"
    )
    print_top_relations(args.db, args.top)


if __name__ == "__main__":
    main()
