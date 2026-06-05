"""编码检测测试"""

import pytest

from kuafu.fetcher.encoding import detect_encoding


class TestDetectEncoding:
    def test_utf8_default(self):
        text = "你好世界"
        body = text.encode("utf-8")
        encoding, decoded = detect_encoding(body)
        assert encoding == "utf-8"
        assert decoded == text

    def test_content_type_charset(self):
        text = "你好世界"
        body = text.encode("gbk")
        encoding, decoded = detect_encoding(body, "text/html; charset=gbk")
        assert encoding.lower() in ("gbk", "gb2312")
        assert decoded == text

    def test_meta_charset(self):
        html = '<html><head><meta charset="gbk"></head><body>你好</body></html>'
        body = html.encode("gbk")
        encoding, decoded = detect_encoding(body)
        # 应该能从 meta 标签中检测到
        assert "你好" in decoded or "gbk" in encoding.lower()

    def test_auto_detect_fallback(self):
        # charset-normalizer 对短 GBK 文本可能误判，用较长文本
        text = "这是一个中文编码检测的测试文本，包含足够多的字符以便自动检测算法能够正确识别编码类型。"
        body = text.encode("gbk")
        encoding, decoded = detect_encoding(body)
        # 只要能正确解码就行，不强制要求编码名精确
        assert "中文" in decoded or encoding.lower() in ("gbk", "gb2312", "gb18030")

    def test_empty_body(self):
        encoding, decoded = detect_encoding(b"")
        assert encoding == "utf-8"
        assert decoded == ""

    def test_ascii_content(self):
        body = b"Hello World"
        encoding, decoded = detect_encoding(body)
        assert decoded == "Hello World"
