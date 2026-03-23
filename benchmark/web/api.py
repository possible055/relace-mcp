import logging
from importlib import resources
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel

from benchmark.analysis.case_map_compare import build_case_map_compare
from benchmark.analysis.search_map_bundle import load_search_map_bundle

from .discovery import list_experiments

logger = logging.getLogger(__name__)


class BundleRequest(BaseModel):
    experiment_root: str


class CompareRequest(BaseModel):
    case_id: str
    experiment_roots: list[str]


def _resolve_within_root(root: Path, raw_path: str) -> Path:
    candidate = Path(raw_path)
    if not candidate.is_absolute():
        candidate = root / candidate

    resolved_root = root.resolve()
    resolved_candidate = candidate.resolve()  # lgtm[py/path-injection]
    try:
        resolved_candidate.relative_to(resolved_root)
    except ValueError:
        raise HTTPException(
            status_code=400, detail="Path must be inside experiments root."
        ) from None
    return resolved_candidate


def _frontend_dist_root() -> Path:
    return Path(__file__).resolve().parents[1] / "frontend" / "dist"


def _fallback_html() -> str:
    with (
        resources.files("benchmark.web")
        .joinpath("static/dev-index.html")
        .open("r", encoding="utf-8") as handle
    ):
        return handle.read()


def create_app(experiments_root: Path) -> FastAPI:
    app = FastAPI(title="Relace Benchmark Web", version="0.1.0")
    app.state.experiments_root = experiments_root.resolve()

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/experiments")
    def experiments() -> list[dict[str, Any]]:
        return list_experiments(app.state.experiments_root)

    @app.post("/api/search-map/bundle")
    def bundle(request: BundleRequest) -> dict[str, Any]:
        try:
            experiment_root = _resolve_within_root(
                app.state.experiments_root, request.experiment_root
            )
            traces_dir = experiment_root / "traces"  # lgtm[py/path-injection]
            if not traces_dir.is_dir():
                raise HTTPException(
                    status_code=404, detail="Experiment traces directory not found."
                )
            return load_search_map_bundle(experiment_root)
        except HTTPException:
            raise
        except Exception as exc:
            logger.exception(f"Failed to load bundle for {request.experiment_root}")
            raise HTTPException(status_code=500, detail="Internal server error.") from exc

    @app.post("/api/case-map/compare")
    def compare(request: CompareRequest) -> dict[str, Any]:
        if not request.experiment_roots:
            raise HTTPException(status_code=400, detail="experiment_roots must not be empty.")
        roots = [
            _resolve_within_root(app.state.experiments_root, root)
            for root in request.experiment_roots
        ]
        try:
            return build_case_map_compare(request.case_id, roots)
        except HTTPException:
            raise
        except Exception as exc:
            logger.exception(f"Failed to compare case {request.case_id!r}")
            raise HTTPException(status_code=500, detail="Internal server error.") from exc

    @app.get("/", response_class=HTMLResponse, response_model=None)
    def root():
        dist_root = _frontend_dist_root()
        index_path = dist_root / "index.html"
        if index_path.exists():
            return FileResponse(index_path)
        return HTMLResponse(_fallback_html())

    @app.get("/{asset_path:path}", response_model=None)
    def spa_assets(asset_path: str):
        if asset_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not found")

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
