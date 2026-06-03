#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from adapters.registry import DEFAULT_PLATFORM_ID, supported_platform_ids
from core.db import DEFAULT_DB_PATH
from core.graph_renderer import DEFAULT_GRAPH_HTML, render_graph_html


def main() -> None:
    parser = argparse.ArgumentParser(description="Render an interactive static graph HTML file.")
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH), help="SQLite database path")
    parser.add_argument("--platform", default=DEFAULT_PLATFORM_ID, choices=supported_platform_ids(), help="Platform to render from the OSGE overlay")
    parser.add_argument("--output", default=str(DEFAULT_GRAPH_HTML), help="Output HTML path")
    args = parser.parse_args()

    result = render_graph_html(args.db, args.output, source_platform=args.platform)
    print(f"Rendered nodes={result['nodes']}, edges={result['edges']} to {result['output']}")


if __name__ == "__main__":
    main()
