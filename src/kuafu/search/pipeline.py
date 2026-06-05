"""SearchIndexPipeline — 将 CrawlResult 转为 SearchDocument 并写入 JSONL"""

from __future__ import annotations

from kuafu.models import CrawlResult
from kuafu.pipeline.pipeline import Pipeline
from kuafu.search.transformer import transform


class SearchIndexPipeline(Pipeline):
    """搜索索引管道

    将 CrawlResult 转换为 SearchDocument，序列化为 JSONL 写入文件。
    完整文本不截断，pydantic v2 自动处理 datetime 序列化。
    """

    def __init__(self, path: str) -> None:
        self._path = path
        self._file = None

    async def process(self, result: CrawlResult) -> None:
        doc = transform(result)
        line = doc.model_dump_json(exclude_none=True) + "\n"

        if self._file is None:
            import aiofiles
            self._file = await aiofiles.open(self._path, "a", encoding="utf-8")

        await self._file.write(line)

    async def close(self) -> None:
        if self._file:
            await self._file.close()
            self._file = None
