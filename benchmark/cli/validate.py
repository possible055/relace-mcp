import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import click

from ..analysis.function_scope import extract_function_scopes
from ..config import get_benchmark_dir, get_repos_dir
from ..datasets.filtered import FilteredCase, load_filtered_dataset
from ..runner.git import ensure_repo


@dataclass
class ValidationResult:
    case_id: str
    valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "valid": self.valid,
            "errors": self.errors,
            "warnings": self.warnings,
        }


@dataclass
class ValidationSummary:
    total_cases: int
    valid_cases: int
    invalid_cases: int
    total_errors: int
    total_warnings: int
    results: list[ValidationResult]

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_cases": self.total_cases,
            "valid_cases": self.valid_cases,
            "invalid_cases": self.invalid_cases,
            "validation_rate": self.valid_cases / self.total_cases if self.total_cases else 0,
            "total_errors": self.total_errors,
            "total_warnings": self.total_warnings,
            "results": [r.to_dict() for r in self.results],
        }


def _validate_file_exists(repo_path: Path, file_path: str) -> str | None:
    """Check if file exists in repo."""
    full_path = repo_path / file_path
    if not full_path.exists():
        return f"File not found: {file_path}"
    return None


def _validate_line_range(repo_path: Path, file_path: str, start: int, end: int) -> str | None:
    """Check if line range is valid."""
    full_path = repo_path / file_path
    if not full_path.exists():
        return None  # Already reported by file check

    try:
        lines = full_path.read_text(encoding="utf-8", errors="replace").splitlines()
        total_lines = len(lines)

        if start < 1:
            return f"{file_path}: Invalid start line {start} (must be >= 1)"
        if end < start:
            return f"{file_path}: Invalid range [{start}, {end}] (end < start)"
        if end > total_lines:
            return f"{file_path}: Line {end} exceeds file length ({total_lines} lines)"
    except Exception as e:
        return f"{file_path}: Error reading file: {e}"

    return None


def _validate_function_name(
    repo_path: Path, file_path: str, func_name: str, start: int, end: int
) -> str | None:
    """Check if function name matches AST at specified lines."""
    if not file_path.endswith(".py"):
        return None  # Skip non-Python files

    full_path = repo_path / file_path
    if not full_path.exists():
        return None

    # Extract functions at these lines
    lines = set(range(start, end + 1))
    scopes = extract_function_scopes(full_path, lines, relative_path=file_path)

    if not scopes:
        return f"{file_path}: No function found at lines {start}-{end}"

    found_names = [s.function_name for s in scopes]
    if func_name not in found_names:
        return f"{file_path}: Expected function '{func_name}', found {found_names}"

    return None


def _validate_solvability_evidence(query: str, evidence: list[str]) -> list[str]:
    """Check if evidence terms appear in query."""
    warnings = []
    query_lower = query.lower()

    for term in evidence:
        if term.lower() not in query_lower:
            warnings.append(f"Evidence term '{term}' not found in query")

    return warnings


