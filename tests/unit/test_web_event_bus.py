"""EventBus 单元测试"""

import asyncio

import pytest

from kuafu.web.event_bus import EventBus


class TestEventBus:
    def test_subscribe_returns_queue(self):
        bus = EventBus()
        q = bus.subscribe()
        assert isinstance(q, asyncio.Queue)
        assert bus.subscriber_count == 1

    def test_multiple_subscribers(self):
        bus = EventBus()
        q1 = bus.subscribe()
        q2 = bus.subscribe()
        assert bus.subscriber_count == 2
        assert q1 is not q2

    def test_unsubscribe(self):
        bus = EventBus()
        q = bus.subscribe()
        bus.unsubscribe(q)
        assert bus.subscriber_count == 0

    def test_unsubscribe_nonexistent(self):
        bus = EventBus()
        q = asyncio.Queue()
        bus.unsubscribe(q)  # 不应抛出异常

    def test_publish_delivers_to_all(self):
        bus = EventBus()
        q1 = bus.subscribe()
        q2 = bus.subscribe()
        bus.publish("test", {"key": "value"})
        assert q1.get_nowait() == {"event": "test", "data": {"key": "value"}}
        assert q2.get_nowait() == {"event": "test", "data": {"key": "value"}}

    def test_publish_drops_oldest_on_full(self):
        bus = EventBus(maxsize=2)
        q = bus.subscribe()
        bus.publish("e1", {"n": 1})
        bus.publish("e2", {"n": 2})
        bus.publish("e3", {"n": 3})  # 满了，应丢弃 e1
        msg1 = q.get_nowait()
        msg2 = q.get_nowait()
        assert msg1["data"]["n"] == 2
        assert msg2["data"]["n"] == 3

    def test_unsubscribed_queue_does_not_receive(self):
        bus = EventBus()
        q = bus.subscribe()
        bus.unsubscribe(q)
        bus.publish("test", {"key": "value"})
        assert q.empty()
