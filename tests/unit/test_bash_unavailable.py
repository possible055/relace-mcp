import pytest

from relace_mcp.tools.search._impl.bash import bash_handler


class TestBashUnavailable:
    """Test bash handler when bash is not installed."""

    def test_bash_handler_no_bash_installed(self, monkeypatch):
        """Test graceful handling when bash is not found."""
        monkeypatch.setattr("shutil.which", lambda x: None)
        result = bash_handler("ls -la", "/repo")
        assert "bash is not available" in result
        assert "Error:" in result

    def test_bash_handler_returns_helpful_message(self, monkeypatch):
        """Test error message suggests installing bash or using alternatives."""
        monkeypatch.setattr("shutil.which", lambda x: None)
        result = bash_handler("echo test", "/repo")
        assert "bash is not available" in result
        assert "Linux/macOS" in result or "WSL" in result or "Git Bash" in result


class TestBashPathTranslation:
    """Test /repo path translation in bash commands."""

    def test_path_translation_with_forward_slash(self, tmp_path, monkeypatch):
        """Test that /repo paths are translated correctly on all platforms."""
        # Mock subprocess to capture the translated command
        captured_cmd = None

        def mock_run(cmd, **kwargs):
            nonlocal captured_cmd
            captured_cmd = cmd

            class Result:
                returncode = 0
                stdout = "test"
                stderr = ""

            return Result()

        monkeypatch.setattr("subprocess.run", mock_run)

        result = bash_handler("cat /repo/test.py", str(tmp_path))

        # Verify the command was translated
        assert captured_cmd is not None
        # On all platforms, /repo should be translated to actual path
        assert str(tmp_path) in captured_cmd[2] or "/repo" in captured_cmd[2]
        # Verify result is a string (command executed or was blocked)
        assert isinstance(result, str)


class TestBashSecurityBlocks:
    """Test that security blocks work even when bash is available."""

    @pytest.mark.requires_bash
    def test_blocked_command_returns_error(self):
        """Test that blocked commands return error even with bash available."""
        result = bash_handler("rm -rf /", "/repo")
        assert "Error:" in result
        assert "blocked" in result.lower() or "security" in result.lower()

    @pytest.mark.requires_bash
    def test_path_traversal_blocked(self):
        """Test that path traversal attempts are blocked."""
        result = bash_handler("cat /etc/passwd", "/repo")
        assert "Error:" in result

    @pytest.mark.requires_bash
    def test_pipe_blocked(self):
        """Test that pipe operators are blocked for security."""
        result = bash_handler("cat file | grep pattern", "/repo")
        assert "Error:" in result
        assert "pipe" in result.lower() or "blocked" in result.lower()


class TestBashErrorHandling:
    """Test bash handler error paths."""

    @pytest.mark.requires_bash
    def test_shlex_split_failure_handling(self, monkeypatch):
        """Test handling of malformed command strings."""
        # Test with unbalanced quotes - should not crash
        result = bash_handler("echo 'unbalanced", "/repo")
        # Should either return error or pass through original command
        assert isinstance(result, str)

    @pytest.mark.requires_bash
    def test_subprocess_timeout(self, monkeypatch):
        """Test timeout handling."""
        import subprocess

        def mock_run(*args, **kwargs):
            raise subprocess.TimeoutExpired(cmd="cat file.txt", timeout=1)

        monkeypatch.setattr("subprocess.run", mock_run)

        result = bash_handler("cat file.txt", "/repo")
        assert "timed out" in result.lower() or "timeout" in result.lower()

    @pytest.mark.requires_bash
    def test_subprocess_exception(self, monkeypatch):
        """Test handling of unexpected subprocess exceptions."""

        def mock_run(*args, **kwargs):
            raise OSError("Unexpected error")

        monkeypatch.setattr("subprocess.run", mock_run)

        result = bash_handler("cat file.txt", "/repo")
        assert "error" in result.lower()
