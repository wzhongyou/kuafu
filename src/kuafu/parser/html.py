"""HTML 解析器 — 基于 lxml + parsel"""

from __future__ import annotations

import json

from parsel import Selector
from yarl import URL

from kuafu.fetcher.encoding import detect_encoding
from kuafu.models import ParseResult
from kuafu.parser.base import Parser
from kuafu.parser.link import LinkExtractor


class HTMLParser(Parser):
    """基于 parsel (lxml) 的 HTML 解析器

    特性:
    - CSS + XPath 选择器
    - 链接提取（<a>, <area>, <iframe>, <link>）
    - Meta 信息提取
    - JSON-LD 结构化数据提取
    - 自动编码检测
    """

    def __init__(
        self,
        *,
        extract_links: bool = True,
        follow_nofollow: bool = False,
    ) -> None:
        self._extract_links = extract_links
        self._follow_nofollow = follow_nofollow
        self._link_extractor = LinkExtractor(follow_nofollow=follow_nofollow)

    async def parse(self, url: str, body: bytes) -> ParseResult:
        _, text = detect_encoding(body)
        selector = Selector(text=text)

        title = self._extract_title(selector)
        meta = self._extract_meta(selector)
        canonical = self._extract_canonical(selector, url)
        language = self._extract_language(selector)
        links = self._link_extractor.extract(selector, url) if self._extract_links else []
        # 在 _extract_text 之前提取，因为后者会移除 script 标签
        structured_data = self._extract_json_ld(selector)
        text_content = self._extract_text(selector)

        return ParseResult(
            title=title,
            text=text_content,
            links=links,
            meta=meta,
            canonical=canonical,
            language=language,
            structured_data=structured_data,
        )

    def _extract_title(self, sel: Selector) -> str:
        return sel.css("title::text").get("").strip()

    def _extract_meta(self, sel: Selector) -> dict[str, str]:
        meta: dict[str, str] = {}
        for tag in sel.css("meta[name][content]"):
            name = tag.attrib.get("name", "").lower()
            content = tag.attrib.get("content", "")
            if name and content:
                meta[name] = content

        # description 和 keywords 单独处理（有些用 property 而非 name）
        for tag in sel.css('meta[property^="og:"][content]'):
            prop = tag.attrib.get("property", "")
            content = tag.attrib.get("content", "")
            if prop and content:
                meta[prop] = content

        return meta

    def _extract_canonical(self, sel: Selector, base_url: str) -> str:
        canonical = sel.css('link[rel="canonical"]::attr(href)').get("")
        if canonical and not canonical.startswith(("http://", "https://")):
            try:
                base = URL(base_url)
                canonical = str(URL(canonical).with_scheme(base.scheme).with_host(base.host))
            except ValueError:
                pass
        return canonical

    def _extract_language(self, sel: Selector) -> str:
        lang = sel.css("html").attrib.get("lang", "")
        return lang.strip()

    def _extract_text(self, sel: Selector) -> str:
        body = sel.css("body")
        if not body:
            return ""
        # 移除 script 和 style 标签内容
        for tag in body.css("script, style"):
            tag.root.getparent().remove(tag.root)
        return body.xpath("string()").get("").strip()

    def _extract_json_ld(self, sel: Selector) -> list[dict]:
        data: list[dict] = []
        for script_tag in sel.css('script[type="application/ld+json"]'):
            text = script_tag.root.text
            if not text:
                continue
            try:
                parsed = json.loads(text)
                if isinstance(parsed, list):
                    data.extend(parsed)
                else:
                    data.append(parsed)
            except (json.JSONDecodeError, TypeError):
                pass
        return data
