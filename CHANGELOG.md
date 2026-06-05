# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-06-06

### Added

- Core crawler engine with async pipeline (URL discovery → schedule → fetch → parse → store)
- URL Frontier with 8-rule normalization and priority queue
- BFS + priority scheduler with dedup and politeness filtering
- HttpxFetcher with HTTP/2, connection pooling, encoding detection (5-level fallback), retry (exponential backoff)
- HTML parser (lxml + parsel) with link extraction, JSON-LD, meta tags
- 4-layer Politeness: robots.txt, circuit breaker, token bucket, per-host semaphore
- Bloom Filter dedup (mmh3, configurable expected_items/false_positive_rate)
- Middleware system: UA rotation, Referer, Depth, Error
- Pipeline chain: Console, File (JSONL), SearchIndex
- Event system (EventEmitter) with 6 event types
- Crawler lifecycle: pause/resume/stop, runtime seed injection, stats
- SearchDocument model with 18 fields for search engine indexing
- Transformer: CrawlResult → SearchDocument with description fallback, JSON-LD extraction, anchor map
- SearchIndexPipeline: full-text JSONL output (no truncation)
- Vortex search engine index building via REST API
- Interactive TUI console (rich) with commands: help/status/pause/resume/stop/results/quit
- Web dashboard (FastAPI + SSE + Jinja2) with real-time progress, page detail, JSONL export, Vortex build
- CLI with --tui, --web, --host, --port flags
- Configuration system (pydantic v2 + YAML)
- 154 tests (unit + integration)
