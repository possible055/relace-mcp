import json
from pathlib import Path

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient

from benchmark.viewer import create_app


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
    reports_dir = experiment_root / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
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
    (reports_dir / "search_map.bundle.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
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
    (run_root / "reports" / "summary.report.json").write_text(
        json.dumps(
            {
                "metadata": {
                    "experiment": {
                        "type": "run",
                        "name": "run-a",
                        "root": str(run_root),
                    },
                    "search": {
                        "provider": "openai",
                        "model": "gpt-5-mini",
                        "max_turns": 8,
                        "temperature": 0.2,
                    },
                    "run": {
                        "search_mode": "agentic",
                        "cases_loaded": 2,
                    },
                }
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (grid_root / "reports").mkdir(parents=True, exist_ok=True)
    (grid_root / "reports" / "summary.report.json").write_text(
        json.dumps(
            {
                "metadata": {
                    "experiment": {
                        "type": "grid",
                        "name": "grid-a",
                        "root": str(grid_root),
                    },
                    "search": {
                        "provider": "openai",
                        "model": "gpt-5.4",
                        "max_turns": 12,
                        "temperature": 0.0,
                    },
                    "run": {
                        "search_mode": "agentic",
                    },
                }
            }
        )
        + "\n",
        encoding="utf-8",
    )

    client = TestClient(create_app(tmp_path))
    response = client.get("/api/experiments")

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 2
    names = {item["name"] for item in payload}
    assert names == {"run-a", "grid-a"}
    run_item = next(item for item in payload if item["name"] == "run-a")
    assert run_item["has_bundle"] is True
    assert run_item["case_count"] == 0


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
