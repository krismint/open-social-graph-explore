#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from core.db import DEFAULT_DB_PATH
from core.edge_builder import build_edges
from core.scoring import parse_datetime


def main() -> None:
    parser = argparse.ArgumentParser(description="Build relationship edges from interactions.")
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH), help="SQLite database path")
    parser.add_argument("--as-of", default="", help="ISO datetime used for time decay calculations")
    args = parser.parse_args()

    as_of = parse_datetime(args.as_of) if args.as_of else datetime.now(timezone.utc)
    result = build_edges(args.db, as_of=as_of)
    print(f"Built edges={result['edges']}, evidences={result['evidences']}")


if __name__ == "__main__":
    main()
