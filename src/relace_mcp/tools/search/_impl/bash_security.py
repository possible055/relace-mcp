import os
import re
import shlex

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
    r"(?<![0-9])>\s*[^&\s>]",  # Redirect stdout to file (allow 2> and >&)
    r"(?<![0-9])>>\s*",  # Append stdout to file (allow 2>>)
    r"\$\(",  # Command substitution (inner commands bypass validation)
    r"`",  # Command substitution (backtick form)
    r"[\r\n]",  # Multi-line commands
    r";\s*\w",  # Command chaining with semicolon
    r"-(exec|execdir|ok|okdir)\b",  # find -exec (executes commands)
    r"-delete\b",  # find -delete
]

_SED_INPLACE_RE = re.compile(r"\bsed\b.*\s-[a-hj-zA-Z]*i")

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


def _check_blocked_patterns(command: str) -> tuple[bool, str]:
    for pattern in BASH_BLOCKED_PATTERNS:
        if re.search(pattern, command):
            return True, f"Blocked pattern: {pattern}"
    if _SED_INPLACE_RE.search(command):
        return True, "Blocked: sed -i (in-place edit)"
    return False, ""


def _parse_command_tokens(command: str) -> list[str]:
    try:
        return shlex.split(command)
    except ValueError:
        return command.split()


def _extract_commands(command: str) -> list[str]:
    parts = re.split(r"\s*(?:&&|\|\|)\s*", command)
    return [p.strip() for p in parts if p.strip()]


def _extract_pipe_commands(command: str) -> list[str]:
    parts = re.split(r"(?<!\|)\|(?!\|)", command)
    return [p.strip() for p in parts if p.strip()]


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


def _check_git_subcommand(tokens: list[str], base_cmd: str) -> tuple[bool, str]:
    if base_cmd != "git":
        return False, ""
    for token in tokens[1:]:
        if token.startswith("-"):
            continue
        if token in GIT_BLOCKED_SUBCOMMANDS:
            return True, f"Git subcommand blocked: {token}"
        break
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

    base_cmd = os.path.basename(tokens[0])

    if base_cmd in BASH_BLOCKED_COMMANDS:
        return True, f"Blocked command: {base_cmd}"

    blocked, reason = _check_git_subcommand(tokens, base_cmd)
    if blocked:
        return blocked, reason

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
