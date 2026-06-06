"""交互式 TUI 控制台 — 基于 rich 的终端交互界面"""

from __future__ import annotations

import asyncio
import time

import structlog
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from kuafu.config import CrawlerConfig
from kuafu.crawler import Crawler
from kuafu.events import CRAWL_STOPPED, PROGRESS, URL_FAILED, URL_FETCHED
from kuafu.models import CrawlResult
from kuafu.pipeline.pipeline import ConsolePipeline

logger = structlog.get_logger()


class CrawlerConsole:
    """交互式爬虫控制台

    - 输入 URL 回车即开始爬取
    - 实时显示进度
    - 命令：help / status / pause / resume / stop / results / quit
    """

    def __init__(self) -> None:
        self._console = Console()
        self._crawler: Crawler | None = None
        self._task: asyncio.Task | None = None
        self._running = False
        self._start_time: float = 0
        self._last_url: str = ""
        self._last_error: str = ""
        self._results: list[CrawlResult] = []

    async def start(self) -> None:
        """启动交互式控制台"""
        self._running = True
        self._console.print(Panel(
            "[bold green]kuafu 交互式爬虫控制台[/bold green]\n\n"
            "输入 URL 开始爬取，输入命令控制流程\n\n"
            "[dim]命令: help | status | pause | resume | stop | results | quit[/dim]",
            title="kuafu",
            border_style="green",
        ))

        loop = asyncio.get_event_loop()

        while self._running:
            try:
                cmd = await loop.run_in_executor(None, lambda: input("kuafu> ").strip())
            except (EOFError, KeyboardInterrupt):
                break

            if not cmd:
                continue

            await self._handle_input(cmd)

        await self._cleanup()

    async def _handle_input(self, cmd: str) -> None:
        """处理用户输入"""
        if cmd in ("quit", "exit", "q"):
            self._running = False
            await self._stop_crawler()
            return

        if cmd == "help":
            self._print_help()
            return

        if cmd == "status":
            self._print_status()
            return

        if cmd == "pause":
            await self._pause_crawler()
            return

        if cmd == "resume":
            await self._resume_crawler()
            return

        if cmd == "stop":
            await self._stop_crawler()
            return

        if cmd == "results":
            self._print_results()
            return

        # 当作 URL 处理
        if cmd.startswith(("http://", "https://")):
            await self._start_crawl(cmd)
        else:
            self._console.print(f"[yellow]未知命令或无效 URL: {cmd}[/yellow]  输入 help 查看帮助")

    async def _start_crawl(self, url: str) -> None:
        """开始爬取指定 URL"""
        if self._crawler and self._crawler.stats.get("running"):
            self._console.print("[yellow]爬虫正在运行中，请先 stop[/yellow]")
            return

        config = CrawlerConfig(seeds=[url], max_depth=2, max_pages=100)
        self._crawler = Crawler(config, pipelines=[ConsolePipeline()])
        self._start_time = time.monotonic()
        self._last_url = ""
        self._last_error = ""
        self._results = []

        # 订阅事件
        self._crawler.events.on(URL_FETCHED, self._on_url_fetched)
        self._crawler.events.on(URL_FAILED, self._on_url_failed)
        self._crawler.events.on(PROGRESS, self._on_progress)
        self._crawler.events.on(CRAWL_STOPPED, self._on_crawl_stopped)

        self._task = self._crawler.run_as_task()
        self._console.print(f"[green]开始爬取: {url}[/green]")

    async def _pause_crawler(self) -> None:
        if self._crawler:
            await self._crawler.pause()
            self._console.print("[yellow]爬取已暂停[/yellow]")

    async def _resume_crawler(self) -> None:
        if self._crawler:
            await self._crawler.resume()
            self._console.print("[green]爬取已恢复[/green]")

    async def _stop_crawler(self) -> None:
        if self._crawler:
            await self._crawler.stop()
            if self._task:
                try:
                    await asyncio.wait_for(self._task, timeout=5.0)
                except asyncio.TimeoutError:
                    self._task.cancel()
                self._task = None
            self._console.print("[red]爬取已停止[/red]")

    async def _cleanup(self) -> None:
        await self._stop_crawler()
        self._console.print("[dim]再见！[/dim]")

    # ── 事件回调 ──

    async def _on_url_fetched(self, result: CrawlResult, **kwargs) -> None:
        self._last_url = result.fetch.url
        self._results.append(result)

    async def _on_url_failed(self, url: str, error: str = "", **kwargs) -> None:
        self._last_error = f"{url} — {error}"

    async def _on_progress(self, **kwargs) -> None:
        stats = kwargs
        elapsed = time.monotonic() - self._start_time if self._start_time else 0
        pages = stats.get("pages_crawled", 0)
        failed = stats.get("pages_failed", 0)
        discovered = stats.get("urls_discovered", 0)

        self._console.print(
            f"  [dim][{elapsed:.0f}s][/dim] "
            f"已抓取: [green]{pages}[/green]  "
            f"失败: [red]{failed}[/red]  "
            f"发现: [blue]{discovered}[/blue]  "
            f"最近: [dim]{self._last_url[:60]}[/dim]"
        )

    async def _on_crawl_stopped(self, **kwargs) -> None:
        pages = kwargs.get("pages_crawled", 0)
        failed = kwargs.get("pages_failed", 0)
        self._console.print(f"\n[bold]爬取完成[/bold] — 成功: {pages}  失败: {failed}")

    # ── 显示方法 ──

    def _print_help(self) -> None:
        table = Table(title="命令列表", show_header=False)
        table.add_column("命令", style="cyan")
        table.add_column("说明")
        for cmd, desc in [
            ("http(s)://...", "输入 URL 开始爬取"),
            ("status", "查看当前状态"),
            ("pause", "暂停爬取"),
            ("resume", "恢复爬取"),
            ("stop", "停止当前爬取"),
            ("results", "查看已抓取结果"),
            ("quit / exit", "退出控制台"),
        ]:
            table.add_row(cmd, desc)
        self._console.print(table)

    def _print_status(self) -> None:
        if not self._crawler:
            self._console.print("[yellow]未启动爬取[/yellow]")
            return
        stats = self._crawler.stats
        elapsed = time.monotonic() - self._start_time if self._start_time else 0
        table = Table(title="爬取状态")
        table.add_column("指标", style="cyan")
        table.add_column("值")
        table.add_row("运行中", str(stats.get("running", False)))
        table.add_row("已暂停", str(stats.get("paused", False)))
        table.add_row("已抓取", str(stats.get("pages_crawled", 0)))
        table.add_row("失败", str(stats.get("pages_failed", 0)))
        table.add_row("已发现", str(stats.get("urls_discovered", 0)))
        table.add_row("耗时", f"{elapsed:.1f}s")
        if self._last_error:
            table.add_row("最近错误", self._last_error[:80])
        self._console.print(table)

    def _print_results(self) -> None:
        if not self._results:
            self._console.print("[yellow]暂无结果[/yellow]")
            return
        table = Table(title=f"已抓取结果 ({len(self._results)})")
        table.add_column("状态码", style="green")
        table.add_column("URL")
        table.add_column("标题")
        for r in self._results[-20:]:
            table.add_row(
                str(r.fetch.status_code),
                r.fetch.url[:50],
                r.parse.title[:30],
            )
        self._console.print(table)
