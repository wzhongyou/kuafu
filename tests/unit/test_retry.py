"""重试策略测试"""

import pytest

from kuafu.fetcher.retry import RetryPolicy
from kuafu.models import FetchResult


class TestRetryPolicy:
    @pytest.fixture
    def policy(self):
        return RetryPolicy(max_retries=3)

    def test_should_retry_on_error(self, policy):
        result = FetchResult(url="http://example.com", error="timeout")
        assert policy.should_retry(result, 0) is True

    def test_should_retry_on_5xx(self, policy):
        result = FetchResult(url="http://example.com", status_code=500)
        assert policy.should_retry(result, 0) is True

    def test_should_retry_on_429(self, policy):
        result = FetchResult(url="http://example.com", status_code=429)
        assert policy.should_retry(result, 0) is True

    def test_should_not_retry_on_4xx(self, policy):
        result = FetchResult(url="http://example.com", status_code=404)
        assert policy.should_retry(result, 0) is False

    def test_should_not_retry_max_reached(self, policy):
        result = FetchResult(url="http://example.com", error="timeout")
        assert policy.should_retry(result, 3) is False

    def test_exponential_backoff_increases(self):
        delays = [RetryPolicy.exponential_backoff(i) for i in range(5)]
        # 指数增长趋势
        for i in range(1, len(delays)):
            assert delays[i] >= delays[i - 1] * 0.5  # 允许抖动

    def test_429_uses_retry_after(self, policy):
        result = FetchResult(
            url="http://example.com",
            status_code=429,
            headers={"retry-after": "5"},
        )
        delay = policy.get_delay(result, 0)
        assert delay == 5.0
