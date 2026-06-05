"""SearchDocumentTransformer 单元测试"""

from datetime import datetime

import pytest

from kuafu.models import CrawlResult, FetchRequest, FetchResult, Link, ParseResult, URLItem, URLStatus
from kuafu.search.transformer import (
    _build_anchor_map,
    _compute_content_hash,
    _compute_doc_id,
    _count_words,
    _extract_author,
    _extract_description,
    _extract_modified_time,
    _extract_published_time,
    _find_in_structured_data,
    transform,
)


def _make_crawl_result(**overrides) -> CrawlResult:
    """构造测试用 CrawlResult"""
    fetch = FetchResult(
        url="https://example.com/page",
        status_code=200,
        content_type="text/html",
        fetch_time=datetime(2024, 1, 15, 10, 30, 0),
        **overrides.get("fetch_overrides", {}),
    )
    parse_kwargs = dict(
        title="Test Page",
        text="This is a test page with some content.",
        meta={"description": "A test description"},
        canonical="https://example.com/page",
        language="en",
        links=[Link(url="https://example.com/other", text="Other page")],
        structured_data=[],
    )
    parse_kwargs.update(overrides.get("parse_overrides", {}))
    parse = ParseResult(**parse_kwargs)
    url_item = URLItem(
        raw="https://example.com/page",
        normalized="https://example.com/page",
        depth=2,
        status=URLStatus.COMPLETED,
    )
    request = FetchRequest(url="https://example.com/page")
    return CrawlResult(request=request, fetch=fetch, parse=parse, url_item=url_item)


class TestTransform:
    def test_basic_transform(self):
        result = _make_crawl_result()
        doc = transform(result)

        assert doc.url == "https://example.com/page"
        assert doc.title == "Test Page"
        assert doc.text == "This is a test page with some content."
        assert doc.lang == "en"
        assert doc.content_type == "text/html"
        assert doc.depth == 2
        assert doc.site == "example.com"
        assert doc.canonical == "https://example.com/page"

    def test_doc_id_is_md5_of_url(self):
        import hashlib
        result = _make_crawl_result()
        doc = transform(result)
        expected = hashlib.md5("https://example.com/page".encode()).hexdigest()
        assert doc.doc_id == expected

    def test_content_hash_is_md5_of_text(self):
        import hashlib
        result = _make_crawl_result()
        doc = transform(result)
        expected = hashlib.md5("This is a test page with some content.".encode()).hexdigest()
        assert doc.content_hash == expected

    def test_description_fallback_meta(self):
        result = _make_crawl_result()
        doc = transform(result)
        assert doc.description == "A test description"

    def test_description_fallback_og(self):
        result = _make_crawl_result(parse_overrides={
            "meta": {"og:description": "OG description"},
        })
        doc = transform(result)
        assert doc.description == "OG description"

    def test_description_fallback_text(self):
        result = _make_crawl_result(parse_overrides={
            "meta": {},
            "text": "A" * 300,
        })
        doc = transform(result)
        assert doc.description == "A" * 200

    def test_published_time_from_meta(self):
        result = _make_crawl_result(parse_overrides={
            "meta": {"article:published_time": "2024-01-15T10:00:00"},
        })
        doc = transform(result)
        assert doc.published_time == "2024-01-15T10:00:00"

    def test_published_time_from_jsonld(self):
        result = _make_crawl_result(parse_overrides={
            "structured_data": [{"datePublished": "2024-01-15"}],
        })
        doc = transform(result)
        assert doc.published_time == "2024-01-15"

    def test_modified_time_from_meta(self):
        result = _make_crawl_result(parse_overrides={
            "meta": {"article:modified_time": "2024-01-16T10:00:00"},
        })
        doc = transform(result)
        assert doc.modified_time == "2024-01-16T10:00:00"

    def test_modified_time_from_jsonld(self):
        result = _make_crawl_result(parse_overrides={
            "structured_data": [{"dateModified": "2024-01-16"}],
        })
        doc = transform(result)
        assert doc.modified_time == "2024-01-16"

    def test_author_from_meta(self):
        result = _make_crawl_result(parse_overrides={
            "meta": {"author": "John Doe"},
        })
        doc = transform(result)
        assert doc.author == "John Doe"

    def test_author_from_jsonld_string(self):
        result = _make_crawl_result(parse_overrides={
            "structured_data": [{"author": "Jane Doe"}],
        })
        doc = transform(result)
        assert doc.author == "Jane Doe"

    def test_author_from_jsonld_person(self):
        result = _make_crawl_result(parse_overrides={
            "structured_data": [{"author": {"@type": "Person", "name": "Jane Doe"}}],
        })
        doc = transform(result)
        assert doc.author == "Jane Doe"

    def test_anchor_map(self):
        result = _make_crawl_result(parse_overrides={
            "links": [
                Link(url="https://example.com/a", text="Link A"),
                Link(url="https://example.com/b", text="Link B"),
                Link(url="https://example.com/c", text=""),
            ],
        })
        doc = transform(result)
        assert doc.anchor_map == {
            "https://example.com/a": "Link A",
            "https://example.com/b": "Link B",
        }

    def test_fetch_time(self):
        result = _make_crawl_result()
        doc = transform(result)
        assert doc.fetch_time == datetime(2024, 1, 15, 10, 30, 0)

    def test_structured_data_preserved(self):
        sd = [{"@type": "Article", "headline": "Test"}]
        result = _make_crawl_result(parse_overrides={"structured_data": sd})
        doc = transform(result)
        assert doc.structured_data == sd


class TestWordCount:
    def test_empty_text(self):
        assert _count_words("") == 0

    def test_english_text(self):
        assert _count_words("hello world foo") == 3

    def test_chinese_text(self):
        assert _count_words("你好世界") == 4

    def test_mixed_text(self):
        count = _count_words("Hello 你好 world 世界")
        assert count >= 4  # 至少 4 个 CJK + 西文


class TestFindInStructuredData:
    def test_simple_key(self):
        assert _find_in_structured_data({"datePublished": "2024-01-01"}, "datePublished") == "2024-01-01"

    def test_nested_key(self):
        data = {"@type": "Article", "author": {"name": "John"}}
        assert _find_in_structured_data(data, "name") == "John"

    def test_person_object(self):
        data = {"author": {"@type": "Person", "name": "John"}}
        result = _find_in_structured_data(data, "author")
        assert result == "John"

    def test_not_found(self):
        assert _find_in_structured_data({"foo": "bar"}, "baz") is None

    def test_list_input(self):
        data = [{"datePublished": "2024-01-01"}, {"dateModified": "2024-01-02"}]
        assert _find_in_structured_data(data, "datePublished") == "2024-01-01"


class TestBuildAnchorMap:
    def test_basic(self):
        links = [
            Link(url="https://a.com", text="A"),
            Link(url="https://b.com", text="B"),
        ]
        assert _build_anchor_map(links) == {"https://a.com": "A", "https://b.com": "B"}

    def test_skip_empty_text(self):
        links = [Link(url="https://a.com", text="")]
        assert _build_anchor_map(links) == {}

    def test_skip_empty_url(self):
        links = [Link(url="", text="A")]
        assert _build_anchor_map(links) == {}
