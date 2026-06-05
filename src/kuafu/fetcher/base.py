"""Fetcher 抽象接口"""

from __future__ import annotations

from abc import ABC, abstractmethod

from kuafu.models import FetchRequest, FetchResult


class Fetcher(ABC):
    """HTTP 抓取器抽象接口"""

    @abstractmethod
    async def fetch(self, request: FetchRequest) -> FetchResult:
        """执行 HTTP 请求"""

    @abstractmethod
    async def close(self) -> None:
        """关闭客户端，释放资源"""
