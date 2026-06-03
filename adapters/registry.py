from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from adapters.minimal_platform import MinimalAdapterConfig


ContextExtractor = Callable[[str], dict[str, str]]


def _empty_context(_: str) -> dict[str, str]:
    return {}


@dataclass(frozen=True)
class PlatformDefinition:
    platform_id: str
    display_name: str
    short_name: str
    base_url: str
    aliases: tuple[str, ...]
    url_markers: tuple[str, ...]
    adapter_factory: Callable[[MinimalAdapterConfig | None], Any]
    normalize_profile_input: Callable[[str], tuple[str, str]]
    context_from_url: ContextExtractor = _empty_context
    requires_comment_context: bool = False
    log_prefix: str = ""
    item_label: str = "posts"
    id_label: str = "平台 ID / Platform ID"
    display_id_field_order: tuple[str, ...] = ("platform_user_id", "username")
    expand_script: str = ""

    def create_adapter(self, config: MinimalAdapterConfig | None = None) -> Any:
        return self.adapter_factory(config)

    def matches_hint(self, value: str) -> bool:
        normalized = value.strip().lower()
        return normalized == self.platform_id or normalized in self.aliases

    def matches_account(self, value: str) -> bool:
        normalized = value.strip().lower()
        prefixes = (self.platform_id, *self.aliases)
        if any(normalized.startswith(f"{prefix}:") for prefix in prefixes):
            return True
        return any(marker in normalized for marker in self.url_markers)

    def ui_metadata(self) -> dict[str, object]:
        return {
            "id": self.platform_id,
            "displayName": self.display_name,
            "shortName": self.short_name,
            "aliases": list(self.aliases),
            "urlMarkers": list(self.url_markers),
            "idLabel": self.id_label,
            "displayIdFieldOrder": list(self.display_id_field_order),
            "expandScript": self.expand_script,
        }


def _douyin_adapter(config: MinimalAdapterConfig | None = None) -> Any:
    from adapters.douyin import DouyinAdapter

    return DouyinAdapter(config)


def _xhs_adapter(config: MinimalAdapterConfig | None = None) -> Any:
    from adapters.xiaohongshu import XiaohongshuAdapter

    return XiaohongshuAdapter(config)


def _normalize_douyin(value: str) -> tuple[str, str]:
    from adapters.douyin import normalize_douyin_profile_input

    return normalize_douyin_profile_input(value)


def _normalize_xhs(value: str) -> tuple[str, str]:
    from adapters.xiaohongshu import normalize_xhs_profile_input

    return normalize_xhs_profile_input(value)


def _xhs_context(value: str) -> dict[str, str]:
    from adapters.xiaohongshu import xhs_context_from_url

    return xhs_context_from_url(value)


PLATFORMS: tuple[PlatformDefinition, ...] = (
    PlatformDefinition(
        platform_id="xiaohongshu",
        display_name="Xiaohongshu",
        short_name="小红书",
        base_url="https://www.xiaohongshu.com",
        aliases=("xhs", "rednote"),
        url_markers=("xiaohongshu.com", "xhslink.com"),
        adapter_factory=_xhs_adapter,
        normalize_profile_input=_normalize_xhs,
        context_from_url=_xhs_context,
        requires_comment_context=True,
        item_label="notes",
        id_label="小红书 ID / Rednote ID",
        display_id_field_order=("username", "platform_user_id"),
        expand_script="scripts/expand_account.py",
    ),
    PlatformDefinition(
        platform_id="douyin",
        display_name="Douyin",
        short_name="抖音",
        base_url="https://www.douyin.com",
        aliases=("dy",),
        url_markers=("douyin.com", "iesdouyin.com"),
        adapter_factory=_douyin_adapter,
        normalize_profile_input=_normalize_douyin,
        log_prefix="douyin_",
        item_label="awemes",
        id_label="抖音号 / Douyin ID",
        display_id_field_order=("username", "platform_user_id"),
        expand_script="scripts/expand_account.py",
    ),
)

PLATFORMS_BY_ID = {platform.platform_id: platform for platform in PLATFORMS}
DEFAULT_PLATFORM_ID = "xiaohongshu"


def supported_platform_ids() -> tuple[str, ...]:
    return tuple(platform.platform_id for platform in PLATFORMS)


def platform_ui_metadata() -> list[dict[str, object]]:
    return [platform.ui_metadata() for platform in PLATFORMS]


def get_platform(platform_id: str) -> PlatformDefinition:
    normalized = platform_id.strip().lower()
    for platform in PLATFORMS:
        if platform.matches_hint(normalized):
            return platform
    raise ValueError(f"Unsupported platform: {platform_id}")


def detect_platform(account: str = "", hint: str = "") -> PlatformDefinition:
    normalized_hint = hint.strip().lower()
    if normalized_hint:
        try:
            return get_platform(normalized_hint)
        except ValueError:
            pass

    for platform in PLATFORMS:
        if platform.matches_account(account):
            return platform
    return get_platform(DEFAULT_PLATFORM_ID)


def platform_display_name(platform_id: str) -> str:
    try:
        return get_platform(platform_id).display_name
    except ValueError:
        return "the platform"
