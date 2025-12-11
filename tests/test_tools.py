import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from relace_mcp.clients import RelaceClient
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
        temp_source_file: Path,
        successful_api_response: dict[str, Any],
        tmp_path: Path,
    ) -> None:
        """Should successfully apply edit and return UDiff."""
        mock_client = MagicMock(spec=RelaceClient)
        mock_client.apply.return_value = successful_api_response

        log_file = tmp_path / "test.log"
        with patch("relace_mcp.tools.apply.LOG_PATH", log_file):
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
        temp_source_file: Path,
        successful_api_response: dict[str, Any],
        tmp_path: Path,
    ) -> None:
        """Should log success event."""
        mock_client = MagicMock(spec=RelaceClient)
        mock_client.apply.return_value = successful_api_response

        log_file = tmp_path / "test.log"
        with patch("relace_mcp.tools.apply.LOG_PATH", log_file):
            apply_file_logic(
                client=mock_client,
                file_path=str(temp_source_file),
                edit_snippet="// edit",
                instruction=None,
                base_dir=str(tmp_path),
            )

        logged = json.loads(log_file.read_text().strip())
        assert logged["kind"] == "apply_success"

    def test_create_new_file(
        self,
        mock_config: RelaceConfig,
        tmp_path: Path,
    ) -> None:
        """Should create new file directly without calling API."""
        mock_client = MagicMock(spec=RelaceClient)
        new_file = tmp_path / "new_file.py"
        content = "def hello():\n    print('Hello')\n"

        log_file = tmp_path / "test.log"
        with patch("relace_mcp.tools.apply.LOG_PATH", log_file):
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
    def test_empty_or_whitespace_edit_snippet_raises(
        self,
        mock_config: RelaceConfig,
        temp_source_file: Path,
        tmp_path: Path,
        snippet: str,
    ) -> None:
        """Should raise on empty or whitespace-only edit_snippet."""
        mock_client = MagicMock(spec=RelaceClient)

        with pytest.raises(RuntimeError, match="edit_snippet cannot be empty"):
            apply_file_logic(
                client=mock_client,
                file_path=str(temp_source_file),
                edit_snippet=snippet,
                instruction=None,
                base_dir=str(tmp_path),
            )

    def test_no_changes_returns_message(
        self,
        mock_config: RelaceConfig,
        temp_source_file: Path,
        tmp_path: Path,
    ) -> None:
        """Should return 'No changes made' when diff is empty."""
        original = temp_source_file.read_text()
        mock_client = MagicMock(spec=RelaceClient)
        mock_client.apply.return_value = {"mergedCode": original, "usage": {}}

        log_file = tmp_path / "test.log"
        with patch("relace_mcp.tools.apply.LOG_PATH", log_file):
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
        temp_large_file: Path,
        tmp_path: Path,
    ) -> None:
        """Should raise on files exceeding size limit."""
        mock_client = MagicMock(spec=RelaceClient)

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
        tmp_path: Path,
        successful_api_response: dict[str, Any],
    ) -> None:
        """Should allow files exactly at size limit."""
        # Create file exactly at limit (10MB)
        limit_file = tmp_path / "limit.py"
        limit_file.write_text("x" * MAX_FILE_SIZE_BYTES)

        mock_client = MagicMock(spec=RelaceClient)
        mock_client.apply.return_value = successful_api_response

        # Should not raise
        log_file = tmp_path / "test.log"
        with patch("relace_mcp.tools.apply.LOG_PATH", log_file):
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
        temp_binary_file: Path,
        tmp_path: Path,
    ) -> None:
        """Should raise on non-UTF-8 encoded files."""
        mock_client = MagicMock(spec=RelaceClient)

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
        tmp_path: Path,
    ) -> None:
        """Should successfully read and write GBK encoded files."""
        mock_client = MagicMock(spec=RelaceClient)
        gbk_file = tmp_path / "gbk_file.py"
        # 寫入 GBK 編碼的中文內容
        gbk_content = "# 这是简体中文注释\nprint('你好')\n"
        gbk_file.write_bytes(gbk_content.encode("gbk"))

        merged_code = "# 这是简体中文注释\nprint('你好世界')\n"
        mock_client.apply.return_value = {"mergedCode": merged_code, "usage": {}}

        log_file = tmp_path / "test.log"
        with patch("relace_mcp.tools.apply.LOG_PATH", log_file):
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
        tmp_path: Path,
    ) -> None:
        """Should block access to files outside base_dir."""
        mock_client = MagicMock(spec=RelaceClient)

        # 嘗試存取 base_dir 外部的檔案
        outside_file = tmp_path.parent / "outside.py"
        outside_file.write_text("content")

        try:
            with pytest.raises(RuntimeError, match="outside allowed directory"):
                apply_file_logic(
                    client=mock_client,
                    file_path=str(outside_file),
                    edit_snippet="// edit",
                    instruction=None,
                    base_dir=str(tmp_path),
                )
        finally:
            outside_file.unlink(missing_ok=True)


