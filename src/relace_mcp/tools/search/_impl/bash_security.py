import os
import re
import shlex
from pathlib import Path

from ....utils import resolve_repo_path

# Block dangerous commands (blacklist)
BASH_BLOCKED_COMMANDS = frozenset(
    {
        # File modification
        "rm",
        "rmdir",
        "unlink",
        "shred",
        "mv",
        "cp",
        "install",
        "mkdir",
        "chmod",
        "chown",
        "chgrp",
        "touch",
        "tee",
        "truncate",
        "ln",
        "mkfifo",
        # Network access
        "wget",
        "curl",
        "fetch",
        "aria2c",
        "ssh",
        "scp",
        "rsync",
        "sftp",
        "ftp",
        "telnet",
        "nc",
        "netcat",
        "ncat",
        "socat",
        # Privilege escalation
        "sudo",
        "su",
        "doas",
        "pkexec",
        # Process control
        "kill",
        "killall",
        "pkill",
        # System administration
        "reboot",
        "shutdown",
        "halt",
        "poweroff",
        "init",
        "useradd",
        "userdel",
        "usermod",
        "passwd",
        "crontab",
        # Dangerous tools
        "dd",
        "eval",
        "exec",
        "source",
        # Package management (may trigger network/ installation)
        "make",
        "cmake",
        "ninja",
        "cargo",
        "npm",
        "pip",
        "pip3",
    }
)


# Block dangerous patterns (prevent bypass)
BASH_BLOCKED_PATTERNS = [
    r">\s*[^&]",  # Redirect write
    r">>\s*",  # Append write
    r"<\(",  # Process substitution (executes commands)
    r"\|",  # Pipe (may bypass restrictions)
    r"`",  # Command substitution
    r"\$\(",  # Command substitution
    r"[\r\n]",  # Multi-line commands (command chaining)
    r";\s*\w",  # Command chaining
    r"&&",  # Conditional execution
    r"\|\|",  # Conditional execution
    r"-(exec|execdir|ok|okdir)\b",  # find -exec/-execdir/-ok/-okdir (executes commands)
    r"-delete\b",  # find -delete
]

# Git allowed read-only subcommands (whitelist strategy)
GIT_ALLOWED_SUBCOMMANDS = frozenset(
    {
        "log",
        "status",
        "shortlog",
        "ls-files",
        "ls-tree",
        "cat-file",
        "rev-parse",
        "rev-list",
        "describe",
        "name-rev",
        "for-each-ref",
        "grep",
    }
)

# Allowed read commands (whitelist: block unknown commands)
BASH_SAFE_COMMANDS = frozenset(
    {
        "ls",
        "find",
        "cat",
        "head",
        "tail",
        "wc",
        "file",
        "stat",
        "tree",
        "grep",
        "egrep",
        "fgrep",
        "rg",
        "ag",
        "sort",
        "uniq",
        "cut",
        "diff",
        "git",
        "basename",
        "dirname",
        "realpath",
        "readlink",
        "date",
        "echo",
        "printf",
        "true",
        "false",
        "test",
        "[",
    }
)

_COMMANDS_WITH_PATH_ARGS = frozenset(
    {
        "ls",
        "find",
        "cat",
        "head",
        "tail",
        "wc",
        "file",
        "stat",
        "tree",
        "grep",
        "egrep",
        "fgrep",
        "rg",
        "ag",
        "diff",
        "basename",
        "dirname",
        "realpath",
        "readlink",
        "test",
        "[",
    }
)


def _expand_home_token(token: str, base_dir: str) -> str:
    """Expand a small set of HOME/tilde forms that bash will expand at runtime.

    This keeps our token-level path validation aligned with the actual execution
    environment where HOME is set to base_dir.
    """
    if token == "~":  # nosec B105 - not a password, shell home symbol
        return base_dir
    if token.startswith("~/"):
        return os.path.join(base_dir, token[2:])
    if token.startswith("$HOME/"):
        return os.path.join(base_dir, token[6:])
    if token.startswith("${HOME}/"):
        return os.path.join(base_dir, token[8:])
    return token


