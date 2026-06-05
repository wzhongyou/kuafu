# kuafu 技术设计文档

> 版本：v3.0
> 日期：2026-06-06
> 定位：工业级、通用网络爬虫引擎

---

## 一、设计目标

### 1.1 项目愿景

kuafu 是一个工业级、通用网络爬虫引擎，提供从 URL 发现、调度、抓取、解析到搜索引擎建库的全链路能力，同时保持架构的轻量和易扩展。

### 1.2 核心设计原则

| 原则 | 说明 | 状态 |
|------|------|------|
| **可插拔** | 调度、存储、解析、渲染、去重全部抽象为接口，支持灵活替换 | 已实现 |
| **Politeness 内置** | robots.txt、令牌桶限速、断路器、并发控制四层保障 | 已实现 |
| **全异步** | 基于 asyncio + httpx，支持 HTTP/2 | 已实现 |
| **Bloom Filter 去重** | 亿级 URL 去重，1% 误判率仅约 17MB 内存 | 已实现 |
| **搜索建库** | SearchDocument 结构化输出，一键对接 Vortex 搜索引擎 | 已实现 |
| **Web 可视化** | FastAPI 控制台，实时进度、页面浏览、手动建库 | 已实现 |
| **渐进式渲染** | 默认不渲染，智能检测后按需 JS 渲染（Playwright） | 规划中 |
| **分布式** | Master-Worker 分离，消息队列解耦，水平扩展 | 规划中 |
| **断点可续** | 状态持久化，任意时刻暂停/恢复 | 部分实现（内存暂停/恢复，无持久化） |

### 1.3 能力分级

| 层级 | 能力 | 状态 |
|------|------|------|
| P0 | URL 管理、HTTP 抓取、HTML 解析、Politeness、Bloom Filter 去重、事件系统 | 已完成 |
| P1 | 搜索文档模型、SearchIndexPipeline、Web 控制台、Vortex 建库对接、TUI 控制台 | 已完成 |
| P2 | JS 渲染（Playwright）、分布式 Master-Worker、状态持久化、Prometheus 指标 | 规划中 |

---

## 二、技术选型

### 2.1 编程语言：Python 3.10+

| 考量 | 选择理由 |
|------|---------|
| 爬虫生态 | httpx/lxml/Playwright/jieba 极其丰富 |
| 开发效率 | 语法简洁，动态类型，快速迭代 |
| 异步支持 | asyncio + async/await 成熟，3.10+ 性能显著改善 |
| 中文支持 | jieba/charset-normalizer 成熟，目标用户需要中文场景 |
| JS 渲染 | Playwright Python 绑定是一等公民 |

### 2.2 核心依赖

| 组件 | 选型 | 说明 |
|------|------|------|
| 异步框架 | asyncio | Python 原生异步 |
| HTTP 客户端 | httpx (async, HTTP/2) | 支持 HTTP/1.1 和 HTTP/2，连接池可配置 |
| HTML 解析 | lxml + parsel | C 扩展高性能，XPath+CSS 选择器（Scrapy 同款） |
| URL 处理 | yarl | aiohttp 生态的 URL 库，规范化能力强 |
| Bloom Filter | mmh3 | MurmurHash3，自实现 Bloom Filter |
| 配置管理 | pydantic v2 + PyYAML | 运行时验证 + YAML 配置文件 |
| 日志 | structlog | 结构化日志，JSON 输出 |
| 编码检测 | charset-normalizer | 比 chardet 更快更准 |
| Web 框架 | FastAPI + Jinja2 | 异步 Web 控制台，SSE 实时推送 |
| ASGI 服务器 | uvicorn | 高性能 ASGI 服务器 |
| 终端 UI | rich | 交互式 TUI 控制台 |
| 文件异步 | aiofiles | Pipeline 异步文件写入 |

### 2.3 行业调研总结

主流搜索引擎爬虫的核心架构模式：

