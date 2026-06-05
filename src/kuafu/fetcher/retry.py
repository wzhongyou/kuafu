"""重试策略"""

from __future__ import annotations

import random

from kuafu.models import FetchResult


class RetryPolicy:
    """HTTP 请求重试策略

    - 408 (Request Timeout): 重试，指数退避
    - 429 (Too Many Requests): 重试，使用 Retry-After 头
    - 5xx: 重试，指数退避
    - 3xx: 跟随重定向（不算重试）
    - 其他 4xx: 不重试
    """

    def __init__(
        self,
        max_retries: int = 3,
        retry_on_status: list[int] | None = None,
    ) -> None:
        self.max_retries = max_retries
        self.retry_on_status = retry_on_status or [408, 429, 500, 502, 503, 504]

    def should_retry(self, result: FetchResult, attempt: int) -> bool:
        """判断是否应该重试"""
        if attempt >= self.max_retries:
            return False
        if result.error is not None:
            return True
        return result.status_code in self.retry_on_status

    def get_delay(self, result: FetchResult, attempt: int) -> float:
        """获取重试延迟（秒）"""
        # 429 优先使用 Retry-After 头
        if result.status_code == 429:
            retry_after = result.headers.get("retry-after")
            if retry_after:
                try:
                    return float(retry_after)
                except ValueError:
                    pass

        return self.exponential_backoff(attempt)

    @staticmethod
    def exponential_backoff(attempt: int) -> float:
        """指数退避 + 随机抖动: 1s, 2s, 4s, 8s... ±25%"""
        base = 2**attempt
        jitter = base * random.uniform(0.75, 1.25)
        return jitter
