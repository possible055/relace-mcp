from pathlib import Path

import click

from .._config.paths import get_experiments_dir


@click.command()
@click.option(
    "--experiments-root",
    default=None,
    help="Experiments root directory (defaults to benchmark/artifacts/experiments).",
)
@click.option("--host", default="127.0.0.1", show_default=True, help="Bind host.")
@click.option("--port", default=8000, show_default=True, type=int, help="Bind port.")
@click.option("--no-open", is_flag=True, help="Reserved for future browser auto-open support.")
def main(experiments_root: str | None, host: str, port: int, no_open: bool) -> None:
    """Run the benchmark web analyzer API and static app server."""
    del no_open

    try:
        import uvicorn
    except ImportError as exc:
        raise click.ClickException(
            "benchmark web requires optional dependencies. Install with: uv sync --extra benchmark-web"
        ) from exc

    try:
        from benchmark.web import create_app
    except ImportError as exc:
        raise click.ClickException(
            "benchmark web requires optional dependencies. Install with: uv sync --extra benchmark-web"
        ) from exc

    root = Path(experiments_root) if experiments_root else get_experiments_dir()
    app = create_app(root)
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
