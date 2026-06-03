from __future__ import annotations

import hashlib
import math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from core.db import DEFAULT_DB_PATH, connect
from core.scoring import parse_datetime, relation_rule, time_decay


def stable_id(*parts: object) -> str:
    raw = "|".join("" if part is None else str(part) for part in parts)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def _iso_min(values: list[str]) -> str | None:
    parsed = [(parse_datetime(value), value) for value in values if value]
    parsed = [(dt, value) for dt, value in parsed if dt is not None]
    if not parsed:
        return None
    return min(parsed, key=lambda item: item[0])[1]


def _iso_max(values: list[str]) -> str | None:
    parsed = [(parse_datetime(value), value) for value in values if value]
    parsed = [(dt, value) for dt, value in parsed if dt is not None]
    if not parsed:
        return None
    return max(parsed, key=lambda item: item[0])[1]


def _evidence_value(source: str, target: str, relation_type: str, count: int, first_seen: str | None, last_seen: str | None, raw_weight: float, decay: float, weight: float) -> str:
    relation_labels = {
        "commented_on": "public comments/replies",
        "replied_to": "public replies",
        "reposted": "public reposts",
        "follows": "public follow record",
        "mentioned": "public mentions",
        "mutual_follow": "reciprocal public follow records",
    }
    label = relation_labels.get(relation_type, relation_type)
    return (
        f"{source} -> {target}: {count} {label}; "
        f"first_seen={first_seen or 'unknown'}; last_seen={last_seen or 'unknown'}; "
        f"raw_weight={raw_weight}; time_decay={decay}; final_weight={weight}"
    )


def _post_popularity_penalty(comment_count: int | None) -> float:
    if comment_count is None or comment_count <= 0:
        return 1.0
    return max(0.15, 1.0 / (1.0 + math.log10(comment_count + 1)))


def _distinct_post_boost(post_count: int) -> float:
    if post_count <= 1:
        return 1.0
    return 1.0 + min(math.log1p(post_count - 1) * 0.35, 1.25)


def _same_location_boost(source_location: str | None, target_location: str | None) -> float:
    source = (source_location or "").strip()
    target = (target_location or "").strip()
    if not source or not target or source.lower() in {"unknown", "未知"} or target.lower() in {"unknown", "未知"}:
        return 1.0
    return 1.2 if source == target else 1.0


def _interaction_score(interaction_type: str, comment_count: int | None) -> tuple[str, float, float] | None:
    rule = relation_rule(interaction_type)
    if rule is None:
        return None
    relation_type, multiplier, confidence = rule
    if interaction_type == "reply":
        multiplier *= 1.5
        confidence = max(confidence, 0.86)
    if interaction_type == "comment":
        confidence = min(confidence, 0.78)
    if interaction_type in {"comment", "reply"}:
        multiplier *= _post_popularity_penalty(comment_count)
    return relation_type, multiplier, confidence


