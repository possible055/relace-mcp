"""Curate elite 50-item *research-grade* benchmark dataset.

Goals:
- 5 target repos x 10 items each (when available)
- Ground truth ranges are anchored to Python functions (includes name + signature)
- Use complete function scope (no arbitrary padding truncation)
- Avoid fragmented ground truth: <= 10 ranges (functions) per case
- Exclude test/doc/config files from ground truth

Output: benchmark/artifacts/data/processed/elite_50.jsonl (DatasetCase-compatible JSONL)
"""

import ast
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from ..analysis.function_scope import FunctionScope, extract_function_scopes
from ..config import DEFAULT_MULOCBENCH_PATH, get_processed_data_dir, get_repos_dir
from ..runner.git import ensure_repo

# Target repositories (expanded to reach 50 items)
TARGET_REPOS = [
    ("scikit-learn", "scikit-learn"),
    ("scrapy", "scrapy"),
    ("localstack", "localstack"),
    ("AntonOsika", "gpt-engineer"),
    ("geekan", "MetaGPT"),
    # Added to fill the gap (gpt-engineer and MetaGPT each have only 6 items)
    ("keras-team", "keras"),
    ("psf", "requests"),
    ("pallets", "flask"),
]

ITEMS_PER_REPO = 10
MAX_GT_BLOCKS = 10
MAX_SINGLE_LINE_RATIO = 0.5

# Large repos to exclude
EXCLUDED_REPOS = {
    "langflow-ai/langflow",
    "PaddlePaddle/PaddleOCR",
    "odoo/odoo",
    "ansible/ansible",
    "pytorch/pytorch",
    "deepfakes/faceswap",
    "huggingface/transformers",
    "python/cpython",
    "All-Hands-AI/OpenHands",
    "hacksider/Deep-Live-Cam",
    "yt-dlp/yt-dlp",
    "pandas-dev/pandas",
    "home-assistant/core",
    "kubernetes/kubernetes",
    "torvalds/linux",
    "chromium/chromium",
}


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


def compute_quality_score(data: dict[str, Any], eligible_changes: list[dict[str, Any]]) -> float:
    """Compute quality score for an item."""
    score = 0.0

    # Query Clarity (0-3): based on title + body length and structure
    title = data.get("title", "") or ""
    body = data.get("body", "") or ""
    query_len = len(title) + len(body)
    if query_len > 500:
        score += 3.0
    elif query_len > 200:
        score += 2.0
    elif query_len > 50:
        score += 1.0

    # Ground Truth Scope (0-3): based on number of files and lines
    total_lines = sum(len(gt["lines"]) for gt in eligible_changes)
    if 5 <= total_lines <= 50:
        score += 3.0  # Sweet spot: not too small, not too large
    elif total_lines > 50:
        score += 1.0
    elif total_lines > 0:
        score += 2.0

    # Single-File Focus (0-2): prefer single file modifications
    if len(eligible_changes) == 1:
        score += 2.0
    elif len(eligible_changes) == 2:
        score += 1.0

    # Code-Only (0-2): prefer PRs that touch only Python code files (heuristic)
    file_loc_str = data.get("file_loc", "") or ""
    try:
        file_loc = ast.literal_eval(file_loc_str) if file_loc_str else {}
    except Exception:
        file_loc = {}
    touched = [
        f.get("path", "")
        for f in (file_loc.get("files", []) or [])
        if isinstance(f, dict) and isinstance(f.get("path"), str)
    ]
    bad = [
        p
        for p in touched
        if not _is_eligible_code_path(p)
        and (not p.endswith(".py") or _is_test_path(p) or _is_doc_path(p) or _is_config_path(p))
    ]
    if len(bad) == 0:
        score += 2.0
    elif len(bad) <= 1:
        score += 1.0

    return score


def _collect_changed_lines(loc: dict[str, Any]) -> list[int]:
    lines: list[int] = []
    for changes in (loc or {}).values():
        if not isinstance(changes, dict):
            continue
        for key in ("add", "mod"):
            vals = changes.get(key, [])
            if isinstance(vals, list):
                lines.extend(v for v in vals if isinstance(v, int))
    return sorted(set(lines))


