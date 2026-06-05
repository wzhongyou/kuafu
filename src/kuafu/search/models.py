"""SearchDocument — 面向搜索引擎建库的结构化文档模型"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class SearchDocument(BaseModel):
    """搜索引擎索引文档

    由 CrawlResult 经 SearchDocumentTransformer 转换而来，
    可直接序列化为 JSONL 导入 Elasticsearch / MongoDB 等索引系统。
    """

    doc_id: str                           # MD5(canonical_url)
    url: str                              # 规范化 URL
    title: str = ""
    description: str = ""                 # meta.description → og:description → text[:200]
    text: str = ""                        # 完整正文，不截断
    lang: str = ""
    content_type: str = ""
    content_hash: str = ""                # MD5(text)，内容去重指纹
    published_time: str | None = None     # og:article:published_time / JSON-LD datePublished
    modified_time: str | None = None      # og:article:modified_time / JSON-LD dateModified
    author: str | None = None             # meta.author / JSON-LD author
    canonical: str = ""
    anchor_map: dict[str, str] = Field(default_factory=dict)  # {link.url: link.text}
    structured_data: list[dict] = Field(default_factory=list)  # JSON-LD 原始数据
    word_count: int = 0
    fetch_time: datetime | None = None
    depth: int = 0
    site: str = ""                        # fetch.host
    category: str = ""                    # 分类标签 (article:section / og:type)