def build_edges(db_path: Path | str = DEFAULT_DB_PATH, as_of: datetime | None = None) -> dict[str, int]:
    as_of = as_of or datetime.now(timezone.utc)
    with connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT interaction_id, source_account_id, target_account_id,
                   interaction_type, i.post_id, i.created_at,
                   COALESCE(p.comment_count, 0) AS post_comment_count,
                   s.location AS source_location,
                   t.location AS target_location
            FROM interactions i
            LEFT JOIN posts p ON p.post_id = i.post_id
            LEFT JOIN accounts s ON s.account_id = i.source_account_id
            LEFT JOIN accounts t ON t.account_id = i.target_account_id
            WHERE source_account_id IS NOT NULL
              AND target_account_id IS NOT NULL
              AND source_account_id != target_account_id
            """
        ).fetchall()

        aggregates: dict[tuple[str, str, str], dict[str, object]] = defaultdict(
            lambda: {
                "count": 0,
                "first_seen": [],
                "last_seen": [],
                "interaction_ids": [],
                "post_ids": set(),
                "raw_weight": 0.0,
                "confidence_values": [],
            }
        )

        for row in rows:
            scored = _interaction_score(row["interaction_type"], row["post_comment_count"])
            if scored is None:
                continue
            relation_type, contribution, confidence = scored
            location_boost = _same_location_boost(row["source_location"], row["target_location"])
            contribution *= location_boost
            if location_boost > 1:
                confidence = min(confidence + 0.03, 0.95)
            key = (row["source_account_id"], row["target_account_id"], relation_type)
            aggregates[key]["count"] = int(aggregates[key]["count"]) + 1
            aggregates[key]["first_seen"].append(row["created_at"])
            aggregates[key]["last_seen"].append(row["created_at"])
            aggregates[key]["interaction_ids"].append(row["interaction_id"])
            aggregates[key]["raw_weight"] = float(aggregates[key]["raw_weight"]) + contribution
            aggregates[key]["confidence_values"].append(confidence)
            if row["post_id"]:
                aggregates[key]["post_ids"].add(row["post_id"])

        conn.execute("DELETE FROM evidences")
        conn.execute("DELETE FROM edges")

        edge_count = 0
        evidence_count = 0
        follow_pairs = set()

        for (source, target, relation_type), item in aggregates.items():
            count = int(item["count"])
            first_seen = _iso_min(item["first_seen"])
            last_seen = _iso_max(item["last_seen"])
            evidence_source_id = ",".join(item["interaction_ids"][:10])

            if relation_type == "follows":
                raw_weight = 30.0
                confidence = 0.90
                follow_pairs.add((source, target))
            else:
                distinct_posts = len(item["post_ids"])
                raw_weight = float(item["raw_weight"]) * _distinct_post_boost(distinct_posts)
                confidence_values = item["confidence_values"]
                confidence = max(confidence_values) if confidence_values else 0.75
                if distinct_posts >= 2:
                    confidence = min(confidence + 0.04, 0.92)
                if distinct_posts >= 4:
                    confidence = min(confidence + 0.04, 0.95)

            decay = time_decay(last_seen, as_of)
            weight = round(raw_weight * decay, 4)
            edge_id = stable_id(source, relation_type, target)
            evidence_id = stable_id("evidence", edge_id, evidence_source_id)
            evidence_value = _evidence_value(
                source,
                target,
                relation_type,
                count,
                first_seen,
                last_seen,
                raw_weight,
                decay,
                weight,
            )

            conn.execute(
                """
                INSERT INTO edges (
                    edge_id, source_node, target_node, relation_type, weight,
                    confidence, interaction_count, first_seen, last_seen,
                    is_inferred, evidence_count, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 1, CURRENT_TIMESTAMP)
                """,
                (
                    edge_id,
                    source,
                    target,
                    relation_type,
                    weight,
                    confidence,
                    count,
                    first_seen,
                    last_seen,
                ),
            )
            conn.execute(
                """
                INSERT INTO evidences (
                    evidence_id, subject_node, object_node, evidence_type,
                    evidence_value, score, source_table, source_id
                )
                VALUES (?, ?, ?, ?, ?, ?, 'interactions', ?)
                """,
                (
                    evidence_id,
                    source,
                    target,
                    relation_type,
                    evidence_value,
                    weight,
                    evidence_source_id,
                ),
            )
            edge_count += 1
            evidence_count += 1

        for source, target in sorted(follow_pairs):
            if (target, source) not in follow_pairs:
                continue
            relation_type = "mutual_follow"
            edge_id = stable_id(source, relation_type, target)
            evidence_id = stable_id("evidence", edge_id)
            conn.execute(
                """
                INSERT OR IGNORE INTO edges (
                    edge_id, source_node, target_node, relation_type, weight,
                    confidence, interaction_count, first_seen, last_seen,
                    is_inferred, evidence_count, updated_at
                )
                VALUES (?, ?, ?, ?, 60, 0.95, 2, NULL, NULL, 1, 1, CURRENT_TIMESTAMP)
                """,
                (edge_id, source, target, relation_type),
            )
            conn.execute(
                """
                INSERT OR IGNORE INTO evidences (
                    evidence_id, subject_node, object_node, evidence_type,
                    evidence_value, score, source_table, source_id
                )
                VALUES (?, ?, ?, ?, ?, 60, 'edges', ?)
                """,
                (
                    evidence_id,
                    source,
                    target,
                    relation_type,
                    _evidence_value(source, target, relation_type, 2, None, None, 60, 1.0, 60),
                    edge_id,
                ),
            )
            edge_count += 1
            evidence_count += 1

        return {"edges": edge_count, "evidences": evidence_count}
