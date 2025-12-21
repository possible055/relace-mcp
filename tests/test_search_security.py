from relace_mcp.tools.search.handlers import _is_blocked_command

DEFAULT_BASE_DIR = "/repo"


class TestIsBlockedCommand:
    """Test command blocking logic."""

    def test_blocks_rm(self) -> None:
        blocked, _ = _is_blocked_command("rm file.txt", DEFAULT_BASE_DIR)
        assert blocked

    def test_blocks_rm_rf(self) -> None:
        blocked, _ = _is_blocked_command("rm -rf /", DEFAULT_BASE_DIR)
        assert blocked

    def test_blocks_full_path_rm(self) -> None:
        blocked, _ = _is_blocked_command("/bin/rm file.txt", DEFAULT_BASE_DIR)
        assert blocked

    def test_allows_ls(self) -> None:
        blocked, _ = _is_blocked_command("ls -la", DEFAULT_BASE_DIR)
        assert not blocked

    def test_allows_cat(self) -> None:
        blocked, _ = _is_blocked_command("cat file.txt", DEFAULT_BASE_DIR)
        assert not blocked

    def test_allows_grep(self) -> None:
        blocked, _ = _is_blocked_command("grep pattern file.txt", DEFAULT_BASE_DIR)
        assert not blocked

    def test_allows_find(self) -> None:
        blocked, _ = _is_blocked_command("find . -name '*.py'", DEFAULT_BASE_DIR)
        assert not blocked

    def test_allows_git_log(self) -> None:
        blocked, _ = _is_blocked_command("git log -n 10", DEFAULT_BASE_DIR)
        assert not blocked

    def test_blocks_pipe(self) -> None:
        blocked, _ = _is_blocked_command("cat file | grep pattern", DEFAULT_BASE_DIR)
        assert blocked

    def test_blocks_redirect_to_file(self) -> None:
        blocked, _ = _is_blocked_command("echo test > output.txt", DEFAULT_BASE_DIR)
        assert blocked

    def test_blocks_append_redirect(self) -> None:
        blocked, _ = _is_blocked_command("echo test >> output.txt", DEFAULT_BASE_DIR)
        assert blocked

    def test_blocks_empty_command(self) -> None:
        blocked, _ = _is_blocked_command("", DEFAULT_BASE_DIR)
        assert blocked

    def test_blocks_semicolon_rm(self) -> None:
        blocked, _ = _is_blocked_command("ls; rm file.txt", DEFAULT_BASE_DIR)
        assert blocked

    def test_blocks_and_rm(self) -> None:
        blocked, _ = _is_blocked_command("ls && rm file.txt", DEFAULT_BASE_DIR)
        assert blocked


class TestAbsolutePathBlocking:
    """Test absolute path sandbox enforcement."""

    def test_blocks_cat_etc_passwd(self) -> None:
        """Should block reading /etc/passwd."""
        blocked, reason = _is_blocked_command("cat /etc/passwd", DEFAULT_BASE_DIR)
        assert blocked
        assert "/etc/passwd" in reason or "Absolute path" in reason

    def test_blocks_cat_etc_shadow(self) -> None:
        """Should block reading /etc/shadow."""
        blocked, reason = _is_blocked_command("cat /etc/shadow", DEFAULT_BASE_DIR)
        assert blocked

    def test_blocks_find_root(self) -> None:
        """Should block find starting from root."""
        blocked, reason = _is_blocked_command("find / -name '*.py'", DEFAULT_BASE_DIR)
        assert blocked

    def test_blocks_ls_home(self) -> None:
        """Should block listing home directory."""
        blocked, reason = _is_blocked_command("ls /home", DEFAULT_BASE_DIR)
        assert blocked

    def test_blocks_head_var_log(self) -> None:
        """Should block reading system logs."""
        blocked, reason = _is_blocked_command("head /var/log/syslog", DEFAULT_BASE_DIR)
        assert blocked

    def test_allows_repo_path(self) -> None:
        """Should allow /repo paths."""
        blocked, _ = _is_blocked_command("cat /repo/file.txt", DEFAULT_BASE_DIR)
        assert not blocked

    def test_allows_repo_subpath(self) -> None:
        """Should allow /repo/subdir paths."""
        blocked, _ = _is_blocked_command("ls /repo/src/", DEFAULT_BASE_DIR)
        assert not blocked

    def test_allows_relative_path(self) -> None:
        """Should allow relative paths."""
        blocked, _ = _is_blocked_command("cat ./file.txt", DEFAULT_BASE_DIR)
        assert not blocked


