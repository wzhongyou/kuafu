"""去重引擎测试"""

import pytest

from kuafu.dedup.bloom import BloomFilterDeduplicator, MemoryDeduplicator


class TestMemoryDeduplicator:
    @pytest.fixture
    def dedup(self):
        return MemoryDeduplicator()

    @pytest.mark.asyncio
    async def test_not_seen_initially(self, dedup):
        assert not await dedup.seen("http://example.com")

    @pytest.mark.asyncio
    async def test_seen_after_mark(self, dedup):
        await dedup.mark("http://example.com")
        assert await dedup.seen("http://example.com")

    @pytest.mark.asyncio
    async def test_batch_mark(self, dedup):
        urls = ["http://a.com", "http://b.com", "http://c.com"]
        await dedup.batch_mark(urls)
        for url in urls:
            assert await dedup.seen(url)

    @pytest.mark.asyncio
    async def test_no_false_positive(self, dedup):
        await dedup.mark("http://example.com")
        assert not await dedup.seen("http://other.com")


class TestBloomFilterDeduplicator:
    @pytest.fixture
    def dedup(self):
        return BloomFilterDeduplicator(expected_items=1000, false_positive_rate=0.01)

    @pytest.mark.asyncio
    async def test_not_seen_initially(self, dedup):
        assert not await dedup.seen("http://example.com")

    @pytest.mark.asyncio
    async def test_seen_after_mark(self, dedup):
        await dedup.mark("http://example.com")
        assert await dedup.seen("http://example.com")

    @pytest.mark.asyncio
    async def test_low_false_positive_rate(self, dedup):
        """测试误判率在可接受范围内"""
        # 插入 500 个 URL
        for i in range(500):
            await dedup.mark(f"http://site{i}.com")

        # 检查 100 个未插入的 URL，误判应极少
        false_positives = 0
        for i in range(500, 600):
            if await dedup.seen(f"http://site{i}.com"):
                false_positives += 1

        # 1% 误判率下，100 次检查期望最多 1-2 个误判
        assert false_positives <= 5, f"Too many false positives: {false_positives}"

    @pytest.mark.asyncio
    async def test_batch_mark(self, dedup):
        urls = [f"http://site{i}.com" for i in range(50)]
        await dedup.batch_mark(urls)
        assert await dedup.seen("http://site0.com")
        assert await dedup.seen("http://site49.com")
