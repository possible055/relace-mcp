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
    r"\|",  # Pipe (may bypass restrictions)
    r"`",  # Command substitution
    r"\$\(",  # Command substitution
    r"[\r\n]",  # Multi-line commands (command chaining)
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
        "awk",
        "sed",
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


def _check_awk_script(tokens: list[str], base_cmd: str) -> tuple[bool, str]:
    """Block awk constructs that can spawn subprocesses or perform I/O.

    awk supports multiple ways to execute shell commands:
    - system() - execute a shell command
    - "cmd" | getline - execute cmd and read its output
    - print | "cmd" - pipe print output to cmd
    We also block loading scripts from files (-f/--file) because we don't
    inspect their contents here.
    """
    if base_cmd != "awk":
        return False, ""

    # Disallow script files: too hard to validate safely without reading them.
    for token in tokens[1:]:
        if token in {"-f", "--file"} or token.startswith("--file="):  # nosec B105 - CLI flag
            return True, "Blocked awk script file flag (-f/--file)"

    # Best-effort: scan all remaining arguments for dangerous patterns.
    # (Avoids having to fully parse awk option grammar.)
    args_blob = " ".join(tokens[1:])

    # Block system() - direct command execution
    if re.search(r"\bsystem\s*\(", args_blob, flags=re.IGNORECASE):
        return True, "Blocked awk system() (subprocess execution)"

    # Block getline with pipe: "cmd" | getline (executes cmd and reads output)
    # Pattern: string/variable followed by | and getline
    if re.search(r"\|\s*getline\b", args_blob, flags=re.IGNORECASE):
        return True, "Blocked awk pipe to getline (subprocess execution)"

    # Block print/printf piped to command: print | "cmd"
    if re.search(r'\bprint[f]?\s*[^|]*\|\s*["\']', args_blob, flags=re.IGNORECASE):
        return True, "Blocked awk print pipe to command (subprocess execution)"

    return False, ""


# Regex to extract substitution command flags: s<delim>...<delim>...<delim>[flags]
# Captures the flags portion after the third delimiter
_SED_SUBST_FLAGS_RE = re.compile(
    r"s([/\#@|:,!])(?:[^\\]|\\.)*?\1(?:[^\\]|\\.)*?\1([giIpPmM0-9ew]*)",
    flags=re.IGNORECASE,
)

# Standalone e/w commands at script start or after semicolon/newline
_SED_STANDALONE_CMD_RE = re.compile(r"(^|[;\n])\s*[ew](\s|$)", flags=re.IGNORECASE)

# Address-prefixed e/w commands: 5e, 1,10e, $e (GNU sed: e executes pattern space)
# Matches: <number>[,<number>]<e|w> or $[ew]
_SED_ADDRESSED_CMD_RE = re.compile(r"(\d+|\$)(,(\d+|\$))?\s*[ew]", flags=re.IGNORECASE)


def _sed_script_has_dangerous_flag(script: str) -> bool:
    """Check if sed script contains dangerous e/w commands.

    Detects:
    - e/w flags in substitution commands (s/.../.../<flags>)
    - Standalone e/w commands at script boundaries
    - Address-prefixed e/w commands (5e, 1,10e, $w)
    """
    # Check substitution command flags (all occurrences)
    for match in _SED_SUBST_FLAGS_RE.finditer(script):
        flags = match.group(2).lower()
        if "e" in flags or "w" in flags:
            return True

    # Check standalone e/w commands
    if _SED_STANDALONE_CMD_RE.search(script):
        return True

    # Check address-prefixed e/w commands (e.g., 5e, 1,10e, $w)
    if _SED_ADDRESSED_CMD_RE.search(script):
        return True

    return False


def _check_sed_script(tokens: list[str], base_cmd: str) -> tuple[bool, str]:
    """Block sed features that can write files or execute commands.

    - `w` writes to a file even without `-i`
    - `e` executes a shell command (GNU sed) and can be used for sandbox escape
    - `-f/--file` loads scripts from a file (not inspected here)
    """
    if base_cmd != "sed":
        return False, ""

    # Reject external script files (-f/--file) to prevent uninspected `e`/`w`.
    i = 1
    while i < len(tokens):
        token = tokens[i]
        if token == "--":  # nosec B105 - CLI argument, not password
            break

        if token == "-f" or token == "--file" or token.startswith("--file="):  # nosec B105
            return True, "Blocked sed script file flag (-f/--file)"

        # Consume arguments for flags that take parameters (best-effort).
        if token in {"-e", "-f", "-i"}:  # nosec B105
            i += 1
            i += 1
            continue
        i += 1

    # Best-effort: inspect inline scripts (from -e and/or first non-flag token).
    scripts: list[str] = []
    saw_e_flag = False
    i = 1
    while i < len(tokens):
        token = tokens[i]
        if token == "--":  # nosec B105
            i += 1
            break

        if token == "-e":  # nosec B105
            if i + 1 < len(tokens):
                scripts.append(tokens[i + 1])
            saw_e_flag = True
            i += 2
            continue

        if token.startswith("-") and token != "-":  # nosec B105
            i += 1
            continue

        # First positional argument is a script ONLY when no -e/-f scripts are provided.
        if not saw_e_flag and not scripts:
            scripts.append(token)
        break

    for script in scripts:
        if _sed_script_has_dangerous_flag(script):
            return True, "Blocked sed script containing e/w (command exec or file write)"

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

    blocked, reason = _check_ripgrep_preprocessor(tokens, base_cmd)
    if blocked:
        return blocked, reason

    blocked, reason = _check_awk_script(tokens, base_cmd)
    if blocked:
        return blocked, reason

    blocked, reason = _check_sed_in_place(tokens, base_cmd)
    if blocked:
        return blocked, reason

    blocked, reason = _check_sed_script(tokens, base_cmd)
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

    blocked, reason = _check_symlink_follow_flags(tokens, base_cmd)
    if blocked:
        return blocked, reason

    blocked, reason = _check_path_escapes_base_dir(tokens, base_cmd, base_dir)
    if blocked:
        return blocked, reason

    # Validate specialized commands
    return _validate_specialized_commands(tokens, base_cmd)
