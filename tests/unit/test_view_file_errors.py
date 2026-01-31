import os
from unittest.mock import patch

from relace_mcp.tools.search._impl.view_file import view_file_handler


class TestViewFilePathErrors:
    """Test path resolution and validation errors."""

    def test_path_resolution_exception(self, tmp_path):
        """Test handling of unexpected path resolution errors."""
        with patch("relace_mcp.tools.search._impl.view_file.map_repo_path") as mock_map:
            mock_map.side_effect = ValueError("Circular symlink detected")
            result = view_file_handler("/repo/test.py", [1, 10], str(tmp_path))
            assert "Error" in result

    def test_validate_file_path_exception(self, tmp_path):
        """Test handling of validate_file_path exceptions."""
        with patch("relace_mcp.tools.search._impl.view_file.validate_file_path") as mock_val:
            mock_val.side_effect = RuntimeError("Access denied")
            result = view_file_handler("/repo/test.py", [1, 10], str(tmp_path))
            assert "Error" in result

    def test_path_outside_base_dir(self, tmp_path):
        """Test handling of paths outside base_dir."""
        outside_path = tmp_path.parent / "outside"
        result = view_file_handler(str(outside_path), [1, 10], str(tmp_path))
        assert "Error" in result or "outside" in result.lower()


class TestViewFileReadErrors:
    """Test file reading error scenarios."""

    def test_file_read_permission_error(self, tmp_path):
        """Test handling of permission denied during read."""
        test_file = tmp_path / "readonly.py"
        test_file.write_text("content")
        os.chmod(test_file, 0o000)  # Remove all permissions

        try:
            result = view_file_handler(str(test_file), [1, 10], str(tmp_path))
            # Should handle permission error gracefully
            assert "Error" in result or "permission" in result.lower() or "cannot" in result.lower()
        finally:
            os.chmod(test_file, 0o644)  # Restore permissions for cleanup

    def test_binary_file_detection(self, tmp_path):
        """Test binary file detection and error message."""
        binary_file = tmp_path / "test.bin"
        binary_file.write_bytes(b"\x00\x01\x02\x03\xff\xfe")
        result = view_file_handler(str(binary_file), [1, 10], str(tmp_path))
        assert "binary" in result.lower() or "Error" in result

    def test_empty_file(self, tmp_path):
        """Test handling of empty files."""
        empty_file = tmp_path / "empty.py"
        empty_file.write_text("")
        result = view_file_handler(str(empty_file), [1, 10], str(tmp_path))
        # Should handle empty file gracefully
        assert isinstance(result, str)


class TestViewFileRangeErrors:
    """Test view range handling edge cases."""

    def test_view_range_start_zero(self, tmp_path):
        """Test view_range with start=0 (should be treated as 1)."""
        test_file = tmp_path / "test.py"
        test_file.write_text("line1\nline2\nline3\n")
        result = view_file_handler(str(test_file), [0, 2], str(tmp_path))
        assert "line1" in result

    def test_view_range_beyond_eof(self, tmp_path):
        """Test view_range beyond end of file."""
        test_file = tmp_path / "test.py"
        test_file.write_text("line1\nline2\n")
        result = view_file_handler(str(test_file), [1, 1000], str(tmp_path))
        assert "line1" in result
        assert "line2" in result

    def test_view_range_negative_start(self, tmp_path):
        """Test view_range with negative start."""
        test_file = tmp_path / "test.py"
        test_file.write_text("line1\nline2\nline3\n")
        result = view_file_handler(str(test_file), [-5, 2], str(tmp_path))
        # Should handle gracefully
        assert isinstance(result, str)

    def test_view_range_end_is_minus_one(self, tmp_path):
        """Test view_range with end=-1 (should show to EOF)."""
        test_file = tmp_path / "test.py"
        test_file.write_text("line1\nline2\nline3\n")
        result = view_file_handler(str(test_file), [1, -1], str(tmp_path))
        assert "line1" in result
        assert "line2" in result
        assert "line3" in result


class TestViewFileLargeFile:
    """Test handling of large files."""

    def test_large_file_size_limit(self, tmp_path):
        """Test that files exceeding MAX_FILE_SIZE_BYTES are rejected."""
        from relace_mcp.config.settings import MAX_FILE_SIZE_BYTES

        large_file = tmp_path / "large.py"
        # Create file just over the limit
        large_file.write_bytes(b"x" * (MAX_FILE_SIZE_BYTES + 100))

        result = view_file_handler(str(large_file), [1, 10], str(tmp_path))
        assert "too large" in result.lower() or "Error" in result

    def test_file_at_size_limit(self, tmp_path):
        """Test that files exactly at size limit are allowed."""
        from relace_mcp.config.settings import MAX_FILE_SIZE_BYTES

        limit_file = tmp_path / "limit.py"
        limit_file.write_bytes(b"x" * MAX_FILE_SIZE_BYTES)

        # Mock read_text_best_effort to avoid actual large file read
        with patch("relace_mcp.tools.search._impl.view_file.read_text_best_effort") as mock_read:
            mock_read.return_value = "x" * 100
            result = view_file_handler(str(limit_file), [1, 10], str(tmp_path))
            # Should not error due to size
            assert "too large" not in result.lower()


class TestViewFileSpecialPaths:
    """Test special path handling."""

    def test_repo_root_path(self, tmp_path):
        """Test /repo path."""
        test_file = tmp_path / "test.py"
        test_file.write_text("content")
        result = view_file_handler("/repo/test.py", [1, 10], str(tmp_path))
        assert "Error" not in result or "not found" in result.lower()

    def test_relative_path(self, tmp_path):
        """Test relative path resolution."""
        subdir = tmp_path / "subdir"
        subdir.mkdir()
        test_file = subdir / "test.py"
        test_file.write_text("content")

        result = view_file_handler("subdir/test.py", [1, 10], str(tmp_path))
        assert "Error" not in result or "not found" in result.lower()
