from relace_mcp.tools.search._impl import is_blocked_command as _is_blocked_command

DEFAULT_BASE_DIR = "/repo"


class TestBlocksDestructiveCommands:
    def test_blocks_rm(self) -> None:
        blocked, _ = _is_blocked_command("rm file.txt", DEFAULT_BASE_DIR)
        assert blocked

    def test_blocks_rm_rf(self) -> None:
        blocked, _ = _is_blocked_command("rm -rf /", DEFAULT_BASE_DIR)
        assert blocked

    def test_blocks_full_path_rm(self) -> None:
        blocked, _ = _is_blocked_command("/bin/rm file.txt", DEFAULT_BASE_DIR)
        assert blocked

    def test_blocks_mv(self) -> None:
        blocked, _ = _is_blocked_command("mv a.txt b.txt", DEFAULT_BASE_DIR)
        assert blocked

    def test_blocks_cp(self) -> None:
        blocked, _ = _is_blocked_command("cp a.txt b.txt", DEFAULT_BASE_DIR)
        assert blocked

    def test_blocks_touch(self) -> None:
        blocked, _ = _is_blocked_command("touch newfile.txt", DEFAULT_BASE_DIR)
        assert blocked

    def test_blocks_tee(self) -> None:
        blocked, _ = _is_blocked_command("tee output.txt", DEFAULT_BASE_DIR)
        assert blocked

    def test_blocks_mkdir(self) -> None:
        blocked, _ = _is_blocked_command("mkdir newdir", DEFAULT_BASE_DIR)
        assert blocked

    def test_blocks_ln(self) -> None:
        blocked, _ = _is_blocked_command("ln -s target link", DEFAULT_BASE_DIR)
        assert blocked

    def test_blocks_chmod(self) -> None:
        blocked, _ = _is_blocked_command("chmod 755 file", DEFAULT_BASE_DIR)
        assert blocked

    def test_blocks_truncate(self) -> None:
        blocked, _ = _is_blocked_command("truncate -s 0 file", DEFAULT_BASE_DIR)
        assert blocked

    def test_blocks_empty_command(self) -> None:
        blocked, _ = _is_blocked_command("", DEFAULT_BASE_DIR)
        assert blocked


class TestBlocksRedirects:
    def test_blocks_redirect_to_file(self) -> None:
        blocked, _ = _is_blocked_command("echo test > output.txt", DEFAULT_BASE_DIR)
        assert blocked

    def test_blocks_append_redirect(self) -> None:
        blocked, _ = _is_blocked_command("echo test >> output.txt", DEFAULT_BASE_DIR)
        assert blocked

    def test_blocks_stderr_redirect_to_file(self) -> None:
        blocked, _ = _is_blocked_command("ls missing 2>/repo/out.txt", DEFAULT_BASE_DIR)
        assert blocked

    def test_blocks_stderr_append_redirect(self) -> None:
        blocked, _ = _is_blocked_command("ls missing 2>>/repo/out.txt", DEFAULT_BASE_DIR)
        assert blocked


class TestBlocksSedInplace:
    def test_blocks_sed_i(self) -> None:
        blocked, _ = _is_blocked_command("sed -i 's/old/new/g' file.txt", DEFAULT_BASE_DIR)
        assert blocked

    def test_blocks_sed_ni(self) -> None:
        blocked, _ = _is_blocked_command("sed -nri 's/old/new/g' file.txt", DEFAULT_BASE_DIR)
        assert blocked

    def test_blocks_sed_readonly(self) -> None:
        blocked, _ = _is_blocked_command("sed 's/foo/bar/g' file.txt", DEFAULT_BASE_DIR)
        assert blocked

    def test_blocks_sed_n(self) -> None:
        blocked, _ = _is_blocked_command("sed -n '1,10p' file.txt", DEFAULT_BASE_DIR)
        assert blocked


