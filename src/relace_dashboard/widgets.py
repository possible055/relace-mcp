from datetime import datetime
from typing import Any

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.message import Message
from textual.reactive import reactive
from textual.widgets import Button, Static, Tree
from textual.widgets.tree import TreeNode

from .log_reader import (
    ALL_KINDS,
    APPLY_KINDS,
    SEARCH_KINDS,
    get_aggregated_tool_stats,
    get_time_presets,
)

TOOL_ABBREVIATIONS = {
    "grep_search": "grep",
    "view_file": "read",
    "fast_apply": "apply",
    "report_back": "rep",
    "find_symbol": "sym",
    "view_directory": "ls",
    "glob": "glob",
    "bash": "bash",
    "read_resource": "res",
    "cloud_search": "search",
    "cloud_list": "list",
    "cloud_info": "info",
    "cloud_sync": "sync",
    "cloud_clear": "clear",
}


class ToggleInsightsFailed(Message):
    def __init__(self, include_failed: bool) -> None:
        super().__init__()
        self.include_failed = include_failed


class SearchTree(Tree[dict[str, Any]]):
    """A tree view for search sessions."""

    MAX_SESSIONS = 200  # Optimization: only keep last 200 sessions

    def __init__(self, **kwargs: Any) -> None:
        super().__init__("Search Sessions", **kwargs)
        self.show_root = False
        self.root.expand()
        self._current_session: TreeNode[dict[str, Any]] | None = None
        self._current_turn: TreeNode[dict[str, Any]] | None = None
        self._session_total_tokens: int = 0
        self._session_total_tools: int = 0

    def clear(self) -> "SearchTree":
        self.root.remove_children()
        self._current_session = None
        self._current_turn = None
        self._session_total_tokens = 0
        self._session_total_tools = 0
        return self

    def add_events(self, events: list[dict[str, Any]]) -> None:
        for event in events:
            self.add_event(event)

    def add_event(self, event: dict[str, Any]) -> None:
        kind = event.get("kind", "")

        if kind == "search_start":
            query = event.get("query_preview", "Unknown Query")
            ts = event.get("timestamp", "")[11:19]

            # Short preview for header
            # header_query = query[:30] + "..." if len(query) > 30 else query
            # label = f"[{ts}] {header_query}"

            # Remove query from header (User request)
            label = f"[{ts}]"

            # Optimization: prune old sessions
            children = self.root.children
            if len(children) >= self.MAX_SESSIONS:
                # Remove first child (oldest)
                children[0].remove()

            # Auto-expand sessions by default (treating as a log stream)
            self._current_session = self.root.add(label, data=event, expand=False)

            # Add full query as the first child node (User request: move content inside)
            # Make it a leaf node (allow_expand=False) so it looks like text, not a folder
            q_node = self._current_session.add(f"[bold]Query:[/bold] {query}", expand=False)
            q_node.allow_expand = False

            self._current_turn = None
            self._session_total_tokens = 0
            self._session_total_tools = 0

        elif kind == "search_turn":
            if not self._current_session:
                return

            turn = event.get("turn", 0)
            max_turns = event.get("max_turns", 1)

            # Calculate and accumulate tokens for this turn
            turn_tokens = 0
            if "total_tokens" in event:
                turn_tokens = event["total_tokens"]
            elif "prompt_tokens" in event:
                turn_tokens = event["prompt_tokens"] + event.get("completion_tokens", 0)
            elif "prompt_tokens_est" in event:
                turn_tokens = event["prompt_tokens_est"]

            self._session_total_tokens += turn_tokens

            # Update Session Label with running stats
            tok_str = (
                f"{self._session_total_tokens / 1000.0:.1f}k"
                if self._session_total_tokens >= 1000
                else f"{self._session_total_tokens}"
            )
            start_event = self._current_session.data
            if start_event:
                s_ts = start_event.get("timestamp", "")[11:19]
                # s_query = start_event.get("query_preview", "")
                # header_query = s_query[:30] + "..." if len(s_query) > 30 else s_query

                # Label: [12:34] (Turn: 1, Tools: 5, Tok: 1.2k)
                self._current_session.label = f"[{s_ts}] [dim](Turn: {turn}, Tools: {self._session_total_tools}, Tok: {tok_str})[/]"

            # Initial progress bar (empty, width 8)
            width = 8
            bar = f"[[cadet_blue][/][dim]{'░' * width}[/]]"

            # Extract time and token info
            tok_info = ""
            if "total_tokens" in event:
                tok = event["total_tokens"]
                tok_info = f" [dim]({tok} tok)[/]"
            elif "prompt_tokens" in event:
                tok = event["prompt_tokens"]
                tok_info = f" [dim]({tok} p_tok)[/]"
            elif "prompt_tokens_est" in event:
                tok = event["prompt_tokens_est"]
                tok_info = f" [dim]({tok} est_tok)[/]"

            latency_info = ""
            if "llm_latency_ms" in event:
                lat = event["llm_latency_ms"]
                latency_info = f" [dim]({lat / 1000.0:.1f}s)[/]"

            label = f"{bar} Turn {turn}/{max_turns}{tok_info}{latency_info}"

            # Auto-expand turns by default to show tool calls
            self._current_turn = self._current_session.add(label, data=event, expand=False)

        elif kind == "tool_call":
            parent = self._current_turn or self._current_session
            if not parent:
                return  # Orphan tool call

            tool = event.get("tool_name", "unknown")
            success = event.get("success", True)

            # Hide failed tool calls from Search view (User request)
            if not success:
                return

            # Increment tools count
            self._session_total_tools += 1

            latency = event.get("latency_ms", 0)

            # Color coding for tools
            style = self._get_tool_style(tool)
            # success is always True here

            status = "✓"
            latency_str = f" [dim]({latency / 1000.0:.2f}s)[/]" if latency else ""

            label = f"[{style}]{tool}[/] {status}{latency_str}"
            parent.add(label, data=event, allow_expand=False)

            # Dynamic Update: Update parent turn's progress bar (Tool Count)
            if (
                parent == self._current_turn
                and parent.data
                and parent.data.get("kind") == "search_turn"
            ):
                count = len(parent.children)
                # Logic: Base width 8. If count > 8, bar expands automatically.
                # e.g. 1 -> [█░░░░░░░]
                # e.g. 9 -> [█████████]
                width = max(8, count)
                filled = count

                bar_inner = "█" * filled
                padding = "░" * (width - filled)
                bar = f"[[cadet_blue]{bar_inner}[/][dim]{padding}[/]]"

                # Retrieve original turn info
                t_val = parent.data.get("turn", "?")
                m_val = parent.data.get("max_turns", "?")

                # Reconstruct extra info (ts, tok, lat) from parent data
                # ts = parent.data.get("timestamp", "")[11:19] # Removed per user request

                tok_info = ""
                if "total_tokens" in parent.data:
                    tok = parent.data["total_tokens"]
                    tok_info = f" [dim]({tok} tok)[/]"
                elif "prompt_tokens" in parent.data:
                    tok = parent.data["prompt_tokens"]
                    tok_info = f" [dim]({tok} p_tok)[/]"
                elif "prompt_tokens_est" in parent.data:
                    tok = parent.data["prompt_tokens_est"]
                    tok_info = f" [dim]({tok} est_tok)[/]"

                latency_info = ""
                if "llm_latency_ms" in parent.data:
                    lat = parent.data["llm_latency_ms"]
                    latency_info = f" [dim]({lat / 1000.0:.1f}s)[/]"

                parent.label = f"{bar} Turn {t_val}/{m_val}{tok_info}{latency_info}"

        elif kind == "search_complete":
            if self._current_session and self._current_session.data:
                # Retrieve original info from start event to ensure clean reconstruction
                start_event = self._current_session.data
                s_ts = start_event.get("timestamp", "")[11:19]
                # s_query = start_event.get("query_preview", "")

                # Truncate query strictly for header
                # header_query = s_query[:30] + "..." if len(s_query) > 30 else s_query

                # Format total tokens
                tok_val = self._session_total_tokens
                tok_str = f"{tok_val / 1000.0:.1f}k" if tok_val >= 1000 else f"{tok_val}"

                files = event.get("files_found", 0)
                turns = event.get("turns_used", "?")

                # Format total latency
                total_ms = event.get("total_latency_ms", 0)
                time_str = f"{total_ms / 1000.0:.1f}s" if total_ms else ""

                # Final label: [12:34:56] (Turns: Y, Tools: Z, Tok: 12k, Files: X, Time: 3.5s)
                time_part = f", Time: {time_str}" if time_str else ""
                self._current_session.label = f"[{s_ts}] [green](Turns: {turns}, Tools: {self._session_total_tools}, Tok: {tok_str}, Files: {files}{time_part})[/]"

        elif kind == "search_error":
            # If a session ends in error, we might want to hide it completely from the Search view
            # if the user considers it "garbage". Alternatively, just ensure the (Error) text
            # is not appended if we strictly follow "only success logs".
            # The current logic just passes, meaning the session REMAINS in the tree,
            # but without any "Error" label update.
            # If the user wants to REMOVE the session because it failed:
            if self._current_session:
                self._current_session.remove()
                self._current_session = None
                self._current_turn = None

    def _get_tool_style(self, tool: str) -> str:
        palette = [
            "#ff7675",
            "#fab1a0",
            "#ffeaa7",
            "#55efc4",
            "#81ecec",
            "#74b9ff",
            "#a29bfe",
            "#fd79a8",
            "#fdcb6e",
            "#e17055",
            "#00b894",
            "#00cec9",
            "#0984e3",
            "#6c5ce7",
            "#e84393",
        ]
        import hashlib

        idx = int(hashlib.md5(tool.encode(), usedforsecurity=False).hexdigest(), 16) % len(palette)
        return palette[idx]


