from importlib import resources
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse

from benchmark.experiments.index import ExperimentIndex
from benchmark.experiments.store import ExperimentStore

from .api.cases import router as cases_router
from .api.experiments import router as experiments_router
from .api.metrics import router as metrics_router
from .discovery import list_experiments


def _frontend_dist_root() -> Path:
    return Path(__file__).resolve().parent / "frontend" / "dist"


def _fallback_html() -> str:
    with (
        resources.files("benchmark.web")
        .joinpath("static/dev-index.html")
        .open("r", encoding="utf-8") as handle
    ):
        return handle.read()


def create_app(experiments_root: Path) -> FastAPI:
    app = FastAPI(title="Relace Benchmark Web", version="0.2.0")
    resolved_root = experiments_root.resolve()
    store = ExperimentStore(resolved_root)
    index = ExperimentIndex(resolved_root.parent / "index.sqlite3")
    index.rebuild(store)

    app.state.experiments_root = resolved_root
    app.state.experiment_store = store
    app.state.experiment_index = index

    app.include_router(experiments_router)
    app.include_router(cases_router)
    app.include_router(metrics_router)

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/experiments/legacy")
    def experiments_legacy() -> list[dict[str, Any]]:
        return list_experiments(app.state.experiments_root)

    @app.api_route(
        "/api/{api_path:path}",
        methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"],
    )
    def missing_api(api_path: str) -> None:
        raise HTTPException(status_code=404, detail="Not found")

    @app.get("/", response_class=HTMLResponse, response_model=None)
    def root():
        dist_root = _frontend_dist_root()
        index_path = dist_root / "index.html"
        if index_path.exists():
            return FileResponse(index_path)
        return HTMLResponse(_fallback_html())

    @app.get("/{asset_path:path}", response_model=None)
    def spa_assets(asset_path: str):
        dist_root = _frontend_dist_root()
        candidate = (dist_root / asset_path).resolve()
        if (
            dist_root.exists()
            and candidate.is_relative_to(dist_root.resolve())
            and candidate.is_file()
        ):
            return FileResponse(candidate)

        index_path = dist_root / "index.html"
        if index_path.exists():
            return FileResponse(index_path)
        return HTMLResponse(_fallback_html())

    return app
