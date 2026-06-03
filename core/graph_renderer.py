from __future__ import annotations

from pathlib import Path

from adapters.registry import DEFAULT_PLATFORM_ID
from core.db import DEFAULT_DB_PATH, PROJECT_ROOT
from core.graph_render_assets import inject_graph_ui
from core.graph_render_network import build_network
from core.graph_render_source import load_render_graph_data


DEFAULT_GRAPH_HTML = PROJECT_ROOT / "data" / "processed" / "osge_graph.html"


def render_graph_html(
    db_path: Path | str = DEFAULT_DB_PATH,
    output_path: Path | str = DEFAULT_GRAPH_HTML,
    center_id: str = "",
    api_enabled: bool = True,
    source_platform: str = DEFAULT_PLATFORM_ID,
) -> dict[str, int | str]:
    output = Path(output_path)
    graph_data = load_render_graph_data(
        db_path=db_path,
        source_platform=source_platform,
    )

    net = build_network(graph_data.nodes, graph_data.edges, center_id=center_id)

    output.parent.mkdir(parents=True, exist_ok=True)
    temp_output = output.with_name(f".{output.stem}.tmp{output.suffix}")
    net.write_html(str(temp_output), notebook=False, open_browser=False)
    html = temp_output.read_text(encoding="utf-8")
    html = inject_graph_ui(
        html,
        db_path=db_path,
        center_id=center_id,
        api_enabled=api_enabled,
        source_platform=graph_data.source_platform,
    )
    temp_output.write_text(html, encoding="utf-8")
    temp_output.replace(output)
    return {"nodes": len(graph_data.nodes), "edges": len(graph_data.edges), "output": str(output)}
