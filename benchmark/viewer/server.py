from importlib import resources
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse

from .discovery import list_experiments


def _frontend_dist_root() -> Path:
    return Path(__file__).resolve().parent / "frontend" / "dist"


def _fallback_html() -> str:
    with (
        resources.files("benchmark.viewer")
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