def parse_item(data: dict[str, Any]) -> dict[str, Any] | None:
    """Parse a raw MULocBench item; return candidate info if usable."""
    org = data.get("organization", "") or ""
    repo_name = data.get("repo_name", "") or ""
    full_repo = f"{org}/{repo_name}"

    # Check if target repo
    is_target = any(org == t[0] and repo_name == t[1] for t in TARGET_REPOS)
    if not is_target:
        return None

    # Must have PR-linked ground truth
    if not data.get("pr_html_url"):
        return None

    # Parse file_loc for ground truth
    file_loc_str = data.get("file_loc", "")
    if not file_loc_str:
        return None

    try:
        file_loc = ast.literal_eval(file_loc_str)
    except Exception:
        return None

    files = file_loc.get("files", []) or []
    if not files:
        return None

    touched_paths: list[str] = []
    eligible_changes: list[dict[str, Any]] = []
    for f in files:
        if not isinstance(f, dict):
            continue
        path = f.get("path", "")
        if not isinstance(path, str) or not path:
            continue
        touched_paths.append(path)
        if not _is_eligible_code_path(path):
            continue
        loc = f.get("Loc", {})
        if not isinstance(loc, dict) or not loc:
            continue
        changed_lines = _collect_changed_lines(loc)
        if changed_lines:
            eligible_changes.append({"path": path, "lines": changed_lines})

    if not eligible_changes:
        return None

    # Build query
    title = data.get("title", "")
    body = data.get("body", "")
    query = f"{title}\n\n{body}".strip()

    if len(query) < 20:
        return None

    # Compute quality score
    quality_score = compute_quality_score(data, eligible_changes)

    return {
        "org": org,
        "repo_name": repo_name,
        "full_repo": full_repo,
        "base_commit": data.get("base_commit", ""),
        "query": query,
        "eligible_changes": eligible_changes,
        "touched_paths": touched_paths,
        "pr_url": data.get("pr_html_url"),
        "issue_url": data.get("iss_html_url"),
        "quality_score": quality_score,
    }


def _count_file_lines(full_path: Path) -> int | None:
    """Return total line count for a file, or None if unreadable."""
    try:
        text = full_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    return len(text.splitlines())


def _build_function_gt_for_file(
    *, repo_path: Path, rel_path: str, changed_lines: list[int]
) -> list[dict[str, Any]] | None:
    full_path = repo_path / rel_path
    if not full_path.exists():
        return None
    total_lines = _count_file_lines(full_path)
    if total_lines is None or total_lines <= 0:
        return None

    target_lines = {ln for ln in changed_lines if isinstance(ln, int) and 1 <= ln <= total_lines}
    if not target_lines:
        return None

    scopes = extract_function_scopes(full_path, target_lines, relative_path=rel_path)
    if not scopes:
        return None

    # Pick the most specific (innermost) function for each changed line.
    selected: dict[tuple[str | None, str, int], FunctionScope] = {}
    for ln in target_lines:
        candidates = [s for s in scopes if s.start_line <= ln <= s.end_line]
        if not candidates:
            # Some edits are outside any Python function (module-level, class-level, etc.)
            return None
        best = min(candidates, key=lambda s: (s.end_line - s.start_line, s.start_line))
        selected[(best.class_name, best.function_name, best.start_line)] = best

    selected_scopes = list(selected.values())

    entries: list[dict[str, Any]] = []
    for s in selected_scopes:
        if not s.function_name or not s.signature:
            return None
        lines_in_scope = [ln for ln in target_lines if s.start_line <= ln <= s.end_line]
        if not lines_in_scope:
            continue
        # Use complete function scope (no arbitrary padding truncation)
        start = s.start_line
        end = s.end_line
        if start < 1:
            start = 1
        if end < start:
            end = start
        entries.append(
            {
                "path": s.path,
                "function": s.function_name,
                "class": s.class_name,
                "range": [start, end],
                "signature": s.signature,
            }
        )

    if not entries:
        return None
    return entries


