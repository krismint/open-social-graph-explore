"""Placeholder adapter for Weibo.

Real adapters should return normalized records from adapters.base and must not
bypass platform access controls.
"""

from adapters.base import PlatformAdapter


class WeiboAdapter(PlatformAdapter):
    platform = "weibo"
