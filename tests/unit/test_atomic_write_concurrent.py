import multiprocessing
import threading
from unittest.mock import patch

import pytest

from relace_mcp.encoding.codec import atomic_write


class TestAtomicWriteConcurrent:
    """Test atomic write behavior with concurrent operations."""

    def test_concurrent_writes_same_file(self, tmp_path):
        """Test multiple processes writing to same file.

        All writes should be atomic - the file should never be corrupted
        or partially written.
        """
        target_file = tmp_path / "concurrent.txt"

        def writer(content):
            atomic_write(target_file, content, "utf-8")

        # Start multiple processes concurrently
        processes = []
        contents = [f"content_{i}_{'x' * 100}" for i in range(5)]

        for content in contents:
            p = multiprocessing.Process(target=writer, args=(content,))
            processes.append(p)

        # Start all processes nearly simultaneously
        for p in processes:
            p.start()

        # Wait for all to complete
        for p in processes:
            p.join(timeout=10)
            assert not p.is_alive(), "Process should have completed"

        # Verify file exists and content is complete (not truncated)
        assert target_file.exists()
        final_content = target_file.read_text(encoding="utf-8")

        # Content should be one of the valid writes, not corrupted
        assert final_content in contents
        # Content should not be truncated
        assert len(final_content) >= 100

    def test_concurrent_writes_different_files(self, tmp_path):
        """Test multiple processes writing to different files."""
        target_files = [tmp_path / f"concurrent_{i}.txt" for i in range(5)]

        def writer(file_path, content):
            atomic_write(file_path, content, "utf-8")

        processes = []
        for i, file_path in enumerate(target_files):
            content = f"content_{i}_{'x' * 100}"
            p = multiprocessing.Process(target=writer, args=(file_path, content))
            processes.append(p)

        for p in processes:
            p.start()

        for p in processes:
            p.join(timeout=10)
            assert not p.is_alive()

        # All files should exist with correct content
        for i, file_path in enumerate(target_files):
            assert file_path.exists()
            content = file_path.read_text(encoding="utf-8")
            assert f"content_{i}" in content

    def test_temp_file_cleanup_on_success(self, tmp_path):
        """Test that temp files are cleaned up after successful write."""
        target_file = tmp_path / "test.txt"

        atomic_write(target_file, "content", "utf-8")

        # No .tmp files should remain
        tmp_files = list(tmp_path.glob("*.tmp"))
        assert len(tmp_files) == 0

    def test_temp_file_cleanup_on_interrupt(self, tmp_path):
        """Test temp file cleanup when write is interrupted."""
        target_file = tmp_path / "test.txt"

        # Simulate an error during write
        with patch("pathlib.Path.open") as mock_open:
            mock_open.side_effect = OSError("Disk full")

            with pytest.raises(IOError):
                atomic_write(target_file, "content", "utf-8")

        # Target file should not exist (write failed)
        assert not target_file.exists()

    def test_atomic_write_with_unicode(self, tmp_path):
        """Test atomic write with unicode content."""
        target_file = tmp_path / "unicode.txt"

        # Test various unicode characters
        contents = [
            "Hello 世界 🌍",
            "Café résumé naïve",
            "日本語テキスト",
            "Arabic: مرحبا",
        ]

        for content in contents:
            atomic_write(target_file, content, "utf-8")
            read_content = target_file.read_text(encoding="utf-8")
            assert read_content == content

    def test_atomic_write_preserves_newlines(self, tmp_path):
        """Test that atomic write preserves different newline styles."""
        target_file = tmp_path / "newlines.txt"

        # Test Unix newlines
        content_unix = "line1\nline2\nline3"
        atomic_write(target_file, content_unix, "utf-8")
        read_content = target_file.read_bytes()
        assert b"\n" in read_content


class TestAtomicWriteEdgeCases:
    """Test edge cases for atomic write."""

    def test_write_to_nonexistent_directory(self, tmp_path):
        """Test writing to a file in a non-existent directory."""
        target_file = tmp_path / "nonexistent" / "subdir" / "test.txt"

        with pytest.raises(OSError):
            atomic_write(target_file, "content", "utf-8")

    def test_write_empty_content(self, tmp_path):
        """Test writing empty content."""
        target_file = tmp_path / "empty.txt"

        atomic_write(target_file, "", "utf-8")

        assert target_file.exists()
        assert target_file.read_text(encoding="utf-8") == ""

    def test_overwrite_existing_file(self, tmp_path):
        """Test overwriting an existing file."""
        target_file = tmp_path / "existing.txt"
        target_file.write_text("old content")

        atomic_write(target_file, "new content", "utf-8")

        assert target_file.read_text(encoding="utf-8") == "new content"

    def test_write_large_file(self, tmp_path):
        """Test writing a large file atomically."""
        target_file = tmp_path / "large.txt"
        content = "x" * (1024 * 1024)  # 1MB

        atomic_write(target_file, content, "utf-8")

        assert target_file.exists()
        assert target_file.stat().st_size == len(content)
        assert target_file.read_text(encoding="utf-8") == content


class TestAtomicWriteThreadSafety:
    """Test thread safety of atomic write."""

    def test_thread_concurrent_writes(self, tmp_path):
        """Test atomic write from multiple threads."""
        target_file = tmp_path / "thread_test.txt"
        errors = []
        success_count = [0]

        def writer(thread_id):
            try:
                content = f"thread_{thread_id}_{'x' * 50}"
                atomic_write(target_file, content, "utf-8")
                success_count[0] += 1
            except Exception as e:
                errors.append((thread_id, str(e)))

        threads = [threading.Thread(target=writer, args=(i,)) for i in range(10)]

        for t in threads:
            t.start()

        for t in threads:
            t.join(timeout=10)

        assert len(errors) == 0, f"Errors occurred: {errors}"
        assert target_file.exists()
        # Content should be complete
        content = target_file.read_text(encoding="utf-8")
        assert len(content) >= 50
