"""编码检测与转换"""

from __future__ import annotations

import re

import charset_normalizer


# 匹配 <meta charset="...">
_META_CHARSET_RE = re.compile(
    rb'<\s*meta[^>]+charset\s*=\s*["\']?\s*([^"\';\s>]+)', re.IGNORECASE
)

# 匹配 <meta http-equiv="Content-Type" content="...; charset=...">
_META_CONTENT_TYPE_RE = re.compile(
    rb'<\s*meta[^>]+http-equiv\s*=\s*["\']?Content-Type["\']?[^>]+'
    rb'content\s*=\s*["\']?[^"\']*charset=([^"\';\s>]+)',
    re.IGNORECASE,
)


def detect_encoding(body: bytes, content_type: str = "") -> tuple[str, str]:
    """检测编码并解码为文本

    检测优先级:
    1. Content-Type 头中的 charset
    2. HTML <meta charset="...">
    3. HTML <meta http-equiv="Content-Type" ...>
    4. charset-normalizer 自动检测
    5. 默认 UTF-8

    Returns:
        (encoding, decoded_text)
    """
    # 1. 从 Content-Type 头提取
    if "charset=" in content_type.lower():
        charset = content_type.lower().split("charset=")[-1].split(";")[0].strip().strip('"\'')
        if charset:
            decoded = _try_decode(body, charset)
            if decoded is not None:
                return charset, decoded

    # 2-3. 从 HTML meta 标签提取
    meta_charset = _extract_meta_charset(body)
    if meta_charset:
        decoded = _try_decode(body, meta_charset)
        if decoded is not None:
            return meta_charset, decoded

    # 4. 自动检测
    result = charset_normalizer.detect(body)
    if result and result.get("encoding"):
        encoding = result["encoding"]
        decoded = _try_decode(body, encoding)
        if decoded is not None:
            return encoding, decoded

    # 5. 默认 UTF-8
    return "utf-8", body.decode("utf-8", errors="replace")


def _extract_meta_charset(body: bytes) -> str | None:
    """从 HTML meta 标签中提取 charset"""
    # <meta charset="...">
    m = _META_CHARSET_RE.search(body)
    if m:
        return m.group(1).decode("ascii", errors="ignore").strip()

    # <meta http-equiv="Content-Type" content="...; charset=...">
    m = _META_CONTENT_TYPE_RE.search(body)
    if m:
        return m.group(1).decode("ascii", errors="ignore").strip()

    return None


def _try_decode(body: bytes, encoding: str) -> str | None:
    """尝试用指定编码解码，失败返回 None"""
    try:
        return body.decode(encoding)
    except (UnicodeDecodeError, LookupError):
        return None
