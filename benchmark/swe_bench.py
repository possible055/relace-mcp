import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, cast

DEFAULT_DATASET_NAME = "princeton-nlp/SWE-bench_Lite_oracle"
DEFAULT_SPLIT = "test"


@dataclass
class BenchmarkCase:
    id: str
    query: str
    repo: str
    base_commit: str
    ground_truth_files: dict[str, list[tuple[int, int]]] = field(default_factory=dict)


def extract_files_from_patch(patch: str) -> dict[str, list[tuple[int, int]]]:
    """Parse diff patch to extract modified files and line ranges.

    Args:
        patch: Git diff formatted patch string.

    Returns:
        Dict mapping file paths to list of (start_line, end_line) tuples.
    """
    return extract_files_from_patch_with_side(patch, side="old")


def extract_files_from_patch_with_side(
    patch: str, *, side: Literal["old", "new"] = "old"
) -> dict[str, list[tuple[int, int]]]:
    """Parse diff patch and extract file -> line ranges.

    SWE-bench provides `base_commit` (pre-patch). If you run searches against `base_commit`,
    prefer `side="old"` so line numbers align with the checked-out code.
    """
    files: dict[str, list[tuple[int, int]]] = {}
    current_file: str | None = None
    is_new_file = False

    for line in patch.splitlines():
        if line.startswith("diff --git "):
            current_file = None
            is_new_file = False
            continue

        if line.startswith("--- "):
            path_spec = line[4:].strip()
            if path_spec == "/dev/null":
                current_file = None
                is_new_file = True
                continue
            if path_spec.startswith("a/"):
                current_file = path_spec[2:]
                is_new_file = False
                files.setdefault(current_file, [])
            continue

        if not current_file or is_new_file:
            continue

        if not line.startswith("@@"):
            continue

        match = re.search(r"@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@", line)
        if not match:
            continue

        if side == "old":
            start = int(match.group(1))
            count = int(match.group(2)) if match.group(2) else 1
        else:
            start = int(match.group(3))
            count = int(match.group(4)) if match.group(4) else 1

        if start <= 0 or count <= 0:
            continue

        end = start + count - 1
        files[current_file].append((start, end))

    return files


def load_swe_bench(
    limit: int = 50,
    *,
    dataset_name: str = DEFAULT_DATASET_NAME,
    split: str = DEFAULT_SPLIT,
    shuffle: bool = True,
    seed: int = 0,
) -> list[BenchmarkCase]:
    """Load SWE-bench dataset and convert to BenchmarkCase objects.

    Args:
        limit: Maximum number of cases to load.
        dataset_name: HuggingFace dataset identifier.
        split: Dataset split to use.
        shuffle: Shuffle dataset before selecting limit (recommended to avoid bias).
        seed: Random seed used for shuffling (ensures reproducible sampling).

    Returns:
        List of BenchmarkCase objects with ground truth extracted from patches.
    """
    try:
        from datasets import load_dataset
    except ImportError as exc:
        raise RuntimeError(
            "Missing optional dependency 'datasets'. Install with `uv run --extra benchmark ...` "
            "or `pip install -e '.[benchmark]'`."
        ) from exc

    dataset = load_dataset(dataset_name, split=split)  # nosec B615
    if shuffle:
        dataset = dataset.shuffle(seed=seed)
    cases: list[BenchmarkCase] = []

    for item in dataset.select(range(min(limit, len(dataset)))):  # pyright: ignore[reportAttributeAccessIssue]
        row = cast(dict[str, Any], item)
        patch = row.get("patch", "")
        ground_truth = extract_files_from_patch(patch) if patch else {}

        cases.append(
            BenchmarkCase(
                id=row["instance_id"],
                query=row["problem_statement"],
                repo=row["repo"],
                base_commit=row["base_commit"],
                ground_truth_files=ground_truth,
            )
        )

    return cases


def get_repos_dir() -> Path:
    """Get directory for cloned repositories."""
    return Path(__file__).parent / "repos"
