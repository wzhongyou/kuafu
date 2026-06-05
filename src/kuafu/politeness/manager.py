"""Politeness — 礼貌策略管理"""

from __future__ import annotations

import asyncio
import time
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from enum import Enum

from kuafu.models import FetchResult, URLItem


# ── 断路器 ──────────────────────────────────────────────

class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    """断路器：连续失败后暂停访问该 Host

    状态转换:
    CLOSED ──连续失败达阈值──▶ OPEN ──冷却结束──▶ HALF_OPEN
    HALF_OPEN ──成功──▶ CLOSED
    HALF_OPEN ──失败──▶ OPEN
    """

    def __init__(self, host: str, *, threshold: int = 5, cooldown: float = 60.0) -> None:
        self.host = host
        self.state = CircuitState.CLOSED
        self.failures = 0
        self.threshold = threshold
        self.cooldown = cooldown
        self.last_fail_time: float = 0.0

    def record_success(self) -> None:
        self.failures = 0
        self.state = CircuitState.CLOSED

    def record_failure(self) -> None:
        self.failures += 1
        self.last_fail_time = time.monotonic()
        if self.failures >= self.threshold:
            self.state = CircuitState.OPEN

    def allow(self) -> bool:
        match self.state:
            case CircuitState.CLOSED:
                return True
            case CircuitState.OPEN:
                if time.monotonic() - self.last_fail_time > self.cooldown:
                    self.state = CircuitState.HALF_OPEN
                    return True
                return False
            case CircuitState.HALF_OPEN:
                return True


# ── 令牌桶速率限制 ──────────────────────────────────────

