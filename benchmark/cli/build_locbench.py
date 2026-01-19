import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import click
import httpx

from ..analysis.function_scope import FunctionScope, extract_function_scopes
from ..config import EXCLUDED_REPOS, get_benchmark_dir, get_raw_data_dir, get_repos_dir
from ..runner.git import ensure_repo

_HF_DATASETS_SERVER = "https://datasets-server.huggingface.co"
_DEFAULT_DATASET = "czlll/Loc-Bench_V1"
_DEFAULT_CONFIG = "default"
_DEFAULT_SPLIT = "test"

_HUNK_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")

_TARGET_RANGE_GAP = 3
_MAX_TARGET_RANGES_PER_FUNCTION = 2


def _resolve_path(path: str) -> Path:
    p = Path(path)
    if p.is_absolute():
        return p
    return get_benchmark_dir() / p


def _fetch_split_size(*, client: httpx.Client, dataset: str, config: str, split: str) -> int:
    resp = client.get(f"{_HF_DATASETS_SERVER}/info", params={"dataset": dataset})
    resp.raise_for_status()
    data = resp.json()
    try:
        return int(data["dataset_info"][config]["splits"][split]["num_examples"])
    except Exception as exc:  # pragma: no cover
        raise RuntimeError(f"Unexpected /info response shape: {data.keys()}") from exc


def _iter_rows(
    *,
    client: httpx.Client,
    dataset: str,
    config: str,
    split: str,
    limit: int | None,
    page_size: int,
) -> Any:
    total = _fetch_split_size(client=client, dataset=dataset, config=config, split=split)
    remaining = min(total, limit) if limit is not None else total

    offset = 0
    while offset < remaining:
        length = min(page_size, remaining - offset)
        resp = client.get(
            f"{_HF_DATASETS_SERVER}/rows",
            params={
                "dataset": dataset,
                "config": config,
                "split": split,
                "offset": offset,
                "length": length,
            },
        )
        resp.raise_for_status()
        payload = resp.json()
        rows = payload.get("rows", [])
        for item in rows:
            row = item.get("row")
            if isinstance(row, dict):
                yield row
        offset += length


def _extract_allowed_paths(edit_functions: list[Any]) -> set[str]:
    allowed: set[str] = set()
    for item in edit_functions:
        if not isinstance(item, str):
            continue
        if ":" not in item:
            continue
        path, _ = item.split(":", 1)
        path = path.strip().lstrip("/")
        if path:
            allowed.add(path)
    return allowed


def _extract_changed_lines_by_file(patch: str) -> dict[str, set[int]]:
    current_file: str | None = None
    in_hunk = False
    base_line: int | None = None

    changed: dict[str, set[int]] = defaultdict(set)

    for raw_line in (patch or "").splitlines():
        line = raw_line.rstrip("\n")

        if line.startswith("diff --git "):
            current_file = None
            in_hunk = False
            base_line = None
            continue

        if line.startswith("--- "):
            if line.startswith("--- a/"):
                path = line[len("--- a/") :].strip()
                if path and path != "/dev/null":
                    current_file = path
            continue

        if line.startswith("+++ "):
            if line.startswith("+++ b/"):
                path = line[len("+++ b/") :].strip()
                if path and path != "/dev/null":
                    current_file = path
            continue

        m = _HUNK_RE.match(line)
        if m:
            if not current_file:
                in_hunk = False
                base_line = None
                continue
            base_line = int(m.group(1))
            in_hunk = True
            continue

        if not in_hunk or not current_file or base_line is None:
            continue

        if not line:
            continue

        prefix = line[0]
        if prefix == " ":
            base_line += 1
            continue
        if prefix == "-":
            changed[current_file].add(base_line)
            base_line += 1
            continue
        if prefix == "+":
            anchor = max(1, base_line - 1) if base_line > 0 else 1
            changed[current_file].add(anchor)
            continue
        if prefix == "\\":
            continue

    return dict(changed)


def _count_file_lines(full_path: Path) -> int | None:
    try:
        text = full_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    return len(text.splitlines())


def _cluster_lines_to_ranges(lines: list[int], *, gap: int) -> list[tuple[int, int]]:
    if not lines:
        return []
    sorted_lines = sorted({ln for ln in lines if isinstance(ln, int) and ln > 0})
    if not sorted_lines:
        return []

    ranges: list[tuple[int, int]] = []
    start = prev = sorted_lines[0]

    for ln in sorted_lines[1:]:
        if ln <= prev + 1 + gap:
            prev = ln
            continue
        ranges.append((start, prev))
        start = prev = ln

    ranges.append((start, prev))
    return ranges


