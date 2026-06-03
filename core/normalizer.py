from __future__ import annotations

import hashlib


def account_id(platform: str, platform_user_id: str) -> str:
    return f"{platform}:{platform_user_id}"


def post_id(platform: str, platform_post_id: str) -> str:
    return f"{platform}:post:{platform_post_id}"


def interaction_id(platform: str, source_account_id: str, target_account_id: str, post_id_value: str, interaction_type: str, created_at: str) -> str:
    raw = "|".join([platform, source_account_id, target_account_id, post_id_value, interaction_type, created_at])
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]
    return f"{platform}:interaction:{digest}"
