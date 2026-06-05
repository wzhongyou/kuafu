"""SearchIndexPipeline 单元测试"""

import json
import tempfile

import pytest

from kuafu.models import CrawlResult, FetchRequest, FetchResult, ParseResult, URLItem, URLStatus
from kuafu.search.pipeline import SearchIndexPipeline


def _make_crawl_result(url="https://example.com/page", title="Test") -> CrawlResult:
    fetch = FetchResult(url=url, status_code=200, content_type="text/html")
    parse = ParseResult(title=title, text="Some content", canonical=url)
    url_item = URLItem(raw=url, normalized=url, depth=1, status=URLStatus.COMPLETED)
    request = FetchRequest(url=url)
    return CrawlResult(request=request, fetch=fetch, parse=parse, url_item=url_item)


class TestSearchIndexPipeline:
    @pytest.mark.asyncio
    async def test_process_writes_jsonl(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            path = f.name

        try:
            pipeline = SearchIndexPipeline(path)
            result = _make_crawl_result()
            await pipeline.process(result)
            await pipeline.close()

            with open(path) as f:
                line = f.readline()
                doc = json.loads(line)
                assert doc["url"] == "https://example.com/page"
                assert doc["title"] == "Test"
                assert doc["text"] == "Some content"
                assert "doc_id" in doc
                assert "content_hash" in doc
        finally:
            import os
            os.unlink(path)

    @pytest.mark.asyncio
    async def test_multiple_results(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            path = f.name

        try:
            pipeline = SearchIndexPipeline(path)
            await pipeline.process(_make_crawl_result(url="https://a.com", title="A"))
            await pipeline.process(_make_crawl_result(url="https://b.com", title="B"))
            await pipeline.close()

            with open(path) as f:
                lines = f.readlines()
            assert len(lines) == 2
            docs = [json.loads(l) for l in lines]
            assert docs[0]["title"] == "A"
            assert docs[1]["title"] == "B"
        finally:
            import os
            os.unlink(path)

    @pytest.mark.asyncio
    async def test_text_not_truncated(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            path = f.name

        try:
            pipeline = SearchIndexPipeline(path)
            long_text = "x" * 10000
            fetch = FetchResult(url="https://example.com/long", status_code=200)
            parse = ParseResult(title="Long", text=long_text, canonical="https://example.com/long")
            url_item = URLItem(raw="https://example.com/long", normalized="https://example.com/long", depth=0, status=URLStatus.COMPLETED)
            request = FetchRequest(url="https://example.com/long")
            result = CrawlResult(request=request, fetch=fetch, parse=parse, url_item=url_item)
            await pipeline.process(result)
            await pipeline.close()

            with open(path) as f:
                doc = json.loads(f.readline())
                assert len(doc["text"]) == 10000
        finally:
            import os
            os.unlink(path)

    @pytest.mark.asyncio
    async def test_close_idempotent(self):
        pipeline = SearchIndexPipeline("/tmp/test_search.jsonl")
        await pipeline.close()
        await pipeline.close()  # 不应抛出异常
