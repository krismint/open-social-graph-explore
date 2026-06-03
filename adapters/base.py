from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Protocol


PlatformContext = dict[str, str]


@dataclass(frozen=True)
class AccountRecord:
    platform: str
    platform_user_id: str
    username: str
    nickname: str = ""
    profile_url: str = ""
    avatar_url: str = ""
    bio: str = ""
    location: str = ""


@dataclass(frozen=True)
class PostRecord:
    platform: str
    platform_post_id: str
    author_platform_user_id: str
    content: str
    url: str = ""
    created_at: str = ""
    like_count: int = 0
    comment_count: int = 0
    repost_count: int = 0
    platform_context: PlatformContext = field(default_factory=dict)


@dataclass(frozen=True)
class InteractionRecord:
    platform: str
    source_platform_user_id: str
    target_platform_user_id: str
    platform_post_id: str
    interaction_type: str
    content: str = ""
    created_at: str = ""
    weight_raw: float = 1.0


@dataclass(frozen=True)
class CommentRecord:
    platform: str
    platform_post_id: str
    comment_id: str
    author_platform_user_id: str
    author_username: str = ""
    author_nickname: str = ""
    author_avatar_url: str = ""
    content: str = ""
    created_at: str = ""
    parent_comment_id: str = ""
    like_count: int = 0


@dataclass(frozen=True)
class CommentCrawlResult:
    platform: str
    platform_post_id: str
    comments: list[CommentRecord]
    stopped_on_known: bool = False
    pages_seen: int = 0


class PlatformAdapter(Protocol):
    platform: str

    async def fetch_profile(self, account_url: str) -> AccountRecord:
        raise NotImplementedError

    async def fetch_posts(self, account_id: str, limit: int, *, platform_context: Mapping[str, str] | None = None) -> list[PostRecord]:
        raise NotImplementedError

    def fetch_interactions(self, post_id: str, limit: int) -> list[InteractionRecord]:
        raise NotImplementedError

    async def fetch_comments(
        self,
        post_id: str,
        limit: int,
        *,
        platform_context: Mapping[str, str] | None = None,
        get_sub_comments: bool = False,
        known_comment_ids: set[str] | None = None,
    ) -> CommentCrawlResult:
        raise NotImplementedError
