"""EventBus — asyncio.Queue 发布-订阅事件桥"""

from __future__ import annotations

import asyncio


class EventBus:
    """将 Crawler 的 fire-and-forget 事件桥接到 SSE 客户端

    每个 SSE 客户端获得一个 asyncio.Queue，
    publish() 广播到所有订阅者。
    """

    def __init__(self, maxsize: int = 100) -> None:
        self._subscribers: list[asyncio.Queue] = []
        self._maxsize = maxsize

    def subscribe(self) -> asyncio.Queue:
        """创建新的订阅队列"""
        q: asyncio.Queue = asyncio.Queue(maxsize=self._maxsize)
        self._subscribers.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        """移除订阅队列"""
        if q in self._subscribers:
            self._subscribers.remove(q)

    def publish(self, event_type: str, data: dict) -> None:
        """广播事件到所有订阅者，满队列丢弃最旧"""
        message = {"event": event_type, "data": data}
        for q in self._subscribers:
            try:
                q.put_nowait(message)
            except asyncio.QueueFull:
                try:
                    q.get_nowait()
                    q.put_nowait(message)
                except (asyncio.QueueEmpty, asyncio.QueueFull):
                    pass

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)
