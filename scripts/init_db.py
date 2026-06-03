#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from core.db import DEFAULT_DB_PATH, initialize_database


def main() -> None:
    parser = argparse.ArgumentParser(description="Initialize the OSGE SQLite database.")
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH), help="SQLite database path")
    args = parser.parse_args()

    initialize_database(args.db)
    print(f"Initialized database: {args.db}")


if __name__ == "__main__":
    main()