class TokenBucket:
    """令牌桶速率限制器

    每个桶对应一个 Host，控制请求间隔。
    """

    def __init__(self, rate: float = 1.0, capacity: int | None = None) -> None:
        """
        Args:
            rate: 每秒添加的令牌数（即每秒允许的请求数）
            capacity: 桶容量（默认等于 rate，允许突发）
        """
        self._rate = rate
        self._capacity = capacity or max(1, int(rate))
        self._tokens: float = float(self._capacity)
        self._last_refill = time.monotonic()

    def acquire(self, timeout: float = 30.0) -> bool:
        """尝试获取一个令牌，非阻塞

        Returns:
            True 成功获取，False 超时
        """
        self._refill()
        if self._tokens >= 1.0:
            self._tokens -= 1.0
            return True
        return False

    async def wait(self) -> None:
        """等待直到获取一个令牌（获取后直接消耗）"""
        while True:
            self._refill()
            if self._tokens >= 1.0:
                self._tokens -= 1.0
                return
            # 计算等待时间
            wait_time = (1.0 - self._tokens) / self._rate
            await asyncio.sleep(min(wait_time, 0.1))

    def _refill(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last_refill
        self._tokens = min(self._capacity, self._tokens + elapsed * self._rate)
        self._last_refill = now


# ── robots.txt 管理 ──────────────────────────────────────

class RobotsRules:
    """robots.txt 规则缓存"""

    def __init__(
        self,
        *,
        allowed: set[str] | None = None,
        disallowed: set[str] | None = None,
        crawl_delay: float | None = None,
    ) -> None:
        self.allowed = allowed or set()
        self.disallowed = disallowed or set()
        self.crawl_delay = crawl_delay

    def is_allowed(self, path: str) -> bool:
        # 精确匹配 + 前缀匹配
        for pattern in self.disallowed:
            if path == pattern or path.startswith(pattern):
                # 检查是否有更具体的 Allow 覆盖
                for allow_pattern in self.allowed:
                    if path.startswith(allow_pattern) and len(allow_pattern) > len(pattern):
                        return True
                return False
        return True


class RobotsTxtManager:
    """robots.txt 管理（带缓存）"""

    def __init__(self, *, cache_ttl: float = 86400.0) -> None:
        self._cache: dict[str, tuple[float, RobotsRules]] = {}
        self._cache_ttl = cache_ttl

    def get_rules(self, host: str) -> RobotsRules | None:
        """获取缓存的 robots 规则"""
        entry = self._cache.get(host)
        if entry is None:
            return None
        cached_time, rules = entry
        if time.monotonic() - cached_time > self._cache_ttl:
            del self._cache[host]
            return None
        return rules

    def set_rules(self, host: str, rules: RobotsRules) -> None:
        """缓存 robots 规则"""
        self._cache[host] = (time.monotonic(), rules)

    def is_allowed(self, user_agent: str, url: str) -> bool:
        """检查 URL 是否被允许"""
        from yarl import URL
        try:
            parsed = URL(url)
            host = parsed.host or ""
            path = parsed.path
        except ValueError:
            return True

        rules = self.get_rules(host)
        if rules is None:
            return True  # 未获取到 robots.txt，默认允许
        return rules.is_allowed(path)


# ── Politeness 管理器 ────────────────────────────────────

class HostPolitenessConfig:
    """单 Host 的礼貌配置"""

    def __init__(
        self,
        *,
        crawl_delay: float = 1.0,
        max_concurrent: int = 2,
        max_requests: int = 0,       # 0 不限
        time_window: float = 60.0,
    ) -> None:
        self.crawl_delay = crawl_delay
        self.max_concurrent = max_concurrent
        self.max_requests = max_requests
        self.time_window = time_window


class PolitenessManager:
    """多层 Politeness 策略管理器

    检查顺序:
    1. robots.txt
    2. 断路器
    3. 速率限制（令牌桶）
    4. 并发限制（信号量）
    """

    def __init__(
        self,
        *,
        default_delay: float = 1.0,
        max_concurrent_per_host: int = 2,
        circuit_threshold: int = 5,
        circuit_cooldown: float = 60.0,
        respect_crawl_delay: bool = True,
        robots_cache_ttl: float = 86400.0,
    ) -> None:
        self._default_delay = default_delay
        self._max_concurrent = max_concurrent_per_host
        self._circuit_threshold = circuit_threshold
        self._circuit_cooldown = circuit_cooldown
        self._respect_crawl_delay = respect_crawl_delay

        # Per-Host 组件
        self._rate_limiters: dict[str, TokenBucket] = {}
        self._circuit_breakers: dict[str, CircuitBreaker] = {}
        self._semaphores: dict[str, asyncio.Semaphore] = {}
        self._host_configs: dict[str, HostPolitenessConfig] = {}

        # robots.txt 管理
        self._robots = RobotsTxtManager(cache_ttl=robots_cache_ttl)

    def _get_rate_limiter(self, host: str) -> TokenBucket:
        if host not in self._rate_limiters:
            config = self._host_configs.get(host)
            delay = config.crawl_delay if config else self._default_delay
            rate = 1.0 / delay if delay > 0 else 10.0
            self._rate_limiters[host] = TokenBucket(rate=rate)
        return self._rate_limiters[host]

    def _get_circuit_breaker(self, host: str) -> CircuitBreaker:
        if host not in self._circuit_breakers:
            self._circuit_breakers[host] = CircuitBreaker(
                host, threshold=self._circuit_threshold, cooldown=self._circuit_cooldown
            )
        return self._circuit_breakers[host]

    def _get_semaphore(self, host: str) -> asyncio.Semaphore:
        if host not in self._semaphores:
            config = self._host_configs.get(host)
            max_conc = config.max_concurrent if config else self._max_concurrent
            self._semaphores[host] = asyncio.Semaphore(max_conc)
        return self._semaphores[host]

    async def allow(self, url: URLItem) -> bool:
        """检查是否允许访问"""
        from yarl import URL
        try:
            host = URL(url.normalized).host or ""
        except ValueError:
            return True

        # 1. robots.txt
        if not self._robots.is_allowed("kuafu", url.normalized):
            return False

        # 2. 断路器
        cb = self._get_circuit_breaker(host)
        if not cb.allow():
            return False

        return True

    async def wait(self, host: str) -> None:
        """等待直到可以访问该 Host"""
        # 3. 速率限制
        limiter = self._get_rate_limiter(host)
        await limiter.wait()

    async def acquire_slot(self, host: str) -> None:
        """获取并发槽位"""
        sem = self._get_semaphore(host)
        await sem.acquire()

    def release_slot(self, host: str) -> None:
        """释放并发槽位"""
        sem = self._semaphores.get(host)
        if sem:
            sem.release()

    def record(self, host: str, result: FetchResult) -> None:
        """记录一次访问结果"""
        cb = self._get_circuit_breaker(host)
        if result.is_success:
            cb.record_success()
        else:
            cb.record_failure()

    @property
    def robots(self) -> RobotsTxtManager:
        return self._robots

    def set_host_config(self, host: str, config: HostPolitenessConfig) -> None:
        """设置特定 Host 的配置"""
        self._host_configs[host] = config
        # 清除缓存，下次访问时用新配置重建
        self._rate_limiters.pop(host, None)
        self._semaphores.pop(host, None)
