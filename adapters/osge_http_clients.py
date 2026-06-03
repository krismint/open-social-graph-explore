from __future__ import annotations

import os
from typing import Any

import httpx


class OsgePlatformRequestError(RuntimeError):
    pass


def make_async_client(**kwargs: Any) -> httpx.AsyncClient:
    disable_verify = os.environ.get("OSGE_DISABLE_SSL_VERIFY", "").lower() in {"1", "true", "yes"}
    kwargs.setdefault("verify", not disable_verify)
    return httpx.AsyncClient(**kwargs)


async def convert_browser_context_cookies(context: Any, urls: list[str] | None = None) -> tuple[str, dict[str, str]]:
    cookies = await context.cookies(urls=urls) if urls else await context.cookies()
    cookie_str = ";".join(f"{cookie.get('name')}={cookie.get('value')}" for cookie in cookies)
    cookie_dict = {str(cookie.get("name")): str(cookie.get("value")) for cookie in cookies}
    return cookie_str, cookie_dict
