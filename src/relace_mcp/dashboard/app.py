import asyncio
from collections import deque
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import Button, ContentSwitcher, Footer, RichLog, Static

from .log_reader import (
    ALL_KINDS,
    filter_event,
    get_log_path,
    parse_log_event,
)
from .widgets import (
    CompactHeader,
    FilterChanged,
    InsightsTree,
    SearchTree,
    TimeRangeChanged,
    ToggleInsightsFailed,
)


class LogViewerApp(App[None]):  # type: ignore[misc]
    TITLE = "Relace MCP"
    CSS_PATH = "styles.tcss"
    ENABLE_COMMAND_PALETTE = False

    FLUSH_INTERVAL_S = 0.05
    MAX_FLUSH_LOG_EVENTS = 250
    MAX_FLUSH_TREE_EVENTS = 100
    TAIL_YIELD_EVERY = 200

    BINDINGS = [
        # Main actions
        Binding("q", "quit", "Quit"),
        Binding("r", "reload", "Reload"),
        # Nav shortcuts (vim style + arrow keys)
        Binding("left,h", "prev_tab", "Prev Tab"),
        Binding("right,l", "next_tab", "Next Tab"),
        # Time shortcuts
        Binding("t", "toggle_time", "Time"),
    ]

    _TAB_ORDER = ["all", "apply", "search", "insights", "errors"]
    _TAB_ID_MAP = {
        "log-all": "all",
        "log-apply": "apply",
        "tree-search": "search",
        "tree-insights": "insights",
        "log-errors": "errors",
    }

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._enabled_kinds: set[str] = set(ALL_KINDS)
        self._time_start: datetime = datetime.now(UTC) - timedelta(hours=24)
        self._time_end: datetime = datetime.now(UTC)
        self._tail_task: asyncio.Task[None] | None = None
        self._flush_timer = None

        # Pending (unrendered) events per view. This decouples file tailing from UI rendering
        # so tab switches remain responsive under heavy log volume.
        self._pending: dict[str, deque[dict[str, Any]]] = {
            "log-all": deque(),
            "log-apply": deque(),
            "tree-search": deque(),
            "tree-insights": deque(),
            "log-errors": deque(),
        }

        # Lightweight stats updated incrementally as events are routed.
        self._stats_total = 0
        self._stats_apply_success = 0
        self._stats_search_complete = 0
        self._stats_dirty = True

        self._insights_include_failed = True

        # When reloading, pause tailing to avoid interleaving/duplicates.
        self._reload_in_progress = False

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

            # 4. INSIGHTS TREE (Persistent)
            from textual.containers import Horizontal, Vertical
            from textual.widgets import Button

            with Vertical(id="tree-insights"):
                with Horizontal(classes="insights-toolbar"):
                    yield Button("[green]✓[/] Show Failed", id="toggle-failed", classes="active")
                    yield Static(" ", classes="spacer")
                yield InsightsTree(id="insights-widget")

            # 5. ERRORS LOGS (Persistent)
            yield RichLog(
                highlight=True,
                markup=True,
                id="log-errors",
                max_lines=10000,
                wrap=True,
            )
        yield Footer()

    async def on_mount(self) -> None:
        self._flush_timer = self.set_interval(self.FLUSH_INTERVAL_S, self._flush_pending)
        await self.action_reload()  # Load initial data to all 4 widgets
        self._tail_task = asyncio.create_task(self._tail_log())

    def _reset_view_state(self) -> None:
        for pending in self._pending.values():
            pending.clear()

        self._stats_total = 0
        self._stats_apply_success = 0
        self._stats_search_complete = 0
        self._stats_dirty = True

        # Clear all widgets (views are persistent but should reset on reload)
        self.query_one("#log-all", RichLog).clear()
        self.query_one("#log-apply", RichLog).clear()
        self.query_one("#tree-search", SearchTree).clear()
        self.query_one("#insights-widget", InsightsTree).clear()
        self.query_one("#log-errors", RichLog).clear()

    def _route_event(self, event: dict[str, Any]) -> None:
        """Route a single event into pending buffers (rendered later in batches)."""
        kind = event.get("kind", "")

        # Stats
        self._stats_total += 1
        if kind == "apply_success":
            self._stats_apply_success += 1
        elif kind == "search_complete":
            self._stats_search_complete += 1
        self._stats_dirty = True

        # 1. To 'All' (Always)
        self._pending["log-all"].append(event)

        # 2. To 'Apply'
        from .log_reader import APPLY_KINDS, SEARCH_KINDS

        if kind in APPLY_KINDS:
            self._pending["log-apply"].append(event)

        # 3. To 'Search' (Tree)
        # Note: SEARCH_KINDS includes search_start/turn/tool/complete/error
        if kind in SEARCH_KINDS:
            self._pending["tree-search"].append(event)

        # 4. To 'Insights'
        from .log_reader import INSIGHTS_KINDS

        if kind in INSIGHTS_KINDS:
            self._pending["tree-insights"].append(event)

        # 5. To 'Errors'
        if "error" in kind:
            self._pending["log-errors"].append(event)

    def _update_stats(self) -> None:
        total = self._stats_total
        apply_ok = self._stats_apply_success
        search_ok = self._stats_search_complete
        header = self.query_one("#header", CompactHeader)
        header.stats_text = f"Total: {total} | Apply: {apply_ok}✓ | Search: {search_ok}✓"

    def _format_event(self, event: dict[str, Any]) -> Text:
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

        return line

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

    async def _flush_pending(self) -> None:
        # Update header stats at most once per tick.
        if self._stats_dirty:
            self._update_stats()
            self._stats_dirty = False

        switcher = self.query_one(ContentSwitcher)
        current = switcher.current

        # Render only the active view each tick to keep tab switches smooth.
        if current in ("log-all", "log-apply", "log-errors"):
            log_widget = self.query_one(f"#{current}", RichLog)
            pending = self._pending[current]
            if not pending:
                return

            width = log_widget.scrollable_content_region.width or log_widget.size.width
            if width <= 0:
                return

            to_flush = min(self.MAX_FLUSH_LOG_EVENTS, len(pending))
            if to_flush <= 0:
                return

            with self.batch_update():
                for i in range(to_flush):
                    event = pending.popleft()
                    scroll_end = None if i == to_flush - 1 else False
                    log_widget.write(
                        self._format_event(event),
                        width=width,
                        scroll_end=scroll_end,
                    )

        elif current == "tree-search":
            tree = self.query_one("#tree-search", SearchTree)
            pending = self._pending["tree-search"]
            if not pending:
                return

            to_flush = min(self.MAX_FLUSH_TREE_EVENTS, len(pending))
            if to_flush <= 0:
                return

            with self.batch_update():
                for _ in range(to_flush):
                    tree.add_event(pending.popleft())

        elif current == "tree-insights":
            tree = self.query_one("#insights-widget", InsightsTree)
            pending = self._pending["tree-insights"]
            if not pending:
                return

            # Insights is a bit different: it re-renders the whole tree based on session state
            # but for consistency with others we'll drain the queue.
            # However, get_tool_turn_stats needs ALL relevant events to compute accurately.
            # So here we'll just clear the queue and trigger a full refresh of the insight tree
            # using the data we already have if needed, but actually the app's _route_event
            # just feeds events.
            # Let's simplify: drain the queue into a local cache if needed, but InsightsTree.update_stats
            # actually takes a list of events.
            # For now, let's just trigger update_stats if we have NEW events.
            has_new = False
            while pending:
                pending.popleft()
                has_new = True

            if has_new:
                # We need all events matching INSIGHTS_KINDS.
                # Easiest way? Fetch from log_reader (re-reading) or keep a local buffer?
                # The app doesn't keep a global list of all events, only deques for widgets.
                # This is a bit tricky with the current architecture.
                # Let's fix this by having action_reload and tail accumulate events for insights.
                # Actually, the most efficient way for Insights is to just re-read the last 100 tool calls.
                from .log_reader import INSIGHTS_KINDS, read_log_events

                events = read_log_events(enabled_kinds=set(INSIGHTS_KINDS), max_events=1000)
                tree.update_stats(events, include_failed=self._insights_include_failed)

    async def _tail_log(self) -> None:
        log_path = get_log_path()
        if not log_path.exists():
            return

        with open(log_path, encoding="utf-8", errors="replace") as f:
            f.seek(0, 2)
            processed = 0
            while True:
                if self._reload_in_progress:
                    await asyncio.sleep(0.1)
                    continue

                line = f.readline()
                if line:
                    event = parse_log_event(line)
                    if event and filter_event(
                        event,
                        enabled_kinds=None,  # Tail everything, dispatch decides where it goes
                        time_start=self._time_start,
                        time_end=None,  # No upper bound for live tailing
                    ):
                        self._route_event(event)
                        processed += 1
                        if processed >= self.TAIL_YIELD_EVERY:
                            processed = 0
                            await asyncio.sleep(0)

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
        elif self._enabled_kinds == {"search_start", "search_turn", "tool_call"}:  # INSIGHTS_KINDS
            switcher.current = "tree-insights"
        elif self._enabled_kinds == {"apply_error", "search_error"}:
            switcher.current = "log-errors"
        else:
            # Default to All
            switcher.current = "log-all"

        # IMPORTANT: Do NOT call action_reload() here.
        # Just switching the view is instant because background updates keep them fresh.

    async def on_time_range_changed(self, message: TimeRangeChanged) -> None:
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
        await self.action_reload()

    def on_toggle_insights_failed(self, message: ToggleInsightsFailed) -> None:
        self._insights_include_failed = message.include_failed
        # Trigger refresh of insights tree
        tree = self.query_one("#insights-widget", InsightsTree)
        from .log_reader import INSIGHTS_KINDS, read_log_events

        events = read_log_events(enabled_kinds=set(INSIGHTS_KINDS), max_events=1000)
        tree.update_stats(events, include_failed=self._insights_include_failed)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "toggle-failed":
            btn = event.button
            if "active" in btn.classes:
                btn.remove_class("active")
                btn.label = "[ ] Show Failed"
                self.post_message(ToggleInsightsFailed(False))
            else:
                btn.add_class("active")
                btn.label = "[green]✓[/] Show Failed"
                self.post_message(ToggleInsightsFailed(True))

    async def action_reload(self) -> None:
        self._reload_in_progress = True
        try:
            self._reset_view_state()

            log_path = get_log_path()
            if not log_path.exists():
                return

            # Snapshot size to avoid duplicating lines written while reloading (tail will pick them up).
            snapshot_size = log_path.stat().st_size
            bytes_read = 0
            matched = 0

            # Stream + yield so the UI can keep responding while loading lots of events.
            with open(log_path, "rb") as f:
                while bytes_read < snapshot_size and matched < 1_000_000:
                    line_bytes = f.readline()
                    if not line_bytes:
                        break
                    bytes_read += len(line_bytes)

                    line = line_bytes.decode("utf-8", errors="replace")
                    event = parse_log_event(line)
                    if event and filter_event(
                        event,
                        enabled_kinds=None,
                        time_start=self._time_start,
                        time_end=self._time_end,
                    ):
                        self._route_event(event)
                        matched += 1
                        if matched % 5000 == 0:
                            await asyncio.sleep(0)
        finally:
            self._reload_in_progress = False

    def action_filter(self, filter_type: str) -> None:
        header = self.query_one("#header", CompactHeader)
        header.set_filter_by_key(filter_type)

    def action_next_tab(self) -> None:
        self._cycle_tab(1)

    def action_prev_tab(self) -> None:
        self._cycle_tab(-1)

    def _cycle_tab(self, delta: int) -> None:
        switcher = self.query_one(ContentSwitcher)
        current_id = switcher.current or "log-all"
        current_type = self._TAB_ID_MAP.get(current_id, "all")

        try:
            idx = self._TAB_ORDER.index(current_type)
        except ValueError:
            idx = 0

        new_idx = (idx + delta) % len(self._TAB_ORDER)
        new_type = self._TAB_ORDER[new_idx]
        self.action_filter(new_type)

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
