"""Douyin platform adapter."""

from __future__ import annotations

import asyncio
import copy
import json
import random
import re
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import httpx

from adapters.base import AccountRecord, CommentCrawlResult, CommentRecord, PlatformAdapter, PostRecord
from adapters.minimal_platform import (
    BrowserSession,
    MinimalAdapterError,
    MinimalCommentAdapter,
    filter_new_comments,
    first_value,
    profile_session_error,
    to_int,
)
from adapters.osge_http_clients import OsgePlatformRequestError, make_async_client


DOUYIN_BLOCKED_RESPONSE_MESSAGE = (
    "Douyin request was blocked or returned an empty response; "
    "open Douyin in the current OSGE Chromium window, complete login or platform verification, then retry."
)


class OsgeDouyinClient:
    def __init__(
        self,
        *,
        headers: dict[str, str],
        playwright_page: Any,
        cookie_dict: dict[str, str],
        timeout: int = 60,
    ) -> None:
        self.headers = headers
        self.playwright_page = playwright_page
        self.cookie_dict = cookie_dict
        self.timeout = timeout
        self._host = "https://www.douyin.com"

    async def request(self, method: str, url: str, **kwargs: Any) -> dict[str, Any]:
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                async with make_async_client() as client:
                    response = await client.request(method, url, timeout=self.timeout, **kwargs)
                if response.text in {"", "blocked"}:
                    raise OsgePlatformRequestError(DOUYIN_BLOCKED_RESPONSE_MESSAGE)
                return response.json()
            except (httpx.HTTPError, json.JSONDecodeError, OsgePlatformRequestError) as exc:
                last_error = exc
                if attempt < 2:
                    await asyncio.sleep(1)
        raise OsgePlatformRequestError(f"Douyin request failed: {last_error}") from last_error

    async def get(
        self,
        uri: str,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        params = dict(params or {})
        headers = headers or self.headers
        await self._prepare_params(uri, params, headers=headers)
        return await self.request("GET", f"{self._host}{uri}", params=params, headers=headers)

    async def _prepare_params(self, uri: str, params: dict[str, Any], *, headers: dict[str, str]) -> None:
        if not params:
            return
        local_storage = await self.playwright_page.evaluate("() => window.localStorage")
        common_params = {
            "device_platform": "webapp",
            "aid": "6383",
            "channel": "channel_pc_web",
            "version_code": "190600",
            "version_name": "19.6.0",
            "update_version_code": "170400",
            "pc_client_type": "1",
            "cookie_enabled": "true",
            "browser_language": "zh-CN",
            "browser_platform": "MacIntel",
            "browser_name": "Chrome",
            "browser_version": "125.0.0.0",
            "browser_online": "true",
            "engine_name": "Blink",
            "os_name": "Mac OS",
            "os_version": "10.15.7",
            "cpu_core_num": "8",
            "device_memory": "8",
            "engine_version": "109.0",
            "platform": "PC",
            "screen_width": "2560",
            "screen_height": "1440",
            "effective_type": "4g",
            "round_trip_time": "50",
            "webid": get_douyin_web_id(),
            "msToken": (local_storage or {}).get("xmst"),
        }
        params.update(common_params)
        query_string = urllib.parse.urlencode(params)
        if "/v1/web/general/search" not in uri:
            params["a_bogus"] = sign_douyin_a_bogus(uri, query_string, headers["User-Agent"])

    async def get_user_info(self, sec_user_id: str) -> dict[str, Any]:
        return await self.get(
            "/aweme/v1/web/user/profile/other/",
            {
                "sec_user_id": sec_user_id,
                "publish_video_strategy_type": 2,
                "personal_center_strategy": 1,
            },
        )

    async def get_user_aweme_posts(self, sec_user_id: str, max_cursor: str = "") -> dict[str, Any]:
        return await self.get(
            "/aweme/v1/web/aweme/post/",
            {
                "sec_user_id": sec_user_id,
                "count": 18,
                "max_cursor": max_cursor,
                "locate_query": "false",
                "publish_video_strategy_type": 2,
            },
        )

    async def get_all_user_aweme_posts(self, sec_user_id: str, *, max_count: int) -> list[dict[str, Any]]:
        posts: list[dict[str, Any]] = []
        has_more = 1
        max_cursor = ""
        while has_more == 1 and (not max_count or len(posts) < max_count):
            response = await self.get_user_aweme_posts(sec_user_id, max_cursor)
            has_more = int(response.get("has_more", 0) or 0)
            max_cursor = str(response.get("max_cursor") or "")
            aweme_list = list(response.get("aweme_list") or [])
            if max_count:
                aweme_list = aweme_list[: max_count - len(posts)]
            posts.extend(aweme_list)
        return posts

    async def get_video_by_id(self, aweme_id: str) -> dict[str, Any]:
        headers = copy.copy(self.headers)
        headers.pop("Origin", None)
        response = await self.get("/aweme/v1/web/aweme/detail/", {"aweme_id": aweme_id}, headers=headers)
        return dict(response.get("aweme_detail") or {})

    async def get_aweme_comments(self, aweme_id: str, cursor: int = 0) -> dict[str, Any]:
        headers = copy.copy(self.headers)
        headers["Referer"] = f"https://www.douyin.com/video/{aweme_id}"
        return await self.get(
            "/aweme/v1/web/comment/list/",
            {"aweme_id": aweme_id, "cursor": cursor, "count": 20, "item_type": 0},
            headers=headers,
        )

    async def get_sub_comments(self, aweme_id: str, comment_id: str, cursor: int = 0) -> dict[str, Any]:
        headers = copy.copy(self.headers)
        headers["Referer"] = f"https://www.douyin.com/video/{aweme_id}"
        return await self.get(
            "/aweme/v1/web/comment/list/reply/",
            {
                "comment_id": comment_id,
                "cursor": cursor,
                "count": 20,
                "item_type": 0,
                "item_id": aweme_id,
            },
            headers=headers,
        )


_DOUYIN_SIGNER: Any | None = None


def sign_douyin_a_bogus(uri: str, params: str, user_agent: str) -> str:
    signer = _douyin_signer()
    function_name = "sign_reply" if "/reply" in uri else "sign_datail"
    return str(signer.call(function_name, params, user_agent))


def _douyin_signer() -> Any:
    global _DOUYIN_SIGNER
    if _DOUYIN_SIGNER is None:
        try:
            import execjs
        except ModuleNotFoundError as exc:
            raise OsgePlatformRequestError("Douyin signing requires pyexecjs and a JS runtime.") from exc
        js_path = Path(__file__).resolve().parent / "assets" / "douyin.js"
        _DOUYIN_SIGNER = execjs.compile(js_path.read_text(encoding="utf-8-sig"))
    return _DOUYIN_SIGNER


def get_douyin_web_id() -> str:
    def fragment(value: int | None) -> str:
        if value is not None:
            return str(value ^ (int(16 * random.random()) >> (value // 4)))
        return "".join([str(int(1e7)), "-", str(int(1e3)), "-", str(int(4e3)), "-", str(int(8e3)), "-", str(int(1e11))])

    web_id = "".join(fragment(int(char)) if char in "018" else char for char in fragment(None))
    return web_id.replace("-", "")[:19]


def extract_douyin_sec_uid(value: str) -> str:
    value = value.strip()
    if value.startswith("douyin:"):
        value = value.split(":", 1)[1]
    parsed = urllib.parse.urlparse(value)
    query = urllib.parse.parse_qs(parsed.query)
    sec_uid = (query.get("sec_uid") or [""])[0]
    if sec_uid:
        return sec_uid
    match = re.search(r"/(?:share/)?user/([^/?\s]+)", value)
    if match:
        value = match.group(1)
    if not value or "/" in value or ":" in value:
        raise ValueError(f"Cannot parse Douyin sec_uid from: {value}")
    return value


def normalize_douyin_profile_input(value: str) -> tuple[str, str]:
    candidate = value.strip()
    if is_douyin_short_url(candidate):
        candidate = resolve_douyin_short_url(candidate)

    platform_user_id = extract_douyin_sec_uid(candidate)
    return platform_user_id, f"https://www.douyin.com/user/{platform_user_id}"


def is_douyin_short_url(value: str) -> bool:
    parsed = urllib.parse.urlparse(value.strip())
    host = (parsed.netloc or "").lower()
    return host in {"v.douyin.com", "www.v.douyin.com"}


def resolve_douyin_short_url(value: str, timeout: float = 12.0) -> str:
    request = urllib.request.Request(
        value.strip(),
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.geturl()
    except urllib.error.URLError as exc:
        raise ValueError(f"Cannot resolve Douyin short URL: {exc}") from exc


class DouyinMinimalAdapter(MinimalCommentAdapter):
    platform = "douyin"
    index_url = "https://www.douyin.com"
    cookie_urls = [
        "https://douyin.com",
        index_url,
        "https://creator.douyin.com",
        "https://douhot.douyin.com",
        "https://live.douyin.com",
    ]

    async def fetch_profile(self, account_url: str) -> AccountRecord:
        async with self.browser_session() as session:
            return await self.fetch_profile_in_session(session, account_url)

    async def fetch_profile_in_session(self, session: BrowserSession, account_url: str) -> AccountRecord:
        sec_uid = extract_douyin_sec_uid(account_url)
        client = await self._client(session)
        try:
            profile = await client.get_user_info(sec_uid)
        except OsgePlatformRequestError:
            raise MinimalAdapterError(profile_session_error("Douyin")) from None
        if not (profile.get("user") or {}):
            raise MinimalAdapterError(profile_session_error("Douyin"))
        return _douyin_profile_record(sec_uid, account_url, profile)

    async def fetch_posts(self, account_id: str, limit: int, *, platform_context: Mapping[str, str] | None = None) -> list[PostRecord]:
        async with self.browser_session() as session:
            return await self.fetch_posts_in_session(
                session,
                account_id,
                limit,
                platform_context=platform_context,
            )

    async def fetch_posts_in_session(
        self,
        session: BrowserSession,
        account_id: str,
        limit: int,
        *,
        platform_context: Mapping[str, str] | None = None,
    ) -> list[PostRecord]:
        client = await self._client(session)
        awemes = await client.get_all_user_aweme_posts(account_id, max_count=limit)
        records: list[PostRecord] = []
        for item in awemes[:limit]:
            aweme_id = str(item.get("aweme_id") or "")
            if not aweme_id:
                continue
            detail = await client.get_video_by_id(aweme_id)
            if detail:
                records.append(_douyin_post_record(detail))
        return records

    async def fetch_comments(
        self,
        post_id: str,
        limit: int,
        *,
        platform_context: Mapping[str, str] | None = None,
        get_sub_comments: bool = False,
        known_comment_ids: set[str] | None = None,
    ) -> CommentCrawlResult:
        async with self.browser_session() as session:
            return await self.fetch_comments_in_session(
                session,
                post_id,
                limit,
                platform_context=platform_context,
                get_sub_comments=get_sub_comments,
                known_comment_ids=known_comment_ids,
            )

    async def fetch_comments_in_session(
        self,
        session: BrowserSession,
        post_id: str,
        limit: int,
        *,
        platform_context: Mapping[str, str] | None = None,
        get_sub_comments: bool = False,
        known_comment_ids: set[str] | None = None,
    ) -> CommentCrawlResult:
        known = set(known_comment_ids or set())
        records: list[CommentRecord] = []
        pages_seen = 0
        stopped = False
        client = await self._client(session)
        has_more = 1
        cursor = 0
        known_streak = 0
        while has_more and len(records) < limit:
            response = await client.get_aweme_comments(post_id, cursor)
            pages_seen += 1
            has_more = int(response.get("has_more", 0) or 0)
            cursor = int(response.get("cursor", 0) or 0)
            page_comments = list(response.get("comments") or [])
            if not page_comments:
                break
            page_comments, stopped = filter_new_comments(page_comments, known, _douyin_comment_id, known_streak=known_streak)
            known_streak = page_comments.known_streak
            if stopped:
                break
            records.extend(_douyin_comment_records(post_id, page_comments.new_comments, known, limit - len(records)))
            if not get_sub_comments:
                await asyncio.sleep(self.config.crawl_interval)
                continue
            for comment in page_comments.traversal_comments:
                if len(records) >= limit:
                    break
                if int(comment.get("reply_comment_total") or 0) <= 0:
                    continue
                root_comment_id = str(comment.get("cid") or "")
                sub_has_more = 1
                sub_cursor = 0
                sub_known_streak = 0
                while sub_has_more and len(records) < limit:
                    sub_response = await client.get_sub_comments(post_id, root_comment_id, sub_cursor)
                    pages_seen += 1
                    sub_has_more = int(sub_response.get("has_more", 0) or 0)
                    sub_cursor = int(sub_response.get("cursor", 0) or 0)
                    sub_comments = list(sub_response.get("comments") or [])
                    if not sub_comments:
                        break
                    sub_comments, sub_stopped = filter_new_comments(
                        sub_comments,
                        known,
                        _douyin_comment_id,
                        known_streak=sub_known_streak,
                    )
                    sub_known_streak = sub_comments.known_streak
                    if sub_stopped:
                        break
                    records.extend(_douyin_comment_records(post_id, sub_comments.new_comments, known, limit - len(records)))
                    await asyncio.sleep(self.config.crawl_interval)
            await asyncio.sleep(self.config.crawl_interval)
        return CommentCrawlResult(self.platform, post_id, records, stopped_on_known=stopped, pages_seen=pages_seen)

    async def _client(self, session: BrowserSession) -> OsgeDouyinClient:
        cookie_str, cookie_dict = await session.cookies()
        return OsgeDouyinClient(
            headers={
                "User-Agent": await session.user_agent(),
                "Cookie": cookie_str,
                "Host": "www.douyin.com",
                "Origin": "https://www.douyin.com/",
                "Referer": "https://www.douyin.com/",
                "Content-Type": "application/json;charset=UTF-8",
            },
            playwright_page=session.page,
            cookie_dict=cookie_dict,
        )


def _douyin_profile_record(sec_uid: str, profile_url: str, profile: dict[str, Any]) -> AccountRecord:
    user = profile.get("user") or {}
    avatar_uri = ((user.get("avatar_300x300") or {}).get("uri") or "")
    avatar_url = f"https://p3-pc.douyinpic.com/img/{avatar_uri}~c5_300x300.jpeg?from=2956013662" if avatar_uri else ""
    return AccountRecord(
        platform="douyin",
        platform_user_id=sec_uid,
        username=str(user.get("unique_id") or user.get("short_id") or sec_uid),
        nickname=str(user.get("nickname") or ""),
        profile_url=profile_url,
        avatar_url=avatar_url,
        bio=str(user.get("signature") or ""),
        location=str(user.get("ip_location") or ""),
    )


def _douyin_post_record(aweme: dict[str, Any]) -> PostRecord:
    user = aweme.get("author") or {}
    statistics = aweme.get("statistics") or {}
    aweme_id = str(aweme.get("aweme_id") or "")
    return PostRecord(
        platform="douyin",
        platform_post_id=aweme_id,
        author_platform_user_id=str(user.get("sec_uid") or user.get("uid") or ""),
        content=str(aweme.get("desc") or ""),
        url=f"https://www.douyin.com/video/{aweme_id}",
        created_at=str(aweme.get("create_time") or ""),
        like_count=to_int(statistics.get("digg_count")),
        comment_count=to_int(statistics.get("comment_count")),
        repost_count=to_int(statistics.get("share_count")),
    )


def _douyin_comment_records(
    aweme_id: str,
    comments: list[dict[str, Any]],
    known: set[str],
    remaining: int,
) -> list[CommentRecord]:
    records: list[CommentRecord] = []
    for comment in comments:
        if remaining <= 0:
            break
        comment_id = _douyin_comment_id(comment)
        if not comment_id or comment_id in known:
            continue
        user_info = comment.get("user") or {}
        avatar_info = (
            user_info.get("avatar_medium")
            or user_info.get("avatar_300x300")
            or user_info.get("avatar_168x168")
            or user_info.get("avatar_thumb")
            or {}
        )
        records.append(
            CommentRecord(
                platform="douyin",
                platform_post_id=aweme_id,
                comment_id=comment_id,
                author_platform_user_id=str(user_info.get("sec_uid") or user_info.get("uid") or ""),
                author_username=str(user_info.get("unique_id") or user_info.get("short_id") or user_info.get("sec_uid") or ""),
                author_nickname=str(user_info.get("nickname") or ""),
                author_avatar_url=first_value(avatar_info.get("url_list") or []),
                content=str(comment.get("text") or ""),
                created_at=str(comment.get("create_time") or ""),
                parent_comment_id=str(comment.get("reply_id") or ""),
                like_count=to_int(comment.get("digg_count")),
            )
        )
        known.add(comment_id)
        remaining -= 1
    return records


def _douyin_comment_id(comment: dict[str, Any]) -> str:
    return str(comment.get("cid") or comment.get("comment_id") or "").strip()


class DouyinAdapter(DouyinMinimalAdapter, PlatformAdapter):
    platform = "douyin"