def _check_symlink_follow_flags(tokens: list[str], base_cmd: str) -> tuple[bool, str]:
    """Block flags that make tools follow symlinks during traversal."""
    if base_cmd == "find":
        if any(t in {"-L", "-H"} for t in tokens[1:]):  # nosec B105 - CLI flags
            return True, "Blocked find symlink-follow flag (-L/-H)"
        if any(t == "-follow" for t in tokens[1:]):  # nosec B105 - find expression
            return True, "Blocked find symlink-follow expression (-follow)"

    if base_cmd == "rg":
        if any(t == "--follow" for t in tokens[1:]):  # nosec B105 - CLI flag
            return True, "Blocked rg symlink-follow flag (--follow)"
        for t in tokens[1:]:
            if t.startswith("-") and "L" in t[1:]:  # nosec B105 - CLI flag
                return True, "Blocked rg symlink-follow flag (-L)"

    if base_cmd in {"grep", "egrep", "fgrep"}:
        if any(
            t in {"--recursive", "--dereference-recursive"}
            for t in tokens[1:]  # nosec B105
        ):
            return True, "Blocked grep recursive flags (may follow symlinks)"
        for t in tokens[1:]:
            if not (t.startswith("-") and not t.startswith("--")):  # nosec B105
                continue
            # Short option bundling: `-Rni` etc.
            if "r" in t[1:] or "R" in t[1:]:
                return True, "Blocked grep recursive flags (may follow symlinks)"

    if base_cmd == "tree":
        for t in tokens[1:]:
            if not (t.startswith("-") and not t.startswith("--")):  # nosec B105
                continue
            if "l" in t[1:]:
                return True, "Blocked tree symlink-follow flag (-l)"

    return False, ""


def _check_path_escapes_base_dir(
    tokens: list[str], base_cmd: str, base_dir: str
) -> tuple[bool, str]:
    """Block path arguments that resolve outside base_dir (typically via symlinks).

    This is a defense-in-depth check for the bash tool, since many otherwise
    "read-only" commands (cat/head/wc/etc.) will happily follow symlinks.
    """
    if base_cmd not in _COMMANDS_WITH_PATH_ARGS:
        return False, ""

    base_dir_path = Path(base_dir)

    for token in tokens[1:]:
        if token.startswith("-") and token != "-":  # nosec B105
            continue
        if token == "-":  # nosec B105 - stdin placeholder, not password
            continue

        # Validate /repo tokens explicitly.
        if token == "/repo" or token.startswith("/repo/"):  # nosec B105
            try:
                resolve_repo_path(token, base_dir, allow_relative=False, allow_absolute=False)
            except ValueError:
                return True, f"Path escapes base_dir: {token}"
            continue

        # Block ~user tilde expansion (e.g., ~root → /root) that Bash would expand
        # to another user's home directory, allowing sandbox escape.
        # Only allow: ~ (alone), ~/ (current user home prefix)
        if token.startswith("~") and token != "~" and not token.startswith("~/"):  # nosec B105 - tilde shell symbol, not password
            return True, f"Blocked ~user tilde pattern (sandbox escape): {token}"

        expanded = _expand_home_token(token, base_dir)
        candidate = Path(expanded) if os.path.isabs(expanded) else (base_dir_path / expanded)

        try:
            if not candidate.exists():
                continue
        except OSError:
            # If we can't stat it, let the command fail normally.
            continue

        try:
            if os.path.isabs(expanded):
                resolve_repo_path(expanded, base_dir, require_within_base_dir=True)
            else:
                resolve_repo_path(expanded, base_dir, allow_absolute=False)
        except ValueError:
            return True, f"Path escapes base_dir: {token}"

    return False, ""


def _is_traversal_token(token: str) -> bool:
    """Check if token is a path traversal pattern.

    Args:
        token: Token to check.

    Returns:
        True if it's a path traversal pattern.
    """
    if token in ("..", "./..", ".\\.."):
        return True
    if token.endswith("/..") or token.endswith("\\.."):
        return True
    if "/../" in token or "\\..\\" in token:
        return True
    return False


def _check_absolute_paths(tokens: list[str]) -> tuple[bool, str]:
    """Check if absolute paths in tokens are safe.

    Args:
        tokens: Command tokens.

    Returns:
        (is_blocked, reason) tuple.
    """
    for token in tokens:
        if token.startswith("/"):
            if token == "/repo" or token.startswith("/repo/"):  # nosec B105
                continue
            # Block access to system directories
            return True, f"Absolute path outside /repo not allowed: {token}"
        # Windows absolute paths and UNC paths (defense-in-depth for Git Bash / MSYS).
        # Examples:
        # - C:\Windows\System32
        # - C:/Windows/System32
        # - \\server\share
        if re.match(r"^[A-Za-z]:[\\/]", token) or token.startswith("\\\\"):
            return True, f"Absolute path outside /repo not allowed: {token}"
    return False, ""


