"""Audit the curated elite dataset for research-grade ground truth quality.

This audit focuses on:
- Function-anchored hard ground truth (function name + signature present)
- Ground truth ranges cover actual changed lines (from raw MULocBench `file_loc`)
- Low fragmentation (<= 10 hard_gt blocks per case; single-line block ratio <= 50%)
- Human-review-friendly per-block "result span vs context" TSV
"""

import json
from collections import Counter
from pathlib import Path
from typing import Any

import click

from ..analysis.function_scope import extract_function_scopes
from ..config import DEFAULT_MULOCBENCH_PATH, get_benchmark_dir, get_repos_dir
from ..datasets import load_dataset
from ..runner.git import ensure_repo
from .curate_elite import (
    CONTEXT_PADDING,
    ITEMS_PER_REPO,
    MAX_GT_BLOCKS,
    MAX_SINGLE_LINE_RATIO,
    TARGET_REPOS,
    parse_item,
)


def _resolve_path(path: str) -> Path:
    p = Path(path)
    if p.is_absolute():
        return p
    return get_benchmark_dir() / p


def _normalize_ws(text: str | None) -> str:
    return " ".join((text or "").split())


def _fmt_int(value: int | None) -> str:
    return "" if value is None else str(int(value))


def _fmt_float(value: float | None, *, digits: int = 3) -> str:
    if value is None:
        return ""
    return f"{float(value):.{digits}f}"


def _fmt_bool(value: bool | None) -> str:
    if value is None:
        return ""
    return "1" if value else "0"


def _is_doc_path(path: str) -> bool:
    p = path.lower()
    return (
        p.startswith("docs/")
        or "/docs/" in p
        or p.startswith("doc/")
        or "/doc/" in p
        or p.endswith(".md")
        or p.endswith(".rst")
        or p.endswith(".txt")
    )


def _is_test_path(path: str) -> bool:
    p = path.lower()
    return p.startswith("tests/") or "/tests/" in p or "/test_" in p or "/test/" in p


def _is_config_path(path: str) -> bool:
    p = path.lower()
    return (
        p.endswith(".yml")
        or p.endswith(".yaml")
        or p.endswith(".toml")
        or p.endswith(".ini")
        or p.endswith(".cfg")
        or p.startswith(".circleci/")
        or p.startswith(".github/")
        or "/.github/" in p
    )


def _is_eligible_code_path(path: str) -> bool:
    return path.endswith(".py") and not (
        _is_test_path(path) or _is_doc_path(path) or _is_config_path(path)
    )


def _load_raw_by_issue_url(raw_file: Path, issue_urls: set[str]) -> dict[str, dict[str, Any]]:
    raw_by_issue_url: dict[str, dict[str, Any]] = {}
    with raw_file.open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                raw = json.loads(line)
            except json.JSONDecodeError:
                continue
            issue_url = raw.get("iss_html_url")
            if issue_url in issue_urls:
                raw_by_issue_url[issue_url] = raw
    return raw_by_issue_url


