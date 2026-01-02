import json
import sys
from pathlib import Path
from typing import Any


def load_results(path: str) -> dict[str, Any]:
    with open(path) as f:
        return json.load(f)  # type: ignore[no-any-return]


def print_detailed_table(results: list[dict[str, Any]]) -> None:
    print("\n" + "=" * 80)
    print("DETAILED RESULTS")
    print("=" * 80)
    print(f"{'Case ID':<40} | F.Rec | F.Prec | L.Cov | L.Prec | L.Prec(M)")
    print(
        "-" * 40
        + "-+-"
        + "-" * 6
        + "+-"
        + "-" * 6
        + "+-"
        + "-" * 6
        + "+-"
        + "-" * 6
        + "+-"
        + "-" * 9
    )

    for r in results:
        case_id = r["case_id"][:38] if len(r["case_id"]) > 38 else r["case_id"]
        print(
            f"{case_id:<40} | "
            f"{r['file_recall'] * 100:5.1f}% | "
            f"{r['file_precision'] * 100:5.1f}% | "
            f"{r['line_coverage'] * 100:5.1f}% | "
            f"{r['line_precision'] * 100:5.1f}% | "
            f"{r['line_precision_matched'] * 100:7.1f}%"
        )


def print_distribution(results: list[dict[str, Any]], key: str, label: str) -> None:
    values = [r[key] * 100 for r in results]
    buckets = [0] * 11  # 0-10, 10-20, ..., 90-100, 100+

    for v in values:
        idx = min(int(v // 10), 10)
        buckets[idx] += 1

    print(f"\n{label} Distribution:")
    for i, count in enumerate(buckets):
        if i == 10:
            label_str = "100%"
        else:
            label_str = f"{i * 10:2d}-{(i + 1) * 10:2d}%"
        bar = "█" * count
        pct = count / len(values) * 100 if values else 0
        print(f"  {label_str}: {bar:<15} {count} ({pct:.0f}%)")


def print_worst_cases(results: list[dict[str, Any]], key: str, label: str, n: int = 3) -> None:
    sorted_results = sorted(results, key=lambda r: r[key])
    worst = sorted_results[:n]

    print(f"\n⚠️  Worst {n} cases by {label}:")
    for r in worst:
        print(f"  - {r['case_id']}")
        print(f"    {label}: {r[key] * 100:.1f}%")
        print(f"    Line Coverage: {r['line_coverage'] * 100:.1f}%")
        print(f"    Turns: {r['turns_used']}, Latency: {r['latency_ms']:.0f}ms")
        if r.get("error"):
            print(f"    Error: {r['error']}")
        print()


def print_summary_stats(results: list[dict[str, Any]], key: str, label: str) -> None:
    values = [r[key] * 100 for r in results]
    if not values:
        return

    values.sort()
    n = len(values)
    mean = sum(values) / n
    median = values[n // 2] if n % 2 else (values[n // 2 - 1] + values[n // 2]) / 2
    min_v, max_v = min(values), max(values)

    print(f"\n{label} Stats:")
    print(f"  Mean:   {mean:.1f}%")
    print(f"  Median: {median:.1f}%")
    print(f"  Min:    {min_v:.1f}%")
    print(f"  Max:    {max_v:.1f}%")
    print(f"  Range:  {max_v - min_v:.1f}%")


def main() -> None:
    # Default path
    default_path = Path(__file__).parent / "results" / "benchmark_results.json"
    path = sys.argv[1] if len(sys.argv) > 1 else str(default_path)

    if not Path(path).exists():
        print(f"Error: File not found: {path}")
        sys.exit(1)

    data = load_results(path)
    results = data.get("results", [])

    if not results:
        print("No results found.")
        sys.exit(1)

    print(f"Analyzing {len(results)} benchmark results from: {path}")

    # Detailed table
    print_detailed_table(results)

    # Distribution
    print_distribution(results, "line_precision_matched", "Line Prec(M)")

    # Summary stats
    print_summary_stats(results, "line_precision_matched", "Line Prec(M)")
    print_summary_stats(results, "line_coverage", "Line Coverage")

    # Worst cases
    print_worst_cases(results, "line_precision_matched", "Line Prec(M)", n=3)


if __name__ == "__main__":
    main()