def _build_target_ranges(
    lines_in_scope: list[int],
    *,
    context_start: int,
    context_end: int,
) -> list[tuple[int, int]]:
    target_ranges = _cluster_lines_to_ranges(lines_in_scope, gap=_TARGET_RANGE_GAP)
    if len(target_ranges) > _MAX_TARGET_RANGES_PER_FUNCTION:
        target_ranges = [(min(lines_in_scope), max(lines_in_scope))]

    clamped: list[tuple[int, int]] = []
    for start, end in target_ranges:
        clamped_start = max(int(context_start), int(start))
        clamped_end = min(int(context_end), int(end))
        if clamped_end >= clamped_start:
            clamped.append((clamped_start, clamped_end))
    return clamped


def _build_function_gt_for_file(
    *,
    repo_path: Path,
    rel_path: str,
    changed_lines: set[int],
) -> list[dict[str, Any]]:
    full_path = repo_path / rel_path
    if not full_path.exists() or full_path.suffix != ".py":
        return []

    total_lines = _count_file_lines(full_path)
    if total_lines is None or total_lines <= 0:
        return []

    target_lines = {ln for ln in changed_lines if isinstance(ln, int) and 1 <= ln <= total_lines}
    if not target_lines:
        return []

    scopes = extract_function_scopes(full_path, target_lines, relative_path=rel_path)
    if not scopes:
        return []

    selected: dict[tuple[str | None, str, int], FunctionScope] = {}
    lines_by_scope: dict[tuple[str | None, str, int], set[int]] = defaultdict(set)

    for ln in target_lines:
        candidates = [s for s in scopes if s.start_line <= ln <= s.end_line]
        if not candidates:
            continue
        best = min(candidates, key=lambda s: (s.end_line - s.start_line, s.start_line))
        key = (best.class_name, best.function_name, best.start_line)
        selected[key] = best
        lines_by_scope[key].add(ln)

    entries: list[dict[str, Any]] = []
    for key, s in selected.items():
        if not s.function_name or not s.signature:
            continue
        lines_in_scope = sorted(lines_by_scope.get(key, set()))
        if not lines_in_scope:
            continue

        target_ranges = _build_target_ranges(
            lines_in_scope,
            context_start=s.start_line,
            context_end=s.end_line,
        )
        if not target_ranges:
            continue

        start = max(1, int(s.start_line))
        end = max(start, int(s.end_line))

        entries.append(
            {
                "path": s.path,
                "function": s.function_name,
                "class": s.class_name,
                "range": [start, end],
                "target_ranges": [[a, b] for a, b in target_ranges],
                "signature": s.signature,
            }
        )

    return entries


def _build_case(
    *,
    row: dict[str, Any],
    repos_dir: Path,
    verbose: bool,
    excluded_lower: set[str],
) -> dict[str, Any] | None:
    repo = row.get("repo", "")
    base_commit = row.get("base_commit", "")
    instance_id = row.get("instance_id", "")
    problem_statement = row.get("problem_statement", "")
    patch = row.get("patch", "")
    edit_functions = row.get("edit_functions", [])

    if not isinstance(repo, str) or not repo:
        return None
    if repo.lower() in excluded_lower:
        return None
    if not isinstance(base_commit, str) or not base_commit:
        return None
    if not isinstance(instance_id, str) or not instance_id:
        return None
    if not isinstance(problem_statement, str) or len(problem_statement.strip()) < 5:
        return None
    if not isinstance(patch, str) or not patch.strip():
        return None
    if not isinstance(edit_functions, list) or not edit_functions:
        return None

    allowed_paths = _extract_allowed_paths(edit_functions)
    if not allowed_paths:
        return None

    try:
        repo_path = ensure_repo(
            repos_dir=repos_dir,
            repo=repo,
            base_commit=base_commit,
            verbose=verbose,
        )
    except Exception:
        return None

    changed_by_file = _extract_changed_lines_by_file(patch)
    filtered_changed: dict[str, set[int]] = {
        path: lines
        for path, lines in changed_by_file.items()
        if path in allowed_paths and path.endswith(".py")
    }
    if not filtered_changed:
        return None

    all_entries: list[dict[str, Any]] = []
    for rel_path, lines in filtered_changed.items():
        all_entries.extend(
            _build_function_gt_for_file(repo_path=repo_path, rel_path=rel_path, changed_lines=lines)
        )

    if not all_entries:
        return None

    deduped: list[dict[str, Any]] = []
    seen: set[tuple[str, str | None, str, int]] = set()
    for e in all_entries:
        path = e.get("path", "")
        fn = e.get("function", "")
        start = int(e["range"][0]) if isinstance(e.get("range"), list) and e["range"] else 0
        key = (path, e.get("class"), fn, start)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(e)

    if not deduped:
        return None

    return {
        "id": instance_id,
        "query": problem_statement.strip(),
        "repo": repo,
        "base_commit": base_commit,
        "hard_gt": deduped,
        "soft_context": [],
        "category": row.get("category"),
        "source_dataset": _DEFAULT_DATASET,
        "source_split": _DEFAULT_SPLIT,
        "edit_functions": edit_functions,
    }