def _check_blocked_patterns(command: str) -> tuple[bool, str]:
    """Check for dangerous patterns in command (pipe, redirect, command substitution, etc.).

    Args:
        command: Command string to check.

    Returns:
        (is_blocked, reason) tuple.
    """
    for pattern in BASH_BLOCKED_PATTERNS:
        if re.search(pattern, command):
            if pattern == r"\|":
                return True, (
                    "Blocked pattern: pipe operator. "
                    "Use grep_search tool for pattern matching instead"
                )
            return True, f"Blocked pattern: {pattern}"
    return False, ""


def _has_variable_expansion(command: str) -> bool:
    """Return True if command contains a `$` that bash would expand.

    This is a defense-in-depth guard for the `bash` tool. Shell variable expansion can be used
    to synthesize absolute paths or bypass token-level path checks (e.g., `${HOME%/*}`).

    Rules:
    - `$` inside single quotes is not expanded by bash.
    - Escaped `$` (e.g., `\\$HOME`) is treated as literal.
    - `$` inside double quotes is still expanded and is blocked.
    """
    in_single = False
    in_double = False
    escaped = False

    for ch in command:
        if escaped:
            escaped = False
            continue

        # Backslash escapes outside single quotes (including inside double quotes).
        if not in_single and ch == "\\":  # nosec B105 - escape char
            escaped = True
            continue

        # Single quotes are only special outside double quotes.
        if ch == "'" and not in_double:  # nosec B105 - quote char
            in_single = not in_single
            continue

        # Double quotes are only special outside single quotes.
        if ch == '"' and not in_single:  # nosec B105 - quote char
            in_double = not in_double
            continue

        if ch == "$" and not in_single:  # nosec B105 - shell sigil
            return True

    return False


def _check_path_safety(command: str, tokens: list[str]) -> tuple[bool, str]:
    """Check path traversal and absolute path safety.

    Args:
        command: Original command string.
        tokens: Command tokens.

    Returns:
        (is_blocked, reason) tuple.
    """
    # Check path traversal
    if "../" in command or "..\\" in command:
        return True, "Path traversal pattern detected"

    if any(_is_traversal_token(t) for t in tokens):
        return True, "Path traversal pattern detected"

    # Check absolute paths
    return _check_absolute_paths(tokens)


def _check_git_subcommand(tokens: list[str], base_cmd: str) -> tuple[bool, str]:
    """Check if git subcommand is in whitelist.

    Args:
        tokens: Command tokens.
        base_cmd: Base command (should be 'git').

    Returns:
        (is_blocked, reason) tuple.
    """
    if base_cmd != "git":
        return False, ""

    # Special handling for git (whitelist strategy: only allow explicit read-only subcommands)
    for token in tokens[1:]:
        if token.startswith("-"):
            continue
        if token not in GIT_ALLOWED_SUBCOMMANDS:
            return True, f"Git subcommand not in allowlist: {token}"
        # Found first non-flag token which is the subcommand, check complete
        break

    return False, ""


_GIT_BLOCKED_FLAGS = frozenset(
    {
        # Can invoke external diff/textconv drivers depending on repo config.
        "--ext-diff",
        "--textconv",
        "--no-index",
        # `git log -p` is effectively a diff/show escape hatch.
        "-p",
        "--patch",
    }
)


def _check_git_dangerous_flags(tokens: list[str], base_cmd: str) -> tuple[bool, str]:
    if base_cmd != "git":
        return False, ""

    for token in tokens[1:]:
        # Exact match for long flags and standalone short flags
        if token in _GIT_BLOCKED_FLAGS:
            return True, f"Blocked git flag: {token}"
        # Handle combined short options (e.g., -pS, -Sp decompose to -p -S)
        # Only single-dash tokens that aren't long flags
        if token.startswith("-") and not token.startswith("--") and len(token) > 2:
            for blocked in _GIT_BLOCKED_FLAGS:
                # Only check single-char short flags (e.g., "-p")
                if blocked.startswith("-") and not blocked.startswith("--") and len(blocked) == 2:
                    if blocked[1] in token[1:]:
                        return True, f"Blocked git flag: {blocked} (in combined option {token})"

    return False, ""