def build_hard_gt(*, eligible_changes: list[dict[str, Any]], repo_path: Path) -> list[dict] | None:
    """Build function-anchored hard_gt entries for a case."""
    all_entries: list[dict[str, Any]] = []
    for change in eligible_changes:
        rel_path = change.get("path", "")
        lines = change.get("lines", [])
        if not isinstance(rel_path, str) or not rel_path:
            return None
        if not _is_eligible_code_path(rel_path):
            return None
        if not isinstance(lines, list) or not lines:
            return None

        file_entries = _build_function_gt_for_file(
            repo_path=repo_path,
            rel_path=rel_path,
            changed_lines=lines,
        )
        if not file_entries:
            return None
        all_entries.extend(file_entries)

    # Deduplicate by (path, class, function, start_line)
    deduped: list[dict[str, Any]] = []
    seen: set[tuple[str, str | None, str, int]] = set()
    for e in all_entries:
        key = (e.get("path", ""), e.get("class"), e.get("function", ""), int(e["range"][0]))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(e)

    if not deduped:
        return None

    if len(deduped) > MAX_GT_BLOCKS:
        return None

    single_line_blocks = sum(1 for e in deduped if e["range"][0] == e["range"][1])
    if (single_line_blocks / len(deduped)) > MAX_SINGLE_LINE_RATIO:
        return None

    return deduped


def main():
    base_path = Path(DEFAULT_MULOCBENCH_PATH)
    output_path = get_processed_data_dir() / "elite_50.jsonl"

    print(f"Reading {base_path}...")

    repos_dir = get_repos_dir()
    repos_dir.mkdir(parents=True, exist_ok=True)

    # Collect items by repo
    items_by_repo: dict[str, list] = defaultdict(list)

    with open(base_path, encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue

            parsed = parse_item(data)
            if parsed:
                items_by_repo[parsed["full_repo"]].append(parsed)

    print("Found items by repo:")
    for repo, items in items_by_repo.items():
        print(f"  {repo}: {len(items)} items")

    output_items: list[dict[str, Any]] = []
    per_repo_selected: dict[str, int] = defaultdict(int)
    per_repo_skipped: dict[str, Counter[str]] = defaultdict(Counter)

    # Select top N per repo, skipping items that fail research-grade constraints.
    for org, repo_name in TARGET_REPOS:
        full_repo = f"{org}/{repo_name}"
        candidates = list(items_by_repo.get(full_repo, []))
        candidates.sort(key=lambda x: (x["quality_score"], len(x["query"])), reverse=True)

        print(f"\n{full_repo}: evaluating {len(candidates)} candidates...")

        for cand in candidates:
            if per_repo_selected[full_repo] >= ITEMS_PER_REPO:
                break

            base_commit = cand.get("base_commit", "")
            if not isinstance(base_commit, str) or not base_commit:
                per_repo_skipped[full_repo]["missing_base_commit"] += 1
                continue

            try:
                repo_path = ensure_repo(
                    repos_dir=repos_dir,
                    repo=full_repo,
                    base_commit=base_commit,
                    verbose=False,
                )
            except Exception:
                per_repo_skipped[full_repo]["ensure_repo_failed"] += 1
                continue

            hard_gt = build_hard_gt(eligible_changes=cand["eligible_changes"], repo_path=repo_path)
            if not hard_gt:
                per_repo_skipped[full_repo]["no_valid_function_gt"] += 1
                continue

            issue_url = cand.get("issue_url", "")
            issue_id = (
                issue_url.split("/")[-1] if isinstance(issue_url, str) and issue_url else "unknown"
            )

            output_items.append(
                {
                    "id": f"{full_repo.replace('/', '_')}_{issue_id}",
                    "query": cand["query"],
                    "repo": full_repo,
                    "base_commit": base_commit,
                    "hard_gt": hard_gt,
                    "soft_context": [],
                    "issue_url": issue_url,
                    "pr_url": cand.get("pr_url"),
                }
            )
            per_repo_selected[full_repo] += 1

        print(f"{full_repo}: selected {per_repo_selected[full_repo]}/{ITEMS_PER_REPO}")
        if per_repo_skipped[full_repo]:
            skipped = per_repo_skipped[full_repo]
            print(
                f"{full_repo}: skipped " + ", ".join(f"{k}={v}" for k, v in skipped.most_common())
            )

    # Write output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        for item in output_items:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    print("\n=== Complete ===")
    print(f"Total elite items: {len(output_items)}")
    print(f"Output: {output_path}")

    # Verify distribution
    repos = Counter(item["repo"] for item in output_items)
    print("\nDistribution:")
    for repo, count in repos.items():
        print(f"  {repo}: {count}")


if __name__ == "__main__":
    main()
