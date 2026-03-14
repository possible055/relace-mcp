"""Regression tests for index_status probe loop (P2).

Verifies that probe=True always executes health checks for available local
backends regardless of MCP_RETRIEVAL_BACKEND value (auto/relace/none/codanna).
These tests will fail immediately if the RETRIEVAL_BACKEND guard is re-introduced.
"""

from unittest.mock import patch

import pytest

from relace_mcp.config import RelaceConfig
from relace_mcp.server import build_server

# check_backend_health is lazy-imported from ..repo.backends inside the probe branch.
# Patch it at the source module so the import inside the closure picks up the mock.
_BACKENDS_PKG = "relace_mcp.repo.backends"
_TOOLS_MOD = "relace_mcp.tools.__init__"


def _make_config(tmp_path) -> RelaceConfig:
    return RelaceConfig(api_key="rlc-test", base_dir=str(tmp_path))


@pytest.mark.parametrize(
    "retrieval_backend",
    ["auto", "relace", "none", "codanna", "chunkhound"],
)
@pytest.mark.asyncio
async def test_probe_not_skipped_for_local_backends_on_any_retrieval_backend(
    tmp_path, retrieval_backend: str
) -> None:
    """codanna/chunkhound probe should never be 'skipped' due to RETRIEVAL_BACKEND mismatch.

    With probe=True and both CLIs present, probe.status should be 'ok' or 'error',
    never 'skipped'. This test would catch a re-introduced RETRIEVAL_BACKEND guard.
    """
    config = _make_config(tmp_path)

    with (
        patch(f"{_TOOLS_MOD}._settings") as mock_settings,
        patch(f"{_TOOLS_MOD}.shutil.which", return_value="/usr/local/bin/fake"),
        patch(f"{_BACKENDS_PKG}.check_backend_health", return_value="ok") as mock_health,
    ):
        mock_settings.RETRIEVAL_BACKEND = retrieval_backend
        mock_settings.RELACE_CLOUD_TOOLS = False
        mock_settings.AGENTIC_RETRIEVAL_ENABLED = False

        server = build_server(config=config)

        from fastmcp import Client

        async with Client(server) as client:
            result = await client.call_tool("index_status", {"probe": True})

    payload = result.structured_content
    assert payload is not None

    for backend in ("codanna", "chunkhound"):
        probe = payload[backend]["probe"]
        assert probe is not None, f"{backend} probe must not be None"
        assert probe.get("status") != "skipped", (
            f"{backend} probe was skipped with RETRIEVAL_BACKEND={retrieval_backend!r}; "
            "this indicates the backend guard was re-introduced"
        )

    # Verify check_backend_health was actually invoked for both backends
    assert mock_health.call_count == 2, (
        f"Expected 2 health probe calls (codanna+chunkhound), got {mock_health.call_count}. "
        f"RETRIEVAL_BACKEND={retrieval_backend!r}"
    )


@pytest.mark.asyncio
async def test_probe_error_not_skipped_when_cli_missing(tmp_path) -> None:
    """When CLI is not found, probe.status should be 'error' (cli_not_found), not 'skipped'."""
    config = _make_config(tmp_path)

    with (
        patch(f"{_TOOLS_MOD}._settings") as mock_settings,
        patch(f"{_TOOLS_MOD}.shutil.which", return_value=None),
    ):
        mock_settings.RETRIEVAL_BACKEND = "auto"
        mock_settings.RELACE_CLOUD_TOOLS = False
        mock_settings.AGENTIC_RETRIEVAL_ENABLED = False

        server = build_server(config=config)

        from fastmcp import Client

        async with Client(server) as client:
            result = await client.call_tool("index_status", {"probe": True})

    payload = result.structured_content
    for backend in ("codanna", "chunkhound"):
        probe = payload[backend]["probe"]
        assert probe is not None
        assert probe.get("status") == "error", (
            f"{backend}: expected 'error' (cli_not_found) but got {probe.get('status')!r}"
        )
        assert probe.get("kind") == "cli_not_found"
