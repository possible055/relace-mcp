import re
from dataclasses import dataclass, field
from pathlib import Path

from datasets import load_dataset


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
    files: dict[str, list[tuple[int, int]]] = {}
    current_file: str | None = None

    for line in patch.split("\n"):
        # Match file path from diff header
        if line.startswith("+++ b/"):
            current_file = line[6:]
            if current_file not in files:
                files[current_file] = []
        # Match hunk header: @@ -old_start,old_count +new_start,new_count @@
        elif line.startswith("@@") and current_file:
            match = re.search(r"@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@", line)
            if match:
                start = int(match.group(1))
                count = int(match.group(2)) if match.group(2) else 1
                end = start + count - 1
                files[current_file].append((start, end))

    return files


def load_swe_bench(
    limit: int = 50,
    *,
    dataset_name: str = "princeton-nlp/SWE-bench_Lite_oracle",
    split: str = "test",
) -> list[BenchmarkCase]:
    """Load SWE-bench dataset and convert to BenchmarkCase objects.

    Args:
        limit: Maximum number of cases to load.
        dataset_name: HuggingFace dataset identifier.
        split: Dataset split to use.

    Returns:
        List of BenchmarkCase objects with ground truth extracted from patches.
    """
    dataset = load_dataset(dataset_name, split=split)  # nosec B615
    cases: list[BenchmarkCase] = []

    for item in dataset.select(range(min(limit, len(dataset)))):
        patch = item.get("patch", "")
        ground_truth = extract_files_from_patch(patch) if patch else {}

        cases.append(
            BenchmarkCase(
                id=item["instance_id"],
                query=item["problem_statement"],
                repo=item["repo"],
                base_commit=item["base_commit"],
                ground_truth_files=ground_truth,
            )
        )

    return cases


def get_repos_dir() -> Path:
    """Get directory for cloned repositories."""
    return Path(__file__).parent / "repos"