@click.command()
@click.option("--dataset", default=_DEFAULT_DATASET, show_default=True)
@click.option("--config", "config_name", default=_DEFAULT_CONFIG, show_default=True)
@click.option("--split", default=_DEFAULT_SPLIT, show_default=True)
@click.option(
    "--output",
    default=None,
    help="Output JSONL path (relative to benchmark/ if not absolute). Default: artifacts/data/raw/locbench_v1.jsonl",
)
@click.option("--limit", default=None, type=int, help="Maximum rows to process (default: all)")
@click.option("--page-size", default=100, show_default=True, type=int)
@click.option("--verbose", "-v", is_flag=True)
@click.option("--dry-run", is_flag=True, help="Only print summary, don't write output")
@click.option(
    "--local-parquet",
    default=None,
    help="Read from a local parquet file instead of HuggingFace API",
)
def main(
    dataset: str,
    config_name: str,
    split: str,
    output: str | None,
    limit: int | None,
    page_size: int,
    verbose: bool,
    dry_run: bool,
    local_parquet: str | None,
) -> None:
    """Build DatasetCase JSONL from Loc-Bench via Hugging Face dataset server."""
    raw_dir = get_raw_data_dir()
    repos_dir = get_repos_dir()
    repos_dir.mkdir(parents=True, exist_ok=True)

    if output:
        output_path = _resolve_path(output)
    else:
        output_path = raw_dir / "locbench_v1.jsonl"

    excluded_lower = {r.lower() for r in EXCLUDED_REPOS}

    click.echo("=== Build Loc-Bench Dataset ===")
    click.echo(f"dataset: {dataset} ({config_name}/{split})")
    click.echo(f"output:  {output_path}")
    click.echo(f"limit:   {limit if limit is not None else 'all'}")
    click.echo(f"excluded repos: {len(EXCLUDED_REPOS)}")

    stats: Counter[str] = Counter()

    # Use local parquet if provided, otherwise fetch from HuggingFace API
    if local_parquet:
        try:
            import pyarrow.parquet as pq
        except ImportError as err:
            raise click.ClickException(
                "pyarrow is required for --local-parquet. Install with: pip install pyarrow"
            ) from err

        parquet_path = Path(local_parquet)
        if not parquet_path.exists():
            raise click.ClickException(f"Local parquet file not found: {parquet_path}")
        click.echo(f"Reading from local parquet: {parquet_path}")
        table = pq.read_table(parquet_path)
        all_rows = table.to_pylist()
        if limit is not None:
            all_rows = all_rows[:limit]
        rows_iter = iter(all_rows)
        if dry_run:
            click.echo(f"[DRY RUN] local parquet rows: {len(all_rows)}")
            return
    else:
        with httpx.Client(timeout=60.0, follow_redirects=True) as client:
            rows_iter = _iter_rows(
                client=client,
                dataset=dataset,
                config=config_name,
                split=split,
                limit=limit,
                page_size=page_size,
            )

            if dry_run:
                total = 0
                for _ in rows_iter:
                    total += 1
                click.echo(f"[DRY RUN] fetched rows: {total}")
                return

            # Convert to list immediately when using API to avoid client scope issues
            rows_iter = list(rows_iter)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    with output_path.open("w", encoding="utf-8") as f:
        for i, row in enumerate(rows_iter, 1):
            case = _build_case(
                row=row,
                repos_dir=repos_dir,
                verbose=verbose,
                excluded_lower=excluded_lower,
            )
            if not case:
                stats["skipped"] += 1
                continue

            f.write(json.dumps(case, ensure_ascii=False) + "\n")
            written += 1
            stats["written"] += 1
            if verbose and written % 10 == 0:
                click.echo(f"  wrote {written} cases (processed {i})")

    click.echo("\n=== Complete ===")
    click.echo(f"written: {stats['written']}")
    click.echo(f"skipped: {stats['skipped']}")


if __name__ == "__main__":
    main()
