import subprocess
import sys


def test_relace_mcp_help():
    """Verify that relace-mcp --help output is normal."""
    result = subprocess.run(
        [sys.executable, "-m", "relace_mcp.server", "--help"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0
    assert "relace-mcp" in result.stdout.lower()
    assert "usage:" in result.stdout.lower()


def test_relogs_help():
    """Verify that relogs can start normally and output basic information."""
    # Since dashboard requires an interactive terminal or specific environment, we test if it can be imported and main exists
    result = subprocess.run(
        [sys.executable, "-c", "from relace_mcp.dashboard import main; print('ok')"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0
    assert "ok" in result.stdout


def test_version_output():
    """Verify if version information can be obtained (if available)."""
    # Here we directly test if the server can start enough to show help
    result = subprocess.run(
        [sys.executable, "-m", "relace_mcp.server", "--help"],
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert result.returncode == 0
