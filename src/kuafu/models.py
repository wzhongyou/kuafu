"""核心数据模型 — 所有模块共享的数据结构定义"""

from __future__ import annotations

from datetime import datetime
from enum import IntEnum

from pydantic import BaseModel, Field


# ── URL 状态 ──────────────────────────────────────────────

class URLStatus(IntEnum):
    DISCOVERED = 0
    PENDING = 1
    FETCHING = 2
    FETCHED = 3
    PARSED = 4
    COMPLETED = 5
    FAILED = 6
    SKIPPED = 7
    ABANDONED = 8


# ── URL 数据 ──────────────────────────────────────────────

class URLItem(BaseModel):
    """URL 条目，贯穿 Frontier → Scheduler → Worker 全链路"""
    raw: str                            # 原始 URL
    normalized: str                     # 规范化后 URL
    parent: str | None = None           # 父页面 URL
    depth: int = 0                      # 从种子起的深度
    priority: int = 0                   # 调度优先级（0=最高）
    status: URLStatus = URLStatus.DISCOVERED
    retries: int = 0                    # 已重试次数
    last_fetch: datetime | None = None
    next_fetch: datetime | None = None
    meta: dict[str, str] = Field(default_factory=dict)


# ── 抓取请求 / 响应 ──────────────────────────────────────

class FetchRequest(BaseModel):
    """Worker 发出的抓取请求"""
    url: str
    method: str = "GET"
    headers: dict[str, str] = Field(default_factory=dict)
    cookies: dict[str, str] = Field(default_factory=dict)
    proxy: str | None = None
    timeout: float = 30.0
    need_render: bool = False
    max_depth: int = -1                 # -1 不限


class FetchResult(BaseModel):
    """抓取结果"""
    url: str                            # 最终 URL（可能重定向后）
    status_code: int = 0
    headers: dict[str, str] = Field(default_factory=dict)
    body: bytes = b""
    content_type: str = ""
    encoding: str = ""
    fetch_time: datetime | None = None
    duration: float = 0.0               # 耗时（秒）
    redirect_chain: list[str] = Field(default_factory=list)
    from_cache: bool = False
    error: str | None = None

    @property
    def host(self) -> str:
        from yarl import URL
        try:
            return URL(self.url).host or ""
        except ValueError:
            return ""

    @property
    def is_success(self) -> bool:
        return self.error is None and 200 <= self.status_code < 300

    @property
    def content_changed(self) -> bool:
        """内容是否变更（基于状态码和 ETag/Last-Modified 判断）"""
        if self.status_code == 304:
            return False
        if self.status_code >= 400:
            return False
        return True


# ── 解析结果 ──────────────────────────────────────────────

class Link(BaseModel):
    """页面中提取的链接"""
    url: str
    text: str = ""
    rel: str = ""
    no_follow: bool = False
    is_external: bool = False


class ParseResult(BaseModel):
    """页面解析结果"""
    title: str = ""
    text: str = ""
    links: list[Link] = Field(default_factory=list)
    meta: dict[str, str] = Field(default_factory=dict)
    canonical: str = ""
    language: str = ""
    structured_data: list[dict] = Field(default_factory=list)


# ── 渲染请求 / 结果 ──────────────────────────────────────

class RenderRequest(BaseModel):
    """JS 渲染请求"""
    url: str
    wait_timeout: float = 10.0
    wait_selector: str = ""
    screenshot: bool = False


class RenderResult(BaseModel):
    """JS 渲染结果"""
    url: str
    body: bytes = b""
    error: str | None = None


# ── 爬取结果（最终输出） ──────────────────────────────────

class CrawlResult(BaseModel):
    """一次完整爬取的最终结果"""
    request: FetchRequest
    fetch: FetchResult
    parse: ParseResult
    url_item: URLItem | None = None
