import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from relace_mcp.clients.apply import ApplyResponse
from relace_mcp.config import RelaceConfig
from relace_mcp.tools.apply import apply_file_logic
from relace_mcp.tools.apply.file_io import set_project_encoding
from relace_mcp.tools.apply.logging import log_event
from relace_mcp.utils import MAX_FILE_SIZE_BYTES, validate_file_path


class TestValidateFilePath:
    """Test validate_file_path security function."""

    def test_valid_absolute_path(self, tmp_path: Path) -> None:
        """Should accept valid absolute paths within base_dir."""
        test_file = tmp_path / "test.py"
        test_file.write_text("content")

        result = validate_file_path(str(test_file), base_dir=str(tmp_path))
        assert result == test_file.resolve()

    def test_empty_path_raises(self, tmp_path: Path) -> None:
        """Should reject empty paths."""
        with pytest.raises(RuntimeError, match="cannot be empty"):
            validate_file_path("", base_dir=str(tmp_path))

    def test_whitespace_only_path_raises(self, tmp_path: Path) -> None:
        """Should reject whitespace-only paths."""
        with pytest.raises(RuntimeError, match="cannot be empty"):
            validate_file_path("   ", base_dir=str(tmp_path))

    def test_path_within_base_dir(self, tmp_path: Path) -> None:
        """Should accept paths within base_dir."""
        test_file = tmp_path / "subdir" / "test.py"
        test_file.parent.mkdir(parents=True, exist_ok=True)
        test_file.write_text("content")

        result = validate_file_path(str(test_file), base_dir=str(tmp_path))
        assert result == test_file.resolve()

    def test_path_outside_base_dir_raises(self, tmp_path: Path) -> None:
        """Should reject paths outside base_dir (path traversal protection)."""
        outside_path = tmp_path.parent / "outside.py"

        with pytest.raises(RuntimeError, match="outside allowed directory"):
            validate_file_path(str(outside_path), base_dir=str(tmp_path))

    def test_path_traversal_attempt_blocked(self, tmp_path: Path) -> None:
        """Should block path traversal attempts."""
        traversal_path = str(tmp_path / ".." / ".." / "etc" / "passwd")

        with pytest.raises(RuntimeError, match="outside allowed directory"):
            validate_file_path(traversal_path, base_dir=str(tmp_path))


class TestLogEvent:
    """Test log_interaction function."""

    def test_writes_json_line(self, mock_log_path: Path) -> None:
        """Should write JSON event to log file."""
        log_event({"kind": "test", "message": "hello"})
        content = mock_log_path.read_text()
        logged = json.loads(content.strip())
        assert logged["kind"] == "test"
        assert logged["message"] == "hello"
        assert "timestamp" in logged

    def test_appends_to_existing_log(self, mock_log_path: Path) -> None:
        """Should append to existing log file."""
        log_event({"event": 1})
        log_event({"event": 2})
        lines = mock_log_path.read_text().strip().split("\n")
        assert len(lines) == 2

    def test_creates_parent_directories(self, tmp_path: Path) -> None:
        """Should create parent directories if needed."""
        log_path = tmp_path / "deep" / "nested" / "dir" / "log.json"
        with (
            patch("relace_mcp.config.settings.RELACE_LOGGING", True),
            patch("relace_mcp.config.settings.LOG_PATH", log_path),
        ):
            log_event({"test": True})
        assert log_path.exists()

    def test_preserves_existing_timestamp(self, mock_log_path: Path) -> None:
        """Should not overwrite existing timestamp."""
        log_event({"kind": "test", "timestamp": "2024-01-01T00:00:00Z"})
        logged = json.loads(mock_log_path.read_text().strip())
        assert logged["timestamp"] == "2024-01-01T00:00:00Z"

    def test_handles_log_failure_gracefully(self, tmp_path: Path) -> None:
        """Should not raise on log write failure (e.g., path is a directory)."""
        # Using directory as log path will fail, but should not raise exception
        with (
            patch("relace_mcp.config.settings.RELACE_LOGGING", True),
            patch("relace_mcp.config.settings.LOG_PATH", tmp_path),
        ):
            log_event({"test": True})  # Should not raise exception


class TestApplyFileLogicSuccess:
    """Test apply_file_logic successful scenarios."""

    @pytest.mark.asyncio
    async def test_successful_apply(
        self,
        mock_config: RelaceConfig,
        mock_backend: AsyncMock,
        temp_source_file: Path,
        successful_api_response: dict[str, Any],
        tmp_path: Path,
    ) -> None:
        """Should successfully apply edit and return UDiff."""
        mock_backend.apply.return_value = ApplyResponse(
            merged_code=successful_api_response["choices"][0]["message"]["content"],
            usage=successful_api_response["usage"],
        )

        # edit_snippet contains anchor lines that exist in temp_source_file
        # temp_source_file: def hello():\n    print('Hello')\n\ndef goodbye():\n    print('Goodbye')\n
        result = await apply_file_logic(
            backend=mock_backend,
            file_path=str(temp_source_file),
            edit_snippet="def hello():\n    print('Hello')\n\ndef goodbye():\n    print('Hello, World!')\n",
            instruction="Add feature",
            base_dir=str(tmp_path),
        )

        assert result["status"] == "ok"
        assert result["message"] == "Applied code changes successfully."
        assert result["diff"] is not None
        assert "--- before" in result["diff"]
        assert "+++ after" in result["diff"]

        # Verify file was written
        assert (
            temp_source_file.read_text()
            == successful_api_response["choices"][0]["message"]["content"]
        )

    @pytest.mark.asyncio
    async def test_logs_success_event(
        self,
        mock_config: RelaceConfig,
        mock_backend: AsyncMock,
        temp_source_file: Path,
        successful_api_response: dict[str, Any],
        tmp_path: Path,
        mock_log_path: Path,
    ) -> None:
        """Should log success event."""
        mock_backend.apply.return_value = ApplyResponse(
            merged_code=successful_api_response["choices"][0]["message"]["content"],
            usage=successful_api_response["usage"],
        )

        # edit_snippet contains anchor lines that exist in temp_source_file
        await apply_file_logic(
            backend=mock_backend,
            file_path=str(temp_source_file),
            edit_snippet="def hello():\n    print('Hello')\n\ndef goodbye():\n    print('Hello, World!')\n",
            instruction=None,
            base_dir=str(tmp_path),
        )

        logged = json.loads(mock_log_path.read_text().strip())
        assert logged["kind"] == "apply_success"

    @pytest.mark.asyncio
    async def test_create_new_file(
        self,
        mock_config: RelaceConfig,
        mock_backend: AsyncMock,
        tmp_path: Path,
    ) -> None:
        """Should create new file directly without calling API."""
        new_file = tmp_path / "new_file.py"
        content = "def hello():\n    print('Hello')\n"

        result = await apply_file_logic(
            backend=mock_backend,
            file_path=str(new_file),
            edit_snippet=content,
            instruction=None,
            base_dir=str(tmp_path),
        )

        assert result["status"] == "ok"
        assert "Created" in result["message"]
        assert new_file.exists()
        assert new_file.read_text() == content
        # API should NOT be called for new files
        mock_backend.apply.assert_not_called()


