"""API 路由 — REST + SSE + 页面"""

from __future__ import annotations

import asyncio
import json

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, Response, StreamingResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field, field_validator

from kuafu.web.crawl_manager import CrawlManager

router = APIRouter()
templates = Jinja2Templates(
    directory=str(__import__("pathlib").Path(__file__).parent / "templates")
)


class CrawlStartRequest(BaseModel):
    url: str
    max_depth: int = Field(default=2, ge=0, le=10)
    max_pages: int = Field(default=100, ge=1, le=100000)

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        v = v.strip()
        if not v.startswith(("http://", "https://")):
            raise ValueError("URL must start with http:// or https://")
        return v


class BuildIndexRequest(BaseModel):
    vortex_url: str

    @field_validator("vortex_url")
    @classmethod
    def validate_vortex_url(cls, v: str) -> str:
        v = v.strip()
        if not v.startswith(("http://", "https://")):
            raise ValueError("Vortex URL must start with http:// or https://")
        return v


def _get_cm(request: Request) -> CrawlManager:
    """获取 CrawlManager，如果 lifespan 未运行则自动创建"""
    if not hasattr(request.app.state, "crawl_manager"):
        request.app.state.crawl_manager = CrawlManager()
    return request.app.state.crawl_manager


# ── 页面路由 ──


@router.get("/", response_class=HTMLResponse, tags=["pages"])
async def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "index.html")


@router.get("/detail", response_class=HTMLResponse, tags=["pages"])
async def detail(request: Request, url: str = "") -> HTMLResponse:
    cm: CrawlManager = _get_cm(request)
    if not url:
        raise HTTPException(400, "Missing url parameter")
    result = cm.get_result(url)
    if not result:
        raise HTTPException(404, "Page not found in crawl results")
    return templates.TemplateResponse(
        request, "detail.html", {"result": result}
    )


# ── REST API ──


@router.get("/api/status", tags=["crawl"])
async def get_status(request: Request) -> dict:
    cm: CrawlManager = _get_cm(request)
    return cm.get_status()


@router.post("/api/crawl/start", tags=["crawl"])
async def start_crawl(request: Request, body: CrawlStartRequest) -> dict:
    cm: CrawlManager = _get_cm(request)
    try:
        await cm.start_crawl(body.url, body.max_depth, body.max_pages)
        return {"ok": True}
    except RuntimeError as e:
        raise HTTPException(400, str(e)) from e


@router.post("/api/crawl/pause", tags=["crawl"])
async def pause_crawl(request: Request) -> dict:
    cm: CrawlManager = _get_cm(request)
    await cm.pause_crawl()
    return {"ok": True}


@router.post("/api/crawl/resume", tags=["crawl"])
async def resume_crawl(request: Request) -> dict:
    cm: CrawlManager = _get_cm(request)
    await cm.resume_crawl()
    return {"ok": True}


@router.post("/api/crawl/stop", tags=["crawl"])
async def stop_crawl(request: Request) -> dict:
    cm: CrawlManager = _get_cm(request)
    await cm.stop_crawl()
    return {"ok": True}


@router.get("/api/results", tags=["results"])
async def get_results(request: Request) -> list[dict]:
    cm: CrawlManager = _get_cm(request)
    return cm.get_results()


@router.post("/api/crawl/export", tags=["results"])
async def export_jsonl(request: Request) -> Response:
    cm: CrawlManager = _get_cm(request)
    if not cm.results:
        raise HTTPException(400, "No results to export")
    content = cm.export_jsonl()
    return Response(
        content=content,
        media_type="application/x-ndjson",
        headers={"Content-Disposition": "attachment; filename=search-index.jsonl"},
    )


@router.post("/api/crawl/build-index", tags=["results"])
async def build_index(request: Request, body: BuildIndexRequest) -> dict:
    cm: CrawlManager = _get_cm(request)
    if not cm.results:
        raise HTTPException(400, "No results to build index from")
    try:
        result = await cm.build_vortex_index(body.vortex_url)
        return result
    except httpx.ConnectError as e:
        raise HTTPException(502, f"Cannot connect to Vortex at {body.vortex_url}: {e}") from e
    except (ValueError, KeyError, AttributeError, httpx.HTTPError) as e:
        raise HTTPException(500, f"Build index failed: {e}") from e


# ── SSE ──


@router.get("/api/events", tags=["events"])
async def sse_events(request: Request) -> StreamingResponse:
    cm: CrawlManager = _get_cm(request)
    queue = cm.event_bus.subscribe()

    async def event_generator():
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    message = await asyncio.wait_for(queue.get(), timeout=30.0)
                    event = message["event"]
                    data = json.dumps(message["data"], ensure_ascii=False, default=str)
                    yield f"event: {event}\ndata: {data}\n\n"
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            cm.event_bus.unsubscribe(queue)

    return StreamingResponse(event_generator(), media_type="text/event-stream")
