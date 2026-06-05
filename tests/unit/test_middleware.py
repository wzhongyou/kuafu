"""中间件测试"""

import pytest

from kuafu.middleware.middleware import UAMiddleware, RefererMiddleware, DepthMiddleware
from kuafu.models import FetchRequest


class TestUAMiddleware:
    @pytest.mark.asyncio
    async def test_sets_user_agent(self):
        mw = UAMiddleware()
        request = FetchRequest(url="http://example.com")
        result = await mw.process_request(request)
        assert "User-Agent" in result.headers
        assert result.headers["User-Agent"] != ""

    @pytest.mark.asyncio
    async def test_custom_agents(self):
        mw = UAMiddleware(user_agents=["TestBot/1.0"])
        request = FetchRequest(url="http://example.com")
        result = await mw.process_request(request)
        assert result.headers["User-Agent"] == "TestBot/1.0"


class TestRefererMiddleware:
    @pytest.mark.asyncio
    async def test_sets_referer(self):
        mw = RefererMiddleware()
        request = FetchRequest(url="http://example.com/page")
        result = await mw.process_request(request)
        assert "Referer" in result.headers

    @pytest.mark.asyncio
    async def test_does_not_override_existing(self):
        mw = RefererMiddleware()
        request = FetchRequest(url="http://example.com/page", headers={"Referer": "http://other.com"})
        result = await mw.process_request(request)
        assert result.headers["Referer"] == "http://other.com"


class TestDepthMiddleware:
    @pytest.mark.asyncio
    async def test_allows_within_depth(self):
        mw = DepthMiddleware(max_depth=5)
        request = FetchRequest(url="http://example.com", max_depth=3)
        result = await mw.process_request(request)
        assert result.headers.get("X-Skip-Depth") != "true"

    @pytest.mark.asyncio
    async def test_marks_over_depth(self):
        mw = DepthMiddleware(max_depth=3)
        request = FetchRequest(url="http://example.com", max_depth=5)
        result = await mw.process_request(request)
        assert result.headers.get("X-Skip-Depth") == "true"