class TestApplyFileLogicValidation:
    """Test apply_file_logic input validation."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("snippet", ["", "   \n\t  "])
    async def test_empty_or_whitespace_edit_snippet_returns_error(
        self,
        mock_config: RelaceConfig,
        mock_backend: AsyncMock,
        temp_source_file: Path,
        tmp_path: Path,
        snippet: str,
    ) -> None:
        """Should return INVALID_INPUT for empty or whitespace-only edit_snippet."""

        result = await apply_file_logic(
            backend=mock_backend,
            file_path=str(temp_source_file),
            edit_snippet=snippet,
            instruction=None,
            base_dir=str(tmp_path),
        )

        assert result["status"] == "error"
        assert result["code"] == "INVALID_INPUT"
        assert "edit_snippet cannot be empty" in result["message"]

    @pytest.mark.asyncio
    async def test_placeholder_only_snippet_returns_error(
        self,
        mock_config: RelaceConfig,
        mock_backend: AsyncMock,
        temp_source_file: Path,
        tmp_path: Path,
    ) -> None:
        """Should return NEEDS_MORE_CONTEXT when snippet has no anchors."""

        result = await apply_file_logic(
            backend=mock_backend,
            file_path=str(temp_source_file),
            edit_snippet="// ... existing code ...\n// ... rest of code ...\n",
            instruction=None,
            base_dir=str(tmp_path),
        )

        assert result["status"] == "error"
        assert result["code"] == "NEEDS_MORE_CONTEXT"
        mock_backend.apply.assert_not_called()

    @pytest.mark.asyncio
    async def test_empty_path_returns_invalid_path(
        self,
        mock_config: RelaceConfig,
        mock_backend: AsyncMock,
        tmp_path: Path,
    ) -> None:
        """Should return INVALID_PATH for empty file_path."""

        result = await apply_file_logic(
            backend=mock_backend,
            file_path="",
            edit_snippet="code",
            instruction=None,
            base_dir=str(tmp_path),
        )

        assert result["status"] == "error"
        assert result["code"] == "INVALID_PATH"
        assert "cannot be empty" in result["message"]
        mock_backend.apply.assert_not_called()

    @pytest.mark.asyncio
    async def test_directory_path_returns_invalid_path(
        self,
        mock_config: RelaceConfig,
        mock_backend: AsyncMock,
        tmp_path: Path,
    ) -> None:
        """Should return INVALID_PATH when file_path is a directory."""

        result = await apply_file_logic(
            backend=mock_backend,
            file_path=str(tmp_path),
            edit_snippet="code",
            instruction=None,
            base_dir=str(tmp_path),
        )

        assert result["status"] == "error"
        assert result["code"] == "INVALID_PATH"
        assert "not a file" in result["message"]
        mock_backend.apply.assert_not_called()

    @pytest.mark.asyncio
    async def test_delete_with_remove_directive_is_allowed(
        self,
        mock_config: RelaceConfig,
        mock_backend: AsyncMock,
        temp_source_file: Path,
        tmp_path: Path,
    ) -> None:
        """Should allow delete with // remove directive when combined with valid anchors."""
        mock_backend.apply.return_value = ApplyResponse(
            merged_code="def hello():\n    print('Hello')\n",
            usage={},
        )

        # snippet contains real anchor (def hello) and remove directive
        result = await apply_file_logic(
            backend=mock_backend,
            file_path=str(temp_source_file),
            edit_snippet="def hello():\n    print('Hello')\n\n// remove goodbye\n",
            instruction="delete goodbye function",
            base_dir=str(tmp_path),
        )

        # Should call API, not return error
        mock_backend.apply.assert_called_once()
        assert result["status"] == "ok"

    @pytest.mark.asyncio
    async def test_delete_with_hash_remove_directive_is_allowed(
        self,
        mock_config: RelaceConfig,
        mock_backend: AsyncMock,
        temp_source_file: Path,
        tmp_path: Path,
    ) -> None:
        """Should allow delete with # remove directive (Python-style) when combined with valid anchors."""
        mock_backend.apply.return_value = ApplyResponse(
            merged_code="def hello():\n    print('Hello')\n",
            usage={},
        )

        # snippet contains real anchor (def hello) and Python-style remove directive
        result = await apply_file_logic(
            backend=mock_backend,
            file_path=str(temp_source_file),
            edit_snippet="def hello():\n    print('Hello')\n\n# remove goodbye\n",
            instruction="delete goodbye function",
            base_dir=str(tmp_path),
        )

        # Should call API, not return error
        mock_backend.apply.assert_called_once()
        assert result["status"] == "ok"

    @pytest.mark.asyncio
    async def test_no_changes_returns_message(
        self,
        mock_config: RelaceConfig,
        mock_backend: AsyncMock,
        temp_source_file: Path,
        tmp_path: Path,
    ) -> None:
        """Should return 'No changes made' when diff is empty (idempotent)."""
        original = temp_source_file.read_text()
        mock_backend.apply.return_value = ApplyResponse(merged_code=original, usage={})

        # edit_snippet contains content already existing in original file (true idempotent scenario)
        result = await apply_file_logic(
            backend=mock_backend,
            file_path=str(temp_source_file),
            edit_snippet="def hello():\n    print('Hello')\n",
            instruction=None,
            base_dir=str(tmp_path),
        )

        assert result["status"] == "ok"
        assert "No changes needed" in result["message"] or "already matches" in result["message"]