| 爬虫 | 架构 | 调度策略 | 去重 | Politeness |
|------|------|---------|------|-----------|
| Googlebot | 分布式 Master-Worker | 优先级 + 刷新频率 | PerDoc 百亿级 | Crawl-Delay, rate limiting |
| Bingbot | 分布式队列 | 优先级队列 | SimHash 近似去重 | robots.txt, rate limiting |
| Baiduspider | 中心化调度 | 广度优先为主 | Bloom Filter | robots.txt, IP 级限速 |
| Yandexbot | 分布式 | 优先级 + 历史质量 | SimHash | Crawl-Delay, 自适应 |

开源框架设计参考：

| 框架 | 架构 | 优势 | kuafu 借鉴 |
|------|------|------|-----------|
| Scrapy | 单进程+中间件管道 | 可插拔中间件/Pipeline | 中间件模式、Pipeline Chain |
| Nutch | Hadoop 分布式 | 大规模分布式 | BFS 调度、Politeness 四层设计 |
| Crawlab | Master-Worker | 任务管理 UI | Web 控制台设计 |
| StormCrawler | 流式 | 实时性好 | 事件驱动架构 |

---

## 三、整体架构

### 3.1 架构总览

```
┌──────────────────────────────────────────────────────────────┐
│                      用户交互层                               │
│  ┌──────────┐  ┌───────────────┐  ┌────────────────────────┐ │
│  │   CLI    │  │  TUI Console  │  │   Web Dashboard        │ │
│  │ (argparse)│  │   (rich)      │  │  (FastAPI+SSE+Jinja2)  │ │
│  └────┬─────┘  └──────┬────────┘  └──────────┬─────────────┘ │
│       │               │                      │               │
│       └───────────────┼──────────────────────┘               │
│                       │                                      │
│              ┌────────▼────────┐                             │
│              │  CrawlManager   │  ← Web 层任务管理            │
│              │  (事件桥接+状态) │                             │
│              └────────┬────────┘                             │
└───────────────────────┼──────────────────────────────────────┘
                        │
┌───────────────────────┼──────────────────────────────────────┐
│              ┌────────▼────────┐                             │
│              │    Crawler      │  ← 核心引擎                  │
│              │  (全链路编排)    │                             │
│              └────────┬────────┘                             │
│                       │                                      │
│  ┌────────┐ ┌────────▼────────┐ ┌────────┐ ┌────────────┐  │
│  │Scheduler│ │   Fetch Engine  │ │ Parser │ │  Pipeline  │  │
│  │ (BFS+  │ │   (httpx/H2)   │ │(lxml+  │ │ (Chain +   │  │
│  │ 优先级) │ │   编码检测+重试  │ │ parsel)│ │  Console   │  │
│  └───┬────┘ └────────┬────────┘ └───┬────┘ │  File      │  │
│      │               │              │       │  Search)   │  │
│  ┌───▼────┐    ┌─────▼─────┐  ┌────▼───┐  └────────────┘  │
│  │Frontier│    │Politeness │  │  Link  │                    │
│  │(URLStore│    │robots.txt │  │Extractor│                   │
│  │ +去重)  │    │断路器+令牌桶│  │ +Filter │                   │
│  └────────┘    └───────────┘  └────────┘                    │
│                                                              │
│  ┌──────────────┐  ┌─────────────┐                          │
│  │  Middleware   │  │   Events    │                          │
│  │ UA/Referer/  │  │  EventEmitter│                          │
│  │ Depth/Error  │  │  6种事件类型  │                          │
│  └──────────────┘  └─────────────┘                          │
└──────────────────────────────────────────────────────────────┘
                        │
              ┌─────────▼──────────┐
              │   Search Package   │
              │ SearchDocument     │
              │ Transformer        │
              │ SearchIndexPipeline│
              │ Vortex 建库对接    │
              └────────────────────┘
```

### 3.2 数据流

```
Seed URLs → Frontier → Scheduler(BFS+去重) → Politeness(4层检查)
    → Fetcher(httpx) → Parser(lxml+parsel) → Pipeline(处理+输出)
    → 新链接 → Frontier → ...

事件流: Crawler → EventEmitter → EventBus → SSE → 浏览器
建库流: CrawlResult → transform() → SearchDocument → Vortex POST /api/document
```

---

## 四、核心模块设计

### 4.1 数据模型 (`models.py`)

