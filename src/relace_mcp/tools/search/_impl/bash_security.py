import os
import re
import shlex

BASH_ALLOWED_COMMANDS = frozenset(
    {
        "cat",
        "diff",
        "echo",
        "file",
        "find",
        "git",
        "grep",
        "head",
        "jq",
        "ls",
        "rg",
        "tail",
        "true",
        "wc",
    }
)

BASH_BLOCKED_COMMANDS = frozenset(
    {
        # File deletion
        "rm",
        "rmdir",
        "unlink",
        "shred",
        # File modification / creation
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
        # System control
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
        # Dangerous execution
        "dd",
        "eval",
        "exec",
        "source",
        # Package management (can install/modify)
        "make",
        "cmake",
        "ninja",
        "cargo",
        "npm",
        "pip",
        "pip3",
    }
)

BASH_BLOCKED_PATTERNS = [
    r"`",  # Command substitution (backtick form)
    r"[\r\n]",  # Multi-line commands
    r";\s*\w",  # Command chaining with semicolon
    r"-(exec|execdir|ok|okdir)\b",  # find -exec (executes commands)
    r"-delete\b",  # find -delete
    r"-f(?:print0?|printf|ls)\b",  # find -fprint/-fprint0/-fprintf/-fls
]

GIT_BLOCKED_SUBCOMMANDS = frozenset(
    {
        # Destructive / write operations
        "push",
        "commit",
        "reset",
        "clean",
        "checkout",
        "switch",
        "restore",
        "rebase",
        "merge",
        "cherry-pick",
        "revert",
        "stash",
        "add",
        "rm",
        "init",
        "tag",
        # Network operations
        "clone",
        "fetch",
        "pull",
        "submodule",
    }
)

GIT_ALLOWED_SUBCOMMANDS = frozenset(
    {
        "blame",
        "diff",
        "grep",
        "log",
        "ls-files",
        "show",
        "status",
    }
)


def _check_unquoted_operators(command: str) -> tuple[bool, str]:
    in_single = False
    in_double = False
    escaped = False
    i = 0
    while i < len(command):
        ch = command[i]

        if escaped:
            escaped = False
            i += 1
            continue

        if ch == "\\" and not in_single:
            escaped = True
            i += 1
            continue

        if ch == "'" and not in_double:
            in_single = not in_single
            i += 1
            continue

        if ch == '"' and not in_single:
            in_double = not in_double
            i += 1
            continue

        if not in_single and ch == "$":
            # Allow $HOME / ${HOME} only (HOME is forced to base_dir in bash_handler).
            if i + 1 < len(command) and command[i + 1] == "{":
                end = command.find("}", i + 2)
                if end != -1 and command[i + 2 : end] == "HOME":
                    i += 1
                    continue
                return True, "Blocked: variable expansion ($...)"

            m = re.match(r"[A-Za-z_][A-Za-z0-9_]*", command[i + 1 :])
            if m and m.group(0) == "HOME":
                i += 1
                continue
            return True, "Blocked: variable expansion ($...)"

        if not in_single and not in_double:
            if ch in ("<", ">"):
                return True, "Blocked: redirects (< or >)"

            if ch == "&":
                if i + 1 < len(command) and command[i + 1] == "&":
                    i += 2
                    continue
                return True, "Blocked: background operator (&)"

        i += 1
    return False, ""


def _check_blocked_patterns(command: str) -> tuple[bool, str]:
    blocked, reason = _check_unquoted_operators(command)
    if blocked:
        return blocked, reason

    for pattern in BASH_BLOCKED_PATTERNS:
        if re.search(pattern, command):
            return True, f"Blocked pattern: {pattern}"
    return False, ""


def _parse_command_tokens(command: str) -> list[str]:
    try:
        return shlex.split(command)
    except ValueError:
        return command.split()


def _extract_commands(command: str) -> list[str]:
    parts: list[str] = []
    buf: list[str] = []
    in_single = False
    in_double = False
    escaped = False
    i = 0
    while i < len(command):
        ch = command[i]

        if escaped:
            escaped = False
            buf.append(ch)
            i += 1
            continue

        if ch == "\\" and not in_single:
            escaped = True
            buf.append(ch)
            i += 1
            continue

        if ch == "'" and not in_double:
            in_single = not in_single
            buf.append(ch)
            i += 1
            continue

        if ch == '"' and not in_single:
            in_double = not in_double
            buf.append(ch)
            i += 1
            continue

        if not in_single and not in_double:
            if ch == "&" and i + 1 < len(command) and command[i + 1] == "&":
                part = "".join(buf).strip()
                if part:
                    parts.append(part)
                buf = []
                i += 2
                continue
            if ch == "|" and i + 1 < len(command) and command[i + 1] == "|":
                part = "".join(buf).strip()
                if part:
                    parts.append(part)
                buf = []
                i += 2
                continue

        buf.append(ch)
        i += 1

    tail = "".join(buf).strip()
    if tail:
        parts.append(tail)
    return parts