class TestApplyFileLogicFileSize:
    """Test file size limit enforcement."""

    @pytest.mark.asyncio
    async def test_large_file_returns_recoverable_error(
        self,
        mock_config: RelaceConfig,
        mock_backend: AsyncMock,
        temp_large_file: Path,
        tmp_path: Path,
    ) -> None:
        """Should return FILE_TOO_LARGE for files exceeding size limit (not crash MCP tool)."""

        result = await apply_file_logic(
            backend=mock_backend,
            file_path=str(temp_large_file),
            edit_snippet="// edit",
            instruction=None,
            base_dir=str(tmp_path),
        )

        assert result["status"] == "error"
        assert result["code"] == "FILE_TOO_LARGE"
        assert "File too large" in result["message"]
        mock_backend.apply.assert_not_called()

    @pytest.mark.asyncio
    async def test_file_at_limit_allowed(
        self,
        mock_config: RelaceConfig,
        mock_backend: AsyncMock,
        tmp_path: Path,
        successful_api_response: dict[str, Any],
    ) -> None:
        """Should allow files exactly at size limit."""
        # Create file exactly at limit (10MB) with recognizable anchor content
        limit_file = tmp_path / "limit.py"
        content = "def placeholder_function():\n" + "x" * (MAX_FILE_SIZE_BYTES - 30)
        # Use binary write to avoid Windows newline conversion
        limit_file.write_bytes(content.encode("utf-8"))

        mock_backend.apply.return_value = ApplyResponse(
            merged_code=successful_api_response["choices"][0]["message"]["content"],
            usage=successful_api_response["usage"],
        )

        # edit_snippet contains locatable anchor lines
        result = await apply_file_logic(
            backend=mock_backend,
            file_path=str(limit_file),
            edit_snippet="def placeholder_function():\n    pass\n",
            instruction=None,
            base_dir=str(tmp_path),
        )
        assert result["status"] == "ok"


class TestApplyFileLogicEncoding:
    """Test file encoding validation."""

    @pytest.mark.asyncio
    async def test_binary_file_returns_recoverable_error(
        self,
        mock_config: RelaceConfig,
        mock_backend: AsyncMock,
        temp_binary_file: Path,
        tmp_path: Path,
    ) -> None:
        """Should return ENCODING_ERROR on non-text/binary files (not crash MCP tool)."""

        result = await apply_file_logic(
            backend=mock_backend,
            file_path=str(temp_binary_file),
            edit_snippet="// edit",
            instruction=None,
            base_dir=str(tmp_path),
        )

        assert result["status"] == "error"
        assert result["code"] == "ENCODING_ERROR"
        assert "Cannot detect encoding" in result["message"]
        mock_backend.apply.assert_not_called()

    @pytest.mark.asyncio
    async def test_gbk_file_supported(
        self,
        mock_config: RelaceConfig,
        mock_backend: AsyncMock,
        tmp_path: Path,
    ) -> None:
        """Should successfully read and write GBK encoded files."""
        gbk_file = tmp_path / "gbk_file.py"
        # Write GBK encoded Chinese content (ensure 2+ sufficiently long anchor lines)
        gbk_content = "# 这是简体中文注释用于测试\ndef process_chinese_data():\n    print('你好')\n"
        gbk_file.write_bytes(gbk_content.encode("gbk"))

        merged_code = (
            "# 这是简体中文注释用于测试\ndef process_chinese_data():\n    print('你好世界')\n"
        )
        mock_backend.apply.return_value = ApplyResponse(merged_code=merged_code, usage={})

        # edit_snippet contains anchor lines that exist in original file
        result = await apply_file_logic(
            backend=mock_backend,
            file_path=str(gbk_file),
            edit_snippet="# 这是简体中文注释用于测试\ndef process_chinese_data():\n    print('你好世界')\n",
            instruction=None,
            base_dir=str(tmp_path),
        )

        assert result["status"] == "ok"
        assert "Applied code changes" in result["message"]
        # Confirm written file is still GBK encoded
        assert gbk_file.read_bytes().decode("gbk") == merged_code

    @pytest.mark.asyncio
    async def test_big5_file_supported(
        self,
        mock_config: RelaceConfig,
        mock_backend: AsyncMock,
        tmp_path: Path,
    ) -> None:
        """Should successfully read and write Big5 encoded files."""
        big5_file = tmp_path / "big5_file.py"
        # Write Big5 encoded Traditional Chinese content (ensure 2+ sufficiently long anchor lines)
        big5_content = (
            "# 繁體中文註解用於測試\ndef process_traditional_data():\n    print('世界')\n"
        )
        big5_file.write_bytes(big5_content.encode("big5"))

        merged_code = (
            "# 繁體中文註解用於測試\ndef process_traditional_data():\n    print('世界您好')\n"
        )
        mock_backend.apply.return_value = ApplyResponse(merged_code=merged_code, usage={})

        try:
            set_project_encoding("big5")
            result = await apply_file_logic(
                backend=mock_backend,
                file_path=str(big5_file),
                edit_snippet=(
                    "# 繁體中文註解用於測試\n"
                    "def process_traditional_data():\n"
                    "    print('世界您好')\n"
                ),
                instruction=None,
                base_dir=str(tmp_path),
            )
        finally:
            set_project_encoding(None)

        assert result["status"] == "ok"
        assert "Applied code changes" in result["message"]
        # Confirm written file is still Big5 encoded
        assert big5_file.read_bytes().decode("big5") == merged_code