所有模型基于 pydantic v2 BaseModel，支持 `model_dump_json()` 零成本序列化。

```
URLStatus(IntEnum)  —  9 种状态：DISCOVERED → PENDING → FETCHING → FETCHED → PARSED → COMPLETED / FAILED / SKIPPED / ABANDONED

URLItem         — URL 条目，贯穿全链路（raw, normalized, parent, depth, priority, status, retries, meta）
FetchRequest    — 抓取请求（url, method, headers, cookies, proxy, timeout, need_render, max_depth）
FetchResult     — 抓取结果（url, status_code, headers, body, content_type, encoding, fetch_time, duration, redirect_chain, error）
  .host         — 属性：从 URL 提取 host
  .is_success   — 属性：200-299 且无 error
  .content_changed — 属性：基于 304/ETag 判断
Link            — 页面链接（url, text, rel, no_follow, is_external）
ParseResult     — 解析结果（title, text, links, meta, canonical, language, structured_data）
CrawlResult     — 最终输出（request + fetch + parse + url_item）
```

### 4.2 配置系统 (`config.py`)

基于 pydantic v2 的层级配置：

```
CrawlerConfig
  name: str                    # 爬取任务名
  seeds: list[str]             # 种子 URL
  max_depth: int = -1          # 最大深度
  max_pages: int = -1          # 最大页面数
  scheduler: SchedulerConfig   # type, batch_size
  fetcher: FetcherConfig       # user_agent, timeout, max_connections, http2, retry
  politeness: PolitenessConfig # default_delay, max_concurrent_per_host, circuit_threshold
  parser: ParserConfig         # extract_links, follow_nofollow
  dedup: DedupConfig           # url.type=bloom/map, bloom params
  worker: WorkerConfig         # concurrency
  log: LogConfig               # level, format
  pipeline: list[PipelineItemConfig]  # type=console/file/search, path
```

支持 YAML 文件加载 `load_config(path)` 和字典加载 `load_config_from_dict(data)`。

### 4.3 URL Frontier (`frontier/`)

**URLStore 抽象**（`base.py`）：
- `put`, `batch_put`, `update_status`, `get`, `pop_pending`, `exists`, `count_by_status`, `close`

**MemoryURLStore**（`memory.py`）：dict + heapq 优先级队列，asyncio.Lock 保护。

**URL 规范化**（`url.py`）— 8 条规则：
1. 协议+域名小写化
2. 默认端口去除（80/443）
3. 路径规范化（`/./`、`/../`）
4. 片段去除
5. 追踪参数去除（utm_*, fbclid, gclid 等 30+ 参数）
6. 查询参数排序
7. 尾斜线统一
8. 百分号编码统一

### 4.4 调度器 (`scheduler/`)

**BFSScheduler**（`bfs.py`）：
- 同一优先级内广度优先（深度递增），保证覆盖面
- 不同优先级间严格按优先级排序
- push 时执行深度检查 + 去重检查 + 状态确保 PENDING
- schedule 时执行 Politeness 过滤
- feedback 将抓取结果反馈给 Politeness（记录 host 状态）

### 4.5 Politeness (`politeness/`)

四层友好策略：

| 层级 | 组件 | 职责 |
|------|------|------|
| 1 | RobotsTxtManager | 解析并缓存 robots.txt，TTL 过期自动刷新 |
| 2 | CircuitBreaker | CLOSE/OPEN/HALF_OPEN 状态机，连续失败触发断路 |
| 3 | TokenBucket | 令牌桶限速，支持动态 Crawl-Delay |
| 4 | asyncio.Semaphore | 每站点并发控制 |

### 4.6 Fetch Engine (`fetcher/`)

**HttpxFetcher**（`httpx_client.py`）：
- httpx.AsyncClient，HTTP/2 支持
- 连接池：max_connections, max_connections_per_host
- 超时配置：connect/read/total 三级
- 重定向链记录
- 错误分类：timeout / HTTP status / generic

**编码检测**（`encoding.py`）— 5 级 fallback：
1. Content-Type header charset
2. meta charset
3. meta http-equiv
4. charset-normalizer 统计检测
5. UTF-8 默认