class TestRelativeTraversalBlocking:
    """Test blocking traversal via relative paths."""

    def test_blocks_ls_parent_dir(self) -> None:
        """Should block listing parent directory."""
        blocked, _ = _is_blocked_command("ls ..", DEFAULT_BASE_DIR)
        assert blocked

    def test_blocks_find_parent_dir(self) -> None:
        """Should block find starting from parent directory."""
        blocked, _ = _is_blocked_command("find .. -name '*.py'", DEFAULT_BASE_DIR)
        assert blocked

    def test_blocks_dotdot_path_token(self) -> None:
        """Should block path tokens that end with /.."""
        blocked, _ = _is_blocked_command("ls ./..", DEFAULT_BASE_DIR)
        assert blocked


class TestWriteOperationBlocking:
    """Test blocking of write/modify operations."""

    def test_blocks_touch(self) -> None:
        """Should block touch command."""
        blocked, _ = _is_blocked_command("touch newfile.txt", DEFAULT_BASE_DIR)
        assert blocked

    def test_blocks_tee(self) -> None:
        """Should block tee command."""
        blocked, _ = _is_blocked_command("tee output.txt", DEFAULT_BASE_DIR)
        assert blocked

    def test_blocks_sed_inplace(self) -> None:
        """Should block sed -i (in-place edit)."""
        blocked, _ = _is_blocked_command("sed -i 's/old/new/g' file.txt", DEFAULT_BASE_DIR)
        assert blocked

    def test_allows_sed_script_containing_dash_i(self) -> None:
        """Should not false-positive on '-i' inside sed script text."""
        blocked, _ = _is_blocked_command("sed 's/this-is-fine/ok/g' file.txt", DEFAULT_BASE_DIR)
        assert not blocked

    def test_blocks_sed_inplace_combined_short_options(self) -> None:
        """Should block -i even when combined with other short options."""
        blocked, _ = _is_blocked_command("sed -nri 's/old/new/g' file.txt", DEFAULT_BASE_DIR)
        assert blocked

    def test_blocks_mkdir(self) -> None:
        """Should block mkdir command."""
        blocked, _ = _is_blocked_command("mkdir newdir", DEFAULT_BASE_DIR)
        assert blocked

    def test_blocks_ln(self) -> None:
        """Should block ln (symlink creation)."""
        blocked, _ = _is_blocked_command("ln -s target link", DEFAULT_BASE_DIR)
        assert blocked

    def test_blocks_find_exec(self) -> None:
        """Should block find -exec."""
        blocked, _ = _is_blocked_command("find . -name '*.py' -exec rm {} \\;", DEFAULT_BASE_DIR)
        assert blocked

    def test_blocks_find_delete(self) -> None:
        """Should block find -delete."""
        blocked, _ = _is_blocked_command("find . -name '*.pyc' -delete", DEFAULT_BASE_DIR)
        assert blocked

    def test_blocks_xargs_rm(self) -> None:
        """Should block xargs with rm."""
        blocked, _ = _is_blocked_command("find . -name '*.tmp' | xargs rm", DEFAULT_BASE_DIR)
        assert blocked


class TestGitSecurityBlocking:
    """Test git subcommand security."""

    def test_allows_git_log(self) -> None:
        """Should allow git log."""
        blocked, _ = _is_blocked_command("git log -n 10", DEFAULT_BASE_DIR)
        assert not blocked

    def test_allows_git_show(self) -> None:
        """Should allow git show."""
        blocked, _ = _is_blocked_command("git show HEAD", DEFAULT_BASE_DIR)
        assert not blocked

    def test_allows_git_diff(self) -> None:
        """Should allow git diff."""
        blocked, _ = _is_blocked_command("git diff HEAD~1", DEFAULT_BASE_DIR)
        assert not blocked

    def test_allows_git_status(self) -> None:
        """Should allow git status."""
        blocked, _ = _is_blocked_command("git status", DEFAULT_BASE_DIR)
        assert not blocked

    def test_allows_git_blame(self) -> None:
        """Should allow git blame."""
        blocked, _ = _is_blocked_command("git blame file.py", DEFAULT_BASE_DIR)
        assert not blocked

    def test_blocks_git_clone(self) -> None:
        """Should block git clone (network operation)."""
        blocked, _ = _is_blocked_command("git clone https://github.com/user/repo", DEFAULT_BASE_DIR)
        assert blocked

    def test_blocks_git_fetch(self) -> None:
        """Should block git fetch (network operation)."""
        blocked, _ = _is_blocked_command("git fetch origin", DEFAULT_BASE_DIR)
        assert blocked

    def test_blocks_git_pull(self) -> None:
        """Should block git pull (network operation)."""
        blocked, _ = _is_blocked_command("git pull origin main", DEFAULT_BASE_DIR)
        assert blocked

    def test_blocks_git_push(self) -> None:
        """Should block git push (network operation)."""
        blocked, _ = _is_blocked_command("git push origin main", DEFAULT_BASE_DIR)
        assert blocked

    def test_blocks_git_checkout(self) -> None:
        """Should block git checkout (modifies working tree)."""
        blocked, _ = _is_blocked_command("git checkout -- .", DEFAULT_BASE_DIR)
        assert blocked

    def test_blocks_git_reset(self) -> None:
        """Should block git reset (modifies repo state)."""
        blocked, _ = _is_blocked_command("git reset --hard HEAD", DEFAULT_BASE_DIR)
        assert blocked

    def test_blocks_git_clean(self) -> None:
        """Should block git clean (deletes files)."""
        blocked, _ = _is_blocked_command("git clean -fd", DEFAULT_BASE_DIR)
        assert blocked

    def test_blocks_git_commit(self) -> None:
        """Should block git commit (modifies repo)."""
        blocked, _ = _is_blocked_command("git commit -m 'msg'", DEFAULT_BASE_DIR)
        assert blocked


