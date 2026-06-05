"""事件系统 — 轻量 asyncio 事件总线"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from collections.abc import Callable, Coroutine
from typing import Any

# ── 事件类型常量 ──────────────────────────────────────────

CRAWL_STARTED = "crawl_started"
CRAWL_STOPPED = "crawl_stopped"
URL_FETCHED = "url_fetched"
URL_FAILED = "url_failed"
URL_DISCOVERED = "url_discovered"
PROGRESS = "progress"


class EventEmitter:
    """异步事件发射器

    - on/off 注册/移除监听器
    - emit 非阻塞派发（通过 create_task）
    - 支持多个监听器同一事件
    """

    def __init__(self) -> None:
        self._listeners: dict[str, list[Callable[..., Coroutine]]] = defaultdict(list)

    def on(self, event: str, callback: Callable[..., Coroutine]) -> None:
        """注册事件监听器"""
        self._listeners[event].append(callback)

    def off(self, event: str, callback: Callable[..., Coroutine]) -> None:
        """移除事件监听器"""
        listeners = self._listeners.get(event)
        if listeners:
            try:
                listeners.remove(callback)
            except ValueError:
                pass

    def emit(self, event: str, **kwargs: Any) -> None:
        """发射事件（非阻塞，fire-and-forget）"""
        for callback in self._listeners.get(event, []):
            try:
                asyncio.get_event_loop().create_task(callback(**kwargs))
            except RuntimeError:
                # 事件循环未运行时忽略（如测试环境）
                pass

    def clear(self) -> None:
        """清除所有监听器"""
        self._listeners.clear()