**重试策略**（`retry.py`）：
- 指数退避 + 随机 jitter
- 429 Retry-After 头解析
- 可配置 retry-on-status 列表

### 4.7 Parser (`parser/`)

**HTMLParser**（`html.py`）— 基于 parsel (lxml)：
- title、text（strips script/style）、meta（含 og:）、canonical、language
- JSON-LD 结构化数据提取（必须在 _extract_text 之前，因为后者会移除 script 标签）
- CSS + XPath 选择器

**LinkExtractor**（`link.py`）：
- 提取 `<a>`, `<area>`, `<iframe>`, `<meta refresh>` 链接
- 相对→绝对 URL 转换
- nofollow 标记、external 检测

**LinkFilter 层级**：
- `DomainFilter` — 限定域名范围
- `FileTypeFilter` — 过滤 30+ 非页面扩展名
- `SchemeFilter` — 只允许 http/https
- `RegexFilter` — 正则匹配

### 4.8 去重 (`dedup/`)

| 实现 | 算法 | 内存 | 误判率 |
|------|------|------|--------|
| `MemoryDeduplicator` | Python set | O(n) 精确 | 0% |
| `BloomFilterDeduplicator` | mmh3 + bytearray | ~17MB/亿 | 可配置（默认 1%） |

Bloom Filter 参数自动计算：给定 expected_items 和 false_positive_rate，计算最优 m（bit 数）和 k（hash 次数）。

### 4.9 中间件 (`middleware/`)

| 中间件 | 类型 | 职责 |
|--------|------|------|
| `UAMiddleware` | Request | 5 种浏览器 UA 随机轮换 |
| `RefererMiddleware` | Request | 自动添加 Referer 头 |
| `DepthMiddleware` | Request | 超出深度时标记 X-Skip-Depth |
| `ErrorMiddleware` | Response | 标记重试次数 |

### 4.10 Pipeline (`pipeline/`)

```python
class Pipeline(ABC):
    async def process(self, result: CrawlResult) -> None: ...
    async def close(self) -> None: ...
```

| 实现 | 说明 |
|------|------|
| `ConsolePipeline` | 打印 [status_code] url (duration) title |
| `FilePipeline` | JSONL 文件输出（aiofiles） |
| `SearchIndexPipeline` | CrawlResult → SearchDocument → JSONL（完整文本不截断） |

`PipelineChain` 顺序执行多个 Pipeline。

### 4.11 事件系统 (`events.py`)

```python
class EventEmitter:
    def on(event, callback)    # 注册异步监听器
    def off(event, callback)   # 移除
    def emit(event, **kwargs)  # 非阻塞派发（create_task）
    def clear()                # 清除全部
```

| 事件 | 触发点 | 数据 |
|------|--------|------|
| `CRAWL_STARTED` | run() 启动 | config |
| `CRAWL_STOPPED` | _shutdown() | pages_crawled, pages_failed |
| `URL_FETCHED` | 抓取成功 | result: CrawlResult |
| `URL_FAILED` | 抓取失败 | url, error |
| `URL_DISCOVERED` | 新 URL 入队 | count |
| `PROGRESS` | 每次状态变更 | **stats |

### 4.12 核心引擎 (`crawler.py`)

`Crawler` 类组装所有模块，驱动完整流程：

**公共 API：**
- `run()` — 启动爬取（阻塞）
- `run_as_task()` — 后台 Task 启动（供 TUI/Web 使用）
- `stop()` / `pause()` / `resume()` — 生命周期控制
- `add_seed(url)` — 运行时动态注入种子
- `events` — EventEmitter 实例
- `config` — CrawlerConfig 实例
- `stats` — {pages_crawled, pages_failed, urls_discovered, running, paused}
- `frontier_stats` — {pending, completed, failed}（async property）

**主循环流程：**
1. 注入种子 → Scheduler
2. 循环：schedule batch → 并发 _process_url
3. _process_url：暂停门 → Politeness → 中间件 → Fetch → 中间件 → Parser → Pipeline → 事件发射
4. _shutdown：关闭所有模块

---

