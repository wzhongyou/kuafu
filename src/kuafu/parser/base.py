"""Parser 抽象接口"""

from __future__ import annotations

from abc import ABC, abstractmethod

from kuafu.models import ParseResult


class Parser(ABC):
    """页面解析器抽象接口"""

    @abstractmethod
    async def parse(self, url: str, body: bytes) -> ParseResult:
        """解析页面内容"""
