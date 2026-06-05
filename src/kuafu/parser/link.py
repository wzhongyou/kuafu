"""链接提取与过滤"""

from __future__ import annotations

from abc import ABC, abstractmethod
from urllib.parse import urljoin

from parsel import Selector
from yarl import URL

from kuafu.models import Link


class LinkExtractor:
    """从 HTML 中提取链接

    支持的标签:
    - <a href>  — 主链接
    - <area href> — 图像映射
    - <iframe src> — 内嵌页面
    - <link href> — canonical, alternate 等
    - <meta http-equiv="refresh"> — 重定向
    """

    def __init__(self, *, follow_nofollow: bool = False) -> None:
        self._follow_nofollow = follow_nofollow

    def extract(self, selector: Selector, base_url: str) -> list[Link]:
        links: list[Link] = []
        seen: set[str] = set()

        # <a href>
        for tag in selector.css("a[href]"):
            link = self._parse_link_tag(tag, base_url)
            if link and link.url not in seen:
                seen.add(link.url)
                links.append(link)

        # <area href>
        for tag in selector.css("area[href]"):
            link = self._parse_area_tag(tag, base_url)
            if link and link.url not in seen:
                seen.add(link.url)
                links.append(link)

        # <iframe src>
        for tag in selector.css("iframe[src]"):
            link = self._parse_src_tag(tag, base_url, "iframe")
            if link and link.url not in seen:
                seen.add(link.url)
                links.append(link)

        # <meta http-equiv="refresh">
        for tag in selector.css('meta[http-equiv="refresh"]'):
            link = self._parse_meta_refresh(tag, base_url)
            if link and link.url not in seen:
                seen.add(link.url)
                links.append(link)

        return links

    def _parse_link_tag(self, tag: Selector, base_url: str) -> Link | None:
        href = tag.attrib.get("href", "").strip()
        if not href or href.startswith(("#", "javascript:", "mailto:", "tel:", "data:")):
            return None

        abs_url = self._resolve_url(href, base_url)
        if not abs_url:
            return None

        rel = tag.attrib.get("rel", "")
        no_follow = "nofollow" in rel.lower()
        if no_follow and not self._follow_nofollow:
            return None

        text = tag.xpath("string()").get("").strip()
        is_external = self._is_external(abs_url, base_url)

        return Link(url=abs_url, text=text, rel=rel, no_follow=no_follow, is_external=is_external)

    def _parse_area_tag(self, tag: Selector, base_url: str) -> Link | None:
        href = tag.attrib.get("href", "").strip()
        if not href or href.startswith(("#", "javascript:")):
            return None

        abs_url = self._resolve_url(href, base_url)
        if not abs_url:
            return None

        text = tag.attrib.get("alt", "")
        return Link(url=abs_url, text=text)

    def _parse_src_tag(self, tag: Selector, base_url: str, tag_name: str) -> Link | None:
        src = tag.attrib.get("src", "").strip()
        if not src:
            return None

        abs_url = self._resolve_url(src, base_url)
        if not abs_url:
            return None

        return Link(url=abs_url, text=tag_name)

    def _parse_meta_refresh(self, tag: Selector, base_url: str) -> Link | None:
        import re
        content = tag.attrib.get("content", "")
        m = re.search(r"url\s*=\s*(.+)", content, re.IGNORECASE)
        if not m:
            return None

        url_str = m.group(1).strip().strip("'\"")
        abs_url = self._resolve_url(url_str, base_url)
        if not abs_url:
            return None

        return Link(url=abs_url, text="meta-refresh")

    @staticmethod
    def _resolve_url(href: str, base_url: str) -> str | None:
        """将相对 URL 解析为绝对 URL"""
        try:
            abs_url = urljoin(base_url, href)
            parsed = URL(abs_url)
            if parsed.scheme in ("http", "https"):
                return str(parsed)
        except ValueError:
            pass
        return None

    @staticmethod
    def _is_external(url: str, base_url: str) -> bool:
        try:
            return URL(url).host != URL(base_url).host
        except ValueError:
            return False


class LinkFilter(ABC):
    """链接过滤器抽象接口"""

    @abstractmethod
    def should_follow(self, url: str) -> bool:
        """判断链接是否应该跟踪"""


class DomainFilter(LinkFilter):
    """限制域名范围"""

    def __init__(self, allowed_domains: list[str]) -> None:
        self._allowed = set(allowed_domains)

    def should_follow(self, url: str) -> bool:
        try:
            host = URL(url).host or ""
            return any(host == d or host.endswith("." + d) for d in self._allowed)
        except ValueError:
            return False


class DepthFilter(LinkFilter):
    """限制深度"""

    def __init__(self, max_depth: int) -> None:
        self._max_depth = max_depth

    def should_follow(self, url: str) -> bool:
        # 深度过滤由 Frontier 层管理，此处总是放行
        return True


class RegexFilter(LinkFilter):
    """正则匹配"""

    def __init__(self, pattern: str) -> None:
        import re
        self._pattern = re.compile(pattern)

    def should_follow(self, url: str) -> bool:
        return bool(self._pattern.search(url))


class FileTypeFilter(LinkFilter):
    """排除非 HTML 文件类型"""

    _BLOCKED_EXTENSIONS: frozenset[str] = frozenset({
        ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
        ".zip", ".tar", ".gz", ".rar", ".7z",
        ".jpg", ".jpeg", ".png", ".gif", ".svg", ".ico", ".webp",
        ".mp3", ".mp4", ".avi", ".mov", ".wmv", ".flv",
        ".css", ".js", ".woff", ".woff2", ".ttf", ".eot",
    })

    def should_follow(self, url: str) -> bool:
        try:
            path = URL(url).path.lower()
            return not any(path.endswith(ext) for ext in self._BLOCKED_EXTENSIONS)
        except ValueError:
            return True


class SchemeFilter(LinkFilter):
    """仅允许 http/https"""

    def should_follow(self, url: str) -> bool:
        try:
            return URL(url).scheme in ("http", "https")
        except ValueError:
            return False
