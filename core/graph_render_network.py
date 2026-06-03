from __future__ import annotations

import math
from collections import deque
from collections.abc import Sequence

from pyvis.network import Network

from core.avatar_cache import avatar_public_url
from core.graph_render_data import node_value


PALETTE = ["#2563eb", "#0f766e", "#b45309", "#7c3aed", "#be123c", "#4d7c0f", "#0369a1"]


def build_network(nodes: Sequence[object], edges: list[dict[str, object]], center_id: str = "") -> Network:
    net = _create_network()
    crawl_level_by_id = _crawl_levels(nodes)
    display_level_by_id = _display_levels(nodes, edges, center_id, crawl_level_by_id)

    for node in nodes:
        node_id, node_options = _node_options(node, center_id, display_level_by_id)
        net.add_node(node_id, **node_options)

    for edge in edges:
        source, target, edge_options = _edge_options(edge, display_level_by_id, crawl_level_by_id)
        net.add_edge(source, target, **edge_options)

    return net


def _create_network() -> Network:
    net = Network(
        height="86vh",
        width="100%",
        directed=True,
        bgcolor="#f8fafc",
        font_color="#172033",
        cdn_resources="in_line",
    )
    net.barnes_hut(gravity=-32000, central_gravity=0.16, spring_length=240, spring_strength=0.035)
    net.set_options(
        """
        {
          "nodes": {
            "font": {
              "size": 18,
              "face": "-apple-system, BlinkMacSystemFont, Segoe UI, sans-serif",
              "color": "#172033",
              "strokeWidth": 4,
              "strokeColor": "#f8fafc"
            },
            "shadow": {
              "enabled": true,
              "color": "rgba(15, 23, 42, 0.16)",
              "size": 8,
              "x": 0,
              "y": 2
            },
            "shapeProperties": {
              "useBorderWithImage": true
            }
          },
          "edges": {
            "smooth": {
              "enabled": true,
              "type": "dynamic"
            },
            "font": {
              "size": 11,
              "color": "#64748b",
              "strokeWidth": 3,
              "strokeColor": "#f8fafc"
            },
            "arrows": {
              "to": {
                "enabled": true,
                "scaleFactor": 0.55
              }
            }
          },
          "interaction": {
            "hover": true,
            "tooltipDelay": 120,
            "navigationButtons": false,
            "keyboard": false
          },
          "physics": {
            "stabilization": {
              "iterations": 180
            }
          }
        }
        """
    )
    return net


def _crawl_levels(nodes: Sequence[object]) -> dict[str, int]:
    return {_text(node, "account_id"): _int(node, "crawl_level") for node in nodes}


def _display_levels(
    nodes: Sequence[object],
    edges: list[dict[str, object]],
    center_id: str,
    crawl_level_by_id: dict[str, int],
) -> dict[str, int]:
    node_ids = {_text(node, "account_id") for node in nodes}
    if not center_id or center_id not in node_ids:
        return dict(crawl_level_by_id)

    adjacency: dict[str, set[str]] = {node_id: set() for node_id in node_ids}
    for edge in edges:
        source = str(edge["source_node"])
        target = str(edge["target_node"])
        if source in adjacency and target in adjacency:
            adjacency[source].add(target)
            adjacency[target].add(source)

    display_level_by_id = {center_id: 0}
    queue: deque[str] = deque([center_id])
    while queue:
        current = queue.popleft()
        for neighbor in adjacency.get(current, set()):
            if neighbor not in display_level_by_id:
                display_level_by_id[neighbor] = display_level_by_id[current] + 1
                queue.append(neighbor)
    return display_level_by_id


def _node_options(
    node: object,
    center_id: str,
    display_level_by_id: dict[str, int],
) -> tuple[str, dict[str, object]]:
    account_id = _text(node, "account_id")
    platform_user_id = _text(node, "platform_user_id")
    username = _text(node, "username")
    nickname = _text(node, "nickname")
    avatar_url = _text(node, "avatar_url")
    avatar_local_path = _text(node, "avatar_local_path")
    avatar_image_url = avatar_public_url(avatar_local_path) if avatar_local_path else ""
    community = _int(node, "community_id")
    crawl_status = _text(node, "crawl_status")
    crawl_level = _int(node, "crawl_level")
    crawl_count = _int(node, "crawl_count")
    weighted_degree = max(_float(node, "weighted_degree"), 0.0)
    actively_crawled = crawl_count > 0 or crawl_status == "crawled"
    public_username = bool(username and username != platform_user_id)
    has_profile_data = bool(
        _text(node, "source_record_id")
        or avatar_url
        or avatar_image_url
        or _text(node, "bio")
        or _text(node, "location")
        or _text(node, "gender")
        or public_username
    )
    color = "#111827" if bool(node_value(node, "is_target")) else PALETTE[community % len(PALETTE)]
    border_color = _node_border_color(crawl_status, actively_crawled)
    is_center = bool(center_id and account_id == center_id)
    size = 20 + min(math.log1p(weighted_degree) * 8, 36)
    label = nickname or username or account_id
    node_options = {
        "label": label,
        "title": _node_title(node, label, community),
        "account_id": account_id,
        "platform": _text(node, "platform"),
        "platform_user_id": platform_user_id,
        "source_record_id": _text(node, "source_record_id"),
        "username": username,
        "nickname": nickname,
        "profile_url": _text(node, "profile_url"),
        "avatar_url": avatar_url,
        "avatar_local_path": avatar_local_path,
        "avatar_image_url": avatar_image_url,
        "bio": _text(node, "bio"),
        "location": _text(node, "location"),
        "gender": _text(node, "gender"),
        "has_profile_data": has_profile_data,
        "actively_crawled": actively_crawled,
        "is_target": bool(node_value(node, "is_target")),
        "crawl_level": node_value(node, "crawl_level"),
        "source": _text(node, "source"),
        "crawl_status": crawl_status,
        "crawl_count": crawl_count,
        "last_crawled_at": _text(node, "last_crawled_at"),
        "display_level": display_level_by_id.get(account_id, crawl_level),
        "pagerank": round(_float(node, "pagerank"), 6),
        "weighted_degree": round(weighted_degree, 3),
        "community_id": community,
        "base_size": 20,
        "weighted_size": round(size, 3),
        "color": {"background": color, "border": border_color},
        "borderWidth": 5 if is_center else 4 if actively_crawled else 2,
        "size": size,
        "shape": "circularImage" if avatar_image_url else "dot",
        "url": _text(node, "profile_url"),
    }
    if avatar_image_url:
        node_options["image"] = avatar_image_url
    return account_id, node_options


