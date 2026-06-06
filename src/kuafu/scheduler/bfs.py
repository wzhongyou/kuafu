"""BFS + 优先级混合调度器"""

from __future__ import annotations

from collections.abc import Sequence

import structlog

from kuafu.dedup.bloom import URLDeduplicator
from kuafu.frontier.base import URLStore
from kuafu.models import FetchResult, URLItem, URLStatus
from kuafu.politeness.manager import PolitenessManager
from kuafu.scheduler.base import Scheduler

logger = structlog.get_logger()


class BFSScheduler(Scheduler):
    """BFS + 优先级混合调度器

    - 同一优先级内广度优先（深度递增），保证覆盖面
    - 不同优先级间严格按优先级排序
    - 受 Politeness 约束，同站点不并发
    - 去重检查，避免重复调度
    """

    def __init__(
        self,
        frontier: URLStore,
        dedup: URLDeduplicator,
        politeness: PolitenessManager,
        *,
        max_depth: int = -1,
    ) -> None:
        self._frontier = frontier
        self._dedup = dedup
        self._politeness = politeness
        self._max_depth = max_depth
        self._running = False

    async def push(self, urls: Sequence[URLItem]) -> None:
        """接收新 URL，去重后入队"""
        new_urls: list[URLItem] = []
        for url in urls:
            # 深度检查
            if self._max_depth >= 0 and url.depth > self._max_depth:
                continue

            # 去重检查
            if await self._dedup.seen(url.normalized):
                continue

            # 标记为已见
            await self._dedup.mark(url.normalized)

            # 确保状态为 PENDING
            if url.status != URLStatus.PENDING:
                url = url.model_copy(update={"status": URLStatus.PENDING})

            # 写入 Frontier
            await self._frontier.put(url)
            new_urls.append(url)

        if new_urls:
            logger.debug("scheduler_push", count=len(new_urls))

    async def schedule(self, limit: int) -> list[URLItem]:
        """获取待调度 URL 批次"""
        urls = await self._frontier.pop_pending(limit)

        # Politeness 过滤
        result: list[URLItem] = []
        for url in urls:
            allowed = await self._politeness.allow(url)
            if allowed:
                result.append(url)
            else:
                # 不允许的 URL 放回 PENDING
                await self._frontier.update_status(url.normalized, URLStatus.PENDING)

            if len(result) >= limit:
                break

        return result

    async def feedback(self, result: FetchResult) -> None:
        """反馈抓取结果，更新 Politeness 状态"""
        host = result.host
        if host:
            self._politeness.record(host, result)

    async def start(self) -> None:
        self._running = True
        logger.info("scheduler_started", type="bfs")

    async def stop(self) -> None:
        self._running = False
        logger.info("scheduler_stopped")
