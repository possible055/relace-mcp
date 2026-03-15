import asyncio
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from relace_mcp.clients.apply import ApplyLLMClient, ApplyResponse
from relace_mcp.tools.apply.core import _get_path_lock, _path_locks, apply_file_logic


@pytest.fixture(autouse=True)
def _clear_path_locks():
    _path_locks.clear()
    yield
    _path_locks.clear()


def _make_mock_backend(merged_code: str) -> AsyncMock:
    backend = AsyncMock(spec=ApplyLLMClient)
    backend.apply.return_value = ApplyResponse(
        merged_code=merged_code,
        usage={"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20},
    )
    return backend


class TestPathLock:
    def test_same_path_returns_same_lock(self) -> None:
        lock1 = _get_path_lock("/tmp/a.py")
        lock2 = _get_path_lock("/tmp/a.py")
        assert lock1 is lock2

    def test_different_paths_return_different_locks(self) -> None:
        lock1 = _get_path_lock("/tmp/a.py")
        lock2 = _get_path_lock("/tmp/b.py")
        assert lock1 is not lock2

    @pytest.mark.asyncio
    async def test_concurrent_edits_serialized(self, tmp_path: Path) -> None:
        """Two concurrent applies to same file should be serialized by lock."""
        source = tmp_path / "target.py"
        initial = "def hello_world():\n    return original_value\n"
        source.write_text(initial, encoding="utf-8", newline="")

        order: list[str] = []

        async def slow_apply(request):
            order.append("start")
            await asyncio.sleep(0.05)
            order.append("end")
            return ApplyResponse(
                merged_code=initial,  # Return unchanged to avoid conflict
                usage={},
            )

        backend = AsyncMock(spec=ApplyLLMClient)
        backend.apply.side_effect = slow_apply

        # Snippet needs anchors that pass precheck
        edit = "def hello_world():\n    return original_value\n"

        async def do_apply():
            return await apply_file_logic(backend, str(source), edit, None, str(tmp_path))

        await asyncio.gather(do_apply(), do_apply())
        # With lock, calls are serialized: start, end, start, end
        assert order == ["start", "end", "start", "end"]


class TestContentConflict:
    @pytest.mark.asyncio
    async def test_file_changed_during_apply(self, tmp_path: Path) -> None:
        """Should return CONTENT_CONFLICT when file changes between read and write."""
        source = tmp_path / "conflict.py"
        initial = "def process_incoming_request():\n    return original_response_value\n"
        source.write_text(initial, encoding="utf-8", newline="")

        merged = "def process_incoming_request():\n    return modified_response_value\n"
        backend = _make_mock_backend(merged)

        original_apply = backend.apply

        async def apply_and_tamper(request):
            result = await original_apply(request)
            # Tamper with file after LLM returns but before conflict check
            source.write_text(
                "def process_incoming_request():\n    return tampered_externally\n",
                encoding="utf-8",
                newline="",
            )
            return result

        backend.apply = apply_and_tamper

        edit = "def process_incoming_request():\n    return modified_response_value\n"
        result = await apply_file_logic(backend, str(source), edit, None, str(tmp_path))

        assert result["status"] == "error"
        assert result["code"] == "CONTENT_CONFLICT"


class TestBlastRadiusGuard:
    @pytest.mark.asyncio
    async def test_rejects_full_file_rewrite(self, tmp_path: Path) -> None:
        """Should reject when LLM rewrites >80% of the file."""
        # 200-line file; blast_limit = max(200*0.8, 100) = 160
        lines = [f"variable_{i} = compute_value({i})" for i in range(200)]
        source = tmp_path / "blast.py"
        source.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="")

        edit_snippet = (
            "variable_0 = compute_value(0)\n"
            "variable_1 = compute_value(1)\n"
            "# ... existing code ...\n"
        )

        # LLM rewrites all 200 lines → max(200 del, 200 add) = 200 > 160
        merged_lines = [f"completely_different_{i} = {i}" for i in range(200)]
        merged_code = "\n".join(merged_lines) + "\n"

        backend = _make_mock_backend(merged_code)
        result = await apply_file_logic(backend, str(source), edit_snippet, None, str(tmp_path))

        assert result["status"] == "error"
        assert result["code"] == "BLAST_RADIUS_EXCEEDED"

    @pytest.mark.asyncio
    async def test_accepts_diff_under_100_line_floor(self, tmp_path: Path) -> None:
        """Should accept when lines touched is under 100 (absolute floor)."""
        # 30-line file; blast_limit = max(30*0.8, 100) = 100
        lines = [f"variable_{i} = compute_value({i})" for i in range(30)]
        source = tmp_path / "moderate.py"
        source.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="")

        edit_snippet = (
            "variable_0 = compute_value(0)\n"
            "variable_1 = compute_value(1)\n"
            "# ... existing code ...\n"
        )
        # Changing 25 lines → max(25 del, 25 add) = 25; limit = 100 → passes
        merged_lines = list(lines)
        for i in range(5, 30):
            merged_lines[i] = f"updated_{i} = new_value({i})"
        merged_code = "\n".join(merged_lines) + "\n"

        backend = _make_mock_backend(merged_code)
        result = await apply_file_logic(backend, str(source), edit_snippet, None, str(tmp_path))

        assert result.get("code") != "BLAST_RADIUS_EXCEEDED"

    @pytest.mark.asyncio
    async def test_rejects_pure_delete_to_empty(self, tmp_path: Path) -> None:
        """Should reject when LLM deletes most of a file (pure deletion)."""
        # 200-line file of constants (no top-level symbols) → blast_limit = 160
        lines = [f"constant_value_{i} = compute({i})" for i in range(200)]
        source = tmp_path / "constants.py"
        source.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="")

        edit_snippet = (
            "constant_value_0 = compute(0)\n"
            "constant_value_1 = compute(1)\n"
            "# ... existing code ...\n"
        )
        # LLM returns empty file → max(0 added, 200 deleted) = 200 > 160
        backend = _make_mock_backend("")

        result = await apply_file_logic(backend, str(source), edit_snippet, None, str(tmp_path))

        assert result["status"] == "error"
        assert result["code"] == "BLAST_RADIUS_EXCEEDED"

    @pytest.mark.asyncio
    async def test_accepts_normal_diff(self, tmp_path: Path) -> None:
        """Should accept when diff is proportional to snippet scope."""
        source = tmp_path / "normal.py"
        source.write_text(
            "def process_incoming_request():\n    return original_response_value\n\ndef handle_outgoing_response():\n    return 2\n",
            encoding="utf-8",
            newline="",
        )

        edit_snippet = (
            "def process_incoming_request():\n"
            "    return new_replaced_response\n"
            "# ... existing code ..."
        )
        merged_code = "def process_incoming_request():\n    return new_replaced_response\n\ndef handle_outgoing_response():\n    return 2\n"

        backend = _make_mock_backend(merged_code)

        result = await apply_file_logic(backend, str(source), edit_snippet, None, str(tmp_path))

        assert result["status"] == "ok"

    @pytest.mark.asyncio
    async def test_remove_directive_bypasses_guard(self, tmp_path: Path) -> None:
        """Should accept removal of large function via // remove directive."""
        # Create a file with a 20-line function
        func_lines = [f"    line_{i} = compute({i})" for i in range(18)]
        initial = (
            "def small_helper():\n    return 1\n\n"
            "def big_function():\n" + "\n".join(func_lines) + "\n\n"
            "def another_helper():\n    return 2\n"
        )
        source = tmp_path / "remove_blast.py"
        source.write_text(initial, encoding="utf-8", newline="")

        # Snippet: 2 anchors + remove directive
        edit_snippet = (
            "def small_helper():\n"
            "    return 1\n"
            "# remove big_function\n"
            "def another_helper():\n"
            "# ... existing code ...\n"
        )
        # LLM returns file without big_function
        merged_code = "def small_helper():\n    return 1\n\ndef another_helper():\n    return 2\n"

        backend = _make_mock_backend(merged_code)
        result = await apply_file_logic(backend, str(source), edit_snippet, None, str(tmp_path))

        assert result["status"] == "ok"


