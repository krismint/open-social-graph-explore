from __future__ import annotations


def relation_label(relation_type: str) -> str:
    if relation_type == "interactions":
        return "互动"
    if relation_type == "commented_on":
        return "评论"
    if relation_type == "replied_to":
        return "回复"
    return relation_type


def merge_display_edges(edges: list[dict[str, object]]) -> list[dict[str, object]]:
    merged: dict[tuple[str, str], dict[str, object]] = {}
    for edge in edges:
        source = str(edge["source_node"])
        target = str(edge["target_node"])
        first, second = sorted((source, target))
        key = (first, second)
        item = merged.get(key)
        source_name = str(edge.get("source_name") or source)
        target_name = str(edge.get("target_name") or target)
        first_name = source_name if source == first else target_name
        second_name = target_name if target == second else source_name
        evidence_items = list(edge.get("evidence_items") or [])
        if item is None:
            item = {
                "edge_id": f"merged:{first}:{second}",
                "source_node": first,
                "target_node": second,
                "source_name": first_name,
                "target_name": second_name,
                "relation_type": "interactions",
                "relation_types": set(),
                "weight": 0.0,
                "confidence": 0.0,
                "interaction_count": 0,
                "first_seen": "",
                "last_seen": "",
                "evidence_count": 0,
                "evidence_items": [],
            }
            merged[key] = item
        item["weight"] = float(item["weight"]) + float(edge.get("weight") or 0)
        item["confidence"] = max(float(item["confidence"]), float(edge.get("confidence") or 0))
        item["interaction_count"] = int(item["interaction_count"]) + int(edge.get("interaction_count") or 0)
        item["evidence_count"] = int(item["evidence_count"]) + int(edge.get("evidence_count") or len(evidence_items))
        item["first_seen"] = min_nonempty(str(item.get("first_seen") or ""), str(edge.get("first_seen") or ""))
        item["last_seen"] = max_nonempty(str(item.get("last_seen") or ""), str(edge.get("last_seen") or ""))
        item["relation_types"].add(str(edge.get("relation_type") or ""))
        if len(item["evidence_items"]) < 50:
            remaining = 50 - len(item["evidence_items"])
            item["evidence_items"].extend(evidence_items[:remaining])

    display_edges = []
    for item in merged.values():
        relation_types = sorted(value for value in item["relation_types"] if value)
        item["relation_types"] = relation_types
        item["relation_type"] = " + ".join(relation_types) if relation_types else "interactions"
        display_edges.append(item)
    return display_edges


def min_nonempty(current: str, incoming: str) -> str:
    if not current:
        return incoming
    if not incoming:
        return current
    return min(current, incoming)


def max_nonempty(current: str, incoming: str) -> str:
    if not current:
        return incoming
    if not incoming:
        return current
    return max(current, incoming)


def attach_overlay_evidence_items(conn, edges: list[dict[str, object]], platform: str, limit_per_edge: int = 10) -> None:
    edge_keys = {
        (str(edge["source_node"]), str(edge["target_node"]), str(edge["relation_type"]))
        for edge in edges
    }
    if not edge_keys:
        return

    evidence_by_edge: dict[tuple[str, str, str], list[dict[str, object]]] = {}
    rows = conn.execute(
        """
        SELECT i.interaction_id,
               i.source_account_id,
               i.target_account_id,
               i.interaction_type,
               i.source_record_id AS comment_id,
               i.parent_source_record_id AS parent_comment_id,
               COALESCE(p.platform_post_id, i.post_id, '') AS post_id,
               COALESCE(p.content, '') AS post_content,
               COALESCE(p.url, '') AS post_url,
               i.content,
               i.created_at,
               i.like_count
        FROM interactions i
        LEFT JOIN posts p ON p.post_id = i.post_id
        WHERE i.platform = ?
          AND i.source_account_id != i.target_account_id
          AND i.interaction_type IN ('comment', 'reply')
        ORDER BY COALESCE(i.created_at, i.last_seen, i.first_seen, '') DESC,
                 i.interaction_id DESC
        """,
        (platform,),
    ).fetchall()

    for row in rows:
        relation_type = interaction_relation_type(str(row["interaction_type"] or ""))
        if relation_type is None:
            continue
        key = (str(row["source_account_id"]), str(row["target_account_id"]), relation_type)
        if key not in edge_keys:
            continue
        items = evidence_by_edge.setdefault(key, [])
        if len(items) >= limit_per_edge:
            continue
        items.append(
            {
                "interaction_id": row["interaction_id"] or "",
                "interaction_type": row["interaction_type"] or "",
                "comment_id": row["comment_id"] or "",
                "parent_comment_id": row["parent_comment_id"] or "",
                "post_id": row["post_id"] or "",
                "post_content": row["post_content"] or "",
                "post_url": row["post_url"] or "",
                "content": row["content"] or "",
                "created_at": row["created_at"] or "",
                "like_count": row["like_count"] if row["like_count"] is not None else "",
            }
        )

    for edge in edges:
        key = (str(edge["source_node"]), str(edge["target_node"]), str(edge["relation_type"]))
        edge["evidence_items"] = evidence_by_edge.get(key, [])


def interaction_relation_type(interaction_type: str) -> str | None:
    if interaction_type == "comment":
        return "commented_on"
    if interaction_type == "reply":
        return "replied_to"
    return None


def node_value(node: object, key: str) -> object:
    if isinstance(node, dict):
        return node.get(key)
    try:
        return node[key]  # type: ignore[index]
    except (IndexError, KeyError, TypeError):
        return None