def _node_border_color(crawl_status: str, actively_crawled: bool) -> str:
    if crawl_status == "running":
        return "#f59e0b"
    if crawl_status == "failed":
        return "#ef4444"
    return "#10b981" if actively_crawled else "#94a3b8"


def _node_title(node: object, label: str, community: int) -> str:
    return (
        f"<b>{label}</b><br>"
        f"account_id={_text(node, 'account_id')}<br>"
        f"platform_user_id={_text(node, 'platform_user_id')}<br>"
        f"source_record_id={_text(node, 'source_record_id') or 'n/a'}<br>"
        f"platform={_text(node, 'platform')}<br>"
        f"crawl_level={node_value(node, 'crawl_level')}<br>"
        f"location={_text(node, 'location') or 'unknown'}<br>"
        f"gender={_text(node, 'gender') or 'unknown'}<br>"
        f"source={_text(node, 'source') or 'unknown'}<br>"
        f"crawl_status={_text(node, 'crawl_status')}<br>"
        f"crawl_count={_int(node, 'crawl_count')}<br>"
        f"last_crawled_at={_text(node, 'last_crawled_at') or 'never'}<br>"
        f"pagerank={_float(node, 'pagerank'):.4f}<br>"
        f"weighted_degree={_float(node, 'weighted_degree'):.2f}<br>"
        f"community={community}<br>"
        f"profile={_text(node, 'profile_url') or 'n/a'}"
    )


def _edge_options(
    edge: dict[str, object],
    display_level_by_id: dict[str, int],
    crawl_level_by_id: dict[str, int],
) -> tuple[object, object, dict[str, object]]:
    source = edge["source_node"]
    target = edge["target_node"]
    edge_weight = max(float(edge["weight"]), 0.0)
    width = 1 + min(math.log1p(edge_weight) * 0.75, 3.2)
    weight_label = f"{edge_weight:.2f}"
    relation_types = list(edge.get("relation_types") or [edge["relation_type"]])
    edge_options = {
        "id": edge["edge_id"],
        "label": weight_label,
        "weight_label": weight_label,
        "relation_label": "互动",
        "relation_type": edge["relation_type"],
        "relation_types": relation_types,
        "title": _edge_title(edge, relation_types, edge_weight),
        "source_name": edge["source_name"],
        "target_name": edge["target_name"],
        "confidence": float(edge["confidence"]),
        "interaction_count": int(edge["interaction_count"]),
        "first_seen": edge.get("first_seen", ""),
        "last_seen": edge.get("last_seen", ""),
        "evidence_items": edge.get("evidence_items", []),
        "width": width,
        "edge_weight": round(edge_weight, 3),
        "spacing_group": _spacing_group(source, target, display_level_by_id, crawl_level_by_id),
        "base_width": 1,
        "weighted_width": round(width, 3),
        "color": "#475569",
        "arrows": {"to": {"enabled": False}},
    }
    return source, target, edge_options


def _edge_title(edge: dict[str, object], relation_types: list[object], edge_weight: float) -> str:
    return (
        f"{edge['source_name']} ↔ {edge['target_name']}<br>"
        f"relations={', '.join(str(item) for item in relation_types)}<br>"
        f"weight={edge_weight:.3f}<br>"
        f"confidence={edge['confidence']}<br>"
        f"count={edge['interaction_count']}<br>"
        f"evidence={edge.get('evidence_count', 0)}"
    )


def _spacing_group(
    source: object,
    target: object,
    display_level_by_id: dict[str, int],
    crawl_level_by_id: dict[str, int],
) -> str:
    source_id = str(source)
    target_id = str(target)
    source_level = display_level_by_id.get(source_id, crawl_level_by_id.get(source_id, 0))
    target_level = display_level_by_id.get(target_id, crawl_level_by_id.get(target_id, 0))
    lower_level = min(source_level, target_level)
    upper_level = max(source_level, target_level)
    if lower_level == 0 and upper_level <= 1:
        return "center"
    if source_level == target_level:
        return "peer"
    return "outer"


def _text(node: object, key: str) -> str:
    return str(node_value(node, key) or "")


def _int(node: object, key: str) -> int:
    return int(node_value(node, key) or 0)


def _float(node: object, key: str) -> float:
    return float(node_value(node, key) or 0)
