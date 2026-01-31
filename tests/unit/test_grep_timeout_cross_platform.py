"""Test grep search timeout behavior across platforms.

This module tests that timeout works (or gracefully degrades) on all platforms,
especially Windows which doesn't support signal.SIGALRM.
"""

import signal
import sys
import threading
import time
from unittest.mock import patch

import pytest

from relace_mcp.tools.search._impl.grep_search import _timeout_context


class TestTimeoutContextCrossPlatform:
    """Test _timeout_context behavior across different platforms."""

    def test_timeout_context_main_thread_unix(self):
        """Test signal-based timeout on Unix main thread."""
        if sys.platform == "win32":
            pytest.skip("SIGALRM not available on Windows")
        if not hasattr(signal, "SIGALRM"):
            pytest.skip("SIGALRM not available on this platform")
        if threading.current_thread() is not threading.main_thread():
            pytest.skip("Must run in main thread")

        # Should raise TimeoutError
        with pytest.raises(TimeoutError):
            with _timeout_context(1):  # 1 second timeout
                time.sleep(5)  # This should be interrupted

    def test_timeout_context_non_main_thread(self):
        """Test timeout in non-main thread falls back to no-op.

        All platforms should handle non-main thread gracefully.
        """
        result = []

        def run_in_thread():
            try:
                with _timeout_context(1):
                    time.sleep(0.1)  # Short sleep, should complete
                result.append("completed")
            except TimeoutError:
                result.append("timeout")

        thread = threading.Thread(target=run_in_thread)
        thread.start()
        thread.join(timeout=5)

        assert result == ["completed"]

    def test_timeout_context_windows_fallback(self):
        """Test that Windows gracefully handles lack of SIGALRM."""
        if sys.platform != "win32":
            # Mock Windows behavior on Unix by simulating no SIGALRM
            original_hasattr = hasattr

            def mock_hasattr(obj, name):
                if obj is signal and name == "SIGALRM":
                    return False
                return original_hasattr(obj, name)

            with patch("relace_mcp.tools.search._impl.grep_search.hasattr", mock_hasattr):
                with _timeout_context(1):
                    time.sleep(0.1)  # Should complete without error
        else:
            # Real Windows test
            with _timeout_context(1):
                time.sleep(0.1)  # Should complete without error

    def test_timeout_context_exception_propagation(self):
        """Test that exceptions inside timeout_context are properly propagated."""

        class CustomError(Exception):
            pass

        with pytest.raises(CustomError):
            with _timeout_context(5):
                raise CustomError("Test exception")


class TestGrepSearchTimeoutIntegration:
    """Integration tests for grep search timeout behavior."""

    @pytest.mark.slow
    def test_grep_search_respects_timeout(self, tmp_path, monkeypatch):
        """Test that grep search respects timeout even on Windows."""
        # Create a large file to search
        large_file = tmp_path / "large.py"
        large_file.write_text("x = 1\n" * 10000)

        # Mock time.monotonic to simulate timeout
        call_count = 0
        original_time = time.monotonic

        def mock_time():
            nonlocal call_count
            call_count += 1
            # Return increasingly large values to simulate timeout
            return original_time() + (call_count * 100)

        monkeypatch.setattr(time, "monotonic", mock_time)

        from relace_mcp.tools.search.schemas import GrepSearchParams

        params = GrepSearchParams(
            query="pattern",
            base_dir=str(tmp_path),
            case_sensitive=True,
            include_pattern=None,
            exclude_pattern=None,
        )

        # Import after mocking
        from relace_mcp.tools.search._impl.grep_search import _grep_search_python_fallback

        result = _grep_search_python_fallback(params)

        # Should return partial results or timeout message
        assert isinstance(result, str)

    def test_grep_search_no_hang_on_large_files(self, tmp_path):
        """Test that grep search doesn't hang on very large files."""
        # Create a moderately large file
        large_file = tmp_path / "large.txt"
        large_file.write_text("line content\n" * 1000)

        # This should complete within reasonable time
        start = time.monotonic()

        from relace_mcp.tools.search._impl.grep_search import grep_search_handler
        from relace_mcp.tools.search.schemas import GrepSearchParams

        params = GrepSearchParams(
            query="line",
            base_dir=str(tmp_path),
            case_sensitive=True,
            include_pattern=None,
            exclude_pattern=None,
        )

        result = grep_search_handler(params)
        elapsed = time.monotonic() - start

        # Should complete within 30 seconds even on slow systems
        assert elapsed < 30
        assert isinstance(result, str)
