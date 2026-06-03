from __future__ import annotations

from datetime import datetime, timezone


RELATION_RULES = {
    "comment": ("commented_on", 2.0, 0.80),
    "reply": ("replied_to", 2.0, 0.80),
    "repost": ("reposted", 3.0, 0.85),
    "follow": ("follows", 30.0, 0.90),
    "mention": ("mentioned", 1.5, 0.70),
}


def parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    normalized = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def time_decay(last_seen: str | None, as_of: datetime | None = None) -> float:
    seen_at = parse_datetime(last_seen)
    if seen_at is None:
        return 1.0
    now = as_of or datetime.now(timezone.utc)
    delta_days = max((now - seen_at).days, 0)
    if delta_days <= 7:
        return 1.0
    if delta_days <= 30:
        return 0.7
    if delta_days <= 90:
        return 0.4
    return 0.1


def relation_rule(interaction_type: str) -> tuple[str, float, float] | None:
    return RELATION_RULES.get(interaction_type)