class TestApplyFileLogicBaseDirSecurity:
    """Test base_dir security restrictions."""

    @pytest.mark.asyncio
    async def test_blocks_path_outside_base_dir(
        self,
        mock_config: RelaceConfig,
        mock_backend: AsyncMock,
        tmp_path: Path,
    ) -> None:
        """Should block access to files outside base_dir."""

        # Attempt to access file outside base_dir
        outside_file = tmp_path.parent / "outside.py"
        # Use binary write to avoid Windows newline conversion
        outside_file.write_bytes(b"content")

        try:
            result = await apply_file_logic(
                backend=mock_backend,
                file_path=str(outside_file),
                edit_snippet="// edit",
                instruction=None,
                base_dir=str(tmp_path),
            )
            assert result["status"] == "error"
            assert result["code"] == "INVALID_PATH"
            assert "outside allowed directory" in result["message"]
            mock_backend.apply.assert_not_called()
        finally:
            outside_file.unlink(missing_ok=True)


class TestApplyFileLogicApiErrors:
    """Test API error handling."""

    @pytest.mark.asyncio
    async def test_logs_error_on_api_failure(
        self,
        mock_config: RelaceConfig,
        mock_backend: AsyncMock,
        temp_source_file: Path,
        tmp_path: Path,
        mock_log_path: Path,
    ) -> None:
        """Should log error event when API call fails."""
        mock_backend.apply.side_effect = RuntimeError("API Error")

        # edit_snippet contains anchor lines that exist in original file
        with pytest.raises(RuntimeError):
            await apply_file_logic(
                backend=mock_backend,
                file_path=str(temp_source_file),
                edit_snippet="def hello():\n    print('Hello')\n",
                instruction=None,
                base_dir=str(tmp_path),
            )

        logged = json.loads(mock_log_path.read_text().strip())
        assert logged["kind"] == "apply_error"
        assert "API Error" in logged["error"]

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "merged_code", [None, 123], ids=["null_merged_code", "non_string_merged_code"]
    )
    async def test_invalid_merged_code_raises(
        self,
        mock_config: RelaceConfig,
        mock_backend: AsyncMock,
        temp_source_file: Path,
        tmp_path: Path,
        merged_code: Any,
    ) -> None:
        """Should return API_INVALID_RESPONSE when API returns an invalid merged_code."""
        mock_backend.apply.return_value = ApplyResponse(merged_code=merged_code, usage={})

        # edit_snippet contains anchor lines that exist in original file
        result = await apply_file_logic(
            backend=mock_backend,
            file_path=str(temp_source_file),
            edit_snippet="def hello():\n    print('Hello')\n",
            instruction=None,
            base_dir=str(tmp_path),
        )

        assert result["status"] == "error"
        assert result["code"] == "API_INVALID_RESPONSE"
        assert "did not return updated code" in result["message"]


class TestApplyFileLogicSnippetPreview:
    """Test edit_snippet_preview in logs."""

    @pytest.mark.asyncio
    async def test_truncates_long_snippet_in_log(
        self,
        mock_config: RelaceConfig,
        mock_backend: AsyncMock,
        temp_source_file: Path,
        tmp_path: Path,
        mock_log_path: Path,
    ) -> None:
        """Should truncate edit_snippet to 200 chars in log."""
        # Long snippet needs locatable anchor lines, and merged_code should contain new content to pass post_check
        long_suffix = "x" * 500
        long_snippet = "def hello():\n    print('Hello')\n" + long_suffix
        merged_code = "def hello():\n    print('Hello')\n" + long_suffix

        mock_backend.apply.return_value = ApplyResponse(merged_code=merged_code, usage={})

        await apply_file_logic(
            backend=mock_backend,
            file_path=str(temp_source_file),
            edit_snippet=long_snippet,
            instruction=None,
            base_dir=str(tmp_path),
        )

        logged = json.loads(mock_log_path.read_text().strip())
        assert len(logged["edit_snippet_preview"]) == 200


class TestApplyFileLogicPathNormalization:
    """Test path normalization for relative and absolute paths."""

    @pytest.mark.asyncio
    async def test_relative_path_accepted(
        self,
        mock_config: RelaceConfig,
        mock_backend: AsyncMock,
        tmp_path: Path,
    ) -> None:
        """Should accept relative path and map to base_dir."""
        test_file = tmp_path / "src" / "file.py"
        test_file.parent.mkdir(parents=True, exist_ok=True)
        # Use binary write to avoid Windows newline conversion
        test_file.write_bytes(b"original_value = True\n")

        mock_backend.apply.return_value = ApplyResponse(
            merged_code="modified_value = True\n", usage={}
        )

        result = await apply_file_logic(
            backend=mock_backend,
            file_path="src/file.py",
            edit_snippet="original_value = True\nmodified_value = True\n",
            instruction=None,
            base_dir=str(tmp_path),
        )

        assert result["status"] == "ok"
        assert "Applied code changes" in result["message"]
        mock_backend.apply.assert_called_once()

    @pytest.mark.asyncio
    async def test_absolute_path_accepted(
        self,
        mock_config: RelaceConfig,
        mock_backend: AsyncMock,
        tmp_path: Path,
    ) -> None:
        """Should accept absolute path within base_dir."""
        test_file = tmp_path / "src" / "file.py"
        test_file.parent.mkdir(parents=True, exist_ok=True)
        # Use binary write to avoid Windows newline conversion
        test_file.write_bytes(b"original_value = True\n")

        mock_backend.apply.return_value = ApplyResponse(
            merged_code="modified_value = True\n", usage={}
        )

        result = await apply_file_logic(
            backend=mock_backend,
            file_path=str(test_file),
            edit_snippet="original_value = True\nmodified_value = True\n",
            instruction=None,
            base_dir=str(tmp_path),
        )

        assert result["status"] == "ok"
        assert "Applied code changes" in result["message"]
        mock_backend.apply.assert_called_once()

    @pytest.mark.asyncio
    async def test_invalid_path_returns_error(
        self,
        mock_config: RelaceConfig,
        mock_backend: AsyncMock,
        tmp_path: Path,
    ) -> None:
        """Should return INVALID_PATH for paths outside base_dir."""

        result = await apply_file_logic(
            backend=mock_backend,
            file_path="/other/path/file.py",
            edit_snippet="code",
            instruction=None,
            base_dir=str(tmp_path),
        )

        assert result["status"] == "error"
        assert result["code"] == "INVALID_PATH"
        assert "outside allowed directory" in result["message"]
        mock_backend.apply.assert_not_called()