def _extract_pipe_commands(command: str) -> list[str]:
    parts: list[str] = []
    buf: list[str] = []
    in_single = False
    in_double = False
    escaped = False
    i = 0
    while i < len(command):
        ch = command[i]

        if escaped:
            escaped = False
            buf.append(ch)
            i += 1
            continue

        if ch == "\\" and not in_single:
            escaped = True
            buf.append(ch)
            i += 1
            continue

        if ch == "'" and not in_double:
            in_single = not in_single
            buf.append(ch)
            i += 1
            continue

        if ch == '"' and not in_single:
            in_double = not in_double
            buf.append(ch)
            i += 1
            continue

        if not in_single and not in_double and ch == "|":
            prev_is_pipe = i > 0 and command[i - 1] == "|"
            next_is_pipe = i + 1 < len(command) and command[i + 1] == "|"
            if not prev_is_pipe and not next_is_pipe:
                part = "".join(buf).strip()
                if part:
                    parts.append(part)
                buf = []
                i += 1
                continue

        buf.append(ch)
        i += 1

    tail = "".join(buf).strip()
    if tail:
        parts.append(tail)
    return parts


def _check_absolute_paths(tokens: list[str]) -> tuple[bool, str]:
    for token in tokens:
        if token.startswith("/"):
            if token == "/repo" or token.startswith("/repo/"):  # nosec B105
                continue
            if token in ("/dev/null",):
                continue
            return True, f"Absolute path outside /repo not allowed: {token}"
        if re.match(r"^[A-Za-z]:[/\\]", token) or token.startswith("\\\\"):
            return True, f"Absolute path outside /repo not allowed: {token}"
    return False, ""


def _check_path_traversal(command: str, tokens: list[str]) -> tuple[bool, str]:
    if "../" in command or "..\\" in command:
        return True, "Path traversal pattern detected"
    for token in tokens:
        if token in ("..", "./..", ".\\.."):
            return True, "Path traversal pattern detected"
        if token.endswith("/..") or token.endswith("\\.."):
            return True, "Path traversal pattern detected"
        if "/../" in token or "\\..\\" in token:
            return True, "Path traversal pattern detected"
    return False, ""


_GIT_BLOCKED_OPTIONS = frozenset(
    {
        "--output",
        "--git-dir",
        "--work-tree",
        "--exec-path",
    }
)


def _check_git_subcommand(tokens: list[str], base_cmd: str) -> tuple[bool, str]:
    if base_cmd != "git":
        return False, ""
    subcmd = ""
    for token in tokens[1:]:
        if token.startswith("-"):
            continue
        subcmd = token
        break

    if not subcmd:
        return False, ""

    if subcmd in GIT_BLOCKED_SUBCOMMANDS:
        return True, f"Git subcommand blocked: {subcmd}"

    if subcmd not in GIT_ALLOWED_SUBCOMMANDS:
        return True, f"Git subcommand not allowlisted: {subcmd}"

    for token in tokens[1:]:
        for opt in _GIT_BLOCKED_OPTIONS:
            if token == opt or token.startswith(opt + "="):
                return True, f"Git option blocked: {opt}"

    return False, ""


def _check_path_containment(tokens: list[str], base_dir: str) -> tuple[bool, str]:
    """Verify resolved file arguments stay within base_dir (symlink-safe).

    Args:
        tokens: Parsed command tokens (first element is the command).
        base_dir: Sandbox root directory.

    Returns:
        (is_blocked, reason) tuple.
    """
    if not base_dir:
        return False, ""
    real_base = os.path.realpath(base_dir)
    for token in tokens[1:]:
        if token.startswith("-"):
            continue
        if not token or token == ".":  # nosec B105 - "." is a path token, not a password
            continue
        candidate = token if os.path.isabs(token) else os.path.join(base_dir, token)
        resolved = os.path.realpath(candidate)
        if resolved != real_base and not resolved.startswith(real_base + os.sep):
            return True, f"Path escapes sandbox: {token}"
    return False, ""


_TILDE_USER_RE = re.compile(r"^~[A-Za-z_][A-Za-z0-9_-]*")


def _validate_single_command(cmd_str: str, base_dir: str) -> tuple[bool, str]:
    tokens = _parse_command_tokens(cmd_str)
    if not tokens:
        return True, "Empty command after parsing"

    blocked, reason = _check_path_traversal(cmd_str, tokens)
    if blocked:
        return blocked, reason

    blocked, reason = _check_absolute_paths(tokens)
    if blocked:
        return blocked, reason

    for token in tokens:
        if _TILDE_USER_RE.match(token):
            return True, f"Blocked: tilde user expansion ({token})"

    base_cmd = os.path.basename(tokens[0])

    if base_cmd in BASH_BLOCKED_COMMANDS:
        return True, f"Blocked command: {base_cmd}"

    if base_cmd not in BASH_ALLOWED_COMMANDS:
        return True, f"Command not allowlisted: {base_cmd}"

    blocked, reason = _check_git_subcommand(tokens, base_cmd)
    if blocked:
        return blocked, reason

    # Sed in-place edit check (defense in depth; sed is not in the allowlist)
    if base_cmd == "sed":
        for token in tokens[1:]:
            if token == "--in-place":  # nosec B105 — not a password, sed flag check
                return True, "Blocked: sed --in-place (in-place edit)"
            if token.startswith("-") and not token.startswith("--"):
                if "i" in token[1:]:
                    return True, "Blocked: sed -i (in-place edit)"

    blocked, reason = _check_path_containment(tokens, base_dir)
    if blocked:
        return blocked, reason

    return False, ""


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

    blocked, reason = _check_blocked_patterns(command)
    if blocked:
        return blocked, reason

    chain_parts = _extract_commands(command_stripped)
    for part in chain_parts:
        pipe_parts = _extract_pipe_commands(part)
        for segment in pipe_parts:
            blocked, reason = _validate_single_command(segment, base_dir)
            if blocked:
                return blocked, reason

    return False, ""