class InsightsTree(Tree[dict[str, Any]]):
    """A tree view for tool call frequency insights."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__("Insights", **kwargs)
        self.show_root = False
        self.root.expand()

    def clear(self) -> "InsightsTree":
        self.root.remove_children()
        return self

    def update_stats(self, events: list[dict[str, Any]], include_failed: bool = True) -> None:
        """Process last 100 tool calls and update the aggregated tree."""
        self.clear()
        stats = get_aggregated_tool_stats(events, max_tool_calls=100, include_failed=include_failed)

        # 1. Add Legend (Use all tools in events for a stable list)
        legend_node = self.root.add("[bold underline]Tool Legend[/]", expand=True)
        all_tools = set()
        for e in events:
            if e.get("kind") == "tool_call":
                all_tools.add(e.get("tool_name", "unknown"))

        for tool in sorted(all_tools):
            style = self._get_tool_style(tool)
            abbr = TOOL_ABBREVIATIONS.get(tool, tool)
            legend_node.add(f"[{style}]█[/] {abbr} [dim]({tool})[/]", allow_expand=False)

        # 2. Add Aggregated Turns
        BAR_TOTAL_WIDTH = 30
        for turn_data in stats:
            turn_num = turn_data["turn"]
            tool_counts = turn_data["tools"]
            total_in_turn = sum(tool_counts.values())

            # Build the bar cells (30 units total)
            cells = []
            sorted_tools = sorted(tool_counts.items(), key=lambda x: x[1], reverse=True)
            remaining_width = BAR_TOTAL_WIDTH
            for i, (tool, count) in enumerate(sorted_tools):
                style = self._get_tool_style(tool)
                pct = count / total_in_turn
                part_width = round(pct * BAR_TOTAL_WIDTH) if total_in_turn > 0 else 0

                if i == len(sorted_tools) - 1:
                    part_width = max(0, remaining_width)
                else:
                    part_width = min(part_width, remaining_width)

                remaining_width -= part_width
                for _ in range(part_width):
                    cells.append(f"[{style}]█[/]")

            # Ensure we have exactly BAR_TOTAL_WIDTH characters
            while len(cells) < BAR_TOTAL_WIDTH:
                cells.append("[dim]░[/]")

            bar_str = "".join(cells)

            # Add small color block indicators to the text labels on the right
            abbr_list = []
            for tool, count in sorted_tools:
                style = self._get_tool_style(tool)
                pct = (count / total_in_turn) * 100
                abbr = TOOL_ABBREVIATIONS.get(tool, tool)
                abbr_list.append(f"[{style}]■[/] {pct:.0f}% {abbr}")

            details_str = ", ".join(abbr_list)

            turn_label = f"Turn {turn_num} [[white]{bar_str}[/]] [dim]({details_str})[/]"
            turn_node = self.root.add(turn_label, expand=False)
            turn_node.allow_expand = False

    def _get_tool_style(self, tool: str) -> str:
        palette = [
            "#ff7675",
            "#fab1a0",
            "#ffeaa7",
            "#55efc4",
            "#81ecec",
            "#74b9ff",
            "#a29bfe",
            "#fd79a8",
            "#fdcb6e",
            "#e17055",
            "#00b894",
            "#00cec9",
            "#0984e3",
            "#6c5ce7",
            "#e84393",
        ]
        import hashlib

        # Deterministic color based on name
        idx = int(hashlib.md5(tool.encode(), usedforsecurity=False).hexdigest(), 16) % len(palette)
        return palette[idx]


class TimeCycleButton(Button):
    """A button that cycles through time ranges."""

    def __init__(self) -> None:
        super().__init__()
        self.presets = get_time_presets()
        self.keys_list = list(self.presets.keys())
        self.current_idx = self.keys_list.index("24h") if "24h" in self.keys_list else 0
        self.update_label()

    def update_label(self) -> None:
        key = self.keys_list[self.current_idx]
        self.label = f"Time: {key}"

    def on_click(self) -> None:
        self.cycle()

    def cycle(self) -> None:
        self.current_idx = (self.current_idx + 1) % len(self.keys_list)
        self.update_label()
        key = self.keys_list[self.current_idx]
        # Get fresh presets so time is relative to now
        current_presets = get_time_presets()
        start, end = current_presets[key]
        self.post_message(TimeRangeChanged(start, end))


class FilterButton(Button):
    """A compact filter tab button."""

    DEFAULT_CSS = """
    FilterButton {
        width: auto;
        height: 1;
        padding: 0 3;
        margin: 0 1;
        border: none;
        background: $surface;
        color: $text-muted;
        content-align: center middle;
        text-align: center;
    }
    FilterButton:hover {
        background: $surface-lighten-1;
        color: $text;
    }
    FilterButton.active {
        background: $primary;
        color: black;
        text-style: bold;
    }
    """


class CompactHeader(Static):
    """Compact header looking like top tabs."""

    DEFAULT_CSS = """
    CompactHeader {
        height: 1;
        background: $surface;
        layout: horizontal;
    }
    CompactHeader > Horizontal {
        height: 1;
        width: 100%;
    }
    .spacer {
        width: 1fr;
    }
    #stats-label {
        color: $success;
        margin: 0 1;
        height: 1;
    }
    """

    stats_text = reactive("")

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._enabled_kinds = set(ALL_KINDS)

    def compose(self) -> ComposeResult:
        with Horizontal():
            yield FilterButton("All", id="filter-all", classes="active")
            yield FilterButton("Apply", id="filter-apply")
            yield FilterButton("Search", id="filter-search")
            yield FilterButton("Insights", id="filter-insights")
            yield FilterButton("Errors", id="filter-errors")
            yield Static(" ", classes="spacer")
            yield Static("", id="stats-label")
            yield Static("[dim]│ [/]")
            yield TimeCycleButton()

    def watch_stats_text(self, value: str) -> None:
        try:
            self.query_one("#stats-label", Static).update(value)
        except Exception:  # noqa: BLE001  # nosec B110
            pass  # Widget not yet mounted

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if isinstance(event.button, TimeCycleButton):
            return  # Handled by the button itself

        button_id = event.button.id or ""

        if not button_id.startswith("filter-"):
            return

        filter_type = button_id.replace("filter-", "")
        self._set_filter(filter_type)

    def _set_filter(self, filter_type: str) -> None:
        # Update button styles
        for btn in self.query(FilterButton):
            btn.remove_class("active")
            if btn.id == f"filter-{filter_type}":
                btn.add_class("active")

        # Update enabled kinds
        if filter_type == "all":
            self._enabled_kinds = set(ALL_KINDS)
        elif filter_type == "apply":
            self._enabled_kinds = set(APPLY_KINDS)
        elif filter_type == "search":
            self._enabled_kinds = set(SEARCH_KINDS)
        elif filter_type == "insights":
            from .log_reader import INSIGHTS_KINDS

            self._enabled_kinds = set(INSIGHTS_KINDS)
        elif filter_type == "errors":
            self._enabled_kinds = {"apply_error", "search_error"}

        self.post_message(FilterChanged(self._enabled_kinds.copy()))

    def set_filter_by_key(self, filter_type: str) -> None:
        self._set_filter(filter_type)


class FilterChanged(Message):
    def __init__(self, enabled_kinds: set[str]) -> None:
        super().__init__()
        self.enabled_kinds = enabled_kinds


class TimeRangeChanged(Message):
    def __init__(self, start: datetime, end: datetime) -> None:
        super().__init__()
        self.start = start
        self.end = end
