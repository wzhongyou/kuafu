"""URL Frontier 存储抽象"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence

from kuafu.models import URLItem, URLStatus


class URLStore(ABC):
    """URL 状态存储的抽象接口

    实现类需保证线程安全 / 协程安全。
    """

    @abstractmethod
    async def put(self, url: URLItem) -> None:
        """写入或更新一个 URL"""

    @abstractmethod
    async def batch_put(self, urls: Sequence[URLItem]) -> None:
        """批量写入"""

    @abstractmethod
    async def update_status(self, normalized_url: str, status: URLStatus) -> None:
        """更新 URL 状态"""

    @abstractmethod
    async def get(self, normalized_url: str) -> URLItem | None:
        """获取 URL 条目"""

    @abstractmethod
    async def pop_pending(self, limit: int, *, host: str | None = None) -> list[URLItem]:
        """弹出待抓取 URL

        Args:
            limit: 最大数量
            host: 可选，限定 Host
        """

    @abstractmethod
    async def exists(self, normalized_url: str) -> bool:
        """URL 是否已存在"""

    @abstractmethod
    async def count_by_status(self, status: URLStatus) -> int:
        """按状态计数"""

    @abstractmethod
    async def close(self) -> None:
        """关闭存储"""