class TestPythonSecurityBlocking:
    """Test Python command security."""

    def test_blocks_python_file_write(self) -> None:
        """Should block Python file write operations."""
        blocked, _ = _is_blocked_command("python -c \"open('f','w').write('x')\"", DEFAULT_BASE_DIR)
        assert blocked

    def test_blocks_pathlib(self) -> None:
        """Should block Python pathlib usage."""
        blocked, _ = _is_blocked_command(
            "python3 -c \"import pathlib; print(pathlib.Path('x').read_text())\"",
            DEFAULT_BASE_DIR,
        )
        assert blocked

    def test_blocks_http_client(self) -> None:
        """Should block Python http.client usage."""
        blocked, _ = _is_blocked_command('python3 -c "import http.client"', DEFAULT_BASE_DIR)
        assert blocked

    def test_blocks_python_requests(self) -> None:
        """Should block Python requests (network)."""
        blocked, _ = _is_blocked_command(
            "python -c \"import requests; requests.get('http://x')\"",
            DEFAULT_BASE_DIR,
        )
        assert blocked

    def test_blocks_python_urllib(self) -> None:
        """Should block Python urllib (network)."""
        blocked, _ = _is_blocked_command('python -c "import urllib.request"', DEFAULT_BASE_DIR)
        assert blocked

    def test_blocks_python_subprocess(self) -> None:
        """Should block Python subprocess."""
        blocked, _ = _is_blocked_command('python -c "import subprocess"', DEFAULT_BASE_DIR)
        assert blocked

    def test_blocks_python_os_system(self) -> None:
        """Should block Python os.system."""
        blocked, _ = _is_blocked_command(
            "python -c \"import os; os.system('rm -rf /')\"",
            DEFAULT_BASE_DIR,
        )
        assert blocked

    def test_blocks_python_script_execution(self) -> None:
        """Should block Python script file execution."""
        blocked, _ = _is_blocked_command("python script.py", DEFAULT_BASE_DIR)
        assert blocked

    def test_blocks_python3_script_execution(self) -> None:
        """Should block Python3 script file execution."""
        blocked, _ = _is_blocked_command("python3 script.py", DEFAULT_BASE_DIR)
        assert blocked


class TestPipeAllowedInQuotes:
    """Test that pipe is blocked everywhere for maximum safety (KISS)."""

    def test_blocks_grep_e_with_pipe_pattern(self) -> None:
        """Should block grep -E 'foo|bar' pattern due to strict pipe blocking."""
        blocked, _ = _is_blocked_command("grep -E 'foo|bar' file.txt", DEFAULT_BASE_DIR)
        assert blocked

    def test_blocks_egrep_with_pipe_pattern(self) -> None:
        """Should block egrep 'foo|bar' pattern."""
        blocked, _ = _is_blocked_command("egrep 'foo|bar' file.txt", DEFAULT_BASE_DIR)
        assert blocked

    def test_blocks_actual_pipe_operator(self) -> None:
        """Should still block actual pipe operator with spaces."""
        blocked, _ = _is_blocked_command("cat file | grep pattern", DEFAULT_BASE_DIR)
        assert blocked


class TestCommandNotInAllowlist:
    """Test that unknown commands are blocked."""

    def test_blocks_unknown_command(self) -> None:
        """Should block commands not in allowlist."""
        blocked, reason = _is_blocked_command("someunknowncommand arg", DEFAULT_BASE_DIR)
        assert blocked
        assert "allowlist" in reason.lower()

    def test_blocks_make(self) -> None:
        """Should block make (build tool)."""
        blocked, _ = _is_blocked_command("make all", DEFAULT_BASE_DIR)
        assert blocked

    def test_blocks_npm(self) -> None:
        """Should block npm."""
        blocked, _ = _is_blocked_command("npm install", DEFAULT_BASE_DIR)
        assert blocked

    def test_blocks_pip(self) -> None:
        """Should block pip."""
        blocked, _ = _is_blocked_command("pip install requests", DEFAULT_BASE_DIR)
        assert blocked
