import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class TraceAnalysis:
    case_id: str
    total_turns: int
    report_back_on_last_turn: bool
    report_back_turn: int | None
    tool_calls_per_turn: list[int]
    tool_frequency_trend: str
    view_directory_in_first_turn: bool
    zero_tool_call_turns: list[int]
    has_failed_tool_calls: bool
    failed_tool_calls: list[dict[str, Any]] = field(default_factory=list)


def _classify_trend(counts: list[int]) -> str:
    if len(counts) <= 1:
        return "flat"
    diffs = [counts[i + 1] - counts[i] for i in range(len(counts) - 1)]
    neg = sum(1 for d in diffs if d < 0)
    pos = sum(1 for d in diffs if d > 0)
    total = len(diffs)
    if all(d == 0 for d in diffs):
        return "flat"
    if neg / total >= 0.7:
        return "decreasing"
    if pos / total >= 0.7:
        return "increasing"
    return "irregular"


def analyze_single_trace(trace_path: Path) -> TraceAnalysis:
    """Analyze a single case trace JSONL file.

    Args:
        trace_path: Path to a .jsonl trace file (one JSON object per turn).

    Returns:
        TraceAnalysis with all 5 behavioral metrics.
    """
    case_id = trace_path.stem
    turns: list[dict[str, Any]] = []
    with trace_path.open("r", encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            if stripped:
                turns.append(json.loads(stripped))

    if not turns:
        return TraceAnalysis(
            case_id=case_id,
            total_turns=0,
            report_back_on_last_turn=False,
            report_back_turn=None,
            tool_calls_per_turn=[],
            tool_frequency_trend="flat",
            view_directory_in_first_turn=False,
            zero_tool_call_turns=[],
            has_failed_tool_calls=False,
        )

    total_turns = len(turns)

    # Q1: report_back position
    report_back_turn: int | None = None
    for t in turns:
        if t.get("report_back") is not None:
            report_back_turn = t["turn"]
            break
    report_back_on_last_turn = report_back_turn == total_turns

    # Q2: tool calls per turn frequency & trend
    tool_calls_per_turn: list[int] = []
    for t in turns:
        tool_results = t.get("tool_results", [])
        tool_calls_per_turn.append(len(tool_results))
    # Exclude the last turn if it's only report_back for trend analysis
    trend_counts = tool_calls_per_turn
    if report_back_turn == total_turns and len(tool_calls_per_turn) > 1:
        trend_counts = tool_calls_per_turn[:-1]
    tool_frequency_trend = _classify_trend(trend_counts)

    # Q3: view_directory in first turn
    view_directory_in_first_turn = False
    if turns:
        first_turn_results = turns[0].get("tool_results", [])
        for tr in first_turn_results:
            if tr.get("name") == "view_directory":
                view_directory_in_first_turn = True
                break

    # Q4: zero tool call turns
    zero_tool_call_turns: list[int] = []
    for i, count in enumerate(tool_calls_per_turn):
        if count == 0:
            zero_tool_call_turns.append(i + 1)

    # Q5: failed tool calls
    failed_tool_calls: list[dict[str, Any]] = []
    for t in turns:
        for tr in t.get("tool_results", []):
            result = tr.get("result", "")
            is_failed = isinstance(result, str) and result.startswith("Error:")
            if is_failed:
                failed_tool_calls.append(
                    {
                        "turn": t["turn"],
                        "name": tr.get("name", ""),
                        "error_preview": result[:200] if isinstance(result, str) else "",
                    }
                )

    return TraceAnalysis(
        case_id=case_id,
        total_turns=total_turns,
        report_back_on_last_turn=report_back_on_last_turn,
        report_back_turn=report_back_turn,
        tool_calls_per_turn=tool_calls_per_turn,
        tool_frequency_trend=tool_frequency_trend,
        view_directory_in_first_turn=view_directory_in_first_turn,
        zero_tool_call_turns=zero_tool_call_turns,
        has_failed_tool_calls=len(failed_tool_calls) > 0,
        failed_tool_calls=failed_tool_calls,
    )


def analyze_batch(traces_dir: Path) -> list[TraceAnalysis]:
    """Analyze all trace files in a directory.

    Args:
        traces_dir: Directory containing .jsonl trace files.

    Returns:
        List of TraceAnalysis, one per case.
    """
    results: list[TraceAnalysis] = []
    trace_files = sorted(traces_dir.glob("*.jsonl"))
    for trace_path in trace_files:
        results.append(analyze_single_trace(trace_path))
    return results


def aggregate_summary(analyses: list[TraceAnalysis]) -> dict[str, Any]:
    """Compute aggregate statistics across all analyses.

    Args:
        analyses: List of per-case TraceAnalysis.

    Returns:
        Summary dict with counts and percentages for each question.
    """
    n = len(analyses)
    if n == 0:
        return {"total_cases": 0}

    # Q1
    rb_last = sum(1 for a in analyses if a.report_back_on_last_turn)
    rb_none = sum(1 for a in analyses if a.report_back_turn is None)

    # Q2
    from collections import Counter

    trend_counts = Counter(a.tool_frequency_trend for a in analyses)
    # Average tool calls per turn position
    max_turns = max(a.total_turns for a in analyses)
    avg_per_position: list[float] = []
    for pos in range(max_turns):
        values = [a.tool_calls_per_turn[pos] for a in analyses if pos < len(a.tool_calls_per_turn)]
        avg_per_position.append(sum(values) / len(values) if values else 0.0)

    # Q3
    vd_first = sum(1 for a in analyses if a.view_directory_in_first_turn)

    # Q4
    has_zero = sum(1 for a in analyses if a.zero_tool_call_turns)
    all_zero_turns: list[int] = []
    for a in analyses:
        all_zero_turns.extend(a.zero_tool_call_turns)

    # Q5
    has_failed = sum(1 for a in analyses if a.has_failed_tool_calls)
    failed_tool_counter: Counter[str] = Counter()
    for a in analyses:
        for fc in a.failed_tool_calls:
            failed_tool_counter[fc["name"]] += 1

    return {
        "total_cases": n,
        "q1_report_back_last_turn": rb_last,
        "q1_report_back_last_turn_pct": rb_last / n,
        "q1_no_report_back": rb_none,
        "q2_trend_counts": dict(trend_counts),
        "q2_avg_tool_calls_per_position": [round(v, 1) for v in avg_per_position],
        "q3_view_directory_first_turn": vd_first,
        "q3_view_directory_first_turn_pct": vd_first / n,
        "q4_has_zero_tool_call_turns": has_zero,
        "q4_has_zero_tool_call_turns_pct": has_zero / n,
        "q4_zero_turn_positions": sorted(set(all_zero_turns)),
        "q5_has_failed_tool_calls": has_failed,
        "q5_has_failed_tool_calls_pct": has_failed / n,
        "q5_top_failed_tools": failed_tool_counter.most_common(10),
    }


def format_report(analyses: list[TraceAnalysis]) -> str:
    """Generate a human-readable report from trace analyses.

    Args:
        analyses: List of per-case TraceAnalysis.

    Returns:
        Formatted report string.
    """
    summary = aggregate_summary(analyses)
    n = summary["total_cases"]
    if n == 0:
        return "No trace data found."

    lines: list[str] = []
    lines.append("=" * 58)
    lines.append(f"TRACE ANALYSIS REPORT ({n} cases)")
    lines.append("=" * 58)

    # Q1
    rb_last = summary["q1_report_back_last_turn"]
    rb_none = summary["q1_no_report_back"]
    lines.append("")
    lines.append("Q1: report_back 位置")
    lines.append(f"  最後一輪 report_back: {rb_last}/{n} ({rb_last / n:.1%})")
    lines.append(
        f"  非最後一輪:            {n - rb_last - rb_none}/{n} ({(n - rb_last - rb_none) / n:.1%})"
    )
    if rb_none:
        lines.append(f"  無 report_back:        {rb_none}/{n} ({rb_none / n:.1%})")

    # Q2
    lines.append("")
    lines.append("Q2: 工具調用頻率趨勢")
    for trend, count in sorted(summary["q2_trend_counts"].items(), key=lambda x: -x[1]):
        lines.append(f"  {trend:20s}: {count}/{n} ({count / n:.1%})")
    avg_positions = summary["q2_avg_tool_calls_per_position"]
    if avg_positions:
        preview = avg_positions[:10]
        lines.append(f"  平均每輪工具調用: {preview}")

    # Q3
    vd = summary["q3_view_directory_first_turn"]
    lines.append("")
    lines.append("Q3: view_directory 首輪出現")
    lines.append(f"  首輪包含 view_directory: {vd}/{n} ({vd / n:.1%})")

    # Q4
    hz = summary["q4_has_zero_tool_call_turns"]
    lines.append("")
    lines.append("Q4: 零工具調用輪次")
    lines.append(f"  存在 0 工具調用的 case: {hz}/{n} ({hz / n:.1%})")
    zero_positions = summary["q4_zero_turn_positions"]
    if zero_positions:
        lines.append(f"  涉及的 turns: {zero_positions}")

    # Q5
    hf = summary["q5_has_failed_tool_calls"]
    lines.append("")
    lines.append("Q5: 失敗工具調用")
    lines.append(f"  包含失敗工具的 case: {hf}/{n} ({hf / n:.1%})")
    top_failed = summary["q5_top_failed_tools"]
    if top_failed:
        parts = [f"{name} ({count})" for name, count in top_failed]
        lines.append(f"  常見失敗工具: {', '.join(parts)}")

    return "\n".join(lines)
