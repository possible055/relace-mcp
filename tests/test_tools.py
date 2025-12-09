import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from relace_mcp.config import RelaceConfig
from relace_mcp.relace_client import RelaceClient
from relace_mcp.tools import (
    MAX_FILE_SIZE_BYTES,
    _apply_file_logic,
    _log_event,
    _validate_file_path,
)


class TestValidateFilePath:
    """Test _validate_file_path security function."""

    def test_valid_absolute_path(self, tmp_path: Path) -> None:
        """Should accept valid absolute paths within base_dir."""
        test_file = tmp_path / "test.py"
        test_file.write_text("content")

        result = _validate_file_path(str(test_file), base_dir=str(tmp_path))
        assert result == test_file.resolve()

    def test_empty_path_raises(self, tmp_path: Path) -> None:
        """Should reject empty paths."""
        with pytest.raises(RuntimeError, match="cannot be empty"):
            _validate_file_path("", base_dir=str(tmp_path))

    def test_whitespace_only_path_raises(self, tmp_path: Path) -> None:
        """Should reject whitespace-only paths."""
        with pytest.raises(RuntimeError, match="cannot be empty"):
            _validate_file_path("   ", base_dir=str(tmp_path))

    def test_path_within_base_dir(self, tmp_path: Path) -> None:
        """Should accept paths within base_dir."""
        test_file = tmp_path / "subdir" / "test.py"
        test_file.parent.mkdir(parents=True, exist_ok=True)
        test_file.write_text("content")

        result = _validate_file_path(str(test_file), base_dir=str(tmp_path))
        assert result == test_file.resolve()

    def test_path_outside_base_dir_raises(self, tmp_path: Path) -> None:
        """Should reject paths outside base_dir (path traversal protection)."""
        outside_path = tmp_path.parent / "outside.py"

        with pytest.raises(RuntimeError, match="outside allowed directory"):
            _validate_file_path(str(outside_path), base_dir=str(tmp_path))

    def test_path_traversal_attempt_blocked(self, tmp_path: Path) -> None:
        """Should block path traversal attempts."""
        traversal_path = str(tmp_path / ".." / ".." / "etc" / "passwd")

        with pytest.raises(RuntimeError, match="outside allowed directory"):
            _validate_file_path(traversal_path, base_dir=str(tmp_path))


class TestLogEvent:
    """Test log_interaction function."""

    def test_writes_json_line(self, tmp_path: Path) -> None:
        """Should write JSON event to log file."""
        log_file = tmp_path / "test.log"
        with patch("relace_mcp.tools.LOG_PATH", log_file):
            _log_event({"kind": "test", "message": "hello"})
        content = log_file.read_text()
        logged = json.loads(content.strip())
        assert logged["kind"] == "test"
        assert logged["message"] == "hello"
        assert "timestamp" in logged

    def test_appends_to_existing_log(self, tmp_path: Path) -> None:
        """Should append to existing log file."""
        log_file = tmp_path / "test.log"
        with patch("relace_mcp.tools.LOG_PATH", log_file):
            _log_event({"event": 1})
            _log_event({"event": 2})

        lines = log_file.read_text().strip().split("\n")
        assert len(lines) == 2

    def test_creates_parent_directories(self, tmp_path: Path) -> None:
        """Should create parent directories if needed."""
        log_path = tmp_path / "deep" / "nested" / "dir" / "log.json"
        with patch("relace_mcp.tools.LOG_PATH", log_path):
            _log_event({"test": True})
        assert log_path.exists()

    def test_preserves_existing_timestamp(self, tmp_path: Path) -> None:
        """Should not overwrite existing timestamp."""
        log_file = tmp_path / "test.log"
        with patch("relace_mcp.tools.LOG_PATH", log_file):
            _log_event({"kind": "test", "timestamp": "2024-01-01T00:00:00Z"})
        logged = json.loads(log_file.read_text().strip())
        assert logged["timestamp"] == "2024-01-01T00:00:00Z"

    def test_handles_log_failure_gracefully(self, tmp_path: Path) -> None:
        """Should not raise on log write failure."""
        # 使用目錄作為 log 路徑會失敗，但不應拋出例外
        log_file = tmp_path / "test.log"
        with patch("relace_mcp.tools.LOG_PATH", log_file):
            _log_event({"test": True})
        # 不應拋出例外


