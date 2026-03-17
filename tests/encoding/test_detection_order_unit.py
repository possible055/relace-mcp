import pytest
from fastmcp import Client

from relace_mcp.config import RelaceConfig
from relace_mcp.encoding import set_project_encoding
from relace_mcp.server import build_server


@pytest.mark.asyncio
async def test_encoding_detection_runs_after_resolve_base_dir(monkeypatch, tmp_path):
    # Ensure global encoding state does not leak across tests.
    set_project_encoding(None)

    order: list[str] = []
    detect_calls: list[str] = []

    async def fake_resolve_base_dir(_config_base_dir, _ctx=None):
        order.append("resolve")
        return str(tmp_path), "test"

    def fake_detect_project_encoding(path, *, sample_limit):
        assert order and order[-1] == "resolve"
        detect_calls.append(str(path))
        return None

    async def fake_apply_file_logic(
        *, backend, file_path, edit_snippet, instruction, base_dir, extra_paths=(), on_progress=None
    ):
        del backend, edit_snippet, instruction, extra_paths, on_progress
        return {"status": "ok", "path": file_path, "diff": ""}

    def _noop_bg_chunkhound_index(_base_dir: str) -> None:
        return

    def _noop_bg_codanna_index(_file_path: str, _base_dir: str) -> None:
        return

    monkeypatch.setattr("relace_mcp.tools.mcp_apply.resolve_base_dir", fake_resolve_base_dir)
    monkeypatch.setattr(
        "relace_mcp.encoding.detect_project_encoding",
        fake_detect_project_encoding,
    )
    monkeypatch.setattr("relace_mcp.tools.mcp_apply.apply_file_logic", fake_apply_file_logic)
    monkeypatch.setattr(
        "relace_mcp.repo.backends.schedule_bg_chunkhound_index",
        _noop_bg_chunkhound_index,
    )
    monkeypatch.setattr(
        "relace_mcp.repo.backends.schedule_bg_codanna_index",
        _noop_bg_codanna_index,
    )

    server = build_server(
        config=RelaceConfig(
            api_key="test-api-key",
            base_dir=None,
            default_encoding=None,
        ),
        run_health_check=False,
    )

    async with Client(server) as client:
        await client.call_tool(
            "fast_apply",
            {"path": "test.py", "edit_snippet": "print('hi')\n", "instruction": ""},
        )
        await client.call_tool(
            "fast_apply",
            {"path": "test.py", "edit_snippet": "print('hi2')\n", "instruction": ""},
        )

    async with Client(server) as client:
        await client.call_tool(
            "fast_apply",
            {"path": "test.py", "edit_snippet": "print('hi3')\n", "instruction": ""},
        )

    assert order.count("resolve") == 3
    assert len(detect_calls) == 2
    assert detect_calls == [str(tmp_path), str(tmp_path)]
