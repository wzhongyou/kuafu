"""CLI 入口"""

from __future__ import annotations

import argparse
import asyncio
import sys

from kuafu.config import load_config
from kuafu.crawler import Crawler


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="kuafu",
        description="kuafu - 轻量、易扩展的工业级网络爬虫引擎",
    )
    parser.add_argument("-c", "--config", default=None, help="配置文件路径 (YAML)")
    parser.add_argument("-s", "--seed", action="append", default=[], help="种子 URL（可多次指定）")
    parser.add_argument("-d", "--max-depth", type=int, default=None, help="最大深度")
    parser.add_argument("-n", "--max-pages", type=int, default=None, help="最大页面数")
    parser.add_argument("-o", "--output", default=None, help="输出目录")
    parser.add_argument("--log-level", default=None, choices=["debug", "info", "warning", "error"])
    parser.add_argument("--tui", action="store_true", help="启动交互式 TUI 控制台")
    parser.add_argument("--web", action="store_true", help="启动 Web 控制台")
    parser.add_argument("--host", default="127.0.0.1", help="Web 控制台绑定地址 (默认 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8080, help="Web 控制台端口 (默认 8080)")

    args = parser.parse_args()

    # TUI 模式
    if args.tui:
        from kuafu.console import CrawlerConsole
        asyncio.run(CrawlerConsole().start())
        return

    # Web 模式
    if args.web:
        from kuafu.web.app import create_app
        import uvicorn
        uvicorn.run(create_app(), host=args.host, port=args.port)
        return

    # 加载配置
    if args.config:
        config = load_config(args.config)
    else:
        from kuafu.config import CrawlerConfig
        config = CrawlerConfig()

    # 命令行参数覆盖
    if args.seed:
        config.seeds = args.seed
    if args.max_depth is not None:
        config.max_depth = args.max_depth
    if args.max_pages is not None:
        config.max_pages = args.max_pages
    if args.output:
        from kuafu.config import PipelineItemConfig
        config.pipeline = [PipelineItemConfig(type="file", path=args.output)]
    if args.log_level:
        config.log.level = args.log_level

    if not config.seeds:
        parser.error("No seeds specified. Use -s/--seed or provide a config file with seeds.")

    # 运行
    crawler = Crawler(config)
    try:
        asyncio.run(crawler.run())
    except KeyboardInterrupt:
        sys.exit(0)


if __name__ == "__main__":
    main()