class TestApplyFileLogicRecoverableErrors:
    """Test recoverable error handling."""

    @pytest.mark.asyncio
    async def test_anchor_precheck_failure_returns_needs_more_context(
        self,
        mock_config: RelaceConfig,
        mock_backend: AsyncMock,
        tmp_path: Path,
    ) -> None:
        """Should return NEEDS_MORE_CONTEXT when anchor lines don't match file content."""
        test_file = tmp_path / "test.py"
        # Use binary write to avoid Windows newline conversion
        test_file.write_bytes(b"def existing_function():\n    return 42\n")

        # edit_snippet contains ellipsis markers (triggers precheck) but anchor cannot be located
        result = await apply_file_logic(
            backend=mock_backend,
            file_path=str(test_file),
            edit_snippet="// ... existing code ...\ndef totally_different_function():\n    return 999\n// ... more code ...\n",
            instruction="Edit something",
            base_dir=str(tmp_path),
        )

        assert result["status"] == "error"
        assert result["code"] == "NEEDS_MORE_CONTEXT"
        assert "cannot be located" in result["message"]
        # API should NOT be called when precheck fails
        mock_backend.apply.assert_not_called()

    @pytest.mark.asyncio
    async def test_anchor_precheck_skipped_with_append_directive(
        self,
        mock_config: RelaceConfig,
        mock_backend: AsyncMock,
        tmp_path: Path,
    ) -> None:
        """Instruction with explicit position directive should skip precheck to avoid false blocking."""
        test_file = tmp_path / "test.py"
        original = "def existing_function():\n    return 42\n"
        # Use binary write to avoid Windows newline conversion
        test_file.write_bytes(original.encode("utf-8"))

        merged = original + "\n# appended\n"
        mock_backend.apply.return_value = ApplyResponse(merged_code=merged, usage={})

        result = await apply_file_logic(
            backend=mock_backend,
            file_path=str(test_file),
            edit_snippet="// ... existing code ...\n# appended\n// ... existing code ...\n",
            instruction="Append to end of file",
            base_dir=str(tmp_path),
        )

        assert result["status"] == "ok"
        mock_backend.apply.assert_called_once()
        assert test_file.read_text() == merged

    @pytest.mark.asyncio
    async def test_permission_error_returns_permission_error(
        self,
        mock_config: RelaceConfig,
        mock_backend: AsyncMock,
        tmp_path: Path,
    ) -> None:
        """PermissionError should convert to PERMISSION_ERROR (avoid MCP tool crash)."""
        test_file = tmp_path / "test.py"
        # Use binary write to avoid Windows newline conversion
        test_file.write_bytes(b"def existing_function():\n    return 42\n")

        with patch(
            "relace_mcp.tools.apply.core.file_io.read_text_with_fallback",
            side_effect=PermissionError("Permission denied"),
        ):
            result = await apply_file_logic(
                backend=mock_backend,
                file_path=str(test_file),
                edit_snippet="def existing_function():\n    return 42\n",
                instruction=None,
                base_dir=str(tmp_path),
            )

        assert result["status"] == "error"
        assert result["code"] == "PERMISSION_ERROR"

    @pytest.mark.asyncio
    async def test_filesystem_error_returns_fs_error_on_create(
        self,
        mock_config: RelaceConfig,
        mock_backend: AsyncMock,
        tmp_path: Path,
    ) -> None:
        """OSError should convert to FS_ERROR (avoid MCP tool crash)."""
        new_file = tmp_path / "new_file.py"

        with patch(
            "relace_mcp.tools.apply.core.file_io.atomic_write",
            side_effect=OSError("Disk full"),
        ):
            result = await apply_file_logic(
                backend=mock_backend,
                file_path=str(new_file),
                edit_snippet="print('hello')\n",
                instruction=None,
                base_dir=str(tmp_path),
            )

        assert result["status"] == "error"
        assert result["code"] == "FS_ERROR"
        assert not new_file.exists()
        mock_backend.apply.assert_not_called()

    @pytest.mark.asyncio
    async def test_read_only_file_returns_file_not_writable(
        self,
        mock_config: RelaceConfig,
        mock_backend: AsyncMock,
        tmp_path: Path,
    ) -> None:
        """Unwritable file should convert to FILE_NOT_WRITABLE (avoid MCP tool crash)."""
        test_file = tmp_path / "readonly.py"
        # Use binary write to avoid Windows newline conversion
        test_file.write_bytes(b"original_value_setting = True\nprocess_data_function()\n")
        test_file.chmod(0o444)

        mock_backend.apply.return_value = ApplyResponse(
            merged_code="modified_value_setting = False\nprocess_data_function()\n",
            usage={},
        )

        result = await apply_file_logic(
            backend=mock_backend,
            file_path=str(test_file),
            edit_snippet="original_value_setting = True\nmodified_value_setting = False\nprocess_data_function()\n",
            instruction="Modify",
            base_dir=str(tmp_path),
        )

        assert result["status"] == "error"
        assert result["code"] == "FILE_NOT_WRITABLE"

    @pytest.mark.asyncio
    async def test_api_auth_error_returns_auth_error(
        self,
        mock_config: RelaceConfig,
        mock_backend: AsyncMock,
        tmp_path: Path,
    ) -> None:
        """Should return AUTH_ERROR for 401/403 API errors."""
        import openai

        test_file = tmp_path / "test.py"
        # Use binary write to avoid Windows newline conversion
        test_file.write_bytes(b"def authenticate_user():\n    return validate_credentials()\n")

        mock_backend.apply.side_effect = openai.AuthenticationError(
            message="Invalid API key",
            response=MagicMock(status_code=401),
            body=None,
        )

        result = await apply_file_logic(
            backend=mock_backend,
            file_path=str(test_file),
            edit_snippet="def authenticate_user():\n    return validate_credentials()\n",
            instruction=None,
            base_dir=str(tmp_path),
        )

        assert result["status"] == "error"
        assert result["code"] == "AUTH_ERROR"
        assert "API authentication or permission error" in result["message"]
        assert result["detail"]["status_code"] == 401

    @pytest.mark.asyncio
    async def test_api_403_error_returns_auth_error(
        self,
        mock_config: RelaceConfig,
        mock_backend: AsyncMock,
        tmp_path: Path,
    ) -> None:
        """Should return AUTH_ERROR for 403 API errors."""
        import openai

        test_file = tmp_path / "test.py"
        # Use binary write to avoid Windows newline conversion
        test_file.write_bytes(b"def authenticate_user():\n    return validate_credentials()\n")

        mock_backend.apply.side_effect = openai.PermissionDeniedError(
            message="Access denied",
            response=MagicMock(status_code=403),
            body=None,
        )

        result = await apply_file_logic(
            backend=mock_backend,
            file_path=str(test_file),
            edit_snippet="def authenticate_user():\n    return validate_credentials()\n",
            instruction=None,
            base_dir=str(tmp_path),
        )

        assert result["status"] == "error"
        assert result["code"] == "AUTH_ERROR"
        assert result["detail"]["status_code"] == 403

    @pytest.mark.asyncio
    async def test_api_other_4xx_returns_api_error(
        self,
        mock_config: RelaceConfig,
        mock_backend: AsyncMock,
        tmp_path: Path,
    ) -> None:
        """Should return API_ERROR for other 4xx errors (e.g., anchor not found)."""
        import openai

        test_file = tmp_path / "test.py"
        # Use binary write to avoid Windows newline conversion
        test_file.write_bytes(b"def authenticate_user():\n    return validate_credentials()\n")

        mock_backend.apply.side_effect = openai.BadRequestError(
            message="Cannot locate anchor lines",
            response=MagicMock(status_code=400),
            body=None,
        )

        result = await apply_file_logic(
            backend=mock_backend,
            file_path=str(test_file),
            edit_snippet="def authenticate_user():\n    return validate_credentials()\n",
            instruction="Edit function",
            base_dir=str(tmp_path),
        )

        assert result["status"] == "error"
        assert result["code"] == "API_ERROR"
        assert "API error" in result["message"]
        assert result["detail"]["status_code"] == 400

    @pytest.mark.asyncio
    async def test_network_error_returns_network_error(
        self,
        mock_config: RelaceConfig,
        mock_backend: AsyncMock,
        tmp_path: Path,
    ) -> None:
        """Should return NETWORK_ERROR for network failures."""
        import openai

        test_file = tmp_path / "test.py"
        # Use binary write to avoid Windows newline conversion
        test_file.write_bytes(b"def authenticate_user():\n    return validate_credentials()\n")

        mock_backend.apply.side_effect = openai.APIConnectionError(request=MagicMock())

        result = await apply_file_logic(
            backend=mock_backend,
            file_path=str(test_file),
            edit_snippet="def authenticate_user():\n    return validate_credentials()\n",
            instruction=None,
            base_dir=str(tmp_path),
        )

        assert result["status"] == "error"
        assert result["code"] == "NETWORK_ERROR"
        assert "Network error" in result["message"]

    @pytest.mark.asyncio
    async def test_timeout_error_returns_timeout_error(
        self,
        mock_config: RelaceConfig,
        mock_backend: AsyncMock,
        tmp_path: Path,
    ) -> None:
        """Should return TIMEOUT_ERROR for timeout failures."""
        import openai

        test_file = tmp_path / "test.py"
        # Use binary write to avoid Windows newline conversion
        test_file.write_bytes(b"def authenticate_user():\n    return validate_credentials()\n")

        mock_backend.apply.side_effect = openai.APITimeoutError(request=MagicMock())

        result = await apply_file_logic(
            backend=mock_backend,
            file_path=str(test_file),
            edit_snippet="def authenticate_user():\n    return validate_credentials()\n",
            instruction=None,
            base_dir=str(tmp_path),
        )

        assert result["status"] == "error"
        assert result["code"] == "TIMEOUT_ERROR"
        assert "Request timed out" in result["message"]

    @pytest.mark.asyncio
    async def test_anchor_precheck_allows_remove_directives(
        self,
        mock_config: RelaceConfig,
        mock_backend: AsyncMock,
        tmp_path: Path,
    ) -> None:
        """Should allow snippets with remove directives if they have valid anchors."""
        test_file = tmp_path / "test.py"
        # Use binary write to avoid Windows newline conversion
        test_file.write_bytes(
            b"def main_function():\n    return process_data()\n\ndef helper_function():\n    return compute_result()\n"
        )

        mock_backend.apply.return_value = ApplyResponse(
            merged_code="def main_function():\n    return process_data()\n",
            usage={},
        )

        result = await apply_file_logic(
            backend=mock_backend,
            file_path=str(test_file),
            edit_snippet="def main_function():\n    return process_data()\n\n// remove helper_function\n",
            instruction="Remove helper function",
            base_dir=str(tmp_path),
        )

        # Should call API, not return NEEDS_MORE_CONTEXT
        mock_backend.apply.assert_called_once()
        assert result["status"] == "ok"

    @pytest.mark.asyncio
    async def test_anchor_precheck_with_indentation_difference(
        self,
        mock_config: RelaceConfig,
        mock_backend: AsyncMock,
        tmp_path: Path,
    ) -> None:
        """Should use strip() for lenient matching despite indentation differences."""
        test_file = tmp_path / "test.py"
        # Use binary write to avoid Windows newline conversion
        test_file.write_bytes(b"def process_data_handler():\n    return calculate_result_value()\n")

        mock_backend.apply.return_value = ApplyResponse(
            merged_code="def process_data_handler():\n    return calculate_result_v2()\n",
            usage={},
        )

        # edit_snippet indentation differs from original file, but should match after strip()
        # Ensure 2 anchor hits: def process_data_handler(): and return calculate_result_value()
        result = await apply_file_logic(
            backend=mock_backend,
            file_path=str(test_file),
            edit_snippet="def process_data_handler():\nreturn calculate_result_value()\n",  # Different indentation
            instruction="Change return value",
            base_dir=str(tmp_path),
        )

        # Should pass precheck and call API
        mock_backend.apply.assert_called_once()
        assert result["status"] == "ok"