class TestBlocksFindDangerous:
    def test_blocks_find_exec(self) -> None:
        blocked, _ = _is_blocked_command("find . -name '*.py' -exec rm {} \\;", DEFAULT_BASE_DIR)
        assert blocked

    def test_blocks_find_execdir(self) -> None:
        blocked, _ = _is_blocked_command("find . -name '*.py' -execdir ls {} \\;", DEFAULT_BASE_DIR)
        assert blocked

    def test_blocks_find_delete(self) -> None:
        blocked, _ = _is_blocked_command("find . -name '*.pyc' -delete", DEFAULT_BASE_DIR)
        assert blocked

    def test_blocks_find_ok(self) -> None:
        blocked, _ = _is_blocked_command("find . -name '*.py' -ok ls {} \\;", DEFAULT_BASE_DIR)
        assert blocked

    def test_blocks_find_fprint(self) -> None:
        blocked, _ = _is_blocked_command("find . -name '*.py' -fprint out.txt", DEFAULT_BASE_DIR)
        assert blocked


class TestBlocksCommandInjection:
    def test_blocks_semicolon_chain(self) -> None:
        blocked, _ = _is_blocked_command("ls; rm file.txt", DEFAULT_BASE_DIR)
        assert blocked

    def test_blocks_and_chain_rm(self) -> None:
        blocked, _ = _is_blocked_command("ls && rm file.txt", DEFAULT_BASE_DIR)
        assert blocked

    def test_blocks_command_substitution(self) -> None:
        blocked, _ = _is_blocked_command("echo $(rm file)", DEFAULT_BASE_DIR)
        assert blocked

    def test_blocks_backtick_substitution(self) -> None:
        blocked, _ = _is_blocked_command("echo `rm file`", DEFAULT_BASE_DIR)
        assert blocked

    def test_blocks_multiline(self) -> None:
        blocked, _ = _is_blocked_command("ls\nrm file", DEFAULT_BASE_DIR)
        assert blocked

    def test_blocks_background_operator(self) -> None:
        blocked, _ = _is_blocked_command("ls & ls", DEFAULT_BASE_DIR)
        assert blocked


class TestBlocksVariableExpansion:
    def test_blocks_simple_var(self) -> None:
        blocked, _ = _is_blocked_command("cat $BASH", DEFAULT_BASE_DIR)
        assert blocked

    def test_blocks_brace_expansion(self) -> None:
        blocked, _ = _is_blocked_command("cat ${HOME%/*}/etc/passwd", DEFAULT_BASE_DIR)
        assert blocked


class TestBlocksPrivilegeAndSystem:
    def test_blocks_sudo(self) -> None:
        blocked, _ = _is_blocked_command("sudo ls", DEFAULT_BASE_DIR)
        assert blocked

    def test_blocks_reboot(self) -> None:
        blocked, _ = _is_blocked_command("reboot", DEFAULT_BASE_DIR)
        assert blocked

    def test_blocks_dd(self) -> None:
        blocked, _ = _is_blocked_command("dd if=/dev/zero of=file", DEFAULT_BASE_DIR)
        assert blocked


class TestBlocksNetwork:
    def test_blocks_curl(self) -> None:
        blocked, _ = _is_blocked_command("curl http://example.com", DEFAULT_BASE_DIR)
        assert blocked

    def test_blocks_wget(self) -> None:
        blocked, _ = _is_blocked_command("wget http://example.com", DEFAULT_BASE_DIR)
        assert blocked

    def test_blocks_ssh(self) -> None:
        blocked, _ = _is_blocked_command("ssh user@host", DEFAULT_BASE_DIR)
        assert blocked


