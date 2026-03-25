import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient

from benchmark.experiments.models import ExperimentManifest, ExperimentState
from benchmark.web import create_app


def _write_bundle(
    experiment_root: Path,
    *,
    experiment_name: str,
    experiment_type: str = "run",
    provider: str = "openai",
    model: str = "gpt-5-mini",
    search_mode: str = "agentic",
    max_turns: int = 8,
    temperature: float = 0.2,
    cases: list[dict] | None = None,
) -> None:
    analysis_dir = experiment_root / "analysis"
    analysis_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": "1.0",
        "kind": "search_map_bundle",
        "experiment": {
            "name": experiment_name,
            "root": str(experiment_root),
            "type": experiment_type,
            "search": {
                "provider": provider,
                "model": model,
                "max_turns": max_turns,
                "temperature": temperature,
            },
            "run": {
                "search_mode": search_mode,
            },
        },
        "summary": {
            "cases": len(cases or []),
        },
        "cases": cases or [],
    }
    (analysis_dir / "search-map.bundle.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _write_experiment_summary(
    experiment_root: Path,
    *,
    experiment_name: str,
    experiment_type: str,
    provider: str,
    model: str,
    max_turns: int,
    temperature: float,
    search_mode: str,
    case_count: int,
) -> None:
    manifest = ExperimentManifest(
        experiment_id=experiment_root.name,
        kind=experiment_type,
        name=experiment_name,
        experiment_root=experiment_root,
        created_at=datetime.now(UTC),
        dataset={"name": "locbench", "case_count": case_count},
        search={
            "provider": provider,
            "model": model,
            "max_turns": max_turns,
            "temperature": temperature,
            "search_mode": search_mode,
        },
    )
    manifest.save()
    ExperimentState(
        status="completed",
        total_cases=case_count,
        completed_cases=case_count,
        failed_cases=0,
    ).save(experiment_root)
    (experiment_root / "summary.json").write_text(
        json.dumps(
            {
                "metadata": {
                    "experiment": {
                        "type": experiment_type,
                        "name": experiment_name,
                        "root": str(experiment_root),
                    },
                    "search": {
                        "provider": provider,
                        "model": model,
                        "max_turns": max_turns,
                        "temperature": temperature,
                    },
                    "run": {
                        "search_mode": search_mode,
                        "cases_loaded": case_count,
                    },
                },
                "manifest": manifest.to_dict(),
                "state": {
                    "status": "completed",
                    "total_cases": case_count,
                    "completed_cases": case_count,
                    "failed_cases": 0,
                },
                "stats": {
                    "completion_rate": 1.0,
                    "avg_file_recall": 0.5,
                    "avg_file_precision": 0.5,
                },
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def test_health_and_static_fallback(tmp_path: Path) -> None:
    client = TestClient(create_app(tmp_path))

    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

    root_response = client.get("/")
    assert root_response.status_code == 200
    assert (
        "Relace Benchmark Web" in root_response.text
        or '<div id="root"></div>' in root_response.text
    )


def test_experiments_endpoint_lists_runs_and_grid(tmp_path: Path) -> None:
    run_root = tmp_path / "run-a"
    grid_root = tmp_path / "grid-a"
    _write_bundle(run_root, experiment_name="run-a")
    _write_experiment_summary(
        run_root,
        experiment_name="run-a",
        experiment_type="run",
        provider="openai",
        model="gpt-5-mini",
        max_turns=8,
        temperature=0.2,
        search_mode="agentic",
        case_count=2,
    )
    _write_experiment_summary(
        grid_root,
        experiment_name="grid-a",
        experiment_type="grid",
        provider="openai",
        model="gpt-5.4",
        max_turns=12,
        temperature=0.0,
        search_mode="agentic",
        case_count=0,
    )

    client = TestClient(create_app(tmp_path))
    response = client.get("/api/experiments")

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 2
    names = {item["name"] for item in payload["items"]}
    assert names == {"run-a", "grid-a"}
    run_item = next(item for item in payload["items"] if item["name"] == "run-a")
    assert run_item["case_count"] == 2


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", "/api/search-map/bundle"),
        ("post", "/api/search-map/bundle"),
        ("post", "/api/cases/intersection"),
        ("post", "/api/run-case/detail"),
        ("post", "/api/case-map/compare"),
    ],
)
def test_removed_api_endpoints_return_not_found(
    tmp_path: Path,
    method: str,
    path: str,
) -> None:
    client = TestClient(create_app(tmp_path))
    if method == "get":
        response = client.get(path)
    else:
        response = getattr(client, method)(path, json={})

    assert response.status_code == 404
    assert response.json() == {"detail": "Not found"}
