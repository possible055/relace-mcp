import builtins

from click.testing import CliRunner

from benchmark.cli.web import main as web_main


def test_web_cli_help_lists_core_options() -> None:
    runner = CliRunner()
    result = runner.invoke(web_main, ["--help"])

    assert result.exit_code == 0
    assert "--experiments-root" in result.output
    assert "--host" in result.output
    assert "--port" in result.output


def test_web_cli_reports_combined_extra_when_uvicorn_missing(monkeypatch) -> None:
    runner = CliRunner()
    original_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "uvicorn":
            raise ImportError("missing uvicorn")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    result = runner.invoke(web_main, [])

    assert result.exit_code == 1
    assert "uv sync --extra benchmark --extra benchmark-web" in result.output


def test_web_cli_reports_combined_extra_when_web_import_fails(monkeypatch) -> None:
    runner = CliRunner()
    original_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "benchmark.web":
            raise ImportError("missing benchmark.web")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    result = runner.invoke(web_main, [])

    assert result.exit_code == 1
    assert "uv sync --extra benchmark --extra benchmark-web" in result.output
