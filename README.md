# Kuafu（夸父）

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/Tests-154%20passed-success.svg)](tests/)
[![Code style: ruff](https://img.shields.io/badge/Code%20style-ruff-orange.svg)](https://docs.astral.sh/ruff/)

轻量、易扩展的工业级网络爬虫引擎，支持数据抓取、提取与搜索引擎建库。

## 特性

- **可插拔架构** — 调度、存储、解析、去重全部抽象为接口，灵活替换
- **Politeness 内置** — robots.txt 遵循、令牌桶限速、断路器、并发控制
- **Bloom Filter 去重** — 亿级 URL 去重，1% 误判率仅约 17MB 内存
- **全异步** — 基于 asyncio + httpx，支持 HTTP/2
- **搜索建库** — SearchDocument 结构化输出，一键对接 Vortex 搜索引擎
- **Web 控制台** — FastAPI 可视化界面，实时进度、页面浏览、手动建库
- **TUI 控制台** — rich 终端交互，输入 URL 即爬取

## 快速开始

### 安装

```bash
# 基础安装
pip install -e .

# 含 Web 控制台
pip install -e ".[web]"

# 含开发工具
pip install -e ".[dev]"

# 全部
pip install -e ".[web,dev]"
```

### CLI 使用

```bash
# 最简用法
kuafu -s https://example.com

# 指定深度和页面数
kuafu -s https://example.com -d 3 -n 1000

# 使用配置文件
kuafu -c configs/kuafu.yaml

# 输出到文件
kuafu -s https://example.com -o ./output/

# 交互式 TUI
kuafu --tui

# Web 控制台（浏览器访问 http://localhost:8080）
kuafu --web
kuafu --web --port 3000
```

### Web 控制台

启动后浏览器访问 `http://localhost:8080`：

1. 输入 URL → 点击 Start 开始爬取
2. SSE 实时显示进度（已抓取/失败/发现/耗时）
3. Pause / Resume / Stop 控制爬取
4. 点击 URL 查看页面详情（标题、正文、出链、Meta）
5. Export JSONL 下载 SearchDocument
6. 输入 Vortex 地址 → Build Index 一键建库

### 编程式 API

```python
import asyncio
from kuafu.config import CrawlerConfig
from kuafu.crawler import Crawler
from kuafu.search.pipeline import SearchIndexPipeline


async def main():
    crawler = Crawler(
        CrawlerConfig(
            seeds=["https://example.com"],
            max_depth=3,
            max_pages=100,
        ),
        pipelines=[SearchIndexPipeline("./search-index.jsonl")],
    )
    await crawler.run()


asyncio.run(main())
```

### 自定义 Pipeline

```python
from kuafu.pipeline.pipeline import Pipeline
from kuafu.models import CrawlResult


class MyPipeline(Pipeline):
    async def process(self, result: CrawlResult) -> None:
        print(f"[{result.fetch.status_code}] {result.parse.title}: {result.fetch.url}")
```

## 项目结构

```
src/kuafu/
├── models.py              # 核心数据模型 (pydantic v2)
├── config.py              # 配置系统 (pydantic + YAML)
├── crawler.py             # 核心引擎
├── events.py              # 事件系统 (EventEmitter)
├── cli.py                 # CLI 入口
├── console.py             # TUI 控制台 (rich)
├── frontier/              # URL 状态管理
│   ├── base.py            #   URLStore 抽象接口
│   ├── url.py             #   URL 规范化
│   └── memory.py          #   内存存储
├── fetcher/               # HTTP 抓取
│   ├── base.py            #   Fetcher 抽象接口
│   ├── httpx_client.py    #   httpx 异步实现
│   ├── retry.py           #   重试策略
│   └── encoding.py        #   编码检测
├── parser/                # 页面解析
│   ├── base.py            #   Parser 抽象接口
│   ├── html.py            #   HTML 解析 (lxml + parsel)
│   └── link.py            #   链接提取与过滤
├── politeness/            # 礼貌策略
│   └── manager.py         #   robots + 断路器 + 令牌桶 + 信号量
├── dedup/                 # 去重
│   └── bloom.py           #   Bloom Filter + Memory
├── pipeline/              # 数据管道
│   └── pipeline.py        #   PipelineChain + Console + File
├── middleware/             # 中间件
│   └── middleware.py       #   UA轮换 + Referer + Depth + Error
├── scheduler/             # 调度器
│   ├── base.py            #   Scheduler 抽象接口
│   └── bfs.py             #   BFS + 优先级调度
├── search/                # 搜索建库
│   ├── models.py          #   SearchDocument 模型
│   ├── transformer.py     #   CrawlResult → SearchDocument
│   └── pipeline.py        #   SearchIndexPipeline
└── web/                   # Web 控制台
    ├── app.py             #   FastAPI 应用工厂
    ├── routes.py          #   REST + SSE 路由
    ├── crawl_manager.py   #   爬取任务管理器
    ├── event_bus.py       #   事件桥接
    ├── templates/          #   Jinja2 模板
    └── static/             #   CSS + JS
```

## 技术栈

| 组件 | 选型 |
|------|------|
| 语言 | Python 3.10+ |
| 异步 | asyncio |
| HTTP | httpx (HTTP/1.1 + HTTP/2) |
| HTML 解析 | lxml + parsel |
| JS 渲染 | Playwright (可选) |
| 去重 | mmh3 Bloom Filter |
| 配置 | pydantic + YAML |
| 日志 | structlog |
| Web | FastAPI + uvicorn + Jinja2 |
| 终端 UI | rich |
| 建库 | Vortex REST API |

## 开发

```bash
# 安装开发依赖
pip install -e ".[dev,web]"

# 运行测试
pytest tests/ -v

# 代码检查
ruff check src/
```

## License

MIT
