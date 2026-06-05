"""httpx 异步 Fetcher 实现"""

from __future__ import annotations

import asyncio
from datetime import datetime

import httpx

from kuafu.fetcher.base import Fetcher
from kuafu.fetcher.encoding import detect_encoding
from kuafu.models import FetchRequest, FetchResult


class HttpxFetcher(Fetcher):
    """基于 httpx 的异步 HTTP 抓取器

    特性:
    - HTTP/1.1 + HTTP/2
    - 连接池管理
    - 自动编码检测
    - 重定向跟随
    """

    def __init__(
        self,
        *,
        user_agent: str = "kuafu/1.0",
        max_connections: int = 100,
        max_connections_per_host: int = 10,
        connect_timeout: float = 10.0,
        read_timeout: float = 30.0,
        total_timeout: float = 60.0,
        max_redirects: int = 10,
        verify_ssl: bool = True,
        http2: bool = True,
    ) -> None:
        self._user_agent = user_agent
        self._max_connections = max_connections
        self._max_connections_per_host = max_connections_per_host
        self._connect_timeout = connect_timeout
        self._read_timeout = read_timeout
        self._total_timeout = total_timeout
        self._max_redirects = max_redirects
        self._verify_ssl = verify_ssl
        self._http2 = http2
        self._client: httpx.AsyncClient | None = None

    async def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(
                    connect=self._connect_timeout,
                    read=self._read_timeout,
                    total=self._total_timeout,
                ),
                max_redirects=self._max_redirects,
                verify=self._verify_ssl,
                http2=self._http2,
                limits=httpx.Limits(
                    max_connections=self._max_connections,
                    max_connections_per_host=self._max_connections_per_host,
                ),
                headers={"User-Agent": self._user_agent},
                follow_redirects=True,
            )
        return self._client

    async def fetch(self, request: FetchRequest) -> FetchResult:
        client = await self._ensure_client()
        start = asyncio.get_event_loop().time()

        # 合并请求头
        headers = {"User-Agent": self._user_agent}
        headers.update(request.headers)

        try:
            response = await client.request(
                method=request.method,
                url=request.url,
                headers=headers,
                cookies=request.cookies,
                proxy=request.proxy,
            )
            duration = asyncio.get_event_loop().time() - start

            # 编码检测
            content_type = response.headers.get("content-type", "")
            encoding, _ = detect_encoding(response.content, content_type)

            return FetchResult(
                url=str(response.url),
                status_code=response.status_code,
                headers=dict(response.headers),
                body=response.content,
                content_type=content_type,
                encoding=encoding,
                fetch_time=datetime.now(),
                duration=duration,
                redirect_chain=[str(h.url) for h in response.history],
            )
        except httpx.TimeoutException as e:
            duration = asyncio.get_event_loop().time() - start
            return FetchResult(
                url=request.url,
                duration=duration,
                error=f"timeout: {e}",
            )
        except httpx.HTTPStatusError as e:
            duration = asyncio.get_event_loop().time() - start
            return FetchResult(
                url=str(e.response.url),
                status_code=e.response.status_code,
                duration=duration,
                error=f"http_error: {e}",
            )
        except httpx.RequestError as e:
            duration = asyncio.get_event_loop().time() - start
            return FetchResult(
                url=request.url,
                duration=duration,
                error=f"error: {e}",
            )

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None
