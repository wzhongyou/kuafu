"""HTML Parser 测试"""

import pytest

from kuafu.parser.html import HTMLParser
from kuafu.parser.link import DomainFilter, FileTypeFilter, RegexFilter, SchemeFilter


class TestHTMLParser:
    @pytest.fixture
    def parser(self):
        return HTMLParser(extract_links=True)

    @pytest.mark.asyncio
    async def test_extract_title(self, parser):
        html = b"<html><head><title>Test Page</title></head><body>Hello</body></html>"
        result = await parser.parse("http://example.com", html)
        assert result.title == "Test Page"

    @pytest.mark.asyncio
    async def test_extract_text(self, parser):
        html = b"<html><body><p>Hello World</p></body></html>"
        result = await parser.parse("http://example.com", html)
        assert "Hello World" in result.text

    @pytest.mark.asyncio
    async def test_extract_links(self, parser):
        html = b"""
        <html><body>
            <a href="/page1">Page 1</a>
            <a href="https://example.com/page2">Page 2</a>
        </body></html>
        """
        result = await parser.parse("http://example.com", html)
        urls = [link.url for link in result.links]
        assert any("/page1" in u for u in urls)
        assert any("page2" in u for u in urls)

    @pytest.mark.asyncio
    async def test_skip_javascript_links(self, parser):
        html = b'<html><body><a href="javascript:void(0)">Click</a></body></html>'
        result = await parser.parse("http://example.com", html)
        assert len(result.links) == 0

    @pytest.mark.asyncio
    async def test_skip_mailto_links(self, parser):
        html = b'<html><body><a href="mailto:test@example.com">Email</a></body></html>'
        result = await parser.parse("http://example.com", html)
        assert len(result.links) == 0

    @pytest.mark.asyncio
    async def test_extract_meta(self, parser):
        html = b"""
        <html><head>
            <meta name="description" content="Test description">
            <meta name="keywords" content="test, kuafu">
        </head><body></body></html>
        """
        result = await parser.parse("http://example.com", html)
        assert result.meta.get("description") == "Test description"
        assert result.meta.get("keywords") == "test, kuafu"

    @pytest.mark.asyncio
    async def test_extract_canonical(self, parser):
        html = b"""
        <html><head>
            <link rel="canonical" href="https://example.com/canonical-page">
        </head><body></body></html>
        """
        result = await parser.parse("http://example.com", html)
        assert "canonical-page" in result.canonical

    @pytest.mark.asyncio
    async def test_extract_language(self, parser):
        html = b'<html lang="zh-CN"><head></head><body></body></html>'
        result = await parser.parse("http://example.com", html)
        assert result.language == "zh-CN"

    @pytest.mark.asyncio
    async def test_extract_json_ld(self, parser):
        html = b"""
        <html><body>
            <script type="application/ld+json">{"@type": "Article", "name": "Test"}</script>
        </body></html>
        """
        result = await parser.parse("http://example.com", html)
        assert len(result.structured_data) == 1
        assert result.structured_data[0]["@type"] == "Article"

    @pytest.mark.asyncio
    async def test_script_style_removed_from_text(self, parser):
        html = b"""
        <html><body>
            <script>var x = 1;</script>
            <style>.cls { color: red; }</style>
            <p>Visible text</p>
        </body></html>
        """
        result = await parser.parse("http://example.com", html)
        assert "var x" not in result.text
        assert "color" not in result.text
        assert "Visible text" in result.text

    @pytest.mark.asyncio
    async def test_nofollow_links_skipped(self):
        parser = HTMLParser(extract_links=True, follow_nofollow=False)
        html = b'<html><body><a href="/page" rel="nofollow">NoFollow</a></body></html>'
        result = await parser.parse("http://example.com", html)
        assert len(result.links) == 0

    @pytest.mark.asyncio
    async def test_extract_links_disabled(self):
        parser = HTMLParser(extract_links=False)
        html = b'<html><body><a href="/page">Link</a></body></html>'
        result = await parser.parse("http://example.com", html)
        assert len(result.links) == 0


class TestLinkFilters:
    def test_domain_filter_allows_matching(self):
        f = DomainFilter(["example.com"])
        assert f.should_follow("http://example.com/page") is True

    def test_domain_filter_blocks_non_matching(self):
        f = DomainFilter(["example.com"])
        assert f.should_follow("http://other.com/page") is False

    def test_domain_filter_allows_subdomain(self):
        f = DomainFilter(["example.com"])
        assert f.should_follow("http://sub.example.com/page") is True

    def test_file_type_filter_blocks_pdf(self):
        f = FileTypeFilter()
        assert f.should_follow("http://example.com/doc.pdf") is False

    def test_file_type_filter_allows_html(self):
        f = FileTypeFilter()
        assert f.should_follow("http://example.com/page.html") is True

    def test_file_type_filter_allows_no_extension(self):
        f = FileTypeFilter()
        assert f.should_follow("http://example.com/page") is True

    def test_scheme_filter_allows_http(self):
        f = SchemeFilter()
        assert f.should_follow("http://example.com") is True

    def test_scheme_filter_blocks_ftp(self):
        f = SchemeFilter()
        assert f.should_follow("ftp://example.com") is False

    def test_regex_filter(self):
        f = RegexFilter(r"/article/\d+")
        assert f.should_follow("http://example.com/article/123") is True
        assert f.should_follow("http://example.com/about") is False
