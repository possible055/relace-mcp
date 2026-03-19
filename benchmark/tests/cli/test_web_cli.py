from click.testing import CliRunner

from benchmark.cli.web import main as web_main


def test_web_cli_help_lists_core_options() -> None:
    runner = CliRunner()
    result = runner.invoke(web_main, ["--help"])

    assert result.exit_code == 0
    assert "--experiments-root" in result.output
    assert "--host" in result.output
    assert "--port" in result.output
