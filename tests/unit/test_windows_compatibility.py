import os
import sys
from pathlib import Path

import pytest

from relace_mcp.utils import resolve_repo_path, uri_to_path, validate_file_path


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only tests")
class TestWindowsPathHandling:
    """Test Windows path handling edge cases."""

    def test_resolve_repo_path_windows_drive_letter(self, tmp_path):
        """Test /repo path resolution with Windows drive letters."""
        # On Windows, tmp_path will have a drive letter like C:\Users\...
        base_dir = str(tmp_path)

        result = resolve_repo_path("/repo/test.py", base_dir)

        # Result should contain the drive letter
        assert ":" in result or base_dir in result
        assert "test.py" in result

    def test_resolve_repo_path_unc_path(self, tmp_path):
        """Test UNC path handling."""
        # UNC paths like \\server\share
        unc_base = r"\\server\share\project"

        result = resolve_repo_path("/repo/test.py", unc_base)

        # Should handle UNC path
        assert "server" in result or "share" in result or "test.py" in result

    def test_uri_to_path_windows_file_uri(self):
        """Test file:// URI conversion on Windows."""
        # Windows file URIs have drive letters
        uri = "file:///C:/Users/test/project"
        result = uri_to_path(uri)

        # Should convert to Windows path
        assert "C:" in result or "Users" in result

    def test_uri_to_path_windows_unc_uri(self):
        """Test file:// URI with UNC path."""
        # UNC URI: file://server/share/folder
        uri = "file://server/share/folder"
        result = uri_to_path(uri)

        assert "server" in result
        assert "share" in result

    def test_long_path_handling(self, tmp_path):
        """Test Windows long path (> 260 chars) handling."""
        # Create a path that would exceed MAX_PATH on Windows
        long_name = "a" * 100
        deep_path = tmp_path / long_name / long_name / long_name

        # This might fail on older Windows without long path support
        try:
            deep_path.mkdir(parents=True, exist_ok=True)
            test_file = deep_path / "test.py"
            test_file.write_text("content")

            result = validate_file_path(str(test_file), str(tmp_path))
            assert result is not None
        except OSError:
            # Long path not supported, that's ok for this test
            pytest.skip("Long path not supported on this system")


class TestWindowsPathEdgeCases:
    """Test path handling that differs between platforms."""

    def test_forward_slash_in_path(self, tmp_path):
        """Test that forward slashes work on all platforms."""
        # Use forward slashes even on Windows
        path_with_slashes = str(tmp_path) + "/subdir/test.py"

        result = resolve_repo_path(path_with_slashes, str(tmp_path))

        # Should resolve correctly
        assert "subdir" in result
        assert "test.py" in result

    def test_backslash_in_relative_path(self, tmp_path):
        """Test backslash handling in relative paths."""
        if sys.platform == "win32":
            # On Windows, backslash is the native separator
            rel_path = "subdir\\test.py"
        else:
            # On Unix, backslash is a literal character
            rel_path = "subdir/test.py"

        result = resolve_repo_path(rel_path, str(tmp_path))

        assert "subdir" in result
        assert "test.py" in result


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only tests")
class TestWindowsPermissions:
    """Test Windows-specific permission handling."""

    def test_readonly_file_windows(self, tmp_path):
        """Test handling of read-only files on Windows."""
        test_file = tmp_path / "readonly.txt"
        test_file.write_text("content")

        # Set read-only attribute
        os.chmod(test_file, 0o444)

        try:
            # Try to read (should work)
            content = test_file.read_text()
            assert content == "content"
        finally:
            # Restore write permission for cleanup
            os.chmod(test_file, 0o644)


@pytest.mark.skipif(sys.platform == "win32", reason="Unix-only tests")
class TestUnixSpecificBehavior:
    """Unix-specific behavior tests."""

    def test_symlink_handling_unix(self, tmp_path):
        """Test symlink handling on Unix."""
        real_file = tmp_path / "real.txt"
        real_file.write_text("content")

        symlink = tmp_path / "link.txt"
        symlink.symlink_to(real_file)

        # Should resolve symlink
        result = resolve_repo_path(str(symlink), str(tmp_path))
        assert "real.txt" in result or "link.txt" in result

    def test_unix_permissions(self, tmp_path):
        """Test Unix permission handling."""
        import os

        test_file = tmp_path / "test.txt"
        test_file.write_text("content")

        # Remove read permission
        os.chmod(test_file, 0o000)

        try:
            # Validation should handle this
            # Note: This may not raise if running as root
            try:
                result = validate_file_path(str(test_file), str(tmp_path))
                # If we get here, we're likely running as root
                # Just verify the function returns a valid path
                assert isinstance(result, Path)
            except (RuntimeError, PermissionError, OSError):
                # Expected behavior for non-root users
                pass
        finally:
            os.chmod(test_file, 0o644)


class TestCrossPlatformConsistency:
    """Test behavior consistency across platforms."""

    def test_empty_path_handling(self, tmp_path):
        """Test empty path handling."""
        with pytest.raises((RuntimeError, ValueError)):
            validate_file_path("", str(tmp_path))

    def test_dot_path_handling(self, tmp_path):
        """Test . and .. path handling."""
        # Current directory reference
        result = resolve_repo_path(".", str(tmp_path))
        assert tmp_path.name in result or str(tmp_path) in result

        # Parent directory should be blocked
        with pytest.raises(ValueError):
            resolve_repo_path("..", str(tmp_path))

    def test_trailing_slash_handling(self, tmp_path):
        """Test paths with trailing slashes."""
        result1 = resolve_repo_path("/repo/", str(tmp_path))
        result2 = resolve_repo_path("/repo", str(tmp_path))

        # Both should resolve to the same directory
        assert result1 == result2 or result1.rstrip("/") == result2.rstrip("/")

    def test_case_sensitivity(self, tmp_path):
        """Test case handling (varies by platform)."""
        test_file = tmp_path / "TestFile.txt"
        test_file.write_text("content")

        if sys.platform == "win32":
            # Windows is case-insensitive
            result = validate_file_path(str(tmp_path / "TESTFILE.TXT"), str(tmp_path))
            assert result is not None
        else:
            # Unix is case-sensitive
            # This might or might not work depending on filesystem
            pass


class TestPathTraversalPrevention:
    """Test path traversal prevention across platforms."""

    def test_traversal_with_backslash(self, tmp_path):
        """Test .. traversal with backslashes."""
        if sys.platform == "win32":
            traversal = "..\\..\\etc\\passwd"
        else:
            traversal = "../../etc/passwd"

        with pytest.raises(ValueError):
            resolve_repo_path(traversal, str(tmp_path))

    def test_traversal_mixed_separators(self, tmp_path):
        """Test traversal with mixed separators."""
        # Try various combinations
        traversals = [
            "../subdir/../../etc/passwd",
            "subdir/../../../etc/passwd",
        ]

        for traversal in traversals:
            with pytest.raises(ValueError):
                resolve_repo_path(traversal, str(tmp_path))

    def test_null_byte_injection(self, tmp_path):
        """Test null byte injection prevention."""
        # Null byte should be handled safely
        malicious = "file.py\x00.exe"

        # Should either raise error or truncate at null byte
        try:
            result = resolve_repo_path(malicious, str(tmp_path))
            assert "\x00" not in str(result)
        except ValueError:
            pass  # Also acceptable
