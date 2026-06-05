"""调度器抽象接口"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence

from kuafu.models import FetchResult, URLItem


class Scheduler(ABC):
    """URL 调度器抽象接口"""

    @abstractmethod
    async def push(self, urls: Sequence[URLItem]) -> None:
        """接收新发现的 URL"""

    @abstractmethod
    async def schedule(self, limit: int) -> list[URLItem]:
        """获取待调度的 URL 批次"""

    @abstractmethod
    async def feedback(self, result: FetchResult) -> None:
        """反馈抓取结果（用于自适应调度）"""

    @abstractmethod
    async def start(self) -> None:
        """启动调度器"""

    @abstractmethod
    async def stop(self) -> None:
        """停止调度器"""
