"""去重引擎抽象与实现"""

from __future__ import annotations

import math
from abc import ABC, abstractmethod

import mmh3


class URLDeduplicator(ABC):
    """URL 去重器抽象接口"""

    @abstractmethod
    async def seen(self, normalized_url: str) -> bool:
        """URL 是否已存在"""

    @abstractmethod
    async def mark(self, normalized_url: str) -> None:
        """标记 URL 为已见"""

    @abstractmethod
    async def batch_mark(self, urls: list[str]) -> None:
        """批量标记"""

    @abstractmethod
    async def close(self) -> None:
        """关闭，释放资源"""


class MemoryDeduplicator(URLDeduplicator):
    """基于 set 的内存去重 — 百万级精确去重"""

    def __init__(self) -> None:
        self._seen: set[str] = set()

    async def seen(self, normalized_url: str) -> bool:
        return normalized_url in self._seen

    async def mark(self, normalized_url: str) -> None:
        self._seen.add(normalized_url)

    async def batch_mark(self, urls: list[str]) -> None:
        self._seen.update(urls)

    async def close(self) -> None:
        self._seen.clear()


class BloomFilterDeduplicator(URLDeduplicator):
    """基于 mmh3 的 Bloom Filter 去重 — 亿级概率去重

    优势: 空间效率极高，1 千万 URL 仅需约 17MB
    劣势: 存在误判率（可配置），且不可删除
    """

    def __init__(
        self,
        expected_items: int = 10_000_000,
        false_positive_rate: float = 0.01,
    ) -> None:
        # 计算最优 bit 数 m 和 hash 函数数 k
        # m = -n * ln(p) / (ln2)^2
        # k = m/n * ln2
        self._m = int(-expected_items * math.log(false_positive_rate) / (math.log(2) ** 2))
        self._k = int(self._m / expected_items * math.log(2))
        self._k = max(1, self._k)
        self._bitarray = bytearray(math.ceil(self._m / 8))
        self._seeds = list(range(self._k))

    def _get_positions(self, url: str) -> list[int]:
        return [mmh3.hash(url, seed) % self._m for seed in self._seeds]

    async def seen(self, normalized_url: str) -> bool:
        for pos in self._get_positions(normalized_url):
            byte_idx = pos >> 3
            bit_idx = pos & 7
            if not (self._bitarray[byte_idx] & (1 << bit_idx)):
                return False
        return True

    async def mark(self, normalized_url: str) -> None:
        for pos in self._get_positions(normalized_url):
            byte_idx = pos >> 3
            bit_idx = pos & 7
            self._bitarray[byte_idx] |= (1 << bit_idx)

    async def batch_mark(self, urls: list[str]) -> None:
        for url in urls:
            await self.mark(url)

    async def close(self) -> None:
        self._bitarray = bytearray(0)