class TestAllowsReadOnlyCommands:
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

    def test_allows_head_tail(self) -> None:
        blocked, _ = _is_blocked_command("head -n 10 file.txt", DEFAULT_BASE_DIR)
        assert not blocked

    def test_allows_wc(self) -> None:
        blocked, _ = _is_blocked_command("wc -l file.txt", DEFAULT_BASE_DIR)
        assert not blocked

    def test_allows_diff(self) -> None:
        blocked, _ = _is_blocked_command("diff a.txt b.txt", DEFAULT_BASE_DIR)
        assert not blocked

    def test_allows_echo(self) -> None:
        blocked, _ = _is_blocked_command("echo hello", DEFAULT_BASE_DIR)
        assert not blocked

    def test_allows_pipe(self) -> None:
        blocked, _ = _is_blocked_command("cat file | grep pattern", DEFAULT_BASE_DIR)
        assert not blocked

    def test_allows_grep_e_pipe_pattern(self) -> None:
        blocked, _ = _is_blocked_command("grep -E 'foo|bar' file.txt", DEFAULT_BASE_DIR)
        assert not blocked

    def test_allows_dollar_in_single_quotes(self) -> None:
        blocked, _ = _is_blocked_command("grep 'foo$' file.txt", DEFAULT_BASE_DIR)
        assert not blocked

    def test_allows_jq(self) -> None:
        blocked, _ = _is_blocked_command("jq '.name' package.json", DEFAULT_BASE_DIR)
        assert not blocked


class TestBlocksNonAllowlistedCommands:
    def test_blocks_python(self) -> None:
        blocked, _ = _is_blocked_command("python --version", DEFAULT_BASE_DIR)
        assert blocked

    def test_blocks_awk(self) -> None:
        blocked, _ = _is_blocked_command("awk '{print $1}' file.txt", DEFAULT_BASE_DIR)
        assert blocked


class TestGitSecurity:
    def test_allows_git_log(self) -> None:
        blocked, _ = _is_blocked_command("git log -n 10", DEFAULT_BASE_DIR)
        assert not blocked

    def test_allows_git_status(self) -> None:
        blocked, _ = _is_blocked_command("git status", DEFAULT_BASE_DIR)
        assert not blocked

    def test_allows_git_diff(self) -> None:
        blocked, _ = _is_blocked_command("git diff HEAD~1", DEFAULT_BASE_DIR)
        assert not blocked

    def test_allows_git_show(self) -> None:
        blocked, _ = _is_blocked_command("git show HEAD", DEFAULT_BASE_DIR)
        assert not blocked

    def test_allows_git_blame(self) -> None:
        blocked, _ = _is_blocked_command("git blame file.py", DEFAULT_BASE_DIR)
        assert not blocked

    def test_allows_git_log_p(self) -> None:
        blocked, _ = _is_blocked_command("git log -p -n 1", DEFAULT_BASE_DIR)
        assert not blocked

    def test_blocks_git_config(self) -> None:
        blocked, _ = _is_blocked_command("git config --global user.name foo", DEFAULT_BASE_DIR)
        assert blocked

    def test_blocks_git_diff_output(self) -> None:
        blocked, _ = _is_blocked_command("git diff --output=patch.txt HEAD~1", DEFAULT_BASE_DIR)
        assert blocked

    def test_blocks_git_push(self) -> None:
        blocked, _ = _is_blocked_command("git push origin main", DEFAULT_BASE_DIR)
        assert blocked

    def test_blocks_git_commit(self) -> None:
        blocked, _ = _is_blocked_command("git commit -m 'msg'", DEFAULT_BASE_DIR)
        assert blocked

    def test_blocks_git_reset(self) -> None:
        blocked, _ = _is_blocked_command("git reset --hard HEAD", DEFAULT_BASE_DIR)
        assert blocked

    def test_blocks_git_clean(self) -> None:
        blocked, _ = _is_blocked_command("git clean -fd", DEFAULT_BASE_DIR)
        assert blocked

    def test_blocks_git_checkout(self) -> None:
        blocked, _ = _is_blocked_command("git checkout -- .", DEFAULT_BASE_DIR)
        assert blocked

    def test_blocks_git_clone(self) -> None:
        blocked, _ = _is_blocked_command("git clone https://github.com/user/repo", DEFAULT_BASE_DIR)
        assert blocked

    def test_blocks_git_fetch(self) -> None:
        blocked, _ = _is_blocked_command("git fetch origin", DEFAULT_BASE_DIR)
        assert blocked

    def test_blocks_git_pull(self) -> None:
        blocked, _ = _is_blocked_command("git pull origin main", DEFAULT_BASE_DIR)
        assert blocked

    def test_blocks_git_add(self) -> None:
        blocked, _ = _is_blocked_command("git add .", DEFAULT_BASE_DIR)
        assert blocked