def validate_case(case: FilteredCase, repos_dir: Path, verbose: bool) -> ValidationResult:
    """Validate a single case."""
    errors: list[str] = []
    warnings: list[str] = []

    # Prepare repo
    try:
        repo_path = ensure_repo(
            repos_dir=repos_dir,
            repo=case.repo,
            base_commit=case.base_commit,
            verbose=verbose,
        )
    except Exception as e:
        return ValidationResult(
            case_id=case.id,
            valid=False,
            errors=[f"Failed to prepare repo: {e}"],
        )

    # Validate hard_gt
    for gt in case.hard_gt:
        path = gt.get("path", "")
        func_name = gt.get("function", "")
        range_data = gt.get("range", [])

        # File exists
        err = _validate_file_exists(repo_path, path)
        if err:
            errors.append(f"[hard_gt] {err}")
            continue

        # Line range valid
        if len(range_data) == 2:
            err = _validate_line_range(repo_path, path, range_data[0], range_data[1])
            if err:
                errors.append(f"[hard_gt] {err}")

            # Function name matches
            if func_name:
                err = _validate_function_name(
                    repo_path, path, func_name, range_data[0], range_data[1]
                )
                if err:
                    errors.append(f"[hard_gt] {err}")

    # Validate soft_context
    for ctx in case.soft_context:
        path = ctx.get("path", "")
        func_name = ctx.get("function", "")
        range_data = ctx.get("range", [])

        err = _validate_file_exists(repo_path, path)
        if err:
            errors.append(f"[soft_context] {err}")
            continue

        if len(range_data) == 2:
            err = _validate_line_range(repo_path, path, range_data[0], range_data[1])
            if err:
                errors.append(f"[soft_context] {err}")

            if func_name:
                err = _validate_function_name(
                    repo_path, path, func_name, range_data[0], range_data[1]
                )
                if err:
                    errors.append(f"[soft_context] {err}")

    # Validate solvability evidence
    evidence = case.solvability.get("evidence", [])
    evidence_warnings = _validate_solvability_evidence(case.query, evidence)
    warnings.extend(evidence_warnings)

    return ValidationResult(
        case_id=case.id,
        valid=len(errors) == 0,
        errors=errors,
        warnings=warnings,
    )


@click.command()
@click.option(
    "--input",
    "input_path",
    default="data/filtered.jsonl",
    show_default=True,
    help="Filtered dataset path",
)
@click.option(
    "--output",
    "output_path",
    default=None,
    help="Output validation report (default: print to stdout)",
)
@click.option("--limit", default=None, type=int, help="Maximum cases to validate")
@click.option("-v", "--verbose", is_flag=True, help="Verbose output")
def main(input_path: str, output_path: str | None, limit: int | None, verbose: bool) -> None:
    """Validate filtered dataset."""
    benchmark_dir = get_benchmark_dir()
    repos_dir = get_repos_dir()

    click.echo("=== Dataset Validation ===")
    click.echo(f"Input: {input_path}")

    # Load dataset
    try:
        cases = load_filtered_dataset(input_path, limit=limit)
    except Exception as e:
        click.echo(f"Error loading dataset: {e}", err=True)
        sys.exit(1)

    click.echo(f"Loaded {len(cases)} cases")

    # Validate each case
    results: list[ValidationResult] = []

    for i, case in enumerate(cases):
        if verbose:
            click.echo(f"[{i + 1}/{len(cases)}] {case.id}")

        result = validate_case(case, repos_dir, verbose=verbose)
        results.append(result)

        if verbose:
            status = "✓" if result.valid else "✗"
            click.echo(f"  {status} {len(result.errors)} errors, {len(result.warnings)} warnings")
            for err in result.errors:
                click.echo(f"    ERROR: {err}")
            for warn in result.warnings[:3]:  # Limit warnings
                click.echo(f"    WARN: {warn}")

    # Build summary
    valid_count = sum(1 for r in results if r.valid)
    summary = ValidationSummary(
        total_cases=len(cases),
        valid_cases=valid_count,
        invalid_cases=len(cases) - valid_count,
        total_errors=sum(len(r.errors) for r in results),
        total_warnings=sum(len(r.warnings) for r in results),
        results=results,
    )

    # Output
    if output_path:
        resolved_output = (
            Path(output_path) if Path(output_path).is_absolute() else (benchmark_dir / output_path)
        )
        with resolved_output.open("w", encoding="utf-8") as f:
            json.dump(summary.to_dict(), f, indent=2, ensure_ascii=False)
        click.echo(f"\nReport saved to: {resolved_output}")
    else:
        click.echo("\n" + "=" * 40)
        click.echo("VALIDATION SUMMARY")
        click.echo("=" * 40)
        click.echo(f"Total cases:     {summary.total_cases}")
        click.echo(f"Valid cases:     {summary.valid_cases}")
        click.echo(f"Invalid cases:   {summary.invalid_cases}")
        click.echo(f"Validation rate: {summary.valid_cases / summary.total_cases:.1%}")
        click.echo(f"Total errors:    {summary.total_errors}")
        click.echo(f"Total warnings:  {summary.total_warnings}")


if __name__ == "__main__":
    main()