class TestApplyNoopDetection:
    """Test no-op detection logic (Defense 2)."""

    @pytest.mark.asyncio
    async def test_noop_with_new_lines_returns_apply_noop(
        self,
        mock_config: RelaceConfig,
        mock_backend: AsyncMock,
        tmp_path: Path,
    ) -> None:
        """Snippet contains new lines but merge produces no changes, should return APPLY_NOOP."""
        test_file = tmp_path / "test.py"
        original_content = "def process_data_from_input():\n    return calculate_result_value()\n"
        # Use binary write to avoid Windows newline conversion
        test_file.write_bytes(original_content.encode("utf-8"))

        # API returns same content as original file (simulating apply failure)
        mock_backend.apply.return_value = ApplyResponse(merged_code=original_content, usage={})

        result = await apply_file_logic(
            backend=mock_backend,
            file_path=str(test_file),
            edit_snippet="def process_data_from_input():\n    return calculate_result_value()\n\ndef new_function_that_should_be_added():\n    pass\n",
            instruction="Add new function",
            base_dir=str(tmp_path),
        )

        assert result["status"] == "error"
        assert result["code"] == "APPLY_NOOP"
        assert "identical to initial" in result["message"]

    @pytest.mark.asyncio
    async def test_noop_idempotent_returns_ok(
        self,
        mock_config: RelaceConfig,
        mock_backend: AsyncMock,
        tmp_path: Path,
    ) -> None:
        """Snippet already exists in file, should return OK (idempotent)."""
        test_file = tmp_path / "test.py"
        original_content = "def process_data_from_input():\n    return calculate_result_value()\n"
        # Use binary write to avoid Windows newline conversion
        test_file.write_bytes(original_content.encode("utf-8"))

        # API returns same content as original file
        mock_backend.apply.return_value = ApplyResponse(merged_code=original_content, usage={})

        # snippet only contains existing code (true idempotent)
        result = await apply_file_logic(
            backend=mock_backend,
            file_path=str(test_file),
            edit_snippet="def process_data_from_input():\n    return calculate_result_value()\n",
            instruction="Ensure function exists",
            base_dir=str(tmp_path),
        )

        assert result["status"] == "ok"
        assert "No changes needed" in result["message"] or "already matches" in result["message"]

    @pytest.mark.asyncio
    async def test_noop_with_remove_directive_returns_apply_noop(
        self,
        mock_config: RelaceConfig,
        mock_backend: AsyncMock,
        tmp_path: Path,
    ) -> None:
        """Has remove directive but no changes, should return APPLY_NOOP."""
        test_file = tmp_path / "test.py"
        original_content = "def main_function_handler():\n    return process_request()\n\ndef helper_utility_function():\n    return compute_value()\n"
        # Use binary write to avoid Windows newline conversion
        test_file.write_bytes(original_content.encode("utf-8"))

        # API returns same content as original file (remove failed)
        mock_backend.apply.return_value = ApplyResponse(merged_code=original_content, usage={})

        result = await apply_file_logic(
            backend=mock_backend,
            file_path=str(test_file),
            edit_snippet="def main_function_handler():\n    return process_request()\n\n// remove helper_utility_function\n",
            instruction="Remove helper function",
            base_dir=str(tmp_path),
        )

        assert result["status"] == "error"
        assert result["code"] == "APPLY_NOOP"

    @pytest.mark.asyncio
    async def test_noop_with_short_new_line_returns_apply_noop(
        self,
        mock_config: RelaceConfig,
        mock_backend: AsyncMock,
        tmp_path: Path,
    ) -> None:
        """Adding short line (e.g., x = 1) but merge produces no changes, should return APPLY_NOOP."""
        test_file = tmp_path / "test.py"
        original_content = "def process_data_handler():\n    return calculate_result()\n"
        # Use binary write to avoid Windows newline conversion
        test_file.write_bytes(original_content.encode("utf-8"))

        # API returns same content as original file (apply failed)
        mock_backend.apply.return_value = ApplyResponse(merged_code=original_content, usage={})

        # Adding short line x = 1 (5 chars)
        result = await apply_file_logic(
            backend=mock_backend,
            file_path=str(test_file),
            edit_snippet="def process_data_handler():\n    return calculate_result()\n    x = 1\n",
            instruction="Add variable",
            base_dir=str(tmp_path),
        )

        assert result["status"] == "error"
        assert result["code"] == "APPLY_NOOP"

    @pytest.mark.asyncio
    async def test_noop_with_trivial_line_returns_ok(
        self,
        mock_config: RelaceConfig,
        mock_backend: AsyncMock,
        tmp_path: Path,
    ) -> None:
        """Adding trivial line (e.g., return) is treated as idempotent, should return OK."""
        test_file = tmp_path / "test.py"
        original_content = "def process_data_handler():\n    calculate_result()\n"
        # Use binary write to avoid Windows newline conversion
        test_file.write_bytes(original_content.encode("utf-8"))

        # API returns same content as original file
        mock_backend.apply.return_value = ApplyResponse(merged_code=original_content, usage={})

        # Only adding trivial line return (common syntax keyword)
        result = await apply_file_logic(
            backend=mock_backend,
            file_path=str(test_file),
            edit_snippet="def process_data_handler():\n    calculate_result()\n    return\n",
            instruction="Add return",
            base_dir=str(tmp_path),
        )

        # return is trivial token, not considered expected change
        assert result["status"] == "ok"

    @pytest.mark.asyncio
    async def test_noop_with_substring_match_returns_apply_noop(
        self,
        mock_config: RelaceConfig,
        mock_backend: AsyncMock,
        tmp_path: Path,
    ) -> None:
        """New line is substring of existing line, should correctly detect as APPLY_NOOP."""
        test_file = tmp_path / "test.py"
        # x = 100 contains x = 1 as substring
        original_content = "def process_data_handler():\n    x = 100\n    return x\n"
        # Use binary write to avoid Windows newline conversion
        test_file.write_bytes(original_content.encode("utf-8"))

        # API returns same content as original file (apply failed)
        mock_backend.apply.return_value = ApplyResponse(merged_code=original_content, usage={})

        # snippet contains x = 1 (is substring of x = 100, but should be treated as new line)
        result = await apply_file_logic(
            backend=mock_backend,
            file_path=str(test_file),
            edit_snippet="def process_data_handler():\n    x = 1\n    return x\n",
            instruction="Change value",
            base_dir=str(tmp_path),
        )

        # x = 1 does not equal x = 100, should detect as expected change
        assert result["status"] == "error"
        assert result["code"] == "APPLY_NOOP"


