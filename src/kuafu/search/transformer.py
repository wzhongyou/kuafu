"""SearchDocumentTransformer — CrawlResult → SearchDocument 纯函数转换"""

from __future__ import annotations

import hashlib
import re
from typing import Any

from kuafu.models import CrawlResult, Link
from kuafu.search.models import SearchDocument


def transform(result: CrawlResult) -> SearchDocument:
    """将 CrawlResult 转换为 SearchDocument"""
    url = _pick_url(result)
    doc_id = _compute_doc_id(url)
    text = result.parse.text
    content_hash = _compute_content_hash(text)
    word_count = _count_words(text)
    description = _extract_description(result)
    published_time = _extract_published_time(result)
    modified_time = _extract_modified_time(result)
    author = _extract_author(result)
    anchor_map = _build_anchor_map(result.parse.links)
    category = _extract_category(result)
    site = result.fetch.host
    canonical = result.parse.canonical or url

    return SearchDocument(
        doc_id=doc_id,
        url=url,
        title=result.parse.title,
        description=description,
        text=text,
        lang=result.parse.language,
        content_type=result.fetch.content_type,
        content_hash=content_hash,
        published_time=published_time,
        modified_time=modified_time,
        author=author,
        canonical=canonical,
        anchor_map=anchor_map,
        structured_data=result.parse.structured_data,
        word_count=word_count,
        fetch_time=result.fetch.fetch_time,
        depth=result.url_item.depth if result.url_item else 0,
        site=site,
        category=category,
    )


def _pick_url(result: CrawlResult) -> str:
    """优先使用 canonical，其次 fetch 最终 URL"""
    if result.parse.canonical:
        return result.parse.canonical
    return result.fetch.url


def _compute_doc_id(url: str) -> str:
    return hashlib.md5(url.encode()).hexdigest()


def _compute_content_hash(text: str) -> str:
    return hashlib.md5(text.encode()).hexdigest()


def _count_words(text: str) -> int:
    """简易分词计数：CJK 字符逐字 + 西文按空格分词"""
    if not text:
        return 0
    cjk = len(re.findall(r"[一-鿿぀-ゟ゠-ヿ가-힯]", text))
    stripped = re.sub(r"[一-鿿぀-ゟ゠-ヿ가-힯]", " ", text)
    western = len(stripped.split())
    return cjk + western


def _extract_description(result: CrawlResult) -> str:
    """3 级 fallback：meta.description → og:description → text[:200]"""
    meta = result.parse.meta
    if meta.get("description"):
        return meta["description"]
    if meta.get("og:description"):
        return meta["og:description"]
    text = result.parse.text
    if text:
        return text[:200]
    return ""


def _extract_published_time(result: CrawlResult) -> str | None:
    """从 meta + JSON-LD 提取发布时间"""
    meta = result.parse.meta
    if meta.get("article:published_time"):
        return meta["article:published_time"]
    if meta.get("og:article:published_time"):
        return meta["og:article:published_time"]

    for sd in result.parse.structured_data:
        val = _find_in_structured_data(sd, "datePublished")
        if val:
            return val
    return None


def _extract_modified_time(result: CrawlResult) -> str | None:
    """从 meta + JSON-LD 提取修改时间"""
    meta = result.parse.meta
    if meta.get("article:modified_time"):
        return meta["article:modified_time"]
    if meta.get("og:article:modified_time"):
        return meta["og:article:modified_time"]

    for sd in result.parse.structured_data:
        val = _find_in_structured_data(sd, "dateModified")
        if val:
            return val
    return None


def _extract_author(result: CrawlResult) -> str | None:
    """从 meta + JSON-LD 提取作者"""
    meta = result.parse.meta
    if meta.get("author"):
        return meta["author"]

    for sd in result.parse.structured_data:
        val = _find_in_structured_data(sd, "author")
        if val:
            return val
    return None


def _find_in_structured_data(data: Any, key: str) -> str | None:
    """在 JSON-LD 结构中递归查找 key 的值"""
    if isinstance(data, dict):
        if key in data:
            val = data[key]
            if isinstance(val, str):
                return val
            if isinstance(val, dict) and "name" in val:
                return val["name"]
        for v in data.values():
            result = _find_in_structured_data(v, key)
            if result:
                return result
    elif isinstance(data, list):
        for item in data:
            result = _find_in_structured_data(item, key)
            if result:
                return result
    return None


def _extract_category(result: CrawlResult) -> str:
    """从 meta 提取分类"""
    meta = result.parse.meta
    if meta.get("article:section"):
        return meta["article:section"]
    if meta.get("og:type"):
        return meta["og:type"]
    return ""


def _build_anchor_map(links: list[Link]) -> dict[str, str]:
    """构建出链锚文本映射 {url: anchor_text}"""
    anchor_map: dict[str, str] = {}
    for link in links:
        if link.url and link.text:
            anchor_map[link.url] = link.text.strip()
    return anchor_map