## 五、搜索建库 (`search/`)

### 5.1 SearchDocument 模型

| 字段 | 来源 | Vortex 映射 | 类型 |
|------|------|------------|------|
| doc_id | MD5(canonical_url) | doc_id | KEYWORD stored |
| url | canonical 或 fetch.url | url | KEYWORD |
| title | parse.title | title | TEXT indexed+stored |
| description | 3 级 fallback | description | TEXT indexed+stored |
| text | parse.text（不截断） | content | TEXT indexed+stored |
| author | meta + JSON-LD | author | TEXT indexed+stored |
| fetch_time | fetch.fetch_time | timestamp | KEYWORD |
| site | fetch.host | site | KEYWORD |
| category | article:section / og:type | category | KEYWORD |
| lang | parse.language | — | — |
| content_type | fetch.content_type | — | — |
| content_hash | MD5(text) | — | 内容去重 |
| published_time | meta + JSON-LD | — | — |
| modified_time | meta + JSON-LD | — | — |
| canonical | parse.canonical | — | — |
| anchor_map | {link.url: link.text} | — | — |
| structured_data | parse.structured_data | — | — |
| word_count | CJK 逐字 + 西文分词 | — | — |
| depth | url_item.depth | — | — |

### 5.2 Transformer

`transform(CrawlResult) → SearchDocument` 纯函数，处理：
- URL 优先级：canonical > fetch.url
- description 3 级 fallback：meta.description → og:description → text[:200]
- published/modified time：meta → JSON-LD 递归查找
- author：meta → JSON-LD（支持 Person 对象 {name: ...}）
- category：article:section → og:type
- content_hash：MD5(text)
- word_count：CJK 逐字 + 西文按空格

### 5.3 Vortex 建库对接

通过 Web 控制台手动触发，使用 Vortex REST API `POST /api/document`：

```
CrawlResult[] → transform() → SearchDocument → Vortex Document JSON
                                                         ↓
                                              POST /api/document (并发=10)
                                                         ↓
                                              返回 {total, success, failed}
```

Vortex Document schema：
```json
{
  "title": "...", "content": "...", "url": "...", "site": "...",
  "author": "...", "timestamp": "...", "description": "...",
  "doc_id": "...", "category": "..."
}
```

---

## 六、Web 控制台 (`web/`)

### 6.1 架构

```
浏览器 ←→ FastAPI (REST + SSE) ←→ CrawlManager ←→ Crawler
                                    ↕
                              EventBus (asyncio.Queue)
                                    ↕
                              SSE → 浏览器实时更新
```

### 6.2 CrawlManager

单任务爬取管理器，桥接 Crawler 与 Web 层：
- 状态机：idle → running ↔ paused → completed/stopped
- 累积 CrawlResult（上限 500，strip body 节省内存）
- 事件回调桥接到 EventBus
- JSONL 导出 + Vortex 建库

### 6.3 EventBus

asyncio.Queue 发布-订阅：
- `subscribe()` → 每个 SSE 客户端一个队列
- `publish(event_type, data)` → 广播，满队列丢弃最旧
- maxsize=100，30s keepalive

### 6.4 API 端点

| Method | Path | 说明 |
|--------|------|------|
| GET | `/` | 主控面板 |
| GET | `/detail?url=...` | 页面详情 |
| GET | `/api/status` | 当前状态 JSON |
| POST | `/api/crawl/start` | 开始爬取 {url, max_depth, max_pages} |
| POST | `/api/crawl/pause` | 暂停 |
| POST | `/api/crawl/resume` | 恢复 |
| POST | `/api/crawl/stop` | 停止 |
| GET | `/api/results` | 结果摘要列表 |
| POST | `/api/crawl/export` | 下载 SearchDocument JSONL |
| POST | `/api/crawl/build-index` | 对接 Vortex 建库 {vortex_url} |
| GET | `/api/events` | SSE 实时事件流 |

### 6.5 SSE 事件

| 事件 | 数据 |
|------|------|
| `crawl_started` | {seed, max_depth, max_pages} |
| `progress` | {pages_crawled, pages_failed, urls_discovered, running, paused} |
| `url_fetched` | {url, status_code, title, duration, depth} |
| `url_failed` | {url, error} |
| `crawl_stopped` | {pages_crawled, pages_failed} |

