"""Xiaohongshu platform adapter."""

from __future__ import annotations

import asyncio
import hashlib
import json
import random
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Mapping
from typing import Any

import httpx

from adapters.base import AccountRecord, CommentCrawlResult, CommentRecord, PlatformAdapter, PostRecord
from adapters.minimal_platform import (
    BrowserSession,
    MinimalAdapterError,
    MinimalCommentAdapter,
    filter_new_comments,
    profile_session_error,
    to_int,
)
from adapters.osge_http_clients import OsgePlatformRequestError, make_async_client


class OsgeXiaohongshuClient:
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
        self._host = "https://edith.xiaohongshu.com"
        self._domain = "https://www.xiaohongshu.com"

    async def request(self, method: str, url: str, **kwargs: Any) -> Any:
        return_response = bool(kwargs.pop("return_response", False))
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                async with make_async_client() as client:
                    response = await client.request(method, url, timeout=self.timeout, **kwargs)
                if return_response:
                    return response.text
                data = response.json()
                if data.get("success"):
                    return data.get("data", data.get("success", {}))
                code = data.get("code")
                if code in {-510000, -510001}:
                    return {}
                raise OsgePlatformRequestError(str(data.get("msg") or response.text))
            except (httpx.HTTPError, json.JSONDecodeError, OsgePlatformRequestError) as exc:
                last_error = exc
                if attempt < 2:
                    await asyncio.sleep(1)
        raise OsgePlatformRequestError(f"Xiaohongshu request failed: {last_error}") from last_error

    async def get(self, uri: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        params = params or {}
        headers = self._signed_headers(uri, params=params)
        query = self._build_query_string(params)
        url = f"{self._host}{uri}?{query}" if query else f"{self._host}{uri}"
        return await self.request("GET", url, headers=headers)

    async def post(self, uri: str, data: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
        headers = self._signed_headers(uri, payload=data)
        body = json.dumps(data, separators=(",", ":"), ensure_ascii=False)
        return await self.request("POST", f"{self._host}{uri}", data=body, headers=headers, **kwargs)

    def _signed_headers(
        self,
        uri: str,
        *,
        params: dict[str, Any] | None = None,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, str]:
        if params is not None:
            method = "GET"
            data = params
        elif payload is not None:
            method = "POST"
            data = payload
        else:
            raise ValueError("params or payload is required")
        signs = sign_xhs_request(uri, data=data, cookie_str=self.headers.get("Cookie", ""), method=method)
        headers = self.headers.copy()
        headers.update(
            {
                "X-S": signs["x-s"],
                "X-T": signs["x-t"],
                "x-S-Common": signs["x-s-common"],
                "X-B3-Traceid": signs["x-b3-traceid"],
            }
        )
        return headers

    @staticmethod
    def _build_query_string(params: dict[str, Any]) -> str:
        parts = []
        for key, value in params.items():
            if isinstance(value, list):
                value_str = ",".join(str(item) for item in value)
            elif value is None:
                value_str = ""
            else:
                value_str = str(value)
            parts.append(f"{key}={urllib.parse.quote(value_str, safe=',')}")
        return "&".join(parts)

    async def get_creator_info(self, user_id: str, xsec_token: str = "", xsec_source: str = "") -> dict[str, Any]:
        uri = f"/user/profile/{user_id}"
        if xsec_token and xsec_source:
            query = urllib.parse.urlencode({"xsec_token": xsec_token, "xsec_source": xsec_source})
            uri = f"{uri}?{query}"
        html = await self.request("GET", f"{self._domain}{uri}", return_response=True, headers=self.headers)
        return extract_xhs_creator_info(html)

    async def get_notes_by_creator(
        self,
        creator: str,
        cursor: str,
        *,
        page_size: int = 30,
        xsec_token: str = "",
        xsec_source: str = "pc_feed",
    ) -> dict[str, Any]:
        return await self.get(
            "/api/sns/web/v1/user_posted",
            {
                "num": page_size,
                "cursor": cursor,
                "user_id": creator,
                "image_formats": "jpg,webp,avif",
                "xsec_token": xsec_token,
                "xsec_source": xsec_source,
            },
        )

    async def get_all_notes_by_creator(
        self,
        user_id: str,
        *,
        max_count: int,
        crawl_interval: float = 1.0,
        xsec_token: str = "",
        xsec_source: str = "pc_feed",
    ) -> list[dict[str, Any]]:
        notes: list[dict[str, Any]] = []
        cursor = ""
        has_more = True
        while has_more and len(notes) < max_count:
            response = await self.get_notes_by_creator(
                user_id,
                cursor,
                xsec_token=xsec_token,
                xsec_source=xsec_source,
            )
            has_more = bool(response.get("has_more", False))
            cursor = str(response.get("cursor") or "")
            page_notes = list(response.get("notes") or [])
            remaining = max_count - len(notes)
            notes.extend(page_notes[:remaining])
            if has_more and len(notes) < max_count:
                await asyncio.sleep(crawl_interval)
        return notes

    async def get_note_by_id(self, note_id: str, xsec_source: str, xsec_token: str) -> dict[str, Any]:
        payload = {
            "source_note_id": note_id,
            "image_formats": ["jpg", "webp", "avif"],
            "extra": {"need_body_topic": 1},
            "xsec_source": xsec_source or "pc_search",
            "xsec_token": xsec_token,
        }
        response = await self.post("/api/sns/web/v1/feed", payload)
        items = list(response.get("items") or [])
        if not items:
            return {}
        note_card = dict((items[0] or {}).get("note_card") or {})
        return note_card

    async def get_note_comments(self, note_id: str, xsec_token: str, cursor: str = "") -> dict[str, Any]:
        return await self.get(
            "/api/sns/web/v2/comment/page",
            {
                "note_id": note_id,
                "cursor": cursor,
                "top_comment_id": "",
                "image_formats": "jpg,webp,avif",
                "xsec_token": xsec_token,
            },
        )

    async def get_note_sub_comments(
        self,
        note_id: str,
        root_comment_id: str,
        xsec_token: str,
        *,
        num: int = 10,
        cursor: str = "",
    ) -> dict[str, Any]:
        return await self.get(
            "/api/sns/web/v2/comment/sub/page",
            {
                "note_id": note_id,
                "root_comment_id": root_comment_id,
                "num": str(num),
                "cursor": cursor,
                "image_formats": "jpg,webp,avif",
                "top_comment_id": "",
                "xsec_token": xsec_token,
            },
        )


def extract_xhs_creator_info(html: str) -> dict[str, Any]:
    match = re.search(r"<script>window.__INITIAL_STATE__=(.+?)</script>", html, re.M | re.S)
    if not match:
        return {}
    state = match.group(1).replace(":undefined", ":null").replace("undefined", "null")
    try:
        info = json.loads(state, strict=False)
    except json.JSONDecodeError:
        return {}
    return dict(((info or {}).get("user") or {}).get("userPageData") or {})


_XHSHOW_PATCHED = False


def sign_xhs_request(
    uri: str,
    *,
    data: dict[str, Any] | str | None = None,
    cookie_str: str = "",
    method: str = "POST",
) -> dict[str, str]:
    try:
        _patch_xhshow_a3_hash()
        from xhshow import Xhshow
    except ModuleNotFoundError as exc:
        raise OsgePlatformRequestError("Xiaohongshu signing requires xhshow.") from exc
    xhshow_client = Xhshow()
    if method.upper() == "POST":
        headers = xhshow_client.sign_headers_post(
            uri=uri,
            cookies=cookie_str,
            payload=data if isinstance(data, dict) else {},
        )
    else:
        content_string = _build_xhs_sign_string(uri, data=data, method=method)
        cookie_dict = xhshow_client._parse_cookies(cookie_str)
        a1_value = cookie_dict.get("a1", "")
        timestamp = time.time()
        d_value = hashlib.md5(content_string.encode("utf-8")).hexdigest()
        payload_array = xhshow_client.crypto_processor.build_payload_array(
            d_value,
            a1_value,
            "xhs-pc-web",
            content_string,
            timestamp,
        )
        xor_result = xhshow_client.crypto_processor.bit_ops.xor_transform_array(payload_array)
        config = xhshow_client.config
        x3_b64 = xhshow_client.crypto_processor.b64encoder.encode_x3(xor_result[: config.PAYLOAD_LENGTH])
        sig_data = config.SIGNATURE_DATA_TEMPLATE.copy()
        sig_data["x3"] = config.X3_PREFIX + x3_b64
        x_s = config.XYS_PREFIX + xhshow_client.crypto_processor.b64encoder.encode(
            json.dumps(sig_data, separators=(",", ":"), ensure_ascii=False)
        )
        headers = {
            "x-s": x_s,
            "x-s-common": xhshow_client.sign_xs_common(cookie_dict),
            "x-t": str(xhshow_client.get_x_t(timestamp)),
            "x-b3-traceid": xhshow_client.get_b3_trace_id(),
        }
    return {
        "x-s": str(headers.get("x-s", "")),
        "x-t": str(headers.get("x-t", "")),
        "x-s-common": str(headers.get("x-s-common", "")),
        "x-b3-traceid": str(headers.get("x-b3-traceid") or _trace_id()),
    }


def _patch_xhshow_a3_hash() -> None:
    global _XHSHOW_PATCHED
    if _XHSHOW_PATCHED:
        return
    from xhshow.core.crypto import CryptoProcessor

    original_build = CryptoProcessor.build_payload_array

    def patched_build(
        self: Any,
        hex_parameter: Any,
        a1_value: Any,
        app_identifier: str = "xhs-pc-web",
        string_param: str = "",
        timestamp: float | None = None,
        sign_state: Any = None,
    ) -> Any:
        payload = original_build(self, hex_parameter, a1_value, app_identifier, string_param, timestamp, sign_state)
        if "{" not in string_param:
            correct_md5_hex = hashlib.md5(string_param.encode("utf-8")).hexdigest()
            correct_md5_bytes = [int(correct_md5_hex[i:i + 2], 16) for i in range(0, 32, 2)]
            seed_byte = payload[4]
            ts_bytes = payload[8:16]
            correct_a3_hash = self._custom_hash_v2(list(ts_bytes) + correct_md5_bytes)
            for index in range(16):
                payload[128 + index] = correct_a3_hash[index] ^ seed_byte
        return payload

    CryptoProcessor.build_payload_array = patched_build
    _XHSHOW_PATCHED = True


def _build_xhs_sign_string(uri: str, data: dict[str, Any] | str | None = None, method: str = "POST") -> str:
    if method.upper() == "POST":
        if isinstance(data, dict):
            return uri + json.dumps(data, separators=(",", ":"), ensure_ascii=False)
        if isinstance(data, str):
            return uri + data
        return uri
    if not data or (isinstance(data, dict) and not data):
        return uri
    if isinstance(data, str):
        return f"{uri}?{data}"
    params = []
    for key, value in data.items():
        if isinstance(value, list):
            value_str = ",".join(str(item) for item in value)
        elif value is None:
            value_str = ""
        else:
            value_str = str(value)
        params.append(f"{key}={urllib.parse.quote(value_str, safe=',')}")
    return f"{uri}?{'&'.join(params)}"


def _trace_id() -> str:
    return "".join(random.choice("abcdef0123456789") for _ in range(16))


def xhs_context_from_url(value: str) -> dict[str, str]:
    parsed = urllib.parse.urlparse(value)
    query = urllib.parse.parse_qs(parsed.query)
    token = (query.get("xsec_token") or [""])[0]
    if not token:
        return {}
    source = (query.get("xsec_source") or ["pc_feed"])[0]
    return {"xsec_token": token, "xsec_source": source or "pc_feed"}


def extract_xhs_user_id(value: str) -> str:
    value = value.strip()
    if value.startswith("xiaohongshu:"):
        value = value.split(":", 1)[1]
    match = re.search(r"/user/profile/([^/?\s]+)", value)
    if match:
        value = match.group(1)
    if not value or "/" in value or ":" in value:
        raise ValueError(f"Cannot parse Xiaohongshu user id from: {value}")
    if not re.fullmatch(r"[0-9a-fA-F]{24}", value):
        raise ValueError(
            "Xiaohongshu crawl needs a profile URL, xhslink share URL, or the 24-character internal profile id, "
            "not the public Rednote ID."
        )
    return value


def normalize_xhs_profile_input(value: str) -> tuple[str, str]:
    candidate = value.strip()
    if is_xhs_short_url(candidate):
        candidate = resolve_xhs_short_url(candidate)

    platform_user_id = extract_xhs_user_id(candidate)
    if "/user/profile/" in candidate:
        return platform_user_id, candidate
    return platform_user_id, f"https://www.xiaohongshu.com/user/profile/{platform_user_id}"


def is_xhs_short_url(value: str) -> bool:
    parsed = urllib.parse.urlparse(value.strip())
    host = (parsed.netloc or "").lower()
    return host in {"xhslink.com", "www.xhslink.com"}


def resolve_xhs_short_url(value: str, timeout: float = 12.0) -> str:
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
        raise ValueError(f"Cannot resolve Xiaohongshu short URL: {exc}") from exc


class XiaohongshuMinimalAdapter(MinimalCommentAdapter):
    platform = "xiaohongshu"
    index_url = "https://www.xiaohongshu.com"
    cookie_urls = [index_url]

    async def fetch_profile(self, account_url: str) -> AccountRecord:
        async with self.browser_session() as session:
            return await self.fetch_profile_in_session(session, account_url)

    async def fetch_profile_in_session(self, session: BrowserSession, account_url: str) -> AccountRecord:
        user_id = extract_xhs_user_id(account_url)
        context = xhs_context_from_url(account_url)
        client = await self._client(session)
        try:
            profile = await client.get_creator_info(
                user_id,
                xsec_token=context.get("xsec_token", ""),
                xsec_source=context.get("xsec_source", ""),
            )
        except OsgePlatformRequestError:
            raise MinimalAdapterError(profile_session_error("Xiaohongshu")) from None
        if not (profile.get("basicInfo") or {}):
            raise MinimalAdapterError(profile_session_error("Xiaohongshu"))
        return _xhs_profile_record(user_id, account_url, profile)

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
        context = dict(platform_context or {})
        client = await self._client(session)
        notes = await client.get_all_notes_by_creator(
            account_id,
            max_count=limit,
            crawl_interval=self.config.crawl_interval,
            xsec_token=context.get("xsec_token", ""),
            xsec_source=context.get("xsec_source", "pc_feed"),
        )
        records: list[PostRecord] = []
        for item in notes[:limit]:
            note_id = str(item.get("note_id") or item.get("id") or "")
            if not note_id:
                continue
            item_token = str(item.get("xsec_token") or context.get("xsec_token", ""))
            item_source = str(item.get("xsec_source") or context.get("xsec_source", "pc_feed"))
            detail = await client.get_note_by_id(note_id, item_source, item_token)
            if detail:
                detail.setdefault("note_id", note_id)
                detail.setdefault("xsec_token", item_token)
                records.append(_xhs_post_record(detail, item_token, item_source))
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
        context = dict(platform_context or {})
        xsec_token = context.get("xsec_token", "")
        if not xsec_token:
            raise MinimalAdapterError("Xiaohongshu comment refresh needs platform context for the target note.")
        known = set(known_comment_ids or set())
        records: list[CommentRecord] = []
        pages_seen = 0
        stopped = False
        client = await self._client(session)
        has_more = True
        cursor = ""
        known_streak = 0
        while has_more and len(records) < limit:
            response = await client.get_note_comments(post_id, xsec_token, cursor)
            pages_seen += 1
            has_more = bool(response.get("has_more", False))
            cursor = str(response.get("cursor") or "")
            page_comments = list(response.get("comments") or [])
            if not page_comments:
                break
            page_comments, stopped = filter_new_comments(page_comments, known, _xhs_comment_id, known_streak=known_streak)
            known_streak = page_comments.known_streak
            if stopped:
                break
            records.extend(_xhs_comment_records(post_id, page_comments.new_comments, known, limit - len(records)))
            if not get_sub_comments:
                await asyncio.sleep(self.config.crawl_interval)
                continue
            for comment in page_comments.traversal_comments:
                if len(records) >= limit:
                    break
                inline_replies = list(comment.get("sub_comments") or [])
                if inline_replies:
                    inline_replies, inline_stop = filter_new_comments(inline_replies, known, _xhs_comment_id)
                    if not inline_stop:
                        records.extend(_xhs_comment_records(post_id, inline_replies.new_comments, known, limit - len(records)))
                if not comment.get("sub_comment_has_more"):
                    continue
                root_comment_id = str(comment.get("id") or "")
                sub_cursor = str(comment.get("sub_comment_cursor") or "")
                sub_has_more = True
                sub_known_streak = 0
                while sub_has_more and len(records) < limit:
                    sub_response = await client.get_note_sub_comments(
                        note_id=post_id,
                        root_comment_id=root_comment_id,
                        xsec_token=xsec_token,
                        num=10,
                        cursor=sub_cursor,
                    )
                    pages_seen += 1
                    sub_has_more = bool(sub_response.get("has_more", False))
                    sub_cursor = str(sub_response.get("cursor") or "")
                    sub_comments = list(sub_response.get("comments") or [])
                    if not sub_comments:
                        break
                    sub_comments, sub_stopped = filter_new_comments(
                        sub_comments,
                        known,
                        _xhs_comment_id,
                        known_streak=sub_known_streak,
                    )
                    sub_known_streak = sub_comments.known_streak
                    if sub_stopped:
                        break
                    records.extend(_xhs_comment_records(post_id, sub_comments.new_comments, known, limit - len(records)))
                    await asyncio.sleep(self.config.crawl_interval)
            await asyncio.sleep(self.config.crawl_interval)
        return CommentCrawlResult(self.platform, post_id, records, stopped_on_known=stopped, pages_seen=pages_seen)

    async def _client(self, session: BrowserSession) -> OsgeXiaohongshuClient:
        cookie_str, cookie_dict = await session.cookies()
        return OsgeXiaohongshuClient(
            headers={
                "accept": "application/json, text/plain, */*",
                "accept-language": "zh-CN,zh;q=0.9",
                "cache-control": "no-cache",
                "content-type": "application/json;charset=UTF-8",
                "origin": self.index_url,
                "pragma": "no-cache",
                "referer": f"{self.index_url}/",
                "user-agent": await session.user_agent(),
                "Cookie": cookie_str,
            },
            playwright_page=session.page,
            cookie_dict=cookie_dict,
        )


def _xhs_profile_record(user_id: str, profile_url: str, profile: dict[str, Any]) -> AccountRecord:
    basic = profile.get("basicInfo") or {}
    return AccountRecord(
        platform="xiaohongshu",
        platform_user_id=user_id,
        username=str(basic.get("redId") or user_id),
        nickname=str(basic.get("nickname") or ""),
        profile_url=profile_url,
        avatar_url=str(basic.get("images") or ""),
        bio=str(basic.get("desc") or ""),
        location=str(basic.get("ipLocation") or ""),
    )


def _xhs_post_record(note: dict[str, Any], xsec_token: str, xsec_source: str) -> PostRecord:
    user = note.get("user") or {}
    interact = note.get("interact_info") or {}
    note_id = str(note.get("note_id") or note.get("id") or "")
    return PostRecord(
        platform="xiaohongshu",
        platform_post_id=note_id,
        author_platform_user_id=str(user.get("user_id") or ""),
        content=str(note.get("title") or note.get("desc") or ""),
        url=f"https://www.xiaohongshu.com/explore/{note_id}?xsec_token={xsec_token}&xsec_source={xsec_source}",
        created_at=str(note.get("time") or ""),
        like_count=to_int(interact.get("liked_count")),
        comment_count=to_int(interact.get("comment_count")),
        repost_count=to_int(interact.get("share_count")),
        platform_context=_xhs_platform_context(xsec_token, xsec_source),
    )


def _xhs_platform_context(xsec_token: str, xsec_source: str) -> dict[str, str]:
    if not xsec_token:
        return {}
    return {"xsec_token": xsec_token, "xsec_source": xsec_source or "pc_feed"}


def _xhs_comment_records(
    note_id: str,
    comments: list[dict[str, Any]],
    known: set[str],
    remaining: int,
) -> list[CommentRecord]:
    records: list[CommentRecord] = []
    for comment in comments:
        if remaining <= 0:
            break
        comment_id = _xhs_comment_id(comment)
        if not comment_id or comment_id in known:
            continue
        user_info = comment.get("user_info") or {}
        target_comment = comment.get("target_comment") or {}
        records.append(
            CommentRecord(
                platform="xiaohongshu",
                platform_post_id=note_id,
                comment_id=comment_id,
                author_platform_user_id=str(user_info.get("user_id") or ""),
                author_username=str(user_info.get("user_id") or ""),
                author_nickname=str(user_info.get("nickname") or ""),
                author_avatar_url=str(user_info.get("image") or ""),
                content=str(comment.get("content") or ""),
                created_at=str(comment.get("create_time") or ""),
                parent_comment_id=str(target_comment.get("id") or ""),
                like_count=to_int(comment.get("like_count")),
            )
        )
        known.add(comment_id)
        remaining -= 1
    return records


def _xhs_comment_id(comment: dict[str, Any]) -> str:
    return str(comment.get("id") or comment.get("comment_id") or "").strip()


class XiaohongshuAdapter(XiaohongshuMinimalAdapter, PlatformAdapter):
    platform = "xiaohongshu"
