"""配置系统测试"""

import pytest
import tempfile
from pathlib import Path

from kuafu.config import CrawlerConfig, load_config, load_config_from_dict


class TestCrawlerConfig:
    def test_default_config(self):
        config = CrawlerConfig()
        assert config.name == "kuafu-crawl"
        assert config.max_depth == -1
        assert config.fetcher.http2 is True
        assert config.politeness.default_delay == 1.0
        assert config.dedup.url.type == "bloom"

    def test_from_dict(self):
        config = load_config_from_dict({
            "name": "test",
            "seeds": ["https://example.com"],
            "max_depth": 5,
        })
        assert config.name == "test"
        assert config.seeds == ["https://example.com"]
        assert config.max_depth == 5

    def test_from_dict_with_crawl_key(self):
        config = load_config_from_dict({
            "crawl": {
                "name": "test",
                "seeds": ["https://example.com"],
            },
        })
        assert config.name == "test"

    def test_load_yaml_file(self):
        yaml_content = """
crawl:
  name: "yaml-test"
  seeds:
    - "https://example.com"
  max_depth: 3
politeness:
  default_delay: 2.0
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False, encoding="utf-8") as f:
            f.write(yaml_content)
            f.flush()
            config = load_config(f.name)

        assert config.name == "yaml-test"
        assert config.max_depth == 3
        assert config.politeness.default_delay == 2.0

    def test_missing_file_raises(self):
        with pytest.raises(FileNotFoundError):
            load_config("/nonexistent/config.yaml")

    def test_nested_config(self):
        config = CrawlerConfig(
            fetcher__http2=False,
            politeness__circuit_threshold=10,
        )
        # pydantic 不支持双下划线嵌套，用正确方式
        config = CrawlerConfig(
            fetcher={"http2": False},
            politeness={"circuit_threshold": 10},
        )
        assert config.fetcher.http2 is False
        assert config.politeness.circuit_threshold == 10
