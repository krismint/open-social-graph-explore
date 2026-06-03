from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from adapters.base import AccountRecord, CommentCrawlResult, PostRecord
from adapters.osge_http_clients import convert_browser_context_cookies
from core.chromium_cdp import DEFAULT_CDP_PORT, ensure_chromium_cdp


KNOWN_COMMENT_STOP_STREAK = 3


@dataclass(frozen=True)
class NewCommentPage:
    new_comments: list[dict[str, Any]]
    traversal_comments: list[dict[str, Any]]
    known_streak: int = 0


class MinimalAdapterError(RuntimeError):
    pass


PROFILE_SESSION_ERROR_MARKER = "Platform profile fetch failed"


def profile_session_error(platform_name: str) -> str:
    return (
        f"{PROFILE_SESSION_ERROR_MARKER}: {platform_name} profile could not be fetched. "
        "The current OSGE Chromium session may not be logged in, or platform verification "
        f"blocked the request. Open {platform_name} in the current OSGE Chromium window, "
        "complete login or verification, then retry."
    )


@dataclass(frozen=True)
class MinimalAdapterConfig:
    cdp_port: int = DEFAULT_CDP_PORT
    crawl_interval: float = 1.0
    page_timeout_ms: int = 60_000


class MinimalCommentAdapter:
    platform: str

    def __init__(self, config: MinimalAdapterConfig | None = None) -> None:
        self.config = config or MinimalAdapterConfig()

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

    async def fetch_profile(self, account_url: str) -> AccountRecord:
        raise NotImplementedError

    async def fetch_posts(self, account_id: str, limit: int, *, platform_context: Mapping[str, str] | None = None) -> list[PostRecord]:
        raise NotImplementedError

    def browser_session(self) -> "BrowserSession":
        return BrowserSession(self.index_url, self.cookie_urls, self.config)


class BrowserSession:
    def __init__(self, index_url: str, cookie_urls: list[str], config: MinimalAdapterConfig) -> None:
        self.index_url = index_url
        self.cookie_urls = cookie_urls
        self.config = config
        self.playwright: Any = None
        self.browser: Any = None
        self.context: Any = None
        self.page: Any = None

    async def __aenter__(self) -> "BrowserSession":
        status = ensure_chromium_cdp(port=self.config.cdp_port)
        if not status.ok:
            raise MinimalAdapterError(f"Chromium CDP is not available: {status.error}")
        try:
            from playwright.async_api import async_playwright
        except ModuleNotFoundError as exc:
            raise MinimalAdapterError("OSGE minimal platform adapter needs playwright installed.") from exc
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.connect_over_cdp(f"http://127.0.0.1:{status.port}")
        self.context = self.browser.contexts[0] if self.browser.contexts else await self.browser.new_context()
        self.page = await self.context.new_page()
        self.page.set_default_navigation_timeout(self.config.page_timeout_ms)
        await self.page.goto(self.index_url, wait_until="domcontentloaded", timeout=self.config.page_timeout_ms)
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        if self.page:
            await self.page.close()
        if self.playwright:
            await self.playwright.stop()

    async def cookies(self) -> tuple[str, dict[str, str]]:
        return await convert_browser_context_cookies(self.context, urls=self.cookie_urls)

    async def user_agent(self) -> str:
        return str(await self.page.evaluate("() => navigator.userAgent"))


def filter_new_comments(
    comments: list[dict[str, Any]],
    known: set[str],
    id_getter,
    stop_streak: int = KNOWN_COMMENT_STOP_STREAK,
    known_streak: int = 0,
) -> tuple[NewCommentPage, bool]:
    if not comments or not known:
        return NewCommentPage(new_comments=comments, traversal_comments=comments), False
    new_comments: list[dict[str, Any]] = []
    traversal_comments: list[dict[str, Any]] = []
    for comment in comments:
        comment_id = id_getter(comment)
        if comment_id and comment_id in known:
            known_streak += 1
            if known_streak >= stop_streak:
                return NewCommentPage(new_comments=new_comments, traversal_comments=traversal_comments, known_streak=known_streak), True
            traversal_comments.append(comment)
            continue
        known_streak = 0
        new_comments.append(comment)
        traversal_comments.append(comment)
    return NewCommentPage(new_comments=new_comments, traversal_comments=traversal_comments, known_streak=known_streak), False


def first_value(values: list[Any]) -> str:
    return str(values[0]) if values else ""


def to_int(value: object) -> int:
    if value is None:
        return 0
    try:
        return int(float(str(value).replace(",", "")))
    except ValueError:
        return 0
