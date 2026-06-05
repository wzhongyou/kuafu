"""Search E2E 集成测试 — CrawlResult → SearchDocument → JSONL 完整流程"""

import json
import tempfile

import pytest

from kuafu.fetcher.base import Fetcher
from kuafu.models import CrawlResult, FetchRequest, FetchResult, ParseResult
from kuafu.search.pipeline import SearchIndexPipeline
from kuafu.search.transformer import transform


class _SimpleFetcher(Fetcher):
    async def fetch(self, request: FetchRequest) -> FetchResult:
        return FetchResult(
            url=request.url,
            status_code=200,
            content_type="text/html",
            body=b'<html><head><title>E2E Test</title><meta name="description" content="E2E desc"><meta name="author" content="Tester"></head><body>Content for search index.</body></html>',
        )

    async def close(self) -> None:
        pass


class TestSearchE2E:
    @pytest.mark.asyncio
    async def test_full_pipeline(self):
        """CrawlResult → SearchDocument → JSONL 完整流程"""
        fetcher = _SimpleFetcher()
        fetch_result = await fetcher.fetch(FetchRequest(url="https://example.com/e2e"))
        parse_result = ParseResult(
            title="E2E Test",
            text="Content for search index.",
            meta={"description": "E2E desc", "author": "Tester"},
            canonical="https://example.com/e2e",
            language="en",
        )
        crawl_result = CrawlResult(
            request=FetchRequest(url="https://example.com/e2e"),
            fetch=fetch_result,
            parse=parse_result,
        )

        # 转换
        doc = transform(crawl_result)
        assert doc.title == "E2E Test"
        assert doc.description == "E2E desc"
        assert doc.author == "Tester"
        assert doc.site == "example.com"

        # 写入 JSONL
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            path = f.name

        try:
            pipeline = SearchIndexPipeline(path)
            await pipeline.process(crawl_result)
            await pipeline.close()

            with open(path) as f:
                written = json.loads(f.readline())
                assert written["title"] == "E2E Test"
                assert written["description"] == "E2E desc"
                assert written["author"] == "Tester"
                assert written["doc_id"] == doc.doc_id
        finally:
            import os
            os.unlink(path)
