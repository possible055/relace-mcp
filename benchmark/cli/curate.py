import json
import random
from collections import defaultdict
from pathlib import Path

import click

from ..config import get_benchmark_dir, get_processed_data_dir, get_raw_data_dir

CATEGORY_WEIGHTS = {
    "Bug Report": 0.40,
    "Feature Request": 0.25,
    "Performance Issue": 0.25,
    "Security Vulnerability": 0.10,
}

DIFFICULTY_BINS = {
    "easy": (1, 2),
    "medium": (3, 5),
    "hard": (6, 100),
}


def _load_raw_cases(input_path: Path) -> list[dict]:
    cases = []
    with input_path.open("r", encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            if not stripped:
                continue
            try:
                cases.append(json.loads(stripped))
            except json.JSONDecodeError:
                continue
    return cases


def _classify_difficulty(case: dict) -> str:
    hard_gt_count = len(case.get("hard_gt", []))
    for difficulty, (low, high) in DIFFICULTY_BINS.items():
        if low <= hard_gt_count <= high:
            return difficulty
    return "hard"


def _stratified_curate(
    cases: list[dict],
    target_count: int,
    seed: int,
    balance_category: bool,
    balance_difficulty: bool,
    balance_repo: bool,
) -> list[dict]:
    rng = random.Random(seed)

    by_category: dict[str, list[dict]] = defaultdict(list)
    by_difficulty: dict[str, list[dict]] = defaultdict(list)
    by_repo: dict[str, list[dict]] = defaultdict(list)

    for case in cases:
        category = case.get("category", "Bug Report")
        difficulty = _classify_difficulty(case)
        repo = case.get("repo", "unknown")

        by_category[category].append(case)
        by_difficulty[difficulty].append(case)
        by_repo[repo].append(case)

    selected: list[dict] = []
    selected_ids: set[str] = set()

    if balance_repo:
        repos = list(by_repo.keys())
        rng.shuffle(repos)
        per_repo = max(1, target_count // len(repos))

        for repo in repos:
            repo_cases = by_repo[repo]
            rng.shuffle(repo_cases)
            for case in repo_cases[:per_repo]:
                if case["id"] not in selected_ids:
                    selected.append(case)
                    selected_ids.add(case["id"])
                    if len(selected) >= target_count:
                        break
            if len(selected) >= target_count:
                break

    if balance_category and len(selected) < target_count:
        remaining = target_count - len(selected)
        for category, weight in CATEGORY_WEIGHTS.items():
            category_target = int(remaining * weight)
            candidates = [c for c in by_category[category] if c["id"] not in selected_ids]
            rng.shuffle(candidates)
            for case in candidates[:category_target]:
                selected.append(case)
                selected_ids.add(case["id"])

    if balance_difficulty and len(selected) < target_count:
        remaining = target_count - len(selected)
        per_difficulty = remaining // 3
        for difficulty in ["easy", "medium", "hard"]:
            candidates = [c for c in by_difficulty[difficulty] if c["id"] not in selected_ids]
            rng.shuffle(candidates)
            for case in candidates[:per_difficulty]:
                selected.append(case)
                selected_ids.add(case["id"])

    if len(selected) < target_count:
        remaining_cases = [c for c in cases if c["id"] not in selected_ids]
        rng.shuffle(remaining_cases)
        selected.extend(remaining_cases[: target_count - len(selected)])

    rng.shuffle(selected)
    return selected[:target_count]


def _print_stats(cases: list[dict], label: str) -> None:
    by_category: dict[str, int] = defaultdict(int)
    by_difficulty: dict[str, int] = defaultdict(int)
    by_repo: dict[str, int] = defaultdict(int)

    for case in cases:
        by_category[case.get("category", "Unknown")] += 1
        by_difficulty[_classify_difficulty(case)] += 1
        by_repo[case.get("repo", "unknown")] += 1

    click.echo(f"\n{label} ({len(cases)} cases):")
    click.echo("  Category distribution:")
    for cat, count in sorted(by_category.items()):
        click.echo(f"    {cat}: {count} ({count / len(cases) * 100:.1f}%)")

    click.echo("  Difficulty distribution:")
    for diff, count in sorted(by_difficulty.items()):
        click.echo(f"    {diff}: {count} ({count / len(cases) * 100:.1f}%)")

    click.echo(f"  Unique repos: {len(by_repo)}")
    top_repos = sorted(by_repo.items(), key=lambda x: -x[1])[:5]
    for repo, count in top_repos:
        click.echo(f"    {repo}: {count}")


@click.command()
@click.option(
    "--input",
    "input_path",
    default=None,
    help="Input dataset (default: raw/locbench_v1.jsonl)",
)
@click.option(
    "--output",
    "output_path",
    default=None,
    help="Output dataset (default: processed/curated_<count>.jsonl)",
)
@click.option(
    "--count",
    default=50,
    type=int,
    show_default=True,
    help="Number of cases to select",
)
@click.option("--seed", default=42, type=int, show_default=True, help="Random seed")
@click.option(
    "--balance-category/--no-balance-category",
    default=True,
    show_default=True,
    help="Balance by category (Bug Report, Feature Request, etc.)",
)
@click.option(
    "--balance-difficulty/--no-balance-difficulty",
    default=True,
    show_default=True,
    help="Balance by difficulty (easy/medium/hard based on GT count)",
)
@click.option(
    "--balance-repo/--no-balance-repo",
    default=True,
    show_default=True,
    help="Ensure repo diversity (at least 1 case per repo)",
)
@click.option("--dry-run", is_flag=True, help="Only show stats, don't write output")
@click.option("-v", "--verbose", is_flag=True, help="Verbose output")
def main(
    input_path: str | None,
    output_path: str | None,
    count: int,
    seed: int,
    balance_category: bool,
    balance_difficulty: bool,
    balance_repo: bool,
    dry_run: bool,
    verbose: bool,
) -> None:
    """Curate a balanced subset from the benchmark dataset.

    Selects cases based on category, difficulty, and repo diversity.

    Difficulty is determined by hard_gt count:
      - easy: 1-2 functions
      - medium: 3-5 functions
      - hard: 6+ functions

    Category weights (default):
      - Bug Report: 40%
      - Feature Request: 25%
      - Performance Issue: 25%
      - Security Vulnerability: 10%
    """
    benchmark_dir = get_benchmark_dir()

    if input_path is None:
        resolved_input = get_raw_data_dir() / "locbench_v1.jsonl"
    else:
        p = Path(input_path)
        resolved_input = p if p.is_absolute() else (benchmark_dir / p)

    if not resolved_input.exists():
        click.echo(f"Error: Input file not found: {resolved_input}", err=True)
        raise SystemExit(1)

    click.echo(f"Loading dataset: {resolved_input}")
    all_cases = _load_raw_cases(resolved_input)
    click.echo(f"Loaded {len(all_cases)} cases")

    if verbose:
        _print_stats(all_cases, "Source distribution")

    selected = _stratified_curate(
        all_cases,
        count,
        seed,
        balance_category,
        balance_difficulty,
        balance_repo,
    )

    _print_stats(selected, "Selected distribution")

    if dry_run:
        click.echo("\n[Dry Run] No output written.")
        return

    if output_path is None:
        resolved_output = get_processed_data_dir() / f"curated_{count}.jsonl"
    else:
        p = Path(output_path)
        resolved_output = p if p.is_absolute() else (benchmark_dir / p)

    resolved_output.parent.mkdir(parents=True, exist_ok=True)

    with resolved_output.open("w", encoding="utf-8") as f:
        for case in selected:
            f.write(json.dumps(case, ensure_ascii=False) + "\n")

    click.echo(f"\nOutput written: {resolved_output}")


if __name__ == "__main__":
    main()
