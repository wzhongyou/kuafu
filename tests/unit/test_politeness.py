"""Politeness 测试 — 断路器、令牌桶"""

import asyncio
import time

import pytest

from kuafu.politeness.manager import CircuitBreaker, TokenBucket


class TestCircuitBreaker:
    def test_initial_state_closed(self):
        cb = CircuitBreaker("example.com")
        assert cb.allow() is True

    def test_opens_after_threshold_failures(self):
        cb = CircuitBreaker("example.com", threshold=3)
        for _ in range(3):
            cb.record_failure()
        assert cb.allow() is False

    def test_success_resets_failures(self):
        cb = CircuitBreaker("example.com", threshold=3)
        cb.record_failure()
        cb.record_failure()
        cb.record_success()
        # 失败计数重置
        for _ in range(3):
            cb.record_failure()
        assert cb.allow() is False

    def test_half_open_after_cooldown(self):
        cb = CircuitBreaker("example.com", threshold=1, cooldown=0.05)
        cb.record_failure()
        assert cb.allow() is False
        time.sleep(0.15)
        assert cb.allow() is True  # HALF_OPEN

    def test_half_open_success_closes(self):
        cb = CircuitBreaker("example.com", threshold=1, cooldown=0.05)
        cb.record_failure()
        time.sleep(0.15)
        cb.allow()  # -> HALF_OPEN
        cb.record_success()
        assert cb.allow() is True  # -> CLOSED


class TestTokenBucket:
    def test_acquire_when_has_tokens(self):
        bucket = TokenBucket(rate=10.0, capacity=10)
        assert bucket.acquire() is True

    def test_acquire_depletes_tokens(self):
        bucket = TokenBucket(rate=1.0, capacity=2)
        assert bucket.acquire() is True
        assert bucket.acquire() is True
        assert bucket.acquire() is False

    @pytest.mark.asyncio
    async def test_wait_consumes_token(self):
        bucket = TokenBucket(rate=100.0, capacity=1)
        # 先消耗令牌
        assert bucket.acquire() is True
        assert bucket.acquire() is False
        # wait 会等待并消耗一个令牌
        await bucket.wait()
        # 令牌已被 wait 消耗，acquire 应该失败
        assert bucket.acquire() is False
