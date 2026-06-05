"""CrawlManager 单元测试"""

import pytest

from kuafu.web.crawl_manager import CrawlManager
from kuafu.web.event_bus import EventBus


class TestCrawlManagerInit:
    def test_initial_state(self):
        cm = CrawlManager()
        assert cm.state == "idle"
        assert cm.results == []
        assert isinstance(cm.event_bus, EventBus)

    def test_initial_status(self):
        cm = CrawlManager()
        status = cm.get_status()
        assert status["state"] == "idle"
        assert status["result_count"] == 0
        assert status["pages_crawled"] == 0


class TestCrawlManagerExport:
    @pytest.mark.asyncio
    async def test_export_empty(self):
        cm = CrawlManager()
        assert cm.export_jsonl() == ""

    @pytest.mark.asyncio
    async def test_start_crawl_already_running(self):
        cm = CrawlManager()
        cm._state = "running"
        with pytest.raises(RuntimeError, match="already in progress"):
            await cm.start_crawl("https://example.com")

    @pytest.mark.asyncio
    async def test_start_crawl_already_paused(self):
        cm = CrawlManager()
        cm._state = "paused"
        with pytest.raises(RuntimeError, match="already in progress"):
            await cm.start_crawl("https://example.com")

    @pytest.mark.asyncio
    async def test_build_vortex_index_empty(self):
        cm = CrawlManager()
        result = await cm.build_vortex_index("http://localhost:9090")
        assert result["total"] == 0
        assert result["success"] == 0

    def test_get_result_not_found(self):
        cm = CrawlManager()
        assert cm.get_result("https://nonexistent.com") is None
