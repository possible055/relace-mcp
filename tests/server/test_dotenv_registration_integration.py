import os
import subprocess
import sys
from pathlib import Path

import pytest


def _clean_prefixed_env(env: dict[str, str], *, prefixes: tuple[str, ...]) -> dict[str, str]:
    cleaned = dict(env)
    for k in list(cleaned.keys()):
        for p in prefixes:
            if k.startswith(p):
                cleaned.pop(k, None)
                break
    return cleaned


@pytest.mark.usefixtures("clean_env")
def test_dotenv_path_enables_cloud_and_retrieval_tools(tmp_path: Path) -> None:
    env_file = tmp_path / ".test.env"
    env_file.write_text(
        "\n".join(
            [
                "RELACE_CLOUD_TOOLS=1",
                "MCP_SEARCH_RETRIEVAL=1",
                "MCP_RETRIEVAL_BACKEND=relace",
                "RELACE_API_KEY=rlc_dummy",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    repo_root = Path(__file__).resolve().parents[2]

    env = _clean_prefixed_env(
        os.environ,
        prefixes=("RELACE_", "SEARCH_", "APPLY_", "MCP_"),
    )
    env["MCP_DOTENV_PATH"] = str(env_file)

    # Ensure subprocess imports local workspace code.
    existing_pythonpath = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = (
        str(repo_root)
        if not existing_pythonpath
        else f"{repo_root}{os.pathsep}{existing_pythonpath}"
    )

    code = r"""
import asyncio

from fastmcp import Client

import relace_mcp.server as server

mcp = server.build_server(run_health_check=False)


async def _run() -> None:
    async with Client(mcp) as client:
        tools = await client.list_tools()
        tool_names = {t.name for t in tools}

        expected = {
            "cloud_sync",
            "cloud_search",
            "cloud_clear",
            "cloud_list",
            "agentic_retrieval",
        }
        missing = expected - tool_names
        assert not missing, f"missing tools: {sorted(missing)}; got: {sorted(tool_names)}"

        resources = await client.list_resources()
        resource_uris = {str(r.uri) for r in resources}
        assert "relace://cloud/status" in resource_uris


asyncio.run(_run())
"""

    proc = subprocess.run(
        [sys.executable, "-c", code],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, (
        f"subprocess failed\nstdout:\n{proc.stdout}\nstderr:\n{proc.stderr}\n"
    )