@click.command()
@click.option(
    "--dataset",
    "dataset_path",
    default="data/processed/elite_50.jsonl",
    show_default=True,
    help="Elite dataset path (relative to benchmark/ unless absolute)",
)
@click.option(
    "--raw",
    "raw_path",
    default=DEFAULT_MULOCBENCH_PATH,
    show_default=True,
    help="Raw MULocBench jsonl path (relative to benchmark/ unless absolute)",
)
@click.option(
    "--output",
    "output_path",
    default="reports/elite_50.audit.json",
    show_default=True,
    help="Output audit report path (relative to benchmark/ unless absolute)",
)
@click.option(
    "--tsv",
    "tsv_path",
    default="reports/elite_50.span_context.tsv",
    show_default=True,
    help="Output TSV listing (relative to benchmark/ unless absolute)",
)
@click.option(
    "--padding",
    default=CONTEXT_PADDING,
    show_default=True,
    type=int,
    help="Expected context padding (±N) used when curating",
)
def main(dataset_path: str, raw_path: str, output_path: str, tsv_path: str, padding: int) -> None:
    dataset_file = _resolve_path(dataset_path)
    raw_file = _resolve_path(raw_path)
    out_file = _resolve_path(output_path)
    tsv_file = _resolve_path(tsv_path)

    cases = load_dataset(dataset_path=str(dataset_file), shuffle=False)
    by_issue_url = {c.issue_url: c for c in cases if c.issue_url}

    raw_by_issue_url = _load_raw_by_issue_url(raw_file, set(by_issue_url.keys()))

    target_full_repos = {f"{o}/{r}" for o, r in TARGET_REPOS}
    repos = Counter(c.repo for c in cases)
    target_total = len(TARGET_REPOS) * ITEMS_PER_REPO

    dataset_checks = {
        "total_items": len(cases),
        "target_total_items": target_total,
        "meets_target_total": len(cases) == target_total,
        "repos_distribution": dict(repos),
        "target_items_per_repo": ITEMS_PER_REPO,
        "meets_target_per_repo": all(
            repos.get(repo, 0) == ITEMS_PER_REPO for repo in target_full_repos
        ),
        "only_target_repos": all(repo in target_full_repos for repo in repos),
        "underfilled_repos": {
            repo: ITEMS_PER_REPO - repos.get(repo, 0)
            for repo in sorted(target_full_repos)
            if repos.get(repo, 0) < ITEMS_PER_REPO
        },
        "missing_raw_records": sorted([u for u in by_issue_url if u not in raw_by_issue_url]),
    }

    counters = Counter()
    case_reports: list[dict[str, Any]] = []

    tsv_header = [
        "case_id",
        "repo",
        "file",
        "class",
        "function",
        "signature",
        "gt_min_changed",
        "gt_max_changed",
        "result_span_len",
        "gt_range_start",
        "gt_range_end",
        "gt_range_len",
        "start_padding",
        "end_padding",
        "end_clamped",
        "changed_count",
        "ctx_to_result_ratio",
        "quality_score",
        "hard_gt_files",
        "hard_gt_blocks",
        "blocks_in_file",
        "single_line_blocks",
        "single_line_ratio",
        "blocks_ok_le_10",
        "single_line_ok_le_50pct",
        "anchor_ok",
        "range_ok",
        "errors",
    ]
    tsv_rows: list[str] = ["\t".join(tsv_header)]

    repos_dir = get_repos_dir()
    repo_cache: dict[tuple[str, str], Path] = {}

    for issue_url, case in by_issue_url.items():
        raw = raw_by_issue_url.get(issue_url)
        if not raw:
            counters["missing_raw_cases"] += 1
            case_reports.append(
                {
                    "id": case.id,
                    "repo": case.repo,
                    "issue_url": issue_url,
                    "error": "raw_record_not_found",
                }
            )
            continue

        parsed = parse_item(raw)
        if not parsed:
            counters["raw_parse_failed_cases"] += 1
            case_reports.append(
                {
                    "id": case.id,
                    "repo": case.repo,
                    "issue_url": issue_url,
                    "error": "raw_parse_failed",
                }
            )
            continue

        eligible_changes = parsed.get("eligible_changes", []) or []
        touched_paths = parsed.get("touched_paths", []) or []
        quality_score = float(parsed.get("quality_score", 0.0))

        modified_lines_by_path: dict[str, list[int]] = {
            ch["path"]: ch["lines"]
            for ch in eligible_changes
            if isinstance(ch, dict)
            and isinstance(ch.get("path"), str)
            and isinstance(ch.get("lines"), list)
        }

        hard_gt_blocks = len(case.hard_gt)
        blocks_in_file = Counter(gt.path for gt in case.hard_gt)
        hard_gt_files = len(blocks_in_file)

        single_line_blocks = sum(1 for gt in case.hard_gt if gt.range[0] == gt.range[1])
        single_line_ratio = (single_line_blocks / hard_gt_blocks) if hard_gt_blocks else 0.0
        blocks_ok = hard_gt_blocks <= MAX_GT_BLOCKS
        single_line_ok = single_line_ratio <= MAX_SINGLE_LINE_RATIO

        if hard_gt_files > 1:
            counters["multi_file_cases"] += 1
        if not blocks_ok:
            counters["blocks_over_limit_cases"] += 1
        if not single_line_ok:
            counters["single_line_ratio_over_limit_cases"] += 1
        if quality_score < 8:
            counters["low_score_lt_8_cases"] += 1

        mixed_touched_paths = [
            p for p in touched_paths if isinstance(p, str) and p and not _is_eligible_code_path(p)
        ]
        if mixed_touched_paths:
            counters["mixed_pr_cases"] += 1

        repo_key = (case.repo, case.base_commit)
        repo_path = repo_cache.get(repo_key)
        repo_error: str | None = None
        if repo_path is None:
            try:
                repo_path = ensure_repo(
                    repos_dir=repos_dir,
                    repo=case.repo,
                    base_commit=case.base_commit,
                    verbose=False,
                )
                repo_cache[repo_key] = repo_path
            except Exception as e:
                repo_error = f"ensure_repo_failed:{e}"
                counters["ensure_repo_failed_cases"] += 1
                repo_path = None

        case_anchor_errors: list[str] = []
        case_range_errors: list[str] = []
        entries: list[dict[str, Any]] = []

        for gt in case.hard_gt:
            path = gt.path
            gt_start, gt_end = gt.range
            gt_range_len = int(gt_end) - int(gt_start) + 1

            entry_errors: list[str] = []
            anchor_errors: list[str] = []
            range_errors: list[str] = []

            if not _is_eligible_code_path(path):
                entry_errors.append("ineligible_hard_gt_path")
                counters["ineligible_hard_gt_entries"] += 1
            if not gt.function:
                entry_errors.append("missing_function")
                counters["missing_function_entries"] += 1
            if not gt.signature:
                entry_errors.append("missing_signature")
                counters["missing_signature_entries"] += 1

            changed_lines = modified_lines_by_path.get(path) or []
            changed_in_range = [ln for ln in changed_lines if gt_start <= ln <= gt_end]

            changed_min: int | None = None
            changed_max: int | None = None
            result_span_len: int | None = None
            start_padding: int | None = None
            end_padding: int | None = None
            ctx_to_result_ratio: float | None = None

            if not changed_lines:
                range_errors.append("no_changed_lines_for_path")
                counters["no_changed_lines_for_path_entries"] += 1
            elif not changed_in_range:
                range_errors.append("no_changed_lines_in_gt_range")
                counters["no_changed_lines_in_range_entries"] += 1
            else:
                changed_min = min(changed_in_range)
                changed_max = max(changed_in_range)
                result_span_len = int(changed_max) - int(changed_min) + 1
                start_padding = int(changed_min) - int(gt_start)
                end_padding = int(gt_end) - int(changed_max)
                if end_padding > padding:
                    range_errors.append("end_padding_exceeds_expected")
                    counters["end_padding_exceeds_expected_entries"] += 1
                if result_span_len > 0:
                    ctx_to_result_ratio = gt_range_len / result_span_len

            function_end_line: int | None = None
            signature_actual: str | None = None

            if repo_path is None:
                anchor_errors.append("repo_unavailable")
                counters["repo_unavailable_entries"] += 1
            else:
                full_path = repo_path / path
                if not full_path.exists():
                    anchor_errors.append("file_not_found_in_repo")
                    counters["file_not_found_entries"] += 1
                else:
                    scopes = extract_function_scopes(full_path, {gt_start}, relative_path=path)
                    scope = next((s for s in scopes if s.start_line == gt_start), None)
                    if not scope:
                        anchor_errors.append("no_function_start_at_gt_start")
                        counters["no_function_start_entries"] += 1
                    else:
                        function_end_line = scope.end_line
                        signature_actual = scope.signature
                        if gt.function and scope.function_name != gt.function:
                            anchor_errors.append("function_name_mismatch")
                            counters["function_name_mismatch_entries"] += 1
                        if (gt.class_name or None) != (scope.class_name or None):
                            anchor_errors.append("class_mismatch")
                            counters["class_mismatch_entries"] += 1
                        if gt.signature and _normalize_ws(scope.signature) != _normalize_ws(
                            gt.signature
                        ):
                            anchor_errors.append("signature_mismatch")
                            counters["signature_mismatch_entries"] += 1
                        if gt_end > scope.end_line:
                            range_errors.append("gt_end_exceeds_function_end")
                            counters["gt_end_exceeds_function_end_entries"] += 1

            end_clamped: bool | None = None
            if (
                function_end_line is not None
                and end_padding is not None
                and gt_end == function_end_line
                and end_padding < padding
            ):
                end_clamped = True
            elif function_end_line is not None and end_padding is not None:
                end_clamped = False

            anchor_ok = not anchor_errors
            range_ok = not range_errors

            if anchor_errors:
                case_anchor_errors.extend([f"{path}:{gt_start}:{e}" for e in anchor_errors])
            if range_errors:
                case_range_errors.extend([f"{path}:{gt_start}:{e}" for e in range_errors])

            error_str = ",".join(entry_errors + anchor_errors + range_errors)
            tsv_rows.append(
                "\t".join(
                    [
                        str(case.id),
                        str(case.repo),
                        str(path),
                        str(gt.class_name or ""),
                        str(gt.function or ""),
                        _normalize_ws(gt.signature).replace("\t", " "),
                        _fmt_int(changed_min),
                        _fmt_int(changed_max),
                        _fmt_int(result_span_len),
                        str(gt_start),
                        str(gt_end),
                        str(gt_range_len),
                        _fmt_int(start_padding),
                        _fmt_int(end_padding),
                        _fmt_bool(end_clamped),
                        str(len(changed_in_range)),
                        _fmt_float(ctx_to_result_ratio),
                        f"{quality_score:.1f}",
                        str(hard_gt_files),
                        str(hard_gt_blocks),
                        str(blocks_in_file.get(path, 0)),
                        str(single_line_blocks),
                        f"{single_line_ratio:.3f}",
                        _fmt_bool(blocks_ok),
                        _fmt_bool(single_line_ok),
                        _fmt_bool(anchor_ok),
                        _fmt_bool(range_ok),
                        error_str,
                    ]
                )
            )

            entries.append(
                {
                    "path": path,
                    "class": gt.class_name,
                    "function": gt.function,
                    "signature": gt.signature,
                    "range": [gt_start, gt_end],
                    "gt_range_len": gt_range_len,
                    "changed_count": len(changed_in_range),
                    "changed_min": changed_min,
                    "changed_max": changed_max,
                    "result_span_len": result_span_len,
                    "start_padding": start_padding,
                    "end_padding": end_padding,
                    "end_clamped": end_clamped,
                    "ctx_to_result_ratio": ctx_to_result_ratio,
                    "blocks_in_file": blocks_in_file.get(path, 0),
                    "function_end_line": function_end_line,
                    "signature_actual": signature_actual,
                    "entry_errors": entry_errors,
                    "anchor_errors": anchor_errors,
                    "range_errors": range_errors,
                }
            )

        if case_anchor_errors:
            counters["anchor_error_cases"] += 1
        if case_range_errors:
            counters["range_error_cases"] += 1

        case_reports.append(
            {
                "id": case.id,
                "repo": case.repo,
                "issue_url": issue_url,
                "pr_url": case.pr_url,
                "base_commit": case.base_commit,
                "query_len": len(case.query),
                "quality_score": quality_score,
                "hard_gt_files": hard_gt_files,
                "hard_gt_blocks": hard_gt_blocks,
                "single_line_blocks": single_line_blocks,
                "single_line_ratio": single_line_ratio,
                "blocks_ok": blocks_ok,
                "single_line_ok": single_line_ok,
                "mixed_touched_paths_count": len(mixed_touched_paths),
                "mixed_touched_paths": mixed_touched_paths[:20],
                "repo_error": repo_error,
                "anchor_errors": case_anchor_errors,
                "range_errors": case_range_errors,
                "entries": entries,
            }
        )

    report = {
        "dataset_checks": dataset_checks,
        "constraints": {
            "context_padding": padding,
            "max_gt_blocks": MAX_GT_BLOCKS,
            "max_single_line_ratio": MAX_SINGLE_LINE_RATIO,
            "hard_gt_paths": "python_only_and_not_tests_docs_config",
        },
        "summary": dict(counters),
        "cases": sorted(case_reports, key=lambda x: (x.get("repo", ""), x.get("id", ""))),
    }

    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    tsv_file.parent.mkdir(parents=True, exist_ok=True)
    tsv_file.write_text("\n".join(tsv_rows) + "\n", encoding="utf-8")

    click.echo("=== Elite Dataset Audit ===")
    click.echo(f"Dataset: {dataset_file}")
    click.echo(f"Raw:     {raw_file}")
    click.echo(f"Output:  {out_file}")
    click.echo(f"TSV:     {tsv_file}")
    click.echo("")
    click.echo(f"Total cases:        {len(cases)}")
    click.echo(f"Target total (5x10):{target_total}")
    click.echo(f"Meets target total: {dataset_checks['meets_target_total']}")
    click.echo(f"Meets per-repo:     {dataset_checks['meets_target_per_repo']}")
    click.echo(f"Range error cases:  {counters.get('range_error_cases', 0)}")
    click.echo(f"Anchor error cases: {counters.get('anchor_error_cases', 0)}")
    click.echo(f"Blocks>10 cases:    {counters.get('blocks_over_limit_cases', 0)}")
    click.echo(f"1-line ratio>50%:   {counters.get('single_line_ratio_over_limit_cases', 0)}")


if __name__ == "__main__":
    main()
