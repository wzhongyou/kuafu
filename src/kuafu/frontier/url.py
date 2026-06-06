"""URL 规范化 — 去重的第一道防线"""

from __future__ import annotations

import re

from yarl import URL

# 已知追踪参数（UTM / 广告 / 社交 / 分析）
_TRACKING_PARAMS: frozenset[str] = frozenset({
    # UTM
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "utm_id", "utm_cid", "utm_reader", "utm_name", "utm_pubreferrer",
    "utm_swu", "utm_viz_id", "utm_brand", "utm_hp_ref",
    # 广告
    "gclid", "gclsrc", "dclid", "fbclid", "msclkid", "mc_eid",
    # 社交
    "ref", "ref_src", "ref_url", "share", "s", "si",
    # 分析
    "_ga", "_gl", "_gid", "_gac", "yclid", "ymclid",
    # 其他
    "igshid",
})


def normalize_url(
    raw: str,
    *,
    strip_trailing_slash: bool = True,
    strip_tracking_params: bool = True,
    sort_query: bool = True,
) -> str:
    """URL 规范化

    执行顺序:
    1. 协议+域名小写化
    2. 端口默认值去除
    3. 路径规范化（移除 /./  /../  连续 /）
    4. 片段去除
    5. 追踪参数去除
    6. 查询参数排序
    7. 尾斜线统一
    8. 编码统一
    """
    if not raw or not raw.strip():
        return ""

    raw = raw.strip()

    # 补全协议
    if raw.startswith("//"):
        raw = "http:" + raw

    try:
        url = URL(raw)
    except ValueError:
        return raw

    # 1. 协议+域名小写化
    scheme = url.scheme.lower() if url.scheme else "http"
    host = (url.host or "").lower()

    if not host:
        return raw

    # 2. 端口默认值去除
    port = url.explicit_port  # None if default for scheme

    # 3. 路径规范化
    path = _normalize_path(url.path)

    # 4. 片段去除（yarl 默认不保留 fragment）

    # 5-6. 查询参数处理
    query = url.query
    if strip_tracking_params or sort_query:
        query = _normalize_query(query, strip_tracking=strip_tracking_params, sort=sort_query)

    # 7. 尾斜线处理（根路径 "/" 特殊处理）
    if strip_trailing_slash and path != "/" and path.endswith("/"):
        path = path.rstrip("/")
    if path == "/" and strip_trailing_slash:
        path = ""  # 根路径去掉尾斜线

    # 重建 URL
    try:
        normalized = URL.build(
            scheme=scheme,
            host=host,
            port=port,
            path=path,
            query=query or None,
        )
    except ValueError:
        return raw

    result = str(normalized)

    # 8. 编码统一：百分号编码大写化
    result = _normalize_percent_encoding(result)

    return result


def _normalize_path(path: str) -> str:
    """路径规范化：移除 /./  /../  连续 /"""
    if not path:
        return "/"

    # 移除连续 /
    segments: list[str] = []
    for seg in path.split("/"):
        if seg == ".":
            continue
        if seg == "..":
            if segments and segments[-1] != "":
                segments.pop()
            continue
        if seg == "" and segments:
            continue
        segments.append(seg)

    if not segments or (len(segments) == 1 and segments[0] == ""):
        return "/"

    result = "/".join(segments)
    if not result.startswith("/"):
        result = "/" + result
    return result


def _normalize_query(
    query: dict | str,
    *,
    strip_tracking: bool = True,
    sort: bool = True,
) -> list[tuple[str, str]]:
    """查询参数规范化：去追踪参数 + 排序"""
    if isinstance(query, str):
        # yarl 有时返回 raw query string
        from urllib.parse import parse_qsl
        items = parse_qsl(query, keep_blank_values=True)
    elif hasattr(query, "items"):
        items = list(query.items())
    else:
        items = list(query) if query else []

    if strip_tracking:
        items = [(k, v) for k, v in items if k not in _TRACKING_PARAMS]

    if sort:
        items.sort()

    return items


def _normalize_percent_encoding(url: str) -> str:
    """百分号编码统一：已编码的大写化，未编码的不动"""
    def _replace(m: re.Match) -> str:
        hex_str = m.group(1)
        try:
            char = chr(int(hex_str, 16))
            # 这些字符保持编码状态
            if char in " /?#[]@!$&'()*+,;=":
                return f"%{hex_str.upper()}"
            # 安全字符则解码
            return char
        except ValueError:
            return m.group(0)

    return re.sub(r"%([0-9a-fA-F]{2})", _replace, url)


def is_same_host(url_a: str, url_b: str) -> bool:
    """判断两个 URL 是否同域"""
    try:
        return URL(url_a).host == URL(url_b).host
    except ValueError:
        return False