class TestApplyWriteVerification:
    """Test atomic write and post-write verification (Defense 3)."""

    @pytest.mark.asyncio
    async def test_atomic_write_creates_temp_file(
        self,
        mock_config: RelaceConfig,
        mock_backend: AsyncMock,
        tmp_path: Path,
    ) -> None:
        """Atomic write should complete normally without leaving .tmp file."""
        test_file = tmp_path / "test.py"
        # Use binary write to avoid Windows newline conversion
        test_file.write_bytes(b"original_content_value = True\nprocess_data_function()\n")

        mock_backend.apply.return_value = ApplyResponse(
            merged_code="modified_content_value = False\nprocess_data_function()\n",
            usage={},
        )

        result = await apply_file_logic(
            backend=mock_backend,
            file_path=str(test_file),
            edit_snippet="original_content_value = True\nmodified_content_value = False\nprocess_data_function()\n",
            instruction="Modify content",
            base_dir=str(tmp_path),
        )

        # Should succeed
        assert result["status"] == "ok"
        # Fixed .tmp file should not exist (now uses unique uuid-based names)
        assert not (tmp_path / "test.py.tmp").exists()
        # Content should be new
        assert test_file.read_text() == "modified_content_value = False\nprocess_data_function()\n"

    @pytest.mark.asyncio
    async def test_post_write_verification_failure_returns_error(
        self,
        mock_config: RelaceConfig,
        mock_backend: AsyncMock,
        tmp_path: Path,
    ) -> None:
        """Post-write verification failure should return WRITE_VERIFY_FAILED."""
        test_file = tmp_path / "test.py"
        original = "original_content_value = True\nprocess_data_function()\n"
        # Use binary write to avoid Windows newline conversion
        test_file.write_bytes(original.encode("utf-8"))

        mock_backend.apply.return_value = ApplyResponse(
            merged_code="modified_content_value = False\nprocess_data_function()\n",
            usage={},
        )

        # Mock read_text_with_fallback to raise exception during verification
        with patch("relace_mcp.tools.apply.core.file_io.read_text_with_fallback") as mock_read:
            # First call (read original file) returns normal content
            # Second call (verify write) raises exception
            mock_read.side_effect = [
                (original, "utf-8"),
                OSError("Permission denied"),
            ]

            result = await apply_file_logic(
                backend=mock_backend,
                file_path=str(test_file),
                edit_snippet="original_content_value = True\nmodified_content_value = False\nprocess_data_function()\n",
                instruction="Modify content",
                base_dir=str(tmp_path),
            )

        assert result["status"] == "error"
        assert result["code"] == "WRITE_VERIFY_FAILED"
        assert "Cannot verify file content after write" in result["message"]


