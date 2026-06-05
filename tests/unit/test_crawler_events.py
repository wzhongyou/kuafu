"""Crawler 事件系统集成测试"""

import asyncio

import pytest

from kuafu.config import CrawlerConfig
from kuafu.crawler import Crawler
from kuafu.events import CRAWL_STARTED, CRAWL_STOPPED, PROGRESS, URL_FETCHED, URL_FAILED
from kuafu.fetcher.base import Fetcher
from kuafu.models import CrawlResult, FetchRequest, FetchResult, ParseResult


class MockFetcher(Fetcher):
    """测试用 Mock Fetcher"""

    def __init__(self, responses: dict[str, FetchResult] | None = None) -> None:
        self._responses = responses or {}
        self._closed = False

    async def fetch(self, request: FetchRequest) -> FetchResult:
        return self._responses.get(request.url, FetchResult(
            url=request.url,
            status_code=200,
            content_type="text/html",
            body=b"<html><head><title>Test</title></head><body>Hello</body></html>",
        ))

    async def close(self) -> None:
        self._closed = True


class TestCrawlerEvents:
    @pytest.mark.asyncio
    async def test_crawl_started_event(self):
        config = CrawlerConfig(seeds=["https://example.com"], max_pages=1)
        crawler = Crawler(config)
        crawler._fetcher = MockFetcher()

        events_received = []
        async def on_start(**kwargs):
            events_received.append("started")

        crawler.events.on(CRAWL_STARTED, on_start)
        await crawler.run()
        await asyncio.sleep(0.05)
        assert "started" in events_received

    @pytest.mark.asyncio
    async def test_crawl_stopped_event(self):
        config = CrawlerConfig(seeds=["https://example.com"], max_pages=1)
        crawler = Crawler(config)
        crawler._fetcher = MockFetcher()

        events_received = []
        async def on_stop(**kwargs):
            events_received.append("stopped")

        crawler.events.on(CRAWL_STOPPED, on_stop)
        await crawler.run()
        await asyncio.sleep(0.05)
        assert "stopped" in events_received

    @pytest.mark.asyncio
    async def test_url_fetched_event(self):
        config = CrawlerConfig(seeds=["https://example.com"], max_pages=1)
        crawler = Crawler(config)
        crawler._fetcher = MockFetcher()

        fetched_urls = []
        async def on_fetched(result=None, **kwargs):
            if result:
                fetched_urls.append(result.fetch.url)

        crawler.events.on(URL_FETCHED, on_fetched)
        await crawler.run()
        await asyncio.sleep(0.05)
        assert "https://example.com" in fetched_urls

    @pytest.mark.asyncio
    async def test_stats_property(self):
        config = CrawlerConfig(seeds=["https://example.com"], max_pages=1)
        crawler = Crawler(config)
        crawler._fetcher = MockFetcher()

        stats = crawler.stats
        assert stats["pages_crawled"] == 0
        assert stats["running"] is False
        assert stats["paused"] is False

    @pytest.mark.asyncio
    async def test_pause_and_resume(self):
        config = CrawlerConfig(seeds=["https://example.com"], max_pages=5)
        crawler = Crawler(config)
        crawler._fetcher = MockFetcher()

        assert crawler.stats["paused"] is False
        await crawler.pause()
        assert crawler.stats["paused"] is True
        await crawler.resume()
        assert crawler.stats["paused"] is False

    @pytest.mark.asyncio
    async def test_add_seed(self):
        config = CrawlerConfig(seeds=["https://example.com"], max_pages=1)
        crawler = Crawler(config)
        # 不实际运行，只验证 add_seed 不抛异常
        await crawler.add_seed("https://example.org")

    @pytest.mark.asyncio
    async def test_run_as_task(self):
        config = CrawlerConfig(seeds=["https://example.com"], max_pages=1)
        crawler = Crawler(config)
        crawler._fetcher = MockFetcher()

        task = crawler.run_as_task()
        await task
        assert crawler.stats["pages_crawled"] >= 1
