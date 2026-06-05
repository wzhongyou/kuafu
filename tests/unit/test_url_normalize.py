"""URL 规范化测试"""

import pytest

from kuafu.frontier.url import normalize_url, is_same_host


class TestNormalizeURL:
    def test_scheme_and_host_lowercase(self):
        assert normalize_url("HTTP://Example.COM/path") == "http://example.com/path"

    def test_default_port_removed(self):
        assert normalize_url("http://example.com:80/path") == "http://example.com/path"

    def test_non_default_port_kept(self):
        result = normalize_url("http://example.com:8080/path")
        assert ":8080" in result

    def test_path_normalization_dot(self):
        assert normalize_url("http://example.com/a/./b") == "http://example.com/a/b"

    def test_path_normalization_dotdot(self):
        assert normalize_url("http://example.com/a/b/../c") == "http://example.com/a/c"

    def test_fragment_removed(self):
        result = normalize_url("http://example.com/path#section")
        assert "#" not in result

    def test_tracking_params_removed(self):
        result = normalize_url("http://example.com/page?utm_source=x&id=1")
        assert "utm_source" not in result
        assert "id=1" in result

    def test_query_params_sorted(self):
        result = normalize_url("http://example.com/page?b=2&a=1")
        assert result.index("a=1") < result.index("b=2")

    def test_trailing_slash_stripped(self):
        assert normalize_url("http://example.com/path/") == "http://example.com/path"

    def test_root_path_kept(self):
        assert normalize_url("http://example.com/") == "http://example.com"

    def test_empty_string(self):
        assert normalize_url("") == ""

    def test_protocol_relative(self):
        result = normalize_url("//example.com/path")
        assert result.startswith("http://example.com/path")

    def test_multiple_tracking_params(self):
        result = normalize_url("http://example.com/page?utm_source=x&fbclid=abc&id=1")
        assert "utm_source" not in result
        assert "fbclid" not in result
        assert "id=1" in result


class TestIsSameHost:
    def test_same_host(self):
        assert is_same_host("http://example.com/a", "http://example.com/b")

    def test_different_host(self):
        assert not is_same_host("http://a.com/x", "http://b.com/y")

    def test_same_host_different_scheme(self):
        assert is_same_host("http://example.com/a", "https://example.com/b")