### 6.6 前端

- Jinja2 模板 + vanilla JS（无需 Node 构建）
- 暗色主题 CSS
- SSE 自动重连
- 表单：seed URL + depth + pages
- 状态面板：运行指示灯 + 计数器 + 耗时
- 控制按钮：Pause / Resume / Stop
- 操作区：Export JSONL + Build Vortex Index
- 结果表格：SSE 实时追加

---

## 七、TUI 控制台 (`console.py`)

基于 rich 的终端交互界面：
- 输入 URL 回车即开始爬取
- 实时显示进度（pages crawled/failed/discovered、当前 URL、耗时）
- 命令：help / status / pause / resume / stop / results / quit
- 订阅 Crawler 事件更新显示

---

## 八、项目结构

```
src/kuafu/
├── __init__.py              # 版本号
├── models.py                # 核心数据模型 (pydantic v2)
├── config.py                # 配置系统 (pydantic + YAML)
├── crawler.py               # 核心引擎 (全链路编排)
├── events.py                # 事件系统 (EventEmitter)
├── cli.py                   # CLI 入口 (--tui / --web)
├── console.py               # TUI 控制台 (rich)
├── frontier/                # URL 状态管理
│   ├── base.py              #   URLStore 抽象接口
│   ├── url.py               #   URL 规范化 (8 条规则)
│   └── memory.py            #   内存存储 (dict + heapq)
├── fetcher/                 # HTTP 抓取
│   ├── base.py              #   Fetcher 抽象接口
│   ├── httpx_client.py      #   httpx 异步实现 (HTTP/2)
│   ├── retry.py             #   重试策略 (指数退避 + jitter)
│   └── encoding.py          #   编码检测 (5 级 fallback)
├── parser/                  # 页面解析
│   ├── base.py              #   Parser 抽象接口
│   ├── html.py              #   HTML 解析 (lxml + parsel)
│   └── link.py              #   链接提取与过滤
├── politeness/              # 礼貌策略
│   └── manager.py           #   robots + 断路器 + 令牌桶 + 信号量
├── dedup/                   # 去重
│   └── bloom.py             #   Bloom Filter + Memory
├── pipeline/                # 数据管道
│   └── pipeline.py          #   PipelineChain + Console + File
├── middleware/              # 中间件
│   └── middleware.py        #   UA轮换 + Referer + Depth + Error
├── scheduler/               # 调度器
│   ├── base.py              #   Scheduler 抽象接口
│   └── bfs.py               #   BFS + 优先级调度
├── search/                  # 搜索建库
│   ├── models.py            #   SearchDocument 模型
│   ├── transformer.py       #   CrawlResult → SearchDocument
│   └── pipeline.py          #   SearchIndexPipeline (JSONL)
└── web/                     # Web 控制台
    ├── app.py               #   FastAPI 应用工厂
    ├── routes.py            #   REST + SSE 路由
    ├── crawl_manager.py     #   爬取任务管理器
    ├── event_bus.py         #   asyncio.Queue 事件桥
    ├── templates/           #   Jinja2 模板
    │   ├── base.html
    │   ├── index.html
    │   └── detail.html
    └── static/              #   静态资源
        ├── style.css
        └── main.js
```

---

## 九、配置设计

### YAML 配置示例

```yaml
crawl:
  name: my-crawl
  seeds:
    - https://example.com
  max_depth: 3
  max_pages: 1000

  fetcher:
    timeout: 30
    max_connections: 100
    http2: true
    retry:
      max_retries: 3
      backoff_factor: 1.0

  politeness:
    default_delay: 1.0
    max_concurrent_per_host: 2
    circuit_threshold: 5
    respect_crawl_delay: true

  dedup:
    url:
      type: bloom
      bloom:
        expected_items: 1000000
        false_positive_rate: 0.01

  worker:
    concurrency: 10

  pipeline:
    - type: console
    - type: search
      path: ./output/search-index.jsonl

  log:
    level: info
    format: json
```