class TestApplyFileLogicApiErrors:
    """Test API error handling."""

    def test_logs_error_on_api_failure(
        self,
        mock_config: RelaceConfig,
        temp_source_file: Path,
        tmp_path: Path,
    ) -> None:
        """Should log error event when API call fails."""
        mock_client = MagicMock(spec=RelaceClient)
        mock_client.apply.side_effect = RuntimeError("API Error")

        log_file = tmp_path / "test.log"
        with patch("relace_mcp.tools.apply.LOG_PATH", log_file):
            with pytest.raises(RuntimeError):
                apply_file_logic(
                    client=mock_client,
                    file_path=str(temp_source_file),
                    edit_snippet="// edit",
                    instruction=None,
                    base_dir=str(tmp_path),
                )

        logged = json.loads(log_file.read_text().strip())
        assert logged["kind"] == "apply_error"
        assert "API Error" in logged["error"]

    def test_missing_merged_code_raises(
        self,
        mock_config: RelaceConfig,
        temp_source_file: Path,
        tmp_path: Path,
    ) -> None:
        """Should raise when API returns no mergedCode."""
        mock_client = MagicMock(spec=RelaceClient)
        mock_client.apply.return_value = {"usage": {}}  # No mergedCode

        log_file = tmp_path / "test.log"
        with patch("relace_mcp.tools.apply.LOG_PATH", log_file):
            with pytest.raises(RuntimeError, match="did not return 'mergedCode'"):
                apply_file_logic(
                    client=mock_client,
                    file_path=str(temp_source_file),
                    edit_snippet="// edit",
                    instruction=None,
                    base_dir=str(tmp_path),
                )

    def test_null_merged_code_raises(
        self,
        mock_config: RelaceConfig,
        temp_source_file: Path,
        tmp_path: Path,
    ) -> None:
        """Should raise when API returns null mergedCode."""
        mock_client = MagicMock(spec=RelaceClient)
        mock_client.apply.return_value = {"mergedCode": None, "usage": {}}

        log_file = tmp_path / "test.log"
        with patch("relace_mcp.tools.apply.LOG_PATH", log_file):
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
        temp_source_file: Path,
        successful_api_response: dict[str, Any],
        tmp_path: Path,
    ) -> None:
        """Should truncate edit_snippet to 200 chars in log."""
        mock_client = MagicMock(spec=RelaceClient)
        mock_client.apply.return_value = successful_api_response

        long_snippet = "x" * 500

        log_file = tmp_path / "test.log"
        with patch("relace_mcp.tools.apply.LOG_PATH", log_file):
            apply_file_logic(
                client=mock_client,
                file_path=str(temp_source_file),
                edit_snippet=long_snippet,
                instruction=None,
                base_dir=str(tmp_path),
            )

        logged = json.loads(log_file.read_text().strip())
        assert len(logged["edit_snippet_preview"]) == 200
