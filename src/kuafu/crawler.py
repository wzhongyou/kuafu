"""核心引擎 — 组装所有模块，驱动爬取流程"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence

import structlog

from kuafu.config import CrawlerConfig
from kuafu.dedup.bloom import BloomFilterDeduplicator, MemoryDeduplicator, URLDeduplicator
from kuafu.events import CRAWL_STARTED, CRAWL_STOPPED, PROGRESS, URL_DISCOVERED, URL_FAILED, URL_FETCHED, EventEmitter
from kuafu.fetcher.httpx_client import HttpxFetcher
from kuafu.frontier.base import URLStore
from kuafu.frontier.memory import MemoryURLStore
from kuafu.frontier.url import normalize_url
from kuafu.middleware.middleware import (
    DepthMiddleware,
    RefererMiddleware,
    RequestMiddleware,
    ResponseMiddleware,
    UAMiddleware,
)
from kuafu.models import CrawlResult, FetchRequest, FetchResult, URLItem, URLStatus
from kuafu.parser.html import HTMLParser
from kuafu.parser.link import DomainFilter, FileTypeFilter, LinkFilter, SchemeFilter
from kuafu.pipeline.pipeline import ConsolePipeline, Pipeline, PipelineChain
from kuafu.politeness.manager import PolitenessManager
from kuafu.scheduler.bfs import BFSScheduler
from kuafu.scheduler.base import Scheduler

logger = structlog.get_logger()


class Crawler:
    """kuafu 爬虫引擎

    组装 Frontier、Scheduler、Fetcher、Parser、Pipeline 等模块，
    驱动完整的 URL 发现 → 调度 → 抓取 → 解析 → 存储 流程。
    """

    def __init__(
        self,
        config: CrawlerConfig,
        *,
        frontier: URLStore | None = None,
        scheduler: Scheduler | None = None,
        dedup: URLDeduplicator | None = None,
        politeness: PolitenessManager | None = None,
        pipelines: list[Pipeline] | None = None,
        req_middlewares: list[RequestMiddleware] | None = None,
        resp_middlewares: list[ResponseMiddleware] | None = None,
        link_filters: list[LinkFilter] | None = None,
    ) -> None:
        self._config = config

        # ── 事件系统 ──
        self._events = EventEmitter()

        # ── 存储层 ──
        self._frontier = frontier or MemoryURLStore()

        # ── 去重 ──
        self._dedup = dedup or self._create_dedup(config)

        # ── Politeness ──
        self._politeness = politeness or self._create_politeness(config)

        # ── 调度器 ──
        self._scheduler = scheduler or BFSScheduler(
            self._frontier,
            self._dedup,
            self._politeness,
            max_depth=config.max_depth,
        )

        # ── Fetcher ──
        self._fetcher = HttpxFetcher(
            user_agent=config.fetcher.user_agent,
            max_connections=config.fetcher.max_connections,
            max_connections_per_host=config.fetcher.max_connections_per_host,
            connect_timeout=config.fetcher.timeout / 3,
            read_timeout=config.fetcher.timeout,
            total_timeout=config.fetcher.timeout * 2,
            max_redirects=config.fetcher.max_redirects,
            verify_ssl=config.fetcher.verify_ssl,
            http2=config.fetcher.http2,
        )

        # ── Parser ──
        self._parser = HTMLParser(
            extract_links=config.parser.extract_links,
            follow_nofollow=config.parser.follow_nofollow,
        )

        # ── Pipeline ──
        self._pipeline = PipelineChain(pipelines or self._create_pipelines(config))

        # ── 中间件 ──
        self._req_middlewares = req_middlewares or [
            UAMiddleware(),
            RefererMiddleware(),
            DepthMiddleware(max_depth=config.max_depth),
        ]
        self._resp_middlewares = resp_middlewares or []

        # ── 链接过滤器 ──
        self._link_filters = link_filters or self._create_link_filters(config)

        # ── 状态 ──
        self._running = False
        self._paused = False
        self._pause_event = asyncio.Event()
        self._pause_event.set()  # 初始不暂停
        self._pages_crawled = 0
        self._pages_failed = 0
        self._urls_discovered = 0

    # ── 公共 API ──

    @property
    def events(self) -> EventEmitter:
        """事件发射器，可注册监听器观察爬取进度"""
        return self._events

    @property
    def config(self) -> CrawlerConfig:
        """爬取配置"""
        return self._config

    @property
    async def frontier_stats(self) -> dict[str, int]:
        """Frontier URL 状态统计"""
        return {
            "pending": await self._frontier.count_by_status(URLStatus.PENDING),
            "completed": await self._frontier.count_by_status(URLStatus.COMPLETED),
            "failed": await self._frontier.count_by_status(URLStatus.FAILED),
        }

    @property
    def stats(self) -> dict:
        """当前爬取统计"""
        return {
            "pages_crawled": self._pages_crawled,
            "pages_failed": self._pages_failed,
            "urls_discovered": self._urls_discovered,
            "running": self._running,
            "paused": self._paused,
        }

    async def pause(self) -> None:
        """暂停爬取"""
        self._paused = True
        self._pause_event.clear()
        logger.info("crawler_paused")

    async def resume(self) -> None:
        """恢复爬取"""
        self._paused = False
        self._pause_event.set()
        logger.info("crawler_resumed")

    async def add_seed(self, url: str) -> None:
        """运行时动态注入种子 URL"""
        normalized = normalize_url(url)
        if not normalized:
            return
        if await self._dedup.seen(normalized):
            return
        item = URLItem(raw=url, normalized=normalized, depth=0, priority=0, status=URLStatus.PENDING)
        await self._scheduler.push([item])

    def run_as_task(self) -> asyncio.Task:
        """以后台 Task 启动爬取，供 TUI 等场景并行运行"""
        return asyncio.create_task(self.run())

    # ── 内部工厂 ──

    @staticmethod
    def _create_dedup(config: CrawlerConfig) -> URLDeduplicator:
        match config.dedup.url.type:
            case "bloom":
                bloom_cfg = config.dedup.url.bloom
                return BloomFilterDeduplicator(
                    expected_items=bloom_cfg.expected_items,
                    false_positive_rate=bloom_cfg.false_positive_rate,
                )
            case "map":
                return MemoryDeduplicator()
            case _:
                return BloomFilterDeduplicator()

    @staticmethod
    def _create_politeness(config: CrawlerConfig) -> PolitenessManager:
        pc = config.politeness
        return PolitenessManager(
            default_delay=pc.default_delay,
            max_concurrent_per_host=pc.max_concurrent_per_host,
            circuit_threshold=pc.circuit_threshold,
            circuit_cooldown=pc.circuit_cooldown,
            respect_crawl_delay=pc.respect_crawl_delay,
            robots_cache_ttl=pc.robots_cache_ttl,
        )

    @staticmethod
    def _create_pipelines(config: CrawlerConfig) -> list[Pipeline]:
        pipelines: list[Pipeline] = []
        for p_cfg in config.pipeline:
            match p_cfg.type:
                case "file":
                    from kuafu.pipeline.pipeline import FilePipeline
                    pipelines.append(FilePipeline(p_cfg.path))
                case "search":
                    from kuafu.search.pipeline import SearchIndexPipeline
                    pipelines.append(SearchIndexPipeline(p_cfg.path))
                case _:
                    pipelines.append(ConsolePipeline())
        if not pipelines:
            pipelines.append(ConsolePipeline())
        return pipelines

    @staticmethod
    def _create_link_filters(config: CrawlerConfig) -> list[LinkFilter]:
        filters: list[LinkFilter] = [
            FileTypeFilter(),
            SchemeFilter(),
        ]
        if config.seeds:
            from yarl import URL
            domains: list[str] = []
            for seed in config.seeds:
                try:
                    host = URL(seed).host
                    if host:
                        domains.append(host)
                except ValueError:
                    pass
            if domains:
                filters.append(DomainFilter(domains))
        return filters

    # ── 主循环 ──

    async def run(self) -> None:
        """启动爬取"""
        self._running = True

        self._setup_logging()

        logger.info("crawler_starting", name=self._config.name)
        self._events.emit(CRAWL_STARTED, config=self._config)

        await self._inject_seeds()
        await self._scheduler.start()

        try:
            concurrency = self._config.worker.concurrency
            semaphore = asyncio.Semaphore(concurrency)
            tasks: set[asyncio.Task] = set()

            while self._running:
                if self._should_stop():
                    break

                batch = await self._scheduler.schedule(self._config.scheduler.batch_size)
                if not batch:
                    if tasks:
                        await asyncio.sleep(0.5)
                        continue
                    else:
                        break

                for url_item in batch:
                    if len(tasks) >= concurrency:
                        done, tasks = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
                        for t in done:
                            await t

                    task = asyncio.create_task(self._process_url(url_item, semaphore))
                    tasks.add(task)
                    task.add_done_callback(tasks.discard)

                await asyncio.sleep(0.01)

            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)

        finally:
            await self._shutdown()

    async def _inject_seeds(self) -> None:
        """注入种子 URL"""
        url_items: list[URLItem] = []
        for seed in self._config.seeds:
            normalized = normalize_url(seed)
            if not normalized:
                continue
            url_items.append(URLItem(
                raw=seed, normalized=normalized, depth=0, priority=0,
                status=URLStatus.PENDING,
            ))

        if url_items:
            await self._scheduler.push(url_items)
            logger.info("seeds_injected", count=len(url_items))

    async def _process_url(self, url_item: URLItem, semaphore: asyncio.Semaphore) -> None:
        """处理单个 URL：抓取 → 解析 → 管道"""
        # 暂停门
        await self._pause_event.wait()

        host = url_item.normalized
        try:
            from yarl import URL
            host = URL(url_item.normalized).host or ""
        except ValueError:
            pass

        async with semaphore:
            await self._politeness.wait(host)
            await self._politeness.acquire_slot(host)

            try:
                request = FetchRequest(url=url_item.normalized, max_depth=url_item.depth)

                for mw in self._req_middlewares:
                    request = await mw.process_request(request)

                if request.headers.get("X-Skip-Depth") == "true":
                    return

                fetch_result = await self._fetcher.fetch(request)

                for mw in self._resp_middlewares:
                    fetch_result = await mw.process_response(request, fetch_result)

                await self._scheduler.feedback(fetch_result)

                if not fetch_result.is_success:
                    self._pages_failed += 1
                    await self._frontier.update_status(url_item.normalized, URLStatus.FAILED)
                    self._events.emit(URL_FAILED, url=url_item.normalized,
                                     error=fetch_result.error or str(fetch_result.status_code))
                    self._events.emit(PROGRESS, **self.stats)
                    return

                parse_result = await self._parser.parse(url_item.normalized, fetch_result.body)

                new_urls = self._extract_new_urls(url_item, parse_result.links)
                if new_urls:
                    await self._scheduler.push(new_urls)
                    self._urls_discovered += len(new_urls)
                    self._events.emit(URL_DISCOVERED, count=len(new_urls))

                await self._frontier.update_status(url_item.normalized, URLStatus.COMPLETED)
                self._pages_crawled += 1

                result = CrawlResult(
                    request=request,
                    fetch=fetch_result,
                    parse=parse_result,
                    url_item=url_item,
                )

                await self._pipeline.process(result)

                self._events.emit(URL_FETCHED, result=result)
                self._events.emit(PROGRESS, **self.stats)

            finally:
                self._politeness.release_slot(host)

    def _extract_new_urls(self, parent: URLItem, links: list) -> list[URLItem]:
        """从解析结果中提取新 URL"""
        new_urls: list[URLItem] = []
        for link in links:
            normalized = normalize_url(link.url)
            if not normalized:
                continue

            if not all(f.should_follow(normalized) for f in self._link_filters):
                continue

            new_urls.append(URLItem(
                raw=link.url,
                normalized=normalized,
                parent=parent.normalized,
                depth=parent.depth + 1,
                priority=parent.priority,
            ))
        return new_urls

    def _should_stop(self) -> bool:
        if not self._running:
            return True
        max_pages = self._config.max_pages
        if max_pages > 0 and self._pages_crawled >= max_pages:
            logger.info("crawler_max_pages_reached", max_pages=max_pages)
            return True
        return False

    async def stop(self) -> None:
        """外部停止"""
        self._running = False

    async def _shutdown(self) -> None:
        logger.info(
            "crawler_stopping",
            pages_crawled=self._pages_crawled,
            pages_failed=self._pages_failed,
        )

        await self._scheduler.stop()
        await self._fetcher.close()
        await self._pipeline.close()
        await self._dedup.close()
        await self._frontier.close()

        self._events.emit(CRAWL_STOPPED, pages_crawled=self._pages_crawled,
                          pages_failed=self._pages_failed)
        logger.info("crawler_stopped")

    def _setup_logging(self) -> None:
        import logging

        log_level = getattr(logging, self._config.log.level.upper(), logging.INFO)

        if self._config.log.format == "json":
            renderer = structlog.processors.JSONRenderer()
        else:
            renderer = structlog.dev.ConsoleRenderer()

        structlog.configure(
            processors=[
                structlog.contextvars.merge_contextvars,
                structlog.processors.add_log_level,
                structlog.processors.StackInfoRenderer(),
                structlog.processors.format_exc_info,
                structlog.processors.TimeStamper(fmt="iso"),
                renderer,
            ],
            wrapper_class=structlog.make_filtering_bound_logger(log_level),
            context_class=dict,
            logger_factory=structlog.PrintLoggerFactory(),
            cache_logger_on_first_use=True,
        )