class TestSymbolPreservationGuard:
    @pytest.mark.asyncio
    async def test_rejects_when_symbol_lost(self, tmp_path: Path) -> None:
        """Should reject when LLM merge accidentally drops a function."""
        source = tmp_path / "symbols.py"
        initial = (
            "def compute_alpha_value():\n    return 1\n\n"
            "def compute_beta_value():\n    return 2\n\n"
            "def compute_gamma_value():\n    return 3\n"
        )
        source.write_text(initial, encoding="utf-8", newline="")

        # Snippet modifies alpha, provides anchors; but LLM drops beta
        edit_snippet = (
            "def compute_alpha_value():\n"
            "    return 1\n"
            "def compute_gamma_value():\n"
            "# ... existing code ...\n"
        )
        merged_code = (
            "def compute_alpha_value():\n    return 1\n\ndef compute_gamma_value():\n    return 3\n"
        )

        backend = _make_mock_backend(merged_code)
        result = await apply_file_logic(backend, str(source), edit_snippet, None, str(tmp_path))

        assert result["status"] == "error"
        assert result["code"] == "SYMBOL_LOST"
        assert "compute_beta_value" in result["message"]

    @pytest.mark.asyncio
    async def test_allows_when_remove_directive_used(self, tmp_path: Path) -> None:
        """Should accept removal when explicitly requested via remove directive."""
        source = tmp_path / "symbols_rm.py"
        initial = (
            "def compute_alpha_value():\n    return 1\n\n"
            "def compute_beta_value():\n    return 2\n\n"
            "def compute_gamma_value():\n    return 3\n"
        )
        source.write_text(initial, encoding="utf-8", newline="")

        edit_snippet = (
            "def compute_alpha_value():\n"
            "    return 1\n"
            "# remove compute_beta_value\n"
            "def compute_gamma_value():\n"
            "# ... existing code ...\n"
        )
        merged_code = (
            "def compute_alpha_value():\n    return 1\n\ndef compute_gamma_value():\n    return 3\n"
        )

        backend = _make_mock_backend(merged_code)
        result = await apply_file_logic(backend, str(source), edit_snippet, None, str(tmp_path))

        assert result["status"] == "ok"

    @pytest.mark.asyncio
    async def test_allows_when_no_symbols_lost(self, tmp_path: Path) -> None:
        """Should accept normal edit that preserves all symbols."""
        source = tmp_path / "symbols_ok.py"
        initial = (
            "def compute_alpha_value():\n    return 1\n\ndef compute_beta_value():\n    return 2\n"
        )
        source.write_text(initial, encoding="utf-8", newline="")

        edit_snippet = (
            "def compute_alpha_value():\n"
            "    return 42\n"
            "def compute_beta_value():\n"
            "# ... existing code ...\n"
        )
        merged_code = (
            "def compute_alpha_value():\n    return 42\n\ndef compute_beta_value():\n    return 2\n"
        )

        backend = _make_mock_backend(merged_code)
        result = await apply_file_logic(backend, str(source), edit_snippet, None, str(tmp_path))

        assert result["status"] == "ok"


class TestImprovedErrorMessage:
    @pytest.mark.asyncio
    async def test_anchor_error_includes_symbol_hints(self, tmp_path: Path) -> None:
        """NEEDS_MORE_CONTEXT error should include file symbol names."""
        source = tmp_path / "hints.py"
        initial = (
            "def process_request():\n    return 1\n\n"
            "def handle_response():\n    return 2\n\n"
            "class MyService:\n    pass\n"
        )
        source.write_text(initial, encoding="utf-8", newline="")

        # Snippet with no matching anchors
        edit_snippet = "def totally_unrelated_anchor_xyz():\n    return 999\n"

        backend = _make_mock_backend("")
        result = await apply_file_logic(backend, str(source), edit_snippet, None, str(tmp_path))

        assert result["status"] == "error"
        assert result["code"] == "NEEDS_MORE_CONTEXT"
        # Should contain symbol hints
        assert "The file defines:" in result["message"]
        assert "process_request" in result["message"]
        assert "handle_response" in result["message"]
        assert "MyService" in result["message"]
