"""Pipeline — 数据管道抽象与实现"""

from __future__ import annotations

from abc import ABC, abstractmethod

from kuafu.models import CrawlResult


class Pipeline(ABC):
    """数据管道抽象接口"""

    @abstractmethod
    async def process(self, result: CrawlResult) -> None:
        """处理爬取结果"""

    async def close(self) -> None:
        """清理资源"""


class PipelineChain:
    """管道链 — 顺序执行多个 Pipeline"""

    def __init__(self, pipelines: list[Pipeline]) -> None:
        self._pipelines = pipelines

    async def process(self, result: CrawlResult) -> None:
        for p in self._pipelines:
            await p.process(result)

    async def close(self) -> None:
        for p in self._pipelines:
            await p.close()


class ConsolePipeline(Pipeline):
    """控制台输出"""

    async def process(self, result: CrawlResult) -> None:
        print(f"[{result.fetch.status_code}] {result.fetch.url} "
              f"({result.fetch.duration:.2f}s) "
              f"title={result.parse.title[:50]!r}")


class FilePipeline(Pipeline):
    """JSON Lines 文件输出"""

    def __init__(self, path: str) -> None:
        self._path = path
        self._file = None

    async def process(self, result: CrawlResult) -> None:
        import json

        if self._file is None:
            import aiofiles
            self._file = await aiofiles.open(self._path, "a", encoding="utf-8")

        data = {
            "url": result.fetch.url,
            "status_code": result.fetch.status_code,
            "title": result.parse.title,
            "text": result.parse.text[:500],
            "links": [link.url for link in result.parse.links],
            "meta": result.parse.meta,
            "fetch_time": result.fetch.fetch_time.isoformat() if result.fetch.fetch_time else None,
            "duration": result.fetch.duration,
        }
        await self._file.write(json.dumps(data, ensure_ascii=False) + "\n")

    async def close(self) -> None:
        if self._file:
            await self._file.close()
            self._file = None