class TestApplyResponseFormat:
    """Test response format includes required fields."""

    @pytest.mark.asyncio
    async def test_success_response_includes_path_and_trace_id(
        self,
        mock_config: RelaceConfig,
        mock_backend: AsyncMock,
        tmp_path: Path,
    ) -> None:
        """Success response should include path and trace_id."""
        test_file = tmp_path / "test.py"
        # Use binary write to avoid Windows newline conversion
        test_file.write_bytes(b"original_value_setting = True\nprocess_data_function()\n")

        mock_backend.apply.return_value = ApplyResponse(
            merged_code="modified_value_setting = False\nprocess_data_function()\n",
            usage={},
        )

        result = await apply_file_logic(
            backend=mock_backend,
            file_path=str(test_file),
            edit_snippet="original_value_setting = True\nmodified_value_setting = False\nprocess_data_function()\n",
            instruction="Modify",
            base_dir=str(tmp_path),
        )

        assert result["status"] == "ok"
        assert result["path"] == str(test_file)
        assert result["trace_id"] is not None
        assert result["timing_ms"] >= 0

    @pytest.mark.asyncio
    async def test_noop_response_includes_path(
        self,
        mock_config: RelaceConfig,
        mock_backend: AsyncMock,
        tmp_path: Path,
    ) -> None:
        """No-op (idempotent) response should also include path."""
        test_file = tmp_path / "test.py"
        original_content = "def existing_function_handler():\n    return process_request_data()\n"
        # Use binary write to avoid Windows newline conversion
        test_file.write_bytes(original_content.encode("utf-8"))

        mock_backend.apply.return_value = ApplyResponse(merged_code=original_content, usage={})

        # True idempotent case
        result = await apply_file_logic(
            backend=mock_backend,
            file_path=str(test_file),
            edit_snippet="def existing_function_handler():\n    return process_request_data()\n",
            instruction="Ensure exists",
            base_dir=str(tmp_path),
        )

        assert result["status"] == "ok"
        assert result["path"] == str(test_file)
        assert result["trace_id"] is not None
