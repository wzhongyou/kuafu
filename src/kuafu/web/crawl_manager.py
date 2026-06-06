"""CrawlManager — 单任务爬取管理器，桥接 Crawler 与 Web 层"""

from __future__ import annotations

import asyncio
import time

import httpx
import structlog

from kuafu.config import CrawlerConfig
from kuafu.crawler import Crawler
from kuafu.events import (
    CRAWL_STARTED,
    CRAWL_STOPPED,
    PROGRESS,
    URL_FAILED,
    URL_FETCHED,
)
from kuafu.models import CrawlResult
from kuafu.pipeline.pipeline import ConsolePipeline
from kuafu.search.transformer import transform
from kuafu.web.event_bus import EventBus

logger = structlog.get_logger()


class CrawlManager:
    """单任务爬取管理器

    管理一个 Crawler 实例的完整生命周期，
    累积抓取结果，桥接事件到 EventBus 供 SSE 推送。
    """

    def __init__(self, max_results: int = 500) -> None:
        self._crawler: Crawler | None = None
        self._task: asyncio.Task | None = None
        self._event_bus = EventBus()
        self._results: list[CrawlResult] = []
        self._search_docs_cache: list[dict] = []  # 预计算的 Vortex 文档
        self._max_results = max_results
        self._state = "idle"  # idle | running | paused | completed | stopped
        self._seed_url: str = ""
        self._start_time: float = 0

    @property
    def event_bus(self) -> EventBus:
        return self._event_bus

    @property
    def state(self) -> str:
        return self._state

    @property
    def results(self) -> list[CrawlResult]:
        return self._results

    async def start_crawl(self, url: str, max_depth: int = 2, max_pages: int = 100) -> None:
        """开始爬取"""
        if self._state in ("running", "paused"):
            raise RuntimeError("Crawl already in progress")

        await self._cleanup()

        config = CrawlerConfig(seeds=[url], max_depth=max_depth, max_pages=max_pages)
        self._crawler = Crawler(config, pipelines=[ConsolePipeline()])
        self._results = []
        self._search_docs_cache = []
        self._seed_url = url
        self._start_time = time.monotonic()
        self._state = "running"

        # 订阅事件
        self._crawler.events.on(CRAWL_STARTED, self._on_crawl_started)
        self._crawler.events.on(CRAWL_STOPPED, self._on_crawl_stopped)
        self._crawler.events.on(URL_FETCHED, self._on_url_fetched)
        self._crawler.events.on(URL_FAILED, self._on_url_failed)
        self._crawler.events.on(PROGRESS, self._on_progress)

        self._task = self._crawler.run_as_task()
        self._task.add_done_callback(self._on_task_done)

    async def stop_crawl(self) -> None:
        if self._crawler:
            await self._crawler.stop()
            self._state = "stopped"

    async def pause_crawl(self) -> None:
        if self._crawler:
            await self._crawler.pause()
            self._state = "paused"

    async def resume_crawl(self) -> None:
        if self._crawler:
            await self._crawler.resume()
            self._state = "running"

    def get_status(self) -> dict:
        """获取当前状态"""
        elapsed = (
            time.monotonic() - self._start_time
            if self._start_time and self._state != "idle"
            else 0
        )
        stats = (
            self._crawler.stats
            if self._crawler
            else {
                "pages_crawled": 0,
                "pages_failed": 0,
                "urls_discovered": 0,
                "running": False,
                "paused": False,
            }
        )
        return {
            "state": self._state,
            "seed_url": self._seed_url,
            "elapsed": round(elapsed, 1),
            "result_count": len(self._results),
            **stats,
        }

    def get_results(self) -> list[dict]:
        """获取结果摘要列表"""
        summaries = []
        for r in self._results:
            summaries.append({
                "url": r.fetch.url,
                "status_code": r.fetch.status_code,
                "title": r.parse.title[:100] if r.parse.title else "",
                "duration": round(r.fetch.duration, 2),
                "depth": r.url_item.depth if r.url_item else 0,
            })
        return summaries

    def get_result(self, url: str) -> dict | None:
        """获取单页详情"""
        for r in self._results:
            if r.fetch.url == url:
                data = r.model_dump()
                # body 是 bytes，转为字符串标记
                if "fetch" in data and "body" in data["fetch"]:
                    data["fetch"]["body"] = ""
                return data
        return None

    def export_jsonl(self) -> str:
        """导出 SearchDocument JSONL"""
        lines = []
        for result in self._results:
            doc = transform(result)
            lines.append(doc.model_dump_json(exclude_none=True))
        return "\n".join(lines) + "\n" if lines else ""

    async def build_vortex_index(self, vortex_url: str) -> dict:
        """对接 Vortex 搜索引擎建库"""
        if not self._results:
            return {"total": 0, "success": 0, "failed": 0, "errors": []}

        # 预计算所有 Vortex 文档
        documents = []
        for result in self._results:
            doc = transform(result)
            vortex_doc = {
                "title": doc.title,
                "content": doc.text,
                "url": doc.url,
                "site": doc.site,
                "author": doc.author or "",
                "timestamp": doc.fetch_time.isoformat() if doc.fetch_time else "",
                "description": doc.description,
                "doc_id": doc.doc_id,
                "category": doc.category or doc.lang,
            }
            documents.append(vortex_doc)

        # 并发推送到 Vortex
        success = 0
        failed = 0
        errors: list[str] = []
        semaphore = asyncio.Semaphore(10)

        async with httpx.AsyncClient(timeout=30.0) as client:
            async def push(doc: dict) -> None:
                nonlocal success, failed
                async with semaphore:
                    try:
                        resp = await client.post(
                            f"{vortex_url.rstrip('/')}/api/document",
                            json=doc,
                        )
                        if resp.status_code == 200:
                            success += 1
                        else:
                            failed += 1
                            errors.append(f"{doc['url']}: HTTP {resp.status_code}")
                    except httpx.RequestError as e:
                        failed += 1
                        errors.append(f"{doc['url']}: {e}")

            await asyncio.gather(*[push(doc) for doc in documents])

        return {
            "total": len(documents),
            "success": success,
            "failed": failed,
            "errors": errors[:20],
        }

    async def _cleanup(self) -> None:
        """清理上一次爬取"""
        if self._crawler and self._state in ("running", "paused"):
            await self._crawler.stop()
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            except Exception:
                logger.warning("unexpected_error_during_cleanup", exc_info=True)
        self._crawler = None
        self._task = None

    def _on_task_done(self, task: asyncio.Task) -> None:
        """Task 完成回调"""
        if self._state == "running":
            self._state = "completed"

    # ── 事件回调 ──

    async def _on_crawl_started(self, config=None, **kwargs) -> None:
        self._event_bus.publish("crawl_started", {
            "seed": self._seed_url,
            "max_depth": config.max_depth if config else 2,
            "max_pages": config.max_pages if config else 100,
        })

    async def _on_crawl_stopped(self, **kwargs) -> None:
        self._event_bus.publish("crawl_stopped", {
            "pages_crawled": kwargs.get("pages_crawled", 0),
            "pages_failed": kwargs.get("pages_failed", 0),
        })

    async def _on_url_fetched(self, result: CrawlResult, **kwargs) -> None:
        # 累积结果，strip body 节省内存
        stripped = result.model_copy(update={
            "fetch": result.fetch.model_copy(update={"body": b""}),
        })
        self._results.append(stripped)
        if len(self._results) > self._max_results:
            self._results.pop(0)

        self._event_bus.publish("url_fetched", {
            "url": result.fetch.url,
            "status_code": result.fetch.status_code,
            "title": result.parse.title[:100] if result.parse.title else "",
            "duration": round(result.fetch.duration, 2),
            "depth": result.url_item.depth if result.url_item else 0,
        })

    async def _on_url_failed(self, url: str = "", error: str = "", **kwargs) -> None:
        self._event_bus.publish("url_failed", {"url": url, "error": error})

    async def _on_progress(self, **kwargs) -> None:
        self._event_bus.publish("progress", kwargs)
