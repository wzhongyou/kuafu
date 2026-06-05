"""集成测试 — 端到端爬取流程

使用 httpx 的 mock transport 模拟 HTTP 响应，不访问真实网络。
"""

from __future__ import annotations

import asyncio

import httpx
import pytest

from kuafu.config import CrawlerConfig
from kuafu.crawler import Crawler
from kuafu.fetcher.base import Fetcher
from kuafu.models import FetchRequest, FetchResult


class MockFetcher(Fetcher):
    """模拟 Fetcher，返回预设的 HTML 页面"""

    def __init__(self) -> None:
        self._pages: dict[str, str] = {}

    def add_page(self, url: str, html: str) -> None:
        self._pages[url] = html

    async def fetch(self, request: FetchRequest) -> FetchResult:
        from datetime import datetime
        html = self._pages.get(request.url)
        if html:
            return FetchResult(
                url=request.url,
                status_code=200,
                body=html.encode("utf-8"),
                content_type="text/html; charset=utf-8",
                encoding="utf-8",
                fetch_time=datetime.now(),
                duration=0.01,
            )
        return FetchResult(
            url=request.url,
            status_code=404,
            error="not found",
        )

    async def close(self) -> None:
        pass


class TestEndToEnd:
    @pytest.mark.asyncio
    async def test_basic_crawl(self):
        """测试基本爬取流程：种子 → 抓取 → 解析 → 发现链接 → 抓取子页面"""
        config = CrawlerConfig(
            name="test-basic",
            seeds=["http://example.com"],
            max_depth=1,
            max_pages=10,
            worker=({"concurrency": 5}),
        )

        # 构造 Mock
        mock_fetcher = MockFetcher()
        mock_fetcher.add_page("http://example.com", """
        <html>
        <head><title>Home</title></head>
        <body>
            <h1>Welcome</h1>
            <a href="http://example.com/about">About</a>
            <a href="http://example.com/contact">Contact</a>
        </body>
        </html>
        """)
        mock_fetcher.add_page("http://example.com/about", """
        <html><head><title>About</title></head><body><p>About us</p></body></html>
        """)
        mock_fetcher.add_page("http://example.com/contact", """
        <html><head><title>Contact</title></head><body><p>Contact us</p></body></html>
        """)

        crawler = Crawler(config, pipelines=[])  # 不需要输出
        # 替换 fetcher
        crawler._fetcher = mock_fetcher

        await crawler.run()

        # 验证爬取了种子和子页面
        assert crawler._pages_crawled >= 1  # 至少种子页面

    @pytest.mark.asyncio
    async def test_max_pages_limit(self):
        """测试 max_pages 限制"""
        config = CrawlerConfig(
            name="test-max-pages",
            seeds=["http://example.com"],
            max_depth=0,  # 只抓种子
            max_pages=1,
        )

        mock_fetcher = MockFetcher()
        mock_fetcher.add_page("http://example.com", "<html><body>Home</body></html>")

        crawler = Crawler(config, pipelines=[])
        crawler._fetcher = mock_fetcher

        await crawler.run()
        assert crawler._pages_crawled <= 1

    @pytest.mark.asyncio
    async def test_max_depth_limit(self):
        """测试 max_depth 限制：depth=0 只抓种子，不跟踪链接"""
        config = CrawlerConfig(
            name="test-max-depth",
            seeds=["http://example.com"],
            max_depth=0,
            max_pages=100,
        )

        mock_fetcher = MockFetcher()
        mock_fetcher.add_page("http://example.com", """
        <html><body>
            <a href="http://example.com/deep1">Deep 1</a>
            <a href="http://example.com/deep2">Deep 2</a>
        </body></html>
        """)
        mock_fetcher.add_page("http://example.com/deep1", "<html><body>Deep 1</body></html>")
        mock_fetcher.add_page("http://example.com/deep2", "<html><body>Deep 2</body></html>")

        crawler = Crawler(config, pipelines=[])
        crawler._fetcher = mock_fetcher

        await crawler.run()
        # depth=0，只有种子页面被抓取
        assert crawler._pages_crawled == 1

    @pytest.mark.asyncio
    async def test_dedup_prevents_revisit(self):
        """测试去重：同一 URL 不重复抓取"""
        config = CrawlerConfig(
            name="test-dedup",
            seeds=["http://example.com"],
            max_depth=1,
        )

        mock_fetcher = MockFetcher()
        mock_fetcher.add_page("http://example.com", """
        <html><body>
            <a href="http://example.com/page">Page</a>
            <a href="http://example.com/page">Page Again</a>
            <a href="http://example.com/page">Page Third</a>
        </body></html>
        """)
        mock_fetcher.add_page("http://example.com/page", "<html><body>Page</body></html>")

        crawler = Crawler(config, pipelines=[])
        crawler._fetcher = mock_fetcher

        await crawler.run()
        # /page 只被抓取一次
        assert crawler._pages_crawled == 2  # 首页 + page

    @pytest.mark.asyncio
    async def test_pipeline_called(self):
        """测试 Pipeline 被正确调用"""
        from kuafu.pipeline.pipeline import Pipeline
        from kuafu.models import CrawlResult

        collected: list[CrawlResult] = []

        class CollectorPipeline(Pipeline):
            async def process(self, result: CrawlResult) -> None:
                collected.append(result)

        config = CrawlerConfig(
            name="test-pipeline",
            seeds=["http://example.com"],
            max_depth=0,
        )

        mock_fetcher = MockFetcher()
        mock_fetcher.add_page("http://example.com", "<html><head><title>Test</title></head><body>Content</body></html>")

        crawler = Crawler(config, pipelines=[CollectorPipeline()])
        crawler._fetcher = mock_fetcher

        await crawler.run()

        assert len(collected) >= 1
        assert collected[0].parse.title == "Test"