### CLI 使用

```bash
# 直接爬取
kuafu -s https://example.com -d 3 -n 100

# 配置文件
kuafu -c configs/kuafu.yaml

# TUI 交互模式
kuafu --tui

# Web 控制台
kuafu --web --port 8080
```

---

## 十、关键设计决策

| 决策 | 选择 | 理由 |
|------|------|------|
| 异步框架 | asyncio | Python 原生，与 httpx/pydantic 生态最契合 |
| HTTP 客户端 | httpx | 原生 async + HTTP/2，比 aiohttp 更现代 |
| HTML 解析 | lxml+parsel | C 扩展高性能，XPath+CSS 双选择器 |
| 去重算法 | Bloom Filter | 亿级 URL 仅需 ~17MB，1% 误判率可接受 |
| 配置验证 | pydantic v2 | 运行时类型安全 + JSON schema 自动生成 |
| Web 框架 | FastAPI | 与 pydantic 深度集成，原生 async，SSE 支持 |
| 实时推送 | SSE (非 WebSocket) | 单向数据流，实现简单，无需额外依赖 |
| 建库协议 | Vortex REST API | 简单易用，无需 C++ SDK，适合中等规模 |
| 前端技术 | Jinja2 + vanilla JS | 无 Node 构建，pip install 即用 |
| JSON-LD 提取先于 text | 提取顺序 | _extract_text 会移除 script 标签，必须在 JSON-LD 之后 |

---

## 十一、测试

| 测试文件 | 覆盖模块 | 测试数 |
|----------|---------|--------|
| test_url_normalize | URL 规范化 | 15 |
| test_dedup | Bloom Filter + Memory 去重 | 6 |
| test_politeness | 断路器 + 令牌桶 + robots | 8 |
| test_encoding | 5 级编码检测 | 5 |
| test_retry | 重试策略 | 5 |
| test_config | 配置加载 | 4 |
| test_parser | HTML 解析 + 链接提取 | 5 |
| test_frontier | URL 存储 | 3 |
| test_middleware | UA/Referer/Depth | 6 |
| test_events | 事件系统 | 7 |
| test_crawler_events | Crawler 事件集成 | 6 |
| test_search_transformer | SearchDocument 转换 | 20 |
| test_search_pipeline | SearchIndexPipeline | 4 |
| test_web_event_bus | EventBus 发布-订阅 | 7 |
| test_web_crawl_manager | CrawlManager | 6 |
| test_e2e (集成) | 端到端爬取 | 1 |
| test_search_e2e (集成) | 搜索建库 E2E | 1 |

共 **154** 测试，全部通过。

---

## 十二、里程碑

### P0 — 核心引擎（已完成）

- [x] 数据模型 (pydantic v2)
- [x] URL Frontier + 规范化
- [x] BFS + 优先级调度
- [x] httpx 异步抓取 + HTTP/2
- [x] 5 级编码检测
- [x] 指数退避重试
- [x] lxml+parsel HTML 解析
- [x] 链接提取 + 4 种过滤器
- [x] Politeness 四层防护
- [x] Bloom Filter 去重
- [x] 中间件体系
- [x] Pipeline Chain + Console + File
- [x] 配置系统 (YAML + pydantic)
- [x] CLI 入口

### P1 — 交互 + 搜索建库（已完成）

- [x] 事件系统 (EventEmitter)
- [x] Crawler 增强 (pause/resume/add_seed/stats/run_as_task)
- [x] TUI 控制台 (rich)
- [x] SearchDocument 模型
- [x] Transformer (CrawlResult → SearchDocument)
- [x] SearchIndexPipeline (JSONL)
- [x] Web 控制台 (FastAPI + SSE + Jinja2)
- [x] Vortex 搜索引擎建库对接

### P2 — 增强（规划中）

- [ ] Playwright JS 渲染
- [ ] 分布式 Master-Worker
- [ ] Redis/Kafka 消息队列
- [ ] 状态持久化 (SQLite/Redis Frontier)
- [ ] Prometheus 指标端点
- [ ] SimHash 内容去重
- [ ] 自适应调度策略
- [ ] 高级反爬对抗
