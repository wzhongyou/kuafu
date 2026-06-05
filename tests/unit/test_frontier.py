"""Frontier (MemoryURLStore) 测试"""

import pytest

from kuafu.frontier.memory import MemoryURLStore
from kuafu.models import URLItem, URLStatus


class TestMemoryURLStore:
    @pytest.fixture
    def store(self):
        return MemoryURLStore()

    @pytest.mark.asyncio
    async def test_put_and_get(self, store):
        item = URLItem(raw="http://example.com", normalized="http://example.com")
        await store.put(item)
        result = await store.get("http://example.com")
        assert result is not None
        assert result.normalized == "http://example.com"

    @pytest.mark.asyncio
    async def test_get_nonexistent(self, store):
        result = await store.get("http://nonexistent.com")
        assert result is None

    @pytest.mark.asyncio
    async def test_exists(self, store):
        await store.put(URLItem(raw="http://example.com", normalized="http://example.com"))
        assert await store.exists("http://example.com") is True
        assert await store.exists("http://other.com") is False

    @pytest.mark.asyncio
    async def test_update_status(self, store):
        await store.put(URLItem(raw="http://example.com", normalized="http://example.com", status=URLStatus.PENDING))
        await store.update_status("http://example.com", URLStatus.FETCHING)
        result = await store.get("http://example.com")
        assert result.status == URLStatus.FETCHING

    @pytest.mark.asyncio
    async def test_pop_pending(self, store):
        await store.put(URLItem(raw="http://a.com", normalized="http://a.com", status=URLStatus.PENDING))
        await store.put(URLItem(raw="http://b.com", normalized="http://b.com", status=URLStatus.PENDING))
        items = await store.pop_pending(2)
        assert len(items) == 2
        # popped items should be FETCHING
        for item in items:
            assert item.status == URLStatus.FETCHING

    @pytest.mark.asyncio
    async def test_pop_pending_limit(self, store):
        for i in range(5):
            await store.put(URLItem(raw=f"http://s{i}.com", normalized=f"http://s{i}.com", status=URLStatus.PENDING))
        items = await store.pop_pending(3)
        assert len(items) == 3

    @pytest.mark.asyncio
    async def test_pop_pending_skips_non_pending(self, store):
        await store.put(URLItem(raw="http://a.com", normalized="http://a.com", status=URLStatus.PENDING))
        await store.put(URLItem(raw="http://b.com", normalized="http://b.com", status=URLStatus.FETCHING))
        items = await store.pop_pending(10)
        assert len(items) == 1
        assert items[0].normalized == "http://a.com"

    @pytest.mark.asyncio
    async def test_count_by_status(self, store):
        await store.put(URLItem(raw="http://a.com", normalized="http://a.com", status=URLStatus.PENDING))
        await store.put(URLItem(raw="http://b.com", normalized="http://b.com", status=URLStatus.PENDING))
        await store.put(URLItem(raw="http://c.com", normalized="http://c.com", status=URLStatus.FETCHING))
        assert await store.count_by_status(URLStatus.PENDING) == 2
        assert await store.count_by_status(URLStatus.FETCHING) == 1

    @pytest.mark.asyncio
    async def test_batch_put(self, store):
        items = [
            URLItem(raw=f"http://s{i}.com", normalized=f"http://s{i}.com")
            for i in range(3)
        ]
        await store.batch_put(items)
        assert await store.count_by_status(URLStatus.DISCOVERED) == 3