class TestPathSandbox:
    def test_blocks_absolute_etc(self) -> None:
        blocked, _ = _is_blocked_command("cat /etc/passwd", DEFAULT_BASE_DIR)
        assert blocked

    def test_blocks_absolute_home(self) -> None:
        blocked, _ = _is_blocked_command("ls /home", DEFAULT_BASE_DIR)
        assert blocked

    def test_allows_repo_path(self) -> None:
        blocked, _ = _is_blocked_command("cat /repo/file.txt", DEFAULT_BASE_DIR)
        assert not blocked

    def test_allows_relative_path(self) -> None:
        blocked, _ = _is_blocked_command("cat ./file.txt", DEFAULT_BASE_DIR)
        assert not blocked

    def test_blocks_path_traversal(self) -> None:
        blocked, _ = _is_blocked_command("cat ../etc/passwd", DEFAULT_BASE_DIR)
        assert blocked

    def test_blocks_dotdot(self) -> None:
        blocked, _ = _is_blocked_command("ls ..", DEFAULT_BASE_DIR)
        assert blocked


class TestTildeExpansion:
    def test_blocks_tilde_root(self) -> None:
        blocked, reason = _is_blocked_command("cat ~root/.bashrc", DEFAULT_BASE_DIR)
        assert blocked
        assert "tilde" in reason.lower()

    def test_blocks_tilde_nobody(self) -> None:
        blocked, _ = _is_blocked_command("ls ~nobody", DEFAULT_BASE_DIR)
        assert blocked

    def test_blocks_tilde_user_with_hyphen(self) -> None:
        blocked, _ = _is_blocked_command("cat ~www-data/.env", DEFAULT_BASE_DIR)
        assert blocked

    def test_allows_bare_tilde(self) -> None:
        blocked, _ = _is_blocked_command("ls ~", DEFAULT_BASE_DIR)
        assert not blocked

    def test_allows_tilde_slash(self) -> None:
        blocked, _ = _is_blocked_command("cat ~/file.txt", DEFAULT_BASE_DIR)
        assert not blocked


class TestGitOptionBlocking:
    def test_blocks_git_dir_equals(self) -> None:
        blocked, reason = _is_blocked_command("git --git-dir=/tmp/other/.git log", DEFAULT_BASE_DIR)
        assert blocked
        assert "--git-dir" in reason

    def test_blocks_git_dir_space(self) -> None:
        blocked, _ = _is_blocked_command("git --git-dir /tmp/other/.git log", DEFAULT_BASE_DIR)
        assert blocked

    def test_blocks_work_tree_equals(self) -> None:
        blocked, reason = _is_blocked_command("git --work-tree=/etc status", DEFAULT_BASE_DIR)
        assert blocked
        assert "--work-tree" in reason

    def test_blocks_exec_path_equals(self) -> None:
        blocked, _ = _is_blocked_command("git --exec-path=/tmp/evil log", DEFAULT_BASE_DIR)
        assert blocked

    def test_allows_normal_git_log(self) -> None:
        blocked, _ = _is_blocked_command("git log --oneline -10", DEFAULT_BASE_DIR)
        assert not blocked

    def test_allows_normal_git_diff(self) -> None:
        blocked, _ = _is_blocked_command("git diff HEAD~1", DEFAULT_BASE_DIR)
        assert not blocked


class TestTreeRemoved:
    def test_blocks_tree(self) -> None:
        blocked, reason = _is_blocked_command("tree", DEFAULT_BASE_DIR)
        assert blocked
        assert "not allowlisted" in reason.lower()
