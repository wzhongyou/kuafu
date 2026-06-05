"""Middleware — 请求/响应中间件"""

from __future__ import annotations

import random
from abc import ABC, abstractmethod

from kuafu.models import FetchRequest, FetchResult


class RequestMiddleware(ABC):
    """请求中间件 — 在请求发出前执行"""

    @abstractmethod
    async def process_request(self, request: FetchRequest) -> FetchRequest:
        """处理请求，返回修改后的请求"""


class ResponseMiddleware(ABC):
    """响应中间件 — 在响应返回后执行"""

    @abstractmethod
    async def process_response(self, request: FetchRequest, result: FetchResult) -> FetchResult:
        """处理响应，返回修改后的结果"""


# ── 内置请求中间件 ──────────────────────────────────────

class UAMiddleware(RequestMiddleware):
    """User-Agent 轮换"""

    _USER_AGENTS: list[str] = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    ]

    def __init__(self, user_agents: list[str] | None = None) -> None:
        self._agents = user_agents or self._USER_AGENTS

    async def process_request(self, request: FetchRequest) -> FetchRequest:
        headers = {**request.headers, "User-Agent": random.choice(self._agents)}
        return request.model_copy(update={"headers": headers})


class RefererMiddleware(RequestMiddleware):
    """自动设置 Referer 头"""

    async def process_request(self, request: FetchRequest) -> FetchRequest:
        if "Referer" not in request.headers and "referer" not in request.headers:
            headers = {**request.headers, "Referer": request.url}
            return request.model_copy(update={"headers": headers})
        return request


class DepthMiddleware(RequestMiddleware):
    """深度检查 — 超过最大深度则标记跳过"""

    def __init__(self, max_depth: int = -1) -> None:
        self._max_depth = max_depth

    async def process_request(self, request: FetchRequest) -> FetchRequest:
        if self._max_depth >= 0 and request.max_depth > self._max_depth:
            # 通过 meta 标记跳过
            meta = {**request.headers, "X-Skip-Depth": "true"}
            return request.model_copy(update={"headers": meta})
        return request


# ── 内置响应中间件 ──────────────────────────────────────

class ErrorMiddleware(ResponseMiddleware):
    """错误分类 — 根据状态码决定是否重试"""

    async def process_response(self, request: FetchRequest, result: FetchResult) -> FetchResult:
        # 标记重试信息到 meta
        should_retry = (
            result.error is not None
            or result.status_code in (408, 429, 500, 502, 503, 504)
        )
        if should_retry:
            headers = {**result.headers, "X-Should-Retry": "true"}
            return result.model_copy(update={"headers": headers})
        return result