def _check_ripgrep_preprocessor(tokens: list[str], base_cmd: str) -> tuple[bool, str]:
    """Block ripgrep preprocessors, which can spawn arbitrary subprocesses.

    `rg --pre=COMMAND` runs COMMAND for every searched file.
    This violates the "read-only, no side effects" contract of the bash tool
    and is a common sandbox escape vector.
    """
    if base_cmd != "rg":
        return False, ""

    for token in tokens[1:]:
        if token == "--pre" or token.startswith("--pre="):  # nosec B105 - CLI flag
            return True, "Blocked rg preprocessor flag (--pre)"
        if token == "--pre-glob" or token.startswith("--pre-glob="):  # nosec B105 - CLI flag
            return True, "Blocked rg preprocessor flag (--pre-glob)"

    return False, ""


def _check_command_in_arguments(tokens: list[str]) -> tuple[bool, str]:
    """Check if dangerous commands are hidden in arguments.

    Args:
        tokens: Command tokens.

    Returns:
        (is_blocked, reason) tuple.
    """
    for token in tokens[1:]:
        if token.startswith("-"):
            continue
        token_base = os.path.basename(token)
        if token_base in BASH_BLOCKED_COMMANDS:
            return True, f"Blocked command in arguments: {token_base}"

    return False, ""


def _parse_command_tokens(command: str) -> list[str]:
    """Parse command into tokens.

    Args:
        command: Command string.

    Returns:
        Token list.
    """
    try:
        return shlex.split(command)
    except ValueError:
        return command.split()


def _validate_command_base(base_cmd: str) -> tuple[bool, str]:
    """Validate command base security (blacklist/whitelist).

    Args:
        base_cmd: Base command name.

    Returns:
        (is_blocked, reason) tuple.
    """
    if base_cmd in BASH_BLOCKED_COMMANDS:
        return True, f"Blocked command: {base_cmd}"

    if base_cmd not in BASH_SAFE_COMMANDS:
        return True, f"Command not in allowlist: {base_cmd}"

    return False, ""


def _validate_specialized_commands(tokens: list[str], base_cmd: str) -> tuple[bool, str]:
    """Validate specialized commands (git, ripgrep) and arguments.

    Args:
        tokens: Command tokens.
        base_cmd: Base command name.

    Returns:
        (is_blocked, reason) tuple.
    """
    blocked, reason = _check_git_subcommand(tokens, base_cmd)
    if blocked:
        return blocked, reason

    blocked, reason = _check_git_dangerous_flags(tokens, base_cmd)
    if blocked:
        return blocked, reason

    blocked, reason = _check_ripgrep_preprocessor(tokens, base_cmd)
    if blocked:
        return blocked, reason

    return _check_command_in_arguments(tokens)


def is_blocked_command(command: str, base_dir: str) -> tuple[bool, str]:
    """Check if command violates security rules.

    Args:
        command: Bash command to execute.
        base_dir: Base directory for command execution.

    Returns:
        (is_blocked, reason) tuple.
    """
    command_stripped = command.strip()
    if not command_stripped:
        return True, "Empty command"

    # Check dangerous patterns
    blocked, reason = _check_blocked_patterns(command)
    if blocked:
        return blocked, reason

    # Block shell variable expansion to prevent sandbox escape / path synthesis.
    if _has_variable_expansion(command):
        return (
            True,
            "Blocked pattern: shell variable expansion ($...). Use explicit /repo paths instead.",
        )

    # Parse command tokens
    tokens = _parse_command_tokens(command)
    if not tokens:
        return True, "Empty command after parsing"

    # Check path safety
    blocked, reason = _check_path_safety(command, tokens)
    if blocked:
        return blocked, reason

    # Validate base command
    base_cmd = os.path.basename(tokens[0])
    blocked, reason = _validate_command_base(base_cmd)
    if blocked:
        return blocked, reason

    blocked, reason = _check_symlink_follow_flags(tokens, base_cmd)
    if blocked:
        return blocked, reason

    blocked, reason = _check_path_escapes_base_dir(tokens, base_cmd, base_dir)
    if blocked:
        return blocked, reason

    # Validate specialized commands
    return _validate_specialized_commands(tokens, base_cmd)
