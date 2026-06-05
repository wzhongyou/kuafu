"""内存 URL 存储 — 单机小规模场景"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence

from kuafu.frontier.base import URLStore
from kuafu.models import URLItem, URLStatus


class MemoryURLStore(URLStore):
    """基于 dict + heapq 的内存存储

    - _urls: normalized_url → URLItem 的主索引
    - _pending: 待抓取的优先级队列（priority, depth, normalized_url）
    """

    def __init__(self) -> None:
        self._urls: dict[str, URLItem] = {}
        self._pending: list[tuple[int, int, str]] = []  # (priority, depth, url)
        self._lock = asyncio.Lock()

    async def put(self, url: URLItem) -> None:
        async with self._lock:
            self._urls[url.normalized] = url
            if url.status == URLStatus.PENDING:
                self._pending.append((url.priority, url.depth, url.normalized))

    async def batch_put(self, urls: Sequence[URLItem]) -> None:
        async with self._lock:
            for url in urls:
                self._urls[url.normalized] = url
                if url.status == URLStatus.PENDING:
                    self._pending.append((url.priority, url.depth, url.normalized))

    async def update_status(self, normalized_url: str, status: URLStatus) -> None:
        async with self._lock:
            item = self._urls.get(normalized_url)
            if item:
                self._urls[normalized_url] = item.model_copy(update={"status": status})

    async def get(self, normalized_url: str) -> URLItem | None:
        return self._urls.get(normalized_url)

    async def pop_pending(self, limit: int, *, host: str | None = None) -> list[URLItem]:
        async with self._lock:
            # 排序：优先级 → 深度
            self._pending.sort()
            result: list[URLItem] = []
            remaining: list[tuple[int, int, str]] = []

            for entry in self._pending:
                if len(result) >= limit:
                    remaining.append(entry)
                    continue

                _, _, normalized = entry
                item = self._urls.get(normalized)
                if item is None or item.status != URLStatus.PENDING:
                    continue

                # Host 过滤
                if host:
                    from yarl import URL
                    try:
                        if URL(item.normalized).host != host:
                            remaining.append(entry)
                            continue
                    except ValueError:
                        remaining.append(entry)
                        continue

                # 标记为 FETCHING
                self._urls[normalized] = item.model_copy(update={"status": URLStatus.FETCHING})
                result.append(self._urls[normalized])

            self._pending = remaining
            return result

    async def exists(self, normalized_url: str) -> bool:
        return normalized_url in self._urls

    async def count_by_status(self, status: URLStatus) -> int:
        return sum(1 for item in self._urls.values() if item.status == status)

    async def close(self) -> None:
        self._urls.clear()
        self._pending.clear()
