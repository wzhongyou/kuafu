"""配置系统 — pydantic 模型 + YAML 加载"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field


class RetryConfig(BaseModel):
    max_retries: int = 3
    backoff: str = "exponential"  # exponential / constant
    retry_on_status: list[int] = [408, 429, 500, 502, 503, 504]


class FetcherConfig(BaseModel):
    user_agent: str = "kuafu/1.0"
    timeout: float = 30.0
    max_redirects: int = 10
    http2: bool = True
    verify_ssl: bool = True
    max_connections: int = 100
    max_connections_per_host: int = 10
    retry: RetryConfig = Field(default_factory=RetryConfig)


class PolitenessConfig(BaseModel):
    default_delay: float = 1.0
    max_concurrent_per_host: int = 2
    circuit_threshold: int = 5
    circuit_cooldown: float = 60.0
    respect_crawl_delay: bool = True
    robots_cache_ttl: float = 86400.0


class SchedulerConfig(BaseModel):
    type: str = "bfs"  # bfs / adaptive
    batch_size: int = 100


class ParserConfig(BaseModel):
    extract_links: bool = True
    follow_nofollow: bool = False


class RenderConfig(BaseModel):
    enabled: bool = False
    max_instances: int = 5
    wait_timeout: float = 10.0


class BloomFilterConfig(BaseModel):
    expected_items: int = 10_000_000
    false_positive_rate: float = 0.01


class DedupURLConfig(BaseModel):
    type: str = "bloom"  # map / bloom / redis
    bloom: BloomFilterConfig = Field(default_factory=BloomFilterConfig)


class DedupConfig(BaseModel):
    url: DedupURLConfig = Field(default_factory=DedupURLConfig)


class StorageConfig(BaseModel):
    url_store_type: str = "memory"  # memory / sqlite / redis
    url_store_path: str = "./data/frontier.db"


class QueueConfig(BaseModel):
    type: str = "asyncio"  # asyncio / redis / kafka


class WorkerConfig(BaseModel):
    concurrency: int = 10


class LogConfig(BaseModel):
    level: str = "info"
    format: str = "json"  # json / console


class MetricsConfig(BaseModel):
    enabled: bool = False
    addr: str = "0.0.0.0:9090"


class PipelineItemConfig(BaseModel):
    type: str = "console"  # console / file
    format: str = "jsonl"  # jsonl / csv
    path: str = "./output/"


class CrawlerConfig(BaseModel):
    """爬虫完整配置"""

    name: str = "kuafu-crawl"
    seeds: list[str] = []
    max_depth: int = -1
    max_pages: int = -1

    scheduler: SchedulerConfig = Field(default_factory=SchedulerConfig)
    fetcher: FetcherConfig = Field(default_factory=FetcherConfig)
    politeness: PolitenessConfig = Field(default_factory=PolitenessConfig)
    parser: ParserConfig = Field(default_factory=ParserConfig)
    render: RenderConfig = Field(default_factory=RenderConfig)
    dedup: DedupConfig = Field(default_factory=DedupConfig)
    storage: StorageConfig = Field(default_factory=StorageConfig)
    queue: QueueConfig = Field(default_factory=QueueConfig)
    worker: WorkerConfig = Field(default_factory=WorkerConfig)
    log: LogConfig = Field(default_factory=LogConfig)
    metrics: MetricsConfig = Field(default_factory=MetricsConfig)
    pipeline: list[PipelineItemConfig] = Field(default_factory=list)


def load_config(path: str | Path) -> CrawlerConfig:
    """从 YAML 文件加载配置"""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    with open(path, encoding="utf-8") as f:
        raw: dict[str, Any] = yaml.safe_load(f) or {}

    # 顶层 crawl 字段展开
    crawl = raw.pop("crawl", {})
    if isinstance(crawl, dict):
        for key in ("name", "seeds", "max_depth", "max_pages"):
            if key in crawl:
                raw[key] = crawl[key]

    return CrawlerConfig(**raw)


def load_config_from_dict(data: dict[str, Any]) -> CrawlerConfig:
    """从字典加载配置"""
    crawl = data.pop("crawl", {})
    if isinstance(crawl, dict):
        for key in ("name", "seeds", "max_depth", "max_pages"):
            if key in crawl:
                data[key] = crawl[key]
    return CrawlerConfig(**data)
