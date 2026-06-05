"""Web 路由集成测试 — TestClient"""

import asyncio

import pytest
from httpx import ASGITransport, AsyncClient

from kuafu.web.app import create_app


@pytest.fixture
def app():
    return create_app()


@pytest.fixture
def transport(app):
    return ASGITransport(app=app)


@pytest.mark.asyncio
async def test_index_page(transport):
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/")
        assert r.status_code == 200
        assert "kuafu" in r.text


@pytest.mark.asyncio
async def test_get_status(transport):
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/api/status")
        assert r.status_code == 200
        data = r.json()
        assert data["state"] == "idle"
        assert data["pages_crawled"] == 0


@pytest.mark.asyncio
async def test_get_results(transport):
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/api/results")
        assert r.status_code == 200
        assert r.json() == []


@pytest.mark.asyncio
async def test_start_crawl_validation(transport):
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 缺少 URL
        r = await client.post("/api/crawl/start", json={"url": ""})
        assert r.status_code == 422

        # 非 http/https
        r = await client.post("/api/crawl/start", json={"url": "file:///etc/passwd"})
        assert r.status_code == 422

        # max_pages 超界
        r = await client.post("/api/crawl/start", json={"url": "https://example.com", "max_pages": -1})
        assert r.status_code == 422


@pytest.mark.asyncio
async def test_export_no_results(transport):
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post("/api/crawl/export")
        assert r.status_code == 400


@pytest.mark.asyncio
async def test_build_index_validation(transport):
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 非 http/https
        r = await client.post("/api/crawl/build-index", json={"vortex_url": "ftp://bad"})
        assert r.status_code == 422


@pytest.mark.asyncio
async def test_build_index_no_results(transport):
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post("/api/crawl/build-index", json={"vortex_url": "http://localhost:9090"})
        assert r.status_code == 400


@pytest.mark.asyncio
async def test_detail_missing_url(transport):
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/detail")
        assert r.status_code == 400


@pytest.mark.asyncio
async def test_detail_not_found(transport):
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/detail", params={"url": "https://nonexistent.com"})
        assert r.status_code == 404


@pytest.mark.asyncio
async def test_sse_endpoint(transport):
    async def _read_stream():
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            async with client.stream("GET", "/api/events") as resp:
                assert resp.status_code == 200
                assert "text/event-stream" in resp.headers.get("content-type", "")
                # Keep reading — the timeout will cancel us
                async for _ in resp.aiter_lines():
                    pass

    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(_read_stream(), timeout=2)
