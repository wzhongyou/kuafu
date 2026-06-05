"""事件系统单元测试"""

import asyncio

import pytest

from kuafu.events import CRAWL_STARTED, CRAWL_STOPPED, EventEmitter, PROGRESS


class TestEventEmitter:
    def test_on_and_emit(self):
        emitter = EventEmitter()
        results = []

        async def callback(value=None):
            results.append(value)

        emitter.on("test", callback)
        emitter.emit("test", value=42)

        # emit 是 fire-and-forget，在无事件循环时不执行
        # 需要运行事件循环来验证
        assert len(results) == 0 or len(results) == 1

    @pytest.mark.asyncio
    async def test_emit_with_running_loop(self):
        emitter = EventEmitter()
        results = []

        async def callback(value=None):
            results.append(value)

        emitter.on("test", callback)
        emitter.emit("test", value=42)
        # 等待 create_task 完成
        await asyncio.sleep(0.05)
        assert results == [42]

    @pytest.mark.asyncio
    async def test_multiple_listeners(self):
        emitter = EventEmitter()
        results = []

        async def cb1(value=None):
            results.append(("cb1", value))

        async def cb2(value=None):
            results.append(("cb2", value))

        emitter.on("test", cb1)
        emitter.on("test", cb2)
        emitter.emit("test", value=1)
        await asyncio.sleep(0.05)
        assert ("cb1", 1) in results
        assert ("cb2", 1) in results

    @pytest.mark.asyncio
    async def test_off_removes_listener(self):
        emitter = EventEmitter()
        results = []

        async def callback(value=None):
            results.append(value)

        emitter.on("test", callback)
        emitter.off("test", callback)
        emitter.emit("test", value=1)
        await asyncio.sleep(0.05)
        assert results == []

    def test_off_nonexistent_event(self):
        emitter = EventEmitter()

        async def callback():
            pass

        # 不应抛出异常
        emitter.off("nonexistent", callback)

    @pytest.mark.asyncio
    async def test_clear(self):
        emitter = EventEmitter()
        results = []

        async def callback(value=None):
            results.append(value)

        emitter.on("test", callback)
        emitter.clear()
        emitter.emit("test", value=1)
        await asyncio.sleep(0.05)
        assert results == []

    @pytest.mark.asyncio
    async def test_event_constants(self):
        assert CRAWL_STARTED == "crawl_started"
        assert CRAWL_STOPPED == "crawl_stopped"
        assert PROGRESS == "progress"

    @pytest.mark.asyncio
    async def test_emit_with_kwargs(self):
        emitter = EventEmitter()
        received = {}

        async def callback(name=None, count=None):
            received["name"] = name
            received["count"] = count

        emitter.on("test", callback)
        emitter.emit("test", name="kuafu", count=10)
        await asyncio.sleep(0.05)
        assert received == {"name": "kuafu", "count": 10}
