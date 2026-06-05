"""FastAPI 应用工厂"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from kuafu.web.crawl_manager import CrawlManager
from kuafu.web.routes import router


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.crawl_manager = CrawlManager()
    yield
    cm: CrawlManager = app.state.crawl_manager
    if cm.state in ("running", "paused"):
        await cm.stop_crawl()


def create_app() -> FastAPI:
    app = FastAPI(title="kuafu Dashboard", lifespan=lifespan)

    # 静态文件
    static_dir = Path(__file__).parent / "static"
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    # 路由
    app.include_router(router)

    return app


def main() -> None:
    import uvicorn
    uvicorn.run(create_app(), host="127.0.0.1", port=8080)
