import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from relace_mcp.config import RelaceConfig
from relace_mcp.tools.apply import apply_file_logic
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
            patch("relace_mcp.tools.apply.logging.EXPERIMENTAL_LOGGING", True),
            patch("relace_mcp.tools.apply.logging.LOG_PATH", log_path),
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
        # 使用目錄作為 log 路徑會失敗，但不應拋出例外
        with (
            patch("relace_mcp.tools.apply.logging.EXPERIMENTAL_LOGGING", True),
            patch("relace_mcp.tools.apply.logging.LOG_PATH", tmp_path),
        ):
            log_event({"test": True})  # 不應拋出例外


class TestApplyFileLogicSuccess:
    """Test apply_file_logic successful scenarios."""

    def test_successful_apply(
        self,
        mock_config: RelaceConfig,
        mock_client: MagicMock,
        temp_source_file: Path,
        successful_api_response: dict[str, Any],
        tmp_path: Path,
    ) -> None:
        """Should successfully apply edit and return UDiff."""
        mock_client.apply.return_value = successful_api_response

        # edit_snippet 包含原始檔案中存在的 anchor lines（temp_source_file 內容）
        # temp_source_file: def hello():\n    print('Hello')\n\ndef goodbye():\n    print('Goodbye')\n
        result = apply_file_logic(
            client=mock_client,
            file_path=str(temp_source_file),
            edit_snippet="def hello():\n    print('Hello')\n\ndef goodbye():\n    print('Hello, World!')\n",
            instruction="Add feature",
            base_dir=str(tmp_path),
        )

        assert result["status"] == "ok"
        assert result["message"] == "Applied code changes using Relace API."
        assert result["diff"] is not None
        assert "--- before" in result["diff"]
        assert "+++ after" in result["diff"]

        # Verify file was written
        assert temp_source_file.read_text() == successful_api_response["mergedCode"]

    def test_logs_success_event(
        self,
        mock_config: RelaceConfig,
        mock_client: MagicMock,
        temp_source_file: Path,
        successful_api_response: dict[str, Any],
        tmp_path: Path,
        mock_log_path: Path,
    ) -> None:
        """Should log success event."""
        mock_client.apply.return_value = successful_api_response

        # edit_snippet 包含原始檔案中存在的 anchor lines（temp_source_file 內容）
        apply_file_logic(
            client=mock_client,
            file_path=str(temp_source_file),
            edit_snippet="def hello():\n    print('Hello')\n\ndef goodbye():\n    print('Hello, World!')\n",
            instruction=None,
            base_dir=str(tmp_path),
        )

        logged = json.loads(mock_log_path.read_text().strip())
        assert logged["kind"] == "apply_success"

    def test_create_new_file(
        self,
        mock_config: RelaceConfig,
        mock_client: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Should create new file directly without calling API."""
        new_file = tmp_path / "new_file.py"
        content = "def hello():\n    print('Hello')\n"

        result = apply_file_logic(
            client=mock_client,
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
        mock_client.apply.assert_not_called()


class TestApplyFileLogicValidation:
    """Test apply_file_logic input validation."""

    @pytest.mark.parametrize("snippet", ["", "   \n\t  "])
    def test_empty_or_whitespace_edit_snippet_returns_error(
        self,
        mock_config: RelaceConfig,
        mock_client: MagicMock,
        temp_source_file: Path,
        tmp_path: Path,
        snippet: str,
    ) -> None:
        """Should return INVALID_INPUT for empty or whitespace-only edit_snippet."""

        result = apply_file_logic(
            client=mock_client,
            file_path=str(temp_source_file),
            edit_snippet=snippet,
            instruction=None,
            base_dir=str(tmp_path),
        )

        assert result["status"] == "error"
        assert result["code"] == "INVALID_INPUT"
        assert "edit_snippet cannot be empty" in result["message"]

    def test_placeholder_only_snippet_returns_error(
        self,
        mock_config: RelaceConfig,
        mock_client: MagicMock,
        temp_source_file: Path,
        tmp_path: Path,
    ) -> None:
        """Should return NEEDS_MORE_CONTEXT when snippet has no anchors."""

        result = apply_file_logic(
            client=mock_client,
            file_path=str(temp_source_file),
            edit_snippet="// ... existing code ...\n// ... rest of code ...\n",
            instruction=None,
            base_dir=str(tmp_path),
        )

        assert result["status"] == "error"
        assert result["code"] == "NEEDS_MORE_CONTEXT"
        mock_client.apply.assert_not_called()

    def test_empty_path_returns_invalid_path(
        self,
        mock_config: RelaceConfig,
        mock_client: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Should return INVALID_PATH for empty file_path."""

        result = apply_file_logic(
            client=mock_client,
            file_path="",
            edit_snippet="code",
            instruction=None,
            base_dir=str(tmp_path),
        )

        assert result["status"] == "error"
        assert result["code"] == "INVALID_PATH"
        assert "cannot be empty" in result["message"]
        mock_client.apply.assert_not_called()

    def test_directory_path_returns_invalid_path(
        self,
        mock_config: RelaceConfig,
        mock_client: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Should return INVALID_PATH when file_path is a directory."""

        result = apply_file_logic(
            client=mock_client,
            file_path=str(tmp_path),
            edit_snippet="code",
            instruction=None,
            base_dir=str(tmp_path),
        )

        assert result["status"] == "error"
        assert result["code"] == "INVALID_PATH"
        assert "not a file" in result["message"]
        mock_client.apply.assert_not_called()

    def test_delete_with_remove_directive_is_allowed(
        self,
        mock_config: RelaceConfig,
        mock_client: MagicMock,
        temp_source_file: Path,
        tmp_path: Path,
    ) -> None:
        """Should allow delete with // remove directive when combined with valid anchors."""
        mock_client.apply.return_value = {
            "mergedCode": "def hello():\n    print('Hello')\n",
            "usage": {},
        }

        # snippet 包含真實 anchor (def hello) 以及 remove directive
        result = apply_file_logic(
            client=mock_client,
            file_path=str(temp_source_file),
            edit_snippet="def hello():\n    print('Hello')\n\n// remove goodbye\n",
            instruction="delete goodbye function",
            base_dir=str(tmp_path),
        )

        # Should call API, not return error
        mock_client.apply.assert_called_once()
        assert result["status"] == "ok"

    def test_no_changes_returns_message(
        self,
        mock_config: RelaceConfig,
        mock_client: MagicMock,
        temp_source_file: Path,
        tmp_path: Path,
    ) -> None:
        """Should return 'No changes made' when diff is empty (idempotent)."""
        original = temp_source_file.read_text()
        mock_client.apply.return_value = {"mergedCode": original, "usage": {}}

        # edit_snippet 包含原始檔案中已存在的內容（真正的 idempotent 場景）
        result = apply_file_logic(
            client=mock_client,
            file_path=str(temp_source_file),
            edit_snippet="def hello():\n    print('Hello')\n",
            instruction=None,
            base_dir=str(tmp_path),
        )

        assert result["status"] == "ok"
        assert "No changes needed" in result["message"] or "already matches" in result["message"]


class TestApplyFileLogicFileSize:
    """Test file size limit enforcement."""

    def test_large_file_returns_recoverable_error(
        self,
        mock_config: RelaceConfig,
        mock_client: MagicMock,
        temp_large_file: Path,
        tmp_path: Path,
    ) -> None:
        """Should return FILE_TOO_LARGE for files exceeding size limit (not crash MCP tool)."""

        result = apply_file_logic(
            client=mock_client,
            file_path=str(temp_large_file),
            edit_snippet="// edit",
            instruction=None,
            base_dir=str(tmp_path),
        )

        assert result["status"] == "error"
        assert result["code"] == "FILE_TOO_LARGE"
        assert "File too large" in result["message"]
        mock_client.apply.assert_not_called()

    def test_file_at_limit_allowed(
        self,
        mock_config: RelaceConfig,
        mock_client: MagicMock,
        tmp_path: Path,
        successful_api_response: dict[str, Any],
    ) -> None:
        """Should allow files exactly at size limit."""
        # Create file exactly at limit (10MB) with recognizable anchor content
        limit_file = tmp_path / "limit.py"
        content = "def placeholder_function():\n" + "x" * (MAX_FILE_SIZE_BYTES - 30)
        limit_file.write_text(content)

        mock_client.apply.return_value = successful_api_response

        # edit_snippet 包含可定位的 anchor lines
        result = apply_file_logic(
            client=mock_client,
            file_path=str(limit_file),
            edit_snippet="def placeholder_function():\n    pass\n",
            instruction=None,
            base_dir=str(tmp_path),
        )
        assert result["status"] == "ok"


class TestApplyFileLogicEncoding:
    """Test file encoding validation."""

    def test_binary_file_returns_recoverable_error(
        self,
        mock_config: RelaceConfig,
        mock_client: MagicMock,
        temp_binary_file: Path,
        tmp_path: Path,
    ) -> None:
        """Should return ENCODING_ERROR on non-text/binary files (not crash MCP tool)."""

        result = apply_file_logic(
            client=mock_client,
            file_path=str(temp_binary_file),
            edit_snippet="// edit",
            instruction=None,
            base_dir=str(tmp_path),
        )

        assert result["status"] == "error"
        assert result["code"] == "ENCODING_ERROR"
        assert "Cannot detect encoding" in result["message"]
        mock_client.apply.assert_not_called()

    def test_gbk_file_supported(
        self,
        mock_config: RelaceConfig,
        mock_client: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Should successfully read and write GBK encoded files."""
        gbk_file = tmp_path / "gbk_file.py"
        # 寫入 GBK 編碼的中文內容（確保有 2 個以上足夠長的 anchor lines）
        gbk_content = "# 这是简体中文注释用于测试\ndef process_chinese_data():\n    print('你好')\n"
        gbk_file.write_bytes(gbk_content.encode("gbk"))

        merged_code = (
            "# 这是简体中文注释用于测试\ndef process_chinese_data():\n    print('你好世界')\n"
        )
        mock_client.apply.return_value = {"mergedCode": merged_code, "usage": {}}

        # edit_snippet 包含原始檔案中存在的 anchor lines
        result = apply_file_logic(
            client=mock_client,
            file_path=str(gbk_file),
            edit_snippet="# 这是简体中文注释用于测试\ndef process_chinese_data():\n    print('你好世界')\n",
            instruction=None,
            base_dir=str(tmp_path),
        )

        assert result["status"] == "ok"
        assert "Applied code changes" in result["message"]
        # 確認寫回的檔案仍為 GBK 編碼
        assert gbk_file.read_bytes().decode("gbk") == merged_code


class TestApplyFileLogicBaseDirSecurity:
    """Test base_dir security restrictions."""

    def test_blocks_path_outside_base_dir(
        self,
        mock_config: RelaceConfig,
        mock_client: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Should block access to files outside base_dir."""

        # 嘗試存取 base_dir 外部的檔案
        outside_file = tmp_path.parent / "outside.py"
        outside_file.write_text("content")

        try:
            result = apply_file_logic(
                client=mock_client,
                file_path=str(outside_file),
                edit_snippet="// edit",
                instruction=None,
                base_dir=str(tmp_path),
            )
            assert result["status"] == "error"
            assert result["code"] == "INVALID_PATH"
            assert "outside allowed directory" in result["message"]
            mock_client.apply.assert_not_called()
        finally:
            outside_file.unlink(missing_ok=True)


class TestApplyFileLogicApiErrors:
    """Test API error handling."""

    def test_logs_error_on_api_failure(
        self,
        mock_config: RelaceConfig,
        mock_client: MagicMock,
        temp_source_file: Path,
        tmp_path: Path,
        mock_log_path: Path,
    ) -> None:
        """Should log error event when API call fails."""
        mock_client.apply.side_effect = RuntimeError("API Error")

        # edit_snippet 包含原始檔案中存在的 anchor lines
        with pytest.raises(RuntimeError):
            apply_file_logic(
                client=mock_client,
                file_path=str(temp_source_file),
                edit_snippet="def hello():\n    print('Hello')\n",
                instruction=None,
                base_dir=str(tmp_path),
            )

        logged = json.loads(mock_log_path.read_text().strip())
        assert logged["kind"] == "apply_error"
        assert "API Error" in logged["error"]

    @pytest.mark.parametrize(
        "response",
        [
            {"usage": {}},  # No mergedCode
            {"mergedCode": None, "usage": {}},  # Null mergedCode
        ],
        ids=["missing_merged_code", "null_merged_code"],
    )
    def test_invalid_merged_code_raises(
        self,
        mock_config: RelaceConfig,
        mock_client: MagicMock,
        temp_source_file: Path,
        tmp_path: Path,
        response: dict[str, Any],
    ) -> None:
        """Should return API_INVALID_RESPONSE when API returns no or null mergedCode."""
        mock_client.apply.return_value = response

        # edit_snippet 包含原始檔案中存在的 anchor lines
        result = apply_file_logic(
            client=mock_client,
            file_path=str(temp_source_file),
            edit_snippet="def hello():\n    print('Hello')\n",
            instruction=None,
            base_dir=str(tmp_path),
        )

        assert result["status"] == "error"
        assert result["code"] == "API_INVALID_RESPONSE"
        assert "did not return 'mergedCode'" in result["message"]


class TestApplyFileLogicSnippetPreview:
    """Test edit_snippet_preview in logs."""

    def test_truncates_long_snippet_in_log(
        self,
        mock_config: RelaceConfig,
        mock_client: MagicMock,
        temp_source_file: Path,
        tmp_path: Path,
        mock_log_path: Path,
    ) -> None:
        """Should truncate edit_snippet to 200 chars in log."""
        # 長 snippet 需包含可定位的 anchor lines，且 mergedCode 應包含新增內容以通過 post_check
        long_suffix = "x" * 500
        long_snippet = "def hello():\n    print('Hello')\n" + long_suffix
        merged_code = "def hello():\n    print('Hello')\n" + long_suffix

        mock_client.apply.return_value = {"mergedCode": merged_code, "usage": {}}

        apply_file_logic(
            client=mock_client,
            file_path=str(temp_source_file),
            edit_snippet=long_snippet,
            instruction=None,
            base_dir=str(tmp_path),
        )

        logged = json.loads(mock_log_path.read_text().strip())
        assert len(logged["edit_snippet_preview"]) == 200


class TestApplyFileLogicPathNormalization:
    """Test path normalization for /repo/... virtual root."""

    @pytest.mark.parametrize(
        "file_path",
        ["/repo/src/file.py", "src/file.py"],
        ids=["virtual_root", "relative_path"],
    )
    def test_path_formats_accepted(
        self,
        mock_config: RelaceConfig,
        mock_client: MagicMock,
        tmp_path: Path,
        file_path: str,
    ) -> None:
        """Should accept /repo/... and relative path formats and map to base_dir."""
        test_file = tmp_path / "src" / "file.py"
        test_file.parent.mkdir(parents=True, exist_ok=True)
        test_file.write_text("original_value = True\n")

        mock_client.apply.return_value = {
            "mergedCode": "modified_value = True\n",
            "usage": {},
        }

        # edit_snippet 包含原始檔案中存在的 anchor lines
        result = apply_file_logic(
            client=mock_client,
            file_path=file_path,
            edit_snippet="original_value = True\nmodified_value = True\n",
            instruction=None,
            base_dir=str(tmp_path),
        )

        assert result["status"] == "ok"
        assert "Applied code changes" in result["message"]
        mock_client.apply.assert_called_once()

    def test_invalid_path_returns_error(
        self,
        mock_config: RelaceConfig,
        mock_client: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Should return INVALID_PATH for paths outside base_dir."""

        result = apply_file_logic(
            client=mock_client,
            file_path="/other/path/file.py",
            edit_snippet="code",
            instruction=None,
            base_dir=str(tmp_path),
        )

        assert result["status"] == "error"
        assert result["code"] == "INVALID_PATH"
        assert "outside allowed directory" in result["message"]
        mock_client.apply.assert_not_called()


class TestApplyFileLogicRecoverableErrors:
    """Test recoverable error handling."""

    def test_anchor_precheck_failure_returns_needs_more_context(
        self,
        mock_config: RelaceConfig,
        mock_client: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Should return NEEDS_MORE_CONTEXT when anchor lines don't match file content."""
        test_file = tmp_path / "test.py"
        test_file.write_text("def existing_function():\n    return 42\n")

        # edit_snippet 包含省略標記（觸發 precheck）但 anchor 無法定位
        result = apply_file_logic(
            client=mock_client,
            file_path=str(test_file),
            edit_snippet="// ... existing code ...\ndef totally_different_function():\n    return 999\n// ... more code ...\n",
            instruction="Edit something",
            base_dir=str(tmp_path),
        )

        assert result["status"] == "error"
        assert result["code"] == "NEEDS_MORE_CONTEXT"
        assert "無法在檔案中定位" in result["message"]
        # API should NOT be called when precheck fails
        mock_client.apply.assert_not_called()

    def test_anchor_precheck_skipped_with_append_directive(
        self,
        mock_config: RelaceConfig,
        mock_client: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Instruction 含明確位置 directive 時應跳過 precheck，避免誤判阻擋。"""
        test_file = tmp_path / "test.py"
        original = "def existing_function():\n    return 42\n"
        test_file.write_text(original)

        merged = original + "\n# appended\n"
        mock_client.apply.return_value = {"mergedCode": merged, "usage": {}}

        result = apply_file_logic(
            client=mock_client,
            file_path=str(test_file),
            edit_snippet="// ... existing code ...\n# appended\n// ... existing code ...\n",
            instruction="Append to end of file",
            base_dir=str(tmp_path),
        )

        assert result["status"] == "ok"
        mock_client.apply.assert_called_once()
        assert test_file.read_text() == merged

    def test_permission_error_returns_permission_error(
        self,
        mock_config: RelaceConfig,
        mock_client: MagicMock,
        tmp_path: Path,
    ) -> None:
        """PermissionError 應轉為 PERMISSION_ERROR（避免 MCP tool crash）。"""
        test_file = tmp_path / "test.py"
        test_file.write_text("def existing_function():\n    return 42\n")

        with patch(
            "relace_mcp.tools.apply.core.file_io.read_text_with_fallback",
            side_effect=PermissionError("Permission denied"),
        ):
            result = apply_file_logic(
                client=mock_client,
                file_path=str(test_file),
                edit_snippet="def existing_function():\n    return 42\n",
                instruction=None,
                base_dir=str(tmp_path),
            )

        assert result["status"] == "error"
        assert result["code"] == "PERMISSION_ERROR"

    def test_filesystem_error_returns_fs_error_on_create(
        self,
        mock_config: RelaceConfig,
        mock_client: MagicMock,
        tmp_path: Path,
    ) -> None:
        """OSError 應轉為 FS_ERROR（避免 MCP tool crash）。"""
        new_file = tmp_path / "new_file.py"

        with patch(
            "relace_mcp.tools.apply.core.file_io.atomic_write",
            side_effect=OSError("Disk full"),
        ):
            result = apply_file_logic(
                client=mock_client,
                file_path=str(new_file),
                edit_snippet="print('hello')\n",
                instruction=None,
                base_dir=str(tmp_path),
            )

        assert result["status"] == "error"
        assert result["code"] == "FS_ERROR"
        assert not new_file.exists()
        mock_client.apply.assert_not_called()

    def test_read_only_file_returns_file_not_writable(
        self,
        mock_config: RelaceConfig,
        mock_client: MagicMock,
        tmp_path: Path,
    ) -> None:
        """檔案不可寫時應轉為 FILE_NOT_WRITABLE（避免 MCP tool crash）。"""
        test_file = tmp_path / "readonly.py"
        test_file.write_text("original_value_setting = True\nprocess_data_function()\n")
        test_file.chmod(0o444)

        mock_client.apply.return_value = {
            "mergedCode": "modified_value_setting = False\nprocess_data_function()\n",
            "usage": {},
        }

        result = apply_file_logic(
            client=mock_client,
            file_path=str(test_file),
            edit_snippet="original_value_setting = True\nmodified_value_setting = False\nprocess_data_function()\n",
            instruction="Modify",
            base_dir=str(tmp_path),
        )

        assert result["status"] == "error"
        assert result["code"] == "FILE_NOT_WRITABLE"

    def test_api_auth_error_returns_auth_error(
        self,
        mock_config: RelaceConfig,
        mock_client: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Should return AUTH_ERROR for 401/403 API errors."""
        from relace_mcp.clients.exceptions import RelaceAPIError

        test_file = tmp_path / "test.py"
        test_file.write_text("def authenticate_user():\n    return validate_credentials()\n")

        mock_client.apply.side_effect = RelaceAPIError(
            status_code=401,
            code="unauthorized",
            message="Invalid API key",
            retryable=False,
        )

        result = apply_file_logic(
            client=mock_client,
            file_path=str(test_file),
            edit_snippet="def authenticate_user():\n    return validate_credentials()\n",
            instruction=None,
            base_dir=str(tmp_path),
        )

        assert result["status"] == "error"
        assert result["code"] == "AUTH_ERROR"
        assert "API 認證或權限錯誤" in result["message"]
        assert result["detail"]["status_code"] == 401
        assert result["detail"]["api_code"] == "unauthorized"
        assert "Invalid API key" in result["detail"]["api_message"]

    def test_api_403_error_returns_auth_error(
        self,
        mock_config: RelaceConfig,
        mock_client: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Should return AUTH_ERROR for 403 API errors."""
        from relace_mcp.clients.exceptions import RelaceAPIError

        test_file = tmp_path / "test.py"
        test_file.write_text("def authenticate_user():\n    return validate_credentials()\n")

        mock_client.apply.side_effect = RelaceAPIError(
            status_code=403,
            code="forbidden",
            message="Access denied",
            retryable=False,
        )

        result = apply_file_logic(
            client=mock_client,
            file_path=str(test_file),
            edit_snippet="def authenticate_user():\n    return validate_credentials()\n",
            instruction=None,
            base_dir=str(tmp_path),
        )

        assert result["status"] == "error"
        assert result["code"] == "AUTH_ERROR"
        assert result["detail"]["status_code"] == 403

    def test_api_other_4xx_returns_api_error(
        self,
        mock_config: RelaceConfig,
        mock_client: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Should return API_ERROR for other 4xx errors (e.g., anchor not found)."""
        from relace_mcp.clients.exceptions import RelaceAPIError

        test_file = tmp_path / "test.py"
        test_file.write_text("def authenticate_user():\n    return validate_credentials()\n")

        mock_client.apply.side_effect = RelaceAPIError(
            status_code=400,
            code="anchor_not_found",
            message="Cannot locate anchor lines",
            retryable=False,
        )

        result = apply_file_logic(
            client=mock_client,
            file_path=str(test_file),
            edit_snippet="def authenticate_user():\n    return validate_credentials()\n",
            instruction="Edit function",
            base_dir=str(tmp_path),
        )

        assert result["status"] == "error"
        assert result["code"] == "API_ERROR"
        assert "Relace API 錯誤" in result["message"]
        assert result["detail"]["status_code"] == 400
        assert result["detail"]["api_code"] == "anchor_not_found"
        assert "Cannot locate anchor lines" in result["detail"]["api_message"]

    def test_network_error_returns_network_error(
        self,
        mock_config: RelaceConfig,
        mock_client: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Should return NETWORK_ERROR for network failures."""
        from relace_mcp.clients.exceptions import RelaceNetworkError

        test_file = tmp_path / "test.py"
        test_file.write_text("def authenticate_user():\n    return validate_credentials()\n")

        mock_client.apply.side_effect = RelaceNetworkError("Connection failed")

        result = apply_file_logic(
            client=mock_client,
            file_path=str(test_file),
            edit_snippet="def authenticate_user():\n    return validate_credentials()\n",
            instruction=None,
            base_dir=str(tmp_path),
        )

        assert result["status"] == "error"
        assert result["code"] == "NETWORK_ERROR"
        assert "網路錯誤" in result["message"]
        assert "Connection failed" in result["detail"]

    def test_timeout_error_returns_timeout_error(
        self,
        mock_config: RelaceConfig,
        mock_client: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Should return TIMEOUT_ERROR for timeout failures."""
        from relace_mcp.clients.exceptions import RelaceTimeoutError

        test_file = tmp_path / "test.py"
        test_file.write_text("def authenticate_user():\n    return validate_credentials()\n")

        mock_client.apply.side_effect = RelaceTimeoutError("Request timed out after 60s")

        result = apply_file_logic(
            client=mock_client,
            file_path=str(test_file),
            edit_snippet="def authenticate_user():\n    return validate_credentials()\n",
            instruction=None,
            base_dir=str(tmp_path),
        )

        assert result["status"] == "error"
        assert result["code"] == "TIMEOUT_ERROR"
        assert "請求逾時" in result["message"]
        assert "Request timed out" in result["detail"]

    def test_anchor_precheck_allows_remove_directives(
        self,
        mock_config: RelaceConfig,
        mock_client: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Should allow snippets with remove directives if they have valid anchors."""
        test_file = tmp_path / "test.py"
        test_file.write_text(
            "def main_function():\n    return process_data()\n\ndef helper_function():\n    return compute_result()\n"
        )

        mock_client.apply.return_value = {
            "mergedCode": "def main_function():\n    return process_data()\n",
            "usage": {},
        }

        result = apply_file_logic(
            client=mock_client,
            file_path=str(test_file),
            edit_snippet="def main_function():\n    return process_data()\n\n// remove helper_function\n",
            instruction="Remove helper function",
            base_dir=str(tmp_path),
        )

        # Should call API, not return NEEDS_MORE_CONTEXT
        mock_client.apply.assert_called_once()
        assert result["status"] == "ok"

    def test_anchor_precheck_with_indentation_difference(
        self,
        mock_config: RelaceConfig,
        mock_client: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Should use strip() for lenient matching despite indentation differences."""
        test_file = tmp_path / "test.py"
        test_file.write_text("def process_data_handler():\n    return calculate_result_value()\n")

        mock_client.apply.return_value = {
            "mergedCode": "def process_data_handler():\n    return calculate_result_v2()\n",
            "usage": {},
        }

        # edit_snippet 的縮排與原檔案不同，但 strip() 後應能匹配
        # 確保有 2 個 anchor hits：def process_data_handler(): 和 return calculate_result_value()
        result = apply_file_logic(
            client=mock_client,
            file_path=str(test_file),
            edit_snippet="def process_data_handler():\nreturn calculate_result_value()\n",  # 縮排不同
            instruction="Change return value",
            base_dir=str(tmp_path),
        )

        # Should pass precheck and call API
        mock_client.apply.assert_called_once()
        assert result["status"] == "ok"


class TestApplyNoopDetection:
    """Test no-op detection logic (Defense 2)."""

    def test_noop_with_new_lines_returns_apply_noop(
        self,
        mock_config: RelaceConfig,
        mock_client: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Snippet 含新行但 merge 後無變更，應回 APPLY_NOOP。"""
        test_file = tmp_path / "test.py"
        original_content = "def process_data_from_input():\n    return calculate_result_value()\n"
        test_file.write_text(original_content)

        # API 返回與原檔相同的內容（模擬 apply 失敗）
        mock_client.apply.return_value = {
            "mergedCode": original_content,
            "usage": {},
        }

        result = apply_file_logic(
            client=mock_client,
            file_path=str(test_file),
            edit_snippet="def process_data_from_input():\n    return calculate_result_value()\n\ndef new_function_that_should_be_added():\n    pass\n",
            instruction="Add new function",
            base_dir=str(tmp_path),
        )

        assert result["status"] == "error"
        assert result["code"] == "APPLY_NOOP"
        assert "identical to initial" in result["message"]

    def test_noop_idempotent_returns_ok(
        self,
        mock_config: RelaceConfig,
        mock_client: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Snippet 本來就已存在，應回 OK（idempotent）。"""
        test_file = tmp_path / "test.py"
        original_content = "def process_data_from_input():\n    return calculate_result_value()\n"
        test_file.write_text(original_content)

        # API 返回與原檔相同的內容
        mock_client.apply.return_value = {
            "mergedCode": original_content,
            "usage": {},
        }

        # snippet 只包含已存在的程式碼（真正的 idempotent）
        result = apply_file_logic(
            client=mock_client,
            file_path=str(test_file),
            edit_snippet="def process_data_from_input():\n    return calculate_result_value()\n",
            instruction="Ensure function exists",
            base_dir=str(tmp_path),
        )

        assert result["status"] == "ok"
        assert "No changes needed" in result["message"] or "already matches" in result["message"]

    def test_noop_with_remove_directive_returns_apply_noop(
        self,
        mock_config: RelaceConfig,
        mock_client: MagicMock,
        tmp_path: Path,
    ) -> None:
        """有 remove directive 但無變更，應回 APPLY_NOOP。"""
        test_file = tmp_path / "test.py"
        original_content = "def main_function_handler():\n    return process_request()\n\ndef helper_utility_function():\n    return compute_value()\n"
        test_file.write_text(original_content)

        # API 返回與原檔相同的內容（remove 失敗）
        mock_client.apply.return_value = {
            "mergedCode": original_content,
            "usage": {},
        }

        result = apply_file_logic(
            client=mock_client,
            file_path=str(test_file),
            edit_snippet="def main_function_handler():\n    return process_request()\n\n// remove helper_utility_function\n",
            instruction="Remove helper function",
            base_dir=str(tmp_path),
        )

        assert result["status"] == "error"
        assert result["code"] == "APPLY_NOOP"

    def test_noop_with_short_new_line_returns_apply_noop(
        self,
        mock_config: RelaceConfig,
        mock_client: MagicMock,
        tmp_path: Path,
    ) -> None:
        """新增短行（如 x = 1）但 merge 後無變更，應回 APPLY_NOOP。"""
        test_file = tmp_path / "test.py"
        original_content = "def process_data_handler():\n    return calculate_result()\n"
        test_file.write_text(original_content)

        # API 返回與原檔相同的內容（apply 失敗）
        mock_client.apply.return_value = {
            "mergedCode": original_content,
            "usage": {},
        }

        # 新增短行 x = 1（5 字元）
        result = apply_file_logic(
            client=mock_client,
            file_path=str(test_file),
            edit_snippet="def process_data_handler():\n    return calculate_result()\n    x = 1\n",
            instruction="Add variable",
            base_dir=str(tmp_path),
        )

        assert result["status"] == "error"
        assert result["code"] == "APPLY_NOOP"

    def test_noop_with_trivial_line_returns_ok(
        self,
        mock_config: RelaceConfig,
        mock_client: MagicMock,
        tmp_path: Path,
    ) -> None:
        """新增 trivial 行（如 return）視為 idempotent，應回 OK。"""
        test_file = tmp_path / "test.py"
        original_content = "def process_data_handler():\n    calculate_result()\n"
        test_file.write_text(original_content)

        # API 返回與原檔相同的內容
        mock_client.apply.return_value = {
            "mergedCode": original_content,
            "usage": {},
        }

        # 只新增 trivial 行 return（常見語法關鍵字）
        result = apply_file_logic(
            client=mock_client,
            file_path=str(test_file),
            edit_snippet="def process_data_handler():\n    calculate_result()\n    return\n",
            instruction="Add return",
            base_dir=str(tmp_path),
        )

        # return 是 trivial token，不視為預期變更
        assert result["status"] == "ok"

    def test_noop_with_substring_match_returns_apply_noop(
        self,
        mock_config: RelaceConfig,
        mock_client: MagicMock,
        tmp_path: Path,
    ) -> None:
        """新行是現有行的子字串時，應正確偵測為 APPLY_NOOP。"""
        test_file = tmp_path / "test.py"
        # x = 100 包含 x = 1 作為子字串
        original_content = "def process_data_handler():\n    x = 100\n    return x\n"
        test_file.write_text(original_content)

        # API 返回與原檔相同的內容（apply 失敗）
        mock_client.apply.return_value = {
            "mergedCode": original_content,
            "usage": {},
        }

        # snippet 包含 x = 1（是 x = 100 的子字串，但應被視為新行）
        result = apply_file_logic(
            client=mock_client,
            file_path=str(test_file),
            edit_snippet="def process_data_handler():\n    x = 1\n    return x\n",
            instruction="Change value",
            base_dir=str(tmp_path),
        )

        # x = 1 不等於 x = 100，應偵測為預期變更
        assert result["status"] == "error"
        assert result["code"] == "APPLY_NOOP"


class TestApplyWriteVerification:
    """Test atomic write and post-write verification (Defense 3)."""

    def test_atomic_write_creates_temp_file(
        self,
        mock_config: RelaceConfig,
        mock_client: MagicMock,
        tmp_path: Path,
    ) -> None:
        """原子寫入應正常完成，不留下 .tmp 檔案。"""
        test_file = tmp_path / "test.py"
        test_file.write_text("original_content_value = True\nprocess_data_function()\n")

        mock_client.apply.return_value = {
            "mergedCode": "modified_content_value = False\nprocess_data_function()\n",
            "usage": {},
        }

        result = apply_file_logic(
            client=mock_client,
            file_path=str(test_file),
            edit_snippet="original_content_value = True\nmodified_content_value = False\nprocess_data_function()\n",
            instruction="Modify content",
            base_dir=str(tmp_path),
        )

        # 應該成功
        assert result["status"] == "ok"
        # .tmp 檔案不應該存在（原子寫入完成後會被刪除）
        assert not (tmp_path / "test.py.tmp").exists()
        # 內容應該是新的
        assert test_file.read_text() == "modified_content_value = False\nprocess_data_function()\n"

    def test_post_write_verification_failure_returns_error(
        self,
        mock_config: RelaceConfig,
        mock_client: MagicMock,
        tmp_path: Path,
    ) -> None:
        """寫入後驗證失敗應返回 WRITE_VERIFY_FAILED。"""
        test_file = tmp_path / "test.py"
        original = "original_content_value = True\nprocess_data_function()\n"
        test_file.write_text(original)

        mock_client.apply.return_value = {
            "mergedCode": "modified_content_value = False\nprocess_data_function()\n",
            "usage": {},
        }

        # Mock read_text_with_fallback 在驗證時拋出異常
        with patch("relace_mcp.tools.apply.core.file_io.read_text_with_fallback") as mock_read:
            # 第一次呼叫（讀取原始檔案）返回正常內容
            # 第二次呼叫（驗證寫入）拋出異常
            mock_read.side_effect = [
                (original, "utf-8"),
                OSError("Permission denied"),
            ]

            result = apply_file_logic(
                client=mock_client,
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

    def test_success_response_includes_path_and_trace_id(
        self,
        mock_config: RelaceConfig,
        mock_client: MagicMock,
        tmp_path: Path,
    ) -> None:
        """成功回應應包含 path 和 trace_id。"""
        test_file = tmp_path / "test.py"
        test_file.write_text("original_value_setting = True\nprocess_data_function()\n")

        mock_client.apply.return_value = {
            "mergedCode": "modified_value_setting = False\nprocess_data_function()\n",
            "usage": {},
        }

        result = apply_file_logic(
            client=mock_client,
            file_path=str(test_file),
            edit_snippet="original_value_setting = True\nmodified_value_setting = False\nprocess_data_function()\n",
            instruction="Modify",
            base_dir=str(tmp_path),
        )

        assert result["status"] == "ok"
        assert result["path"] == str(test_file)
        assert result["trace_id"] is not None
        assert result["timing_ms"] >= 0

    def test_noop_response_includes_path(
        self,
        mock_config: RelaceConfig,
        mock_client: MagicMock,
        tmp_path: Path,
    ) -> None:
        """No-op（idempotent）回應也應包含 path。"""
        test_file = tmp_path / "test.py"
        original_content = "def existing_function_handler():\n    return process_request_data()\n"
        test_file.write_text(original_content)

        mock_client.apply.return_value = {
            "mergedCode": original_content,
            "usage": {},
        }

        # 真正的 idempotent 情況
        result = apply_file_logic(
            client=mock_client,
            file_path=str(test_file),
            edit_snippet="def existing_function_handler():\n    return process_request_data()\n",
            instruction="Ensure exists",
            base_dir=str(tmp_path),
        )

        assert result["status"] == "ok"
        assert result["path"] == str(test_file)
        assert result["trace_id"] is not None
