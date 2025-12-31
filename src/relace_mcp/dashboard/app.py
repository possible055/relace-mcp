import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import ContentSwitcher, Footer, RichLog

from .log_reader import (
    ALL_KINDS,
    compute_stats,
    filter_event,
    get_log_path,
    parse_log_event,
    read_log_events,
)
from .widgets import CompactHeader, FilterChanged, SearchTree, TimeRangeChanged


class LogViewerApp(App[None]):  # type: ignore[misc]
    TITLE = "Relace MCP"
    CSS_PATH = "styles.tcss"
    ENABLE_COMMAND_PALETTE = False

    BINDINGS = [
        # Main actions
        Binding("q", "quit", "Quit"),
        Binding("r", "reload", "Reload"),
        # Filter shortcuts
        Binding("f1", "filter('all')", "All", show=False),
        Binding("f2", "filter('apply')", "Apply", show=False),
        Binding("f3", "filter('search')", "Search", show=False),
        Binding("f4", "filter('errors')", "Errors", show=False),
        # Time shortcuts
        Binding("t", "toggle_time", "Time"),
    ]

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._enabled_kinds: set[str] = set(ALL_KINDS)
        self._time_start: datetime = datetime.now(UTC) - timedelta(hours=24)
        self._time_end: datetime = datetime.now(UTC)
        self._tail_task: asyncio.Task[None] | None = None

    def compose(self) -> ComposeResult:
        yield CompactHeader(id="header")
        with ContentSwitcher(initial="log-all"):
            # 1. ALL LOGS (Persistent)
            yield RichLog(
                highlight=True,
                markup=True,
                id="log-all",
                max_lines=10000,
                wrap=True,
            )

            # 2. APPLY LOGS (Persistent)
            yield RichLog(
                highlight=True,
                markup=True,
                id="log-apply",
                max_lines=10000,
                wrap=True,
            )

            # 3. SEARCH TREE (Persistent)
            yield SearchTree(id="tree-search")

            # 4. ERRORS LOGS (Persistent)
            yield RichLog(
                highlight=True,
                markup=True,
                id="log-errors",
                max_lines=10000,
                wrap=True,
            )
        yield Footer()

    async def on_mount(self) -> None:
        self.action_reload()  # Load initial data to all 4 widgets
        self._tail_task = asyncio.create_task(self._tail_log())

    def _dispatch_event(self, event: dict[str, Any]) -> None:
        """Dispatch a single event to all relevant widgets."""
        kind = event.get("kind", "")

        # 1. To 'All' (Always)
        self._write_event(self.query_one("#log-all", RichLog), event)

        # 2. To 'Apply'
        from .log_reader import APPLY_KINDS, SEARCH_KINDS

        if kind in APPLY_KINDS:
            self._write_event(self.query_one("#log-apply", RichLog), event)

        # 3. To 'Search' (Tree)
        # Note: SEARCH_KINDS includes search_start/turn/tool/complete/error
        if kind in SEARCH_KINDS:
            self.query_one("#tree-search", SearchTree).add_event(event)

        # 4. To 'Errors'
        if "error" in kind:
            self._write_event(self.query_one("#log-errors", RichLog), event)

    def _load_initial_events(self) -> None:
        # Load almost unlimited events
        events = read_log_events(
            enabled_kinds=None,  # None = Read everything (don't pre-filter by kind)
            time_start=self._time_start,
            time_end=self._time_end,
            max_events=1000000,
        )

        # Clear all widgets first
        self.query_one("#log-all", RichLog).clear()
        self.query_one("#log-apply", RichLog).clear()
        self.query_one("#tree-search", SearchTree).clear()
        self.query_one("#log-errors", RichLog).clear()

        # Dispatch all
        for event in events:
            self._dispatch_event(event)

        stats = compute_stats(events)
        self._update_stats(stats)

    def _update_stats(self, stats: dict[str, Any]) -> None:
        total = stats.get("total", 0)
        apply_ok = stats.get("apply_success", 0)
        search_ok = stats.get("search_complete", 0)
        header = self.query_one("#header", CompactHeader)
        header.stats_text = f"Total: {total} | Apply: {apply_ok}✓ | Search: {search_ok}✓"

    def _write_event(self, log_widget: RichLog, event: dict[str, Any]) -> None:
        kind = event.get("kind", "unknown")
        ts = event.get("timestamp", "")[11:19]  # Time only (HH:MM:SS) for htop vibe

        line = Text()
        line.append(f"{ts} ", style="dim white")

        # Compact Type Badge
        kind_style = self._get_kind_style(kind)
        short_kind = (
            kind.replace("_success", "").replace("_start", "").replace("tool_call", "tool").upper()
        )
        if len(short_kind) > 6:
            short_kind = short_kind[:6]

        line.append(f"{short_kind:<7}", style=kind_style)

        if kind in ("apply_success", "create_success"):
            file_path = event.get("file_path", "")
            if file_path:
                line.append(f" {Path(file_path).name}", style="bold cyan")

            # Application Token Usage
            usage = event.get("usage", {})
            if usage:
                # Approximate total tokens if exact total is not provided (OpenAI format usually has total_tokens)
                total_tokens = usage.get("total_tokens")
                if total_tokens is None:
                    total_tokens = usage.get("prompt_tokens", 0) + usage.get("completion_tokens", 0)
                if total_tokens > 0:
                    line.append(f" tok:{total_tokens}", style="dim")

            if "latency_ms" in event:
                latency_s = event["latency_ms"] / 1000.0
                line.append(f" ({latency_s:.3f}s)", style="dim")
        elif kind == "apply_error":
            file_path = event.get("file_path", "")
            if file_path:
                line.append(f" {Path(file_path).name}", style="bold red")
            error = event.get("error", "")
            if error:
                line.append(f" {error}", style="bold red")
        elif kind == "search_start":
            query = event.get("query_preview", "")
            line.append(f' "{query}"', style="italic white")
        elif kind == "search_turn":
            turn = event.get("turn", "?")
            max_turns = event.get("max_turns", "?")
            tokens = event.get("prompt_tokens") or event.get("prompt_tokens_est") or 0
            line.append(f" {turn}/{max_turns}", style="bold")
            line.append(f" tok:{tokens}", style="dim")
        elif kind == "tool_call":
            tool_name = event.get("tool_name", "")
            latency = event.get("latency_ms", 0)
            success = event.get("success", True)
            line.append(f" {tool_name}", style="" if success else "yellow")
            if not success:
                line.append(" FAIL", style="bold red")
            line.append(f" ({latency / 1000.0:.3f}s)", style="dim")
        elif kind == "search_complete":
            turns = event.get("turns_used", "?")
            files = event.get("files_found", 0)
            latency = event.get("total_latency_ms", 0)
            line.append(f" turns:{turns} files:{files}", style="green")
            line.append(f" ({latency / 1000.0:.3f}s)", style="dim")
        elif kind == "search_error":
            error = event.get("error", "")
            line.append(f" {error}", style="bold red")

        log_widget.write(line)

    def _get_kind_style(self, kind: str) -> str:
        if "error" in kind:
            return "bold red reversed"
        if "success" in kind:
            return "bold green"
        if "search" in kind:
            return "bold blue"
        if "tool" in kind:
            return "magenta"
        return "white"

    async def _tail_log(self) -> None:
        log_path = get_log_path()
        if not log_path.exists():
            return

        with open(log_path, encoding="utf-8", errors="replace") as f:
            f.seek(0, 2)
            while True:
                line = f.readline()
                if line:
                    event = parse_log_event(line)
                    if event and filter_event(
                        event,
                        enabled_kinds=None,  # Tail everything, dispatch decides where it goes
                        time_start=self._time_start,
                        time_end=None,  # No upper bound for live tailing
                    ):
                        self._dispatch_event(event)

                        # If current view is a RichLog, maybe scroll to end?
                        # RichLog usually auto-scrolls if at bottom.
                else:
                    await asyncio.sleep(0.2)

    def on_filter_changed(self, message: FilterChanged) -> None:
        self._enabled_kinds = message.enabled_kinds

        # Switch view based on persistent widgets
        from .log_reader import APPLY_KINDS, SEARCH_KINDS

        switcher = self.query_one(ContentSwitcher)

        if self._enabled_kinds == SEARCH_KINDS:
            switcher.current = "tree-search"
        elif self._enabled_kinds == APPLY_KINDS:
            switcher.current = "log-apply"
        elif self._enabled_kinds == {"apply_error", "search_error"}:
            switcher.current = "log-errors"
        else:
            # Default to All
            switcher.current = "log-all"

        # IMPORTANT: Do NOT call action_reload() here.
        # Just switching the view is instant because background updates keep them fresh.

    def on_time_range_changed(self, message: TimeRangeChanged) -> None:
        self._time_start = message.start
        self._time_end = message.end

        # Show a momentary notification
        from .log_reader import get_time_presets

        # Find which key matches this range (reverse lookup)
        presets = get_time_presets()
        label = "Custom"
        for k, (s, _) in presets.items():
            # Approximate match for start time (within 1s)
            if abs((s - message.start).total_seconds()) < 5:
                label = k
                break

        self.notify(f"Time Filter set to: {label}", title="Time Range", severity="information")
        self.action_reload()

    def action_reload(self) -> None:
        self._load_initial_events()

    def action_filter(self, filter_type: str) -> None:
        header = self.query_one("#header", CompactHeader)
        header.set_filter_by_key(filter_type)

    def action_toggle_time(self) -> None:
        # Trigger the button click programmatically or find button and call cycle
        # Just find the button
        from .widgets import TimeCycleButton

        btn = self.query_one(TimeCycleButton)
        btn.cycle()

    async def action_quit(self) -> None:
        if self._tail_task:
            self._tail_task.cancel()
        self.exit()


def main() -> None:
    try:
        import importlib.util

        if importlib.util.find_spec("textual") is None:
            raise ImportError("textual not found")
    except ImportError:
        print("Error: textual is not installed.")
        print("Install with: pip install relace-mcp[tools]")
        raise SystemExit(1) from None

    app = LogViewerApp()
    app.run()


if __name__ == "__main__":
    main()
