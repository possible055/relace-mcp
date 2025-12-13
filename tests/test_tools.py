import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from relace_mcp.config import RelaceConfig
from relace_mcp.tools.apply import (
    MAX_FILE_SIZE_BYTES,
    _log_event,
    apply_file_logic,
)
from relace_mcp.utils import validate_file_path


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

    def test_writes_json_line(self, tmp_path: Path) -> None:
        """Should write JSON event to log file."""
        log_file = tmp_path / "test.log"
        with patch("relace_mcp.tools.apply.LOG_PATH", log_file):
            _log_event({"kind": "test", "message": "hello"})
        content = log_file.read_text()
        logged = json.loads(content.strip())
        assert logged["kind"] == "test"
        assert logged["message"] == "hello"
        assert "timestamp" in logged

    def test_appends_to_existing_log(self, tmp_path: Path) -> None:
        """Should append to existing log file."""
        log_file = tmp_path / "test.log"
        with patch("relace_mcp.tools.apply.LOG_PATH", log_file):
            _log_event({"event": 1})
            _log_event({"event": 2})

        lines = log_file.read_text().strip().split("\n")
        assert len(lines) == 2

    def test_creates_parent_directories(self, tmp_path: Path) -> None:
        """Should create parent directories if needed."""
        log_path = tmp_path / "deep" / "nested" / "dir" / "log.json"
        with patch("relace_mcp.tools.apply.LOG_PATH", log_path):
            _log_event({"test": True})
        assert log_path.exists()

    def test_preserves_existing_timestamp(self, tmp_path: Path) -> None:
        """Should not overwrite existing timestamp."""
        log_file = tmp_path / "test.log"
        with patch("relace_mcp.tools.apply.LOG_PATH", log_file):
            _log_event({"kind": "test", "timestamp": "2024-01-01T00:00:00Z"})
        logged = json.loads(log_file.read_text().strip())
        assert logged["timestamp"] == "2024-01-01T00:00:00Z"

    def test_handles_log_failure_gracefully(self, tmp_path: Path) -> None:
        """Should not raise on log write failure (e.g., path is a directory)."""
        # 使用目錄作為 log 路徑會失敗，但不應拋出例外
        with patch("relace_mcp.tools.apply.LOG_PATH", tmp_path):  # tmp_path 是目錄
            _log_event({"test": True})  # 不應拋出例外


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

        result = apply_file_logic(
            client=mock_client,
            file_path=str(temp_source_file),
            edit_snippet="// new code",
            instruction="Add feature",
            base_dir=str(tmp_path),
        )

        assert "Applied code changes using Relace API" in result
        assert "Changes made:" in result
        assert "--- before" in result
        assert "+++ after" in result

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

        apply_file_logic(
            client=mock_client,
            file_path=str(temp_source_file),
            edit_snippet="// edit",
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

        assert "Created" in result
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

        assert "INVALID_INPUT" in result
        assert "edit_snippet cannot be empty" in result

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

        assert "NEEDS_MORE_CONTEXT" in result
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

        assert "INVALID_PATH" in result
        assert "cannot be empty" in result
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

        assert "INVALID_PATH" in result
        assert "not a file" in result
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
        assert "Applied code changes" in result or "No changes made" in result

    def test_no_changes_returns_message(
        self,
        mock_config: RelaceConfig,
        mock_client: MagicMock,
        temp_source_file: Path,
        tmp_path: Path,
    ) -> None:
        """Should return 'No changes made' when diff is empty."""
        original = temp_source_file.read_text()
        mock_client.apply.return_value = {"mergedCode": original, "usage": {}}

        result = apply_file_logic(
            client=mock_client,
            file_path=str(temp_source_file),
            edit_snippet="// edit",
            instruction=None,
            base_dir=str(tmp_path),
        )

        assert result == "No changes made"


class TestApplyFileLogicFileSize:
    """Test file size limit enforcement."""

    def test_large_file_raises(
        self,
        mock_config: RelaceConfig,
        mock_client: MagicMock,
        temp_large_file: Path,
        tmp_path: Path,
    ) -> None:
        """Should raise on files exceeding size limit."""

        with pytest.raises(RuntimeError, match="File too large"):
            apply_file_logic(
                client=mock_client,
                file_path=str(temp_large_file),
                edit_snippet="// edit",
                instruction=None,
                base_dir=str(tmp_path),
            )

    def test_file_at_limit_allowed(
        self,
        mock_config: RelaceConfig,
        mock_client: MagicMock,
        tmp_path: Path,
        successful_api_response: dict[str, Any],
    ) -> None:
        """Should allow files exactly at size limit."""
        # Create file exactly at limit (10MB)
        limit_file = tmp_path / "limit.py"
        limit_file.write_text("x" * MAX_FILE_SIZE_BYTES)

        mock_client.apply.return_value = successful_api_response

        # Should not raise
        result = apply_file_logic(
            client=mock_client,
            file_path=str(limit_file),
            edit_snippet="// edit",
            instruction=None,
            base_dir=str(tmp_path),
        )
        assert "Applied code changes" in result or "No changes made" in result


class TestApplyFileLogicEncoding:
    """Test file encoding validation."""

    def test_binary_file_raises(
        self,
        mock_config: RelaceConfig,
        mock_client: MagicMock,
        temp_binary_file: Path,
        tmp_path: Path,
    ) -> None:
        """Should raise on non-UTF-8 encoded files."""

        with pytest.raises(RuntimeError, match="Cannot detect encoding"):
            apply_file_logic(
                client=mock_client,
                file_path=str(temp_binary_file),
                edit_snippet="// edit",
                instruction=None,
                base_dir=str(tmp_path),
            )

    def test_gbk_file_supported(
        self,
        mock_config: RelaceConfig,
        mock_client: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Should successfully read and write GBK encoded files."""
        gbk_file = tmp_path / "gbk_file.py"
        # 寫入 GBK 編碼的中文內容
        gbk_content = "# 这是简体中文注释\nprint('你好')\n"
        gbk_file.write_bytes(gbk_content.encode("gbk"))

        merged_code = "# 这是简体中文注释\nprint('你好世界')\n"
        mock_client.apply.return_value = {"mergedCode": merged_code, "usage": {}}

        result = apply_file_logic(
            client=mock_client,
            file_path=str(gbk_file),
            edit_snippet="// edit",
            instruction=None,
            base_dir=str(tmp_path),
        )

        assert "Applied code changes" in result
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
            assert "INVALID_PATH" in result
            assert "outside allowed directory" in result
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

        with pytest.raises(RuntimeError):
            apply_file_logic(
                client=mock_client,
                file_path=str(temp_source_file),
                edit_snippet="// edit",
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
        """Should raise when API returns no or null mergedCode."""
        mock_client.apply.return_value = response

        with pytest.raises(RuntimeError, match="did not return 'mergedCode'"):
            apply_file_logic(
                client=mock_client,
                file_path=str(temp_source_file),
                edit_snippet="// edit",
                instruction=None,
                base_dir=str(tmp_path),
            )


class TestApplyFileLogicSnippetPreview:
    """Test edit_snippet_preview in logs."""

    def test_truncates_long_snippet_in_log(
        self,
        mock_config: RelaceConfig,
        mock_client: MagicMock,
        temp_source_file: Path,
        successful_api_response: dict[str, Any],
        tmp_path: Path,
        mock_log_path: Path,
    ) -> None:
        """Should truncate edit_snippet to 200 chars in log."""
        mock_client.apply.return_value = successful_api_response

        long_snippet = "x" * 500

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
        test_file.write_text("original = True\n")

        mock_client.apply.return_value = {
            "mergedCode": "modified = True\n",
            "usage": {},
        }

        result = apply_file_logic(
            client=mock_client,
            file_path=file_path,
            edit_snippet="modified = True\n",
            instruction=None,
            base_dir=str(tmp_path),
        )

        assert "Applied code changes" in result
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

        assert "INVALID_PATH" in result
        assert "outside allowed directory" in result
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

        assert "NEEDS_MORE_CONTEXT" in result
        assert "無法在檔案中定位" in result
        # API should NOT be called when precheck fails
        mock_client.apply.assert_not_called()

    def test_api_auth_error_returns_auth_error(
        self,
        mock_config: RelaceConfig,
        mock_client: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Should return AUTH_ERROR for 401/403 API errors."""
        from relace_mcp.clients.exceptions import RelaceAPIError

        test_file = tmp_path / "test.py"
        test_file.write_text("def foo():\n    pass\n")

        mock_client.apply.side_effect = RelaceAPIError(
            status_code=401,
            code="unauthorized",
            message="Invalid API key",
            retryable=False,
        )

        result = apply_file_logic(
            client=mock_client,
            file_path=str(test_file),
            edit_snippet="def foo():\n    pass\n",
            instruction=None,
            base_dir=str(tmp_path),
        )

        assert "AUTH_ERROR" in result
        assert "API 認證或權限錯誤" in result
        assert "status: 401" in result
        assert "code: unauthorized" in result
        assert "Invalid API key" in result

    def test_api_403_error_returns_auth_error(
        self,
        mock_config: RelaceConfig,
        mock_client: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Should return AUTH_ERROR for 403 API errors."""
        from relace_mcp.clients.exceptions import RelaceAPIError

        test_file = tmp_path / "test.py"
        test_file.write_text("def foo():\n    pass\n")

        mock_client.apply.side_effect = RelaceAPIError(
            status_code=403,
            code="forbidden",
            message="Access denied",
            retryable=False,
        )

        result = apply_file_logic(
            client=mock_client,
            file_path=str(test_file),
            edit_snippet="def foo():\n    pass\n",
            instruction=None,
            base_dir=str(tmp_path),
        )

        assert "AUTH_ERROR" in result
        assert "status: 403" in result

    def test_api_other_4xx_returns_api_error(
        self,
        mock_config: RelaceConfig,
        mock_client: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Should return API_ERROR for other 4xx errors (e.g., anchor not found)."""
        from relace_mcp.clients.exceptions import RelaceAPIError

        test_file = tmp_path / "test.py"
        test_file.write_text("def foo():\n    pass\n")

        mock_client.apply.side_effect = RelaceAPIError(
            status_code=400,
            code="anchor_not_found",
            message="Cannot locate anchor lines",
            retryable=False,
        )

        result = apply_file_logic(
            client=mock_client,
            file_path=str(test_file),
            edit_snippet="def foo():\n    pass\n",
            instruction="Edit function",
            base_dir=str(tmp_path),
        )

        assert "API_ERROR" in result
        assert "Relace API 錯誤" in result
        assert "status: 400" in result
        assert "code: anchor_not_found" in result
        assert "Cannot locate anchor lines" in result

    def test_network_error_returns_network_error(
        self,
        mock_config: RelaceConfig,
        mock_client: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Should return NETWORK_ERROR for network failures."""
        from relace_mcp.clients.exceptions import RelaceNetworkError

        test_file = tmp_path / "test.py"
        test_file.write_text("def foo():\n    pass\n")

        mock_client.apply.side_effect = RelaceNetworkError("Connection failed")

        result = apply_file_logic(
            client=mock_client,
            file_path=str(test_file),
            edit_snippet="def foo():\n    pass\n",
            instruction=None,
            base_dir=str(tmp_path),
        )

        assert "NETWORK_ERROR" in result
        assert "網路錯誤" in result
        assert "Connection failed" in result

    def test_timeout_error_returns_timeout_error(
        self,
        mock_config: RelaceConfig,
        mock_client: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Should return TIMEOUT_ERROR for timeout failures."""
        from relace_mcp.clients.exceptions import RelaceTimeoutError

        test_file = tmp_path / "test.py"
        test_file.write_text("def foo():\n    pass\n")

        mock_client.apply.side_effect = RelaceTimeoutError("Request timed out after 60s")

        result = apply_file_logic(
            client=mock_client,
            file_path=str(test_file),
            edit_snippet="def foo():\n    pass\n",
            instruction=None,
            base_dir=str(tmp_path),
        )

        assert "TIMEOUT_ERROR" in result
        assert "請求逾時" in result
        assert "Request timed out" in result

    def test_anchor_precheck_allows_remove_directives(
        self,
        mock_config: RelaceConfig,
        mock_client: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Should allow snippets with remove directives if they have valid anchors."""
        test_file = tmp_path / "test.py"
        test_file.write_text("def foo():\n    pass\n\ndef bar():\n    pass\n")

        mock_client.apply.return_value = {
            "mergedCode": "def foo():\n    pass\n",
            "usage": {},
        }

        result = apply_file_logic(
            client=mock_client,
            file_path=str(test_file),
            edit_snippet="def foo():\n    pass\n\n// remove bar\n",
            instruction="Remove bar function",
            base_dir=str(tmp_path),
        )

        # Should call API, not return NEEDS_MORE_CONTEXT
        mock_client.apply.assert_called_once()
        assert "Applied code changes" in result or "No changes made" in result

    def test_anchor_precheck_with_indentation_difference(
        self,
        mock_config: RelaceConfig,
        mock_client: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Should use strip() for lenient matching despite indentation differences."""
        test_file = tmp_path / "test.py"
        test_file.write_text("def foo():\n    return True\n")

        mock_client.apply.return_value = {
            "mergedCode": "def foo():\n    return False\n",
            "usage": {},
        }

        # edit_snippet 的縮排與原檔案不同，但 strip() 後應能匹配
        result = apply_file_logic(
            client=mock_client,
            file_path=str(test_file),
            edit_snippet="def foo():\nreturn False\n",  # 縮排不同
            instruction="Change return value",
            base_dir=str(tmp_path),
        )

        # Should pass precheck and call API
        mock_client.apply.assert_called_once()
        assert "Applied code changes" in result or "No changes made" in result
