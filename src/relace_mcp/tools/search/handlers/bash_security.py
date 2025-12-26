import os
import re

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
    r"\|",  # Pipe (may bypass restrictions)
    r"`",  # Command substitution
    r"\$\(",  # Command substitution
    r";\s*\w",  # Command chaining
    r"&&",  # Conditional execution
    r"\|\|",  # Conditional execution
    r"-exec\b",  # find -exec (may execute dangerous commands)
    r"-delete\b",  # find -delete
]

# Git allowed read-only subcommands (whitelist strategy)
GIT_ALLOWED_SUBCOMMANDS = frozenset(
    {
        "log",
        "show",
        "diff",
        "status",
        "branch",
        "blame",
        "annotate",
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
        "tag",
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
        "awk",
        "sed",
        "sort",
        "uniq",
        "cut",
        "diff",
        "git",
        "python",
        "python3",
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

# Python dangerous patterns (check dangerous operations in python -c commands)
PYTHON_DANGEROUS_PATTERNS = [
    # File operations
    (r"open\s*\(", "file operations"),
    (r"\bwrite\s*\(", "write operations"),
    (r"\bremove\s*\(", "file removal"),
    (r"\bunlink\s*\(", "file removal"),
    (r"\brmdir\s*\(", "directory removal"),
    (r"\brename\s*\(", "file rename"),
    (r"\bmkdir\s*\(", "directory creation"),
    (r"\bchmod\s*\(", "permission change"),
    (r"\bchown\s*\(", "ownership change"),
    # Module imports (dangerous)
    (r"os\.remove", "os.remove"),
    (r"os\.unlink", "os.unlink"),
    (r"os\.rmdir", "os.rmdir"),
    (r"os\.system", "os.system"),
    (r"os\.popen", "os.popen"),
    (r"shutil\.rmtree", "shutil.rmtree"),
    (r"shutil\.move", "shutil.move"),
    (r"shutil\.copy", "shutil.copy"),
    (r"pathlib", "pathlib (file operations)"),
    (r"subprocess", "subprocess execution"),
    # Network operations
    (r"urllib", "network access"),
    (r"requests\.", "network access"),
    (r"http\.client", "network access"),
    (r"http\.server", "network access"),
    (r"socket", "network access"),
    # Dangerous built-in functions
    (r"\beval\s*\(", "eval"),
    (r"\bexec\s*\(", "exec"),
    (r"__import__", "__import__"),
    (r"compile\s*\(", "compile"),
]


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


def _check_python_code(tokens: list[str], base_cmd: str) -> tuple[bool, str]:
    """Check for dangerous operations in python -c code.

    Args:
        tokens: Command tokens.
        base_cmd: Base command (should be 'python' or 'python3').

    Returns:
        (is_blocked, reason) tuple.
    """
    if base_cmd not in ("python", "python3"):
        return False, ""

    # Special handling for python (only allow -c, and check dangerous patterns)
    if len(tokens) < 3 or tokens[1] != "-c":
        return True, "Python without -c flag is not allowed (prevents script execution)"

    # Check dangerous patterns in -c code (covers all possible file modification and network operations)
    python_code = " ".join(tokens[2:])
    for pattern, desc in PYTHON_DANGEROUS_PATTERNS:
        if re.search(pattern, python_code, re.IGNORECASE):
            return True, f"Blocked Python pattern: {desc}"

    return False, ""


def _check_sed_in_place(tokens: list[str], base_cmd: str) -> tuple[bool, str]:
    """Block sed in-place editing (-i/--in-place) while allowing safe read-only usage.

    This check is token-based (not regex on the raw command string) to avoid false
    positives when `-i` appears inside a sed script, e.g. `sed 's/this-is-fine/ok/'`.
    """
    if base_cmd != "sed":
        return False, ""

    # Parse options conservatively and stop at `--`.
    i = 1
    while i < len(tokens):
        token = tokens[i]
        if token == "--":  # nosec B105 - CLI argument, not password
            break

        # GNU sed supports --in-place[=SUFFIX]
        if token == "--in-place" or token.startswith("--in-place="):  # nosec B105
            return True, "Blocked pattern: sed in-place edit (--in-place)"

        if token.startswith("-") and token != "-" and not token.startswith("--"):  # nosec B105
            # Fast path: -i[SUFFIX]
            if token.startswith("-i"):
                return True, "Blocked pattern: sed in-place edit (-i)"

            # Handle combined short options, while respecting options that consume
            # arguments (-e/-f). Remainder of token after -e/-f is the argument.
            j = 1
            while j < len(token):
                opt = token[j]
                if opt == "i":
                    return True, "Blocked pattern: sed in-place edit (-i)"
                if opt in ("e", "f"):
                    # -eSCRIPT or -fFILE: consume remainder as argument.
                    if j + 1 < len(token):
                        break
                    # -e SCRIPT or -f FILE: consume next token as argument.
                    i += 1
                    break
                j += 1

        i += 1

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
    import shlex

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
    """Validate specialized commands (git, python) and arguments.

    Args:
        tokens: Command tokens.
        base_cmd: Base command name.

    Returns:
        (is_blocked, reason) tuple.
    """
    blocked, reason = _check_git_subcommand(tokens, base_cmd)
    if blocked:
        return blocked, reason

    blocked, reason = _check_python_code(tokens, base_cmd)
    if blocked:
        return blocked, reason

    blocked, reason = _check_sed_in_place(tokens, base_cmd)
    if blocked:
        return blocked, reason

    return _check_command_in_arguments(tokens)


def _is_blocked_command(command: str, base_dir: str) -> tuple[bool, str]:
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

    # Validate specialized commands
    return _validate_specialized_commands(tokens, base_cmd)
