from __future__ import annotations

import json
from pathlib import Path

from adapters.registry import DEFAULT_PLATFORM_ID, platform_ui_metadata


ASSET_DIR = Path(__file__).with_name("graph_assets")


def _read_asset(filename: str) -> str:
    return (ASSET_DIR / filename).read_text(encoding="utf-8")


def inject_graph_ui(
    html: str,
    db_path: Path | str,
    center_id: str,
    api_enabled: bool,
    source_platform: str,
) -> str:
    runtime_config = json.dumps(
        {
            "apiEnabled": api_enabled,
            "apiBase": "",
            "centerId": center_id,
            "dbPath": str(db_path),
            "sourcePlatform": source_platform,
            "defaultPlatform": DEFAULT_PLATFORM_ID,
            "platforms": platform_ui_metadata(),
        }
    )
    html = html.replace("</head>", f"{_read_asset('panel.css')}\n</head>")
    html = html.replace("<body>", f"<body>\n{_read_asset('panel.html')}")
    html = html.replace(
        "network = new vis.Network(container, data, options);",
        _read_asset("network_bootstrap.js"),
    )
    return html.replace("__OSGE_CONFIG__", runtime_config)
