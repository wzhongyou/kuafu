"""搜索文档模型 — 面向搜索引擎建库的结构化 schema"""

from kuafu.search.models import SearchDocument
from kuafu.search.transformer import transform
from kuafu.search.pipeline import SearchIndexPipeline

__all__ = ["SearchDocument", "transform", "SearchIndexPipeline"]