class TestApplyFileLogicSuccess:
    """Test apply_file_logic successful scenarios."""

    def test_successful_apply(
        self,
        mock_config: RelaceConfig,
        temp_source_file: Path,
        successful_api_response: dict[str, Any],
        tmp_path: Path,
    ) -> None:
        """Should successfully apply edit and write result."""
        mock_client = MagicMock(spec=RelaceClient)
        mock_client.apply.return_value = successful_api_response

        log_file = tmp_path / "test.log"
        with patch("relace_mcp.tools.LOG_PATH", log_file):
            result = _apply_file_logic(
                client=mock_client,
                file_path=str(temp_source_file),
                edit_snippet="// new code",
                instruction="Add feature",
                base_dir=str(tmp_path),
            )

        assert "merged_code_preview" in result
        assert result["file_path"] == str(temp_source_file.resolve())
        assert result["instruction"] == "Add feature"
        assert "usage" in result

        # 驗證檔案已被寫入
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
        with patch("relace_mcp.tools.LOG_PATH", log_file):
            _apply_file_logic(
                client=mock_client,
                file_path=str(temp_source_file),
                edit_snippet="// edit",
                instruction=None,
                base_dir=str(tmp_path),
            )

        logged = json.loads(log_file.read_text().strip())
        assert logged["kind"] == "apply_success"

    def test_truncates_preview(
        self,
        mock_config: RelaceConfig,
        temp_source_file: Path,
        tmp_path: Path,
    ) -> None:
        """Should truncate merged_code_preview to 4000 chars."""
        long_code = "x" * 5000
        mock_client = MagicMock(spec=RelaceClient)
        mock_client.apply.return_value = {"mergedCode": long_code, "usage": {}}

        log_file = tmp_path / "test.log"
        with patch("relace_mcp.tools.LOG_PATH", log_file):
            result = _apply_file_logic(
                client=mock_client,
                file_path=str(temp_source_file),
                edit_snippet="// edit",
                instruction=None,
                base_dir=str(tmp_path),
            )

        assert len(result["merged_code_preview"]) == 4000

    def test_dry_run_does_not_write(
        self,
        mock_config: RelaceConfig,
        temp_source_file: Path,
        successful_api_response: dict[str, Any],
        tmp_path: Path,
    ) -> None:
        """Should not write file when dry_run is True."""
        original_content = temp_source_file.read_text()
        mock_client = MagicMock(spec=RelaceClient)
        mock_client.apply.return_value = successful_api_response

        log_file = tmp_path / "test.log"
        with patch("relace_mcp.tools.LOG_PATH", log_file):
            result = _apply_file_logic(
                client=mock_client,
                file_path=str(temp_source_file),
                edit_snippet="// new code",
                instruction="Add feature",
                base_dir=str(tmp_path),
                dry_run=True,
            )

        assert result["dry_run"] is True
        # 檔案內容不變
        assert temp_source_file.read_text() == original_content


class TestApplyFileLogicValidation:
    """Test apply_file_logic input validation."""

    def test_empty_edit_snippet_raises(
        self,
        mock_config: RelaceConfig,
        temp_source_file: Path,
        tmp_path: Path,
    ) -> None:
        """Should raise on empty edit_snippet."""
        mock_client = MagicMock(spec=RelaceClient)

        with pytest.raises(RuntimeError, match="edit_snippet cannot be empty"):
            _apply_file_logic(
                client=mock_client,
                file_path=str(temp_source_file),
                edit_snippet="",
                instruction=None,
                base_dir=str(tmp_path),
            )

    def test_whitespace_edit_snippet_raises(
        self,
        mock_config: RelaceConfig,
        temp_source_file: Path,
        tmp_path: Path,
    ) -> None:
        """Should raise on whitespace-only edit_snippet."""
        mock_client = MagicMock(spec=RelaceClient)

        with pytest.raises(RuntimeError, match="edit_snippet cannot be empty"):
            _apply_file_logic(
                client=mock_client,
                file_path=str(temp_source_file),
                edit_snippet="   \n\t  ",
                instruction=None,
                base_dir=str(tmp_path),
            )

    def test_nonexistent_file_raises(
        self,
        mock_config: RelaceConfig,
        tmp_path: Path,
    ) -> None:
        """Should raise on non-existent file."""
        mock_client = MagicMock(spec=RelaceClient)

        with pytest.raises(RuntimeError, match="File not found"):
            _apply_file_logic(
                client=mock_client,
                file_path=str(tmp_path / "does_not_exist.py"),
                edit_snippet="// edit",
                instruction=None,
                base_dir=str(tmp_path),
            )


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
            _apply_file_logic(
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
        with patch("relace_mcp.tools.LOG_PATH", log_file):
            result = _apply_file_logic(
                client=mock_client,
                file_path=str(limit_file),
                edit_snippet="// edit",
                instruction=None,
                base_dir=str(tmp_path),
            )
        assert "merged_code_preview" in result


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

        with pytest.raises(RuntimeError, match="not valid UTF-8"):
            _apply_file_logic(
                client=mock_client,
                file_path=str(temp_binary_file),
                edit_snippet="// edit",
                instruction=None,
                base_dir=str(tmp_path),
            )


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
                _apply_file_logic(
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
        with patch("relace_mcp.tools.LOG_PATH", log_file):
            with pytest.raises(RuntimeError):
                _apply_file_logic(
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
        with patch("relace_mcp.tools.LOG_PATH", log_file):
            with pytest.raises(RuntimeError, match="did not return 'mergedCode'"):
                _apply_file_logic(
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
        with patch("relace_mcp.tools.LOG_PATH", log_file):
            with pytest.raises(RuntimeError, match="did not return 'mergedCode'"):
                _apply_file_logic(
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
        with patch("relace_mcp.tools.LOG_PATH", log_file):
            _apply_file_logic(
                client=mock_client,
                file_path=str(temp_source_file),
                edit_snippet=long_snippet,
                instruction=None,
                base_dir=str(tmp_path),
            )

        logged = json.loads(log_file.read_text().strip())
        assert len(logged["edit_snippet_preview"]) == 200
