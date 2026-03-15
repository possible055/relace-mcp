import ast
import os
import re
from bisect import bisect_right
from collections import Counter

# Directive patterns for remove operations
_REMOVE_DIRECTIVE_PATTERNS = ("// remove ", "# remove ")

_FENCE_PREFIX = "```"


def is_truncation_placeholder(line: str) -> bool:
    """Determine if line is a truncation placeholder (ellipsis marker).

    Note: // remove Block is a directive, not a placeholder.

    Args:
        line: The line to check.

    Returns:
        True if it's a placeholder, False otherwise.
    """
    s = line.strip()
    if not s:
        return True

    lower = s.lower()
    return (
        lower.startswith("// ...")
        or lower.startswith("# ...")
        or lower.startswith("//...")
        or lower.startswith("#...")
    )


def normalize_edit_snippet(edit_snippet: str) -> str:
    """Normalize edit_snippet input.

    Agents sometimes wrap tool arguments in markdown fences. When nested inside
    apply XML tags, fences can confuse merge models and anchors.

    This strips a single outer fence pair:
      ```lang
      ...
      ```
    """
    trimmed = edit_snippet.strip()
    lines = trimmed.splitlines()
    if len(lines) < 3:
        return edit_snippet

    first = lines[0].strip()
    last = lines[-1].strip()
    if not first.startswith(_FENCE_PREFIX) or last != _FENCE_PREFIX:
        return edit_snippet

    lang = first[len(_FENCE_PREFIX) :].strip()
    for ch in lang:
        if ch.isalnum() or ch in "-_":
            continue
        return edit_snippet

    inner = "\n".join(lines[1:-1])
    if edit_snippet.endswith("\n") and not inner.endswith("\n"):
        inner += "\n"
    return inner


def _is_explicit_marker_line(line: str) -> bool:
    """True if line is an explicit truncation marker (not just whitespace)."""
    s = line.strip()
    if not s:
        return False
    lower = s.lower()
    return (
        lower.startswith("// ...")
        or lower.startswith("# ...")
        or lower.startswith("//...")
        or lower.startswith("#...")
    )


def contains_truncation_markers(text: str) -> bool:
    """Return True if text contains any explicit truncation marker line."""
    return any(_is_explicit_marker_line(line) for line in text.splitlines())


def concrete_lines(text: str) -> list[str]:
    """Return non-placeholder lines (including remove directives).

    Args:
        text: Edit snippet text.

    Returns:
        List of non-placeholder lines.
    """
    return [line for line in text.splitlines() if not is_truncation_placeholder(line)]


def anchor_precheck(concrete_lines_list: list[str], initial_code: str) -> tuple[bool, str | None]:
    """Check if concrete lines can be located in initial_code.

    Three-tier result:
      0 matches            → (False, None)          hard block
      1 ambiguous match    → (True, warning_str)     allow with warning
      1 unique or 2+ match → (True, None)            allow clean

    A match is a stripped, non-trivial line that appears in initial_code.
    A match is 'unique' if it appears exactly once in initial_code.

    Args:
        concrete_lines_list: Non-placeholder lines from the edit snippet.
        initial_code: Original file content.

    Returns:
        (passed, warning) tuple.
    """
    if not concrete_lines_list:
        return False, None

    anchor_lines = [
        line
        for line in concrete_lines_list
        if not any(line.strip().startswith(pat) for pat in _REMOVE_DIRECTIVE_PATTERNS)
    ]

    if not anchor_lines:
        return False, None

    matches: list[str] = []
    unique_count = 0
    initial_lines = [line.strip() for line in initial_code.splitlines()]
    initial_counts = Counter(initial_lines)

    for line in anchor_lines:
        stripped = line.strip()
        if not stripped or _is_trivial_line(stripped):
            continue
        if initial_counts.get(stripped, 0) > 0:
            matches.append(stripped)
            if initial_counts.get(stripped, 0) == 1:
                unique_count += 1

    if not matches:
        return False, None

    if len(matches) >= 2 or unique_count >= 1:
        return True, None

    # Exactly 1 match, and it's ambiguous (appears multiple times)
    return True, (
        "WEAK_ANCHOR: only 1 ambiguous anchor matched; "
        "edit may target the wrong location. Add more unique context lines."
    )


def _is_trivial_line(line: str) -> bool:
    """Determine if line is a non-distinctive short line (syntax keywords/symbols).

    These lines are too common in code and should not be used to determine expected changes.
    """
    trivial_tokens = {
        # Brackets/symbols
        "}",
        "{",
        "]",
        "[",
        ")",
        "(",
        # Python keywords
        "pass",
        "break",
        "continue",
        "return",
        "else:",
        "try:",
        "except:",
        "finally:",
        "raise",
        "yield",
        # JavaScript/TypeScript
        "return;",
        "break;",
        "continue;",
        "default:",
        # Common short statements
        "return null",
        "return null;",
        "return true",
        "return true;",
        "return false",
        "return false;",
    }
    return line in trivial_tokens


def _has_omission_style_deletion(edit_snippet: str, initial_code: str) -> bool:
    """Detect omission-style deletion intent.

    If two concrete lines appear adjacent in edit_snippet (no truncation marker
    between them), but those same lines are not adjacent in the original file
    in at least one occurrence, treat as deletion intent.
    """
    snippet_lines = edit_snippet.splitlines()
    if len(snippet_lines) < 2:
        return False

    initial_lines = [line.strip() for line in initial_code.splitlines()]
    if len(initial_lines) < 2:
        return False

    initial_index: dict[str, list[int]] = {}
    for i, line in enumerate(initial_lines):
        if line:
            initial_index.setdefault(line, []).append(i)

    def is_remove_directive(s: str) -> bool:
        return any(s.startswith(pat) for pat in _REMOVE_DIRECTIVE_PATTERNS)

    MIN_CONTEXT_LINE_LENGTH = 5

    for i in range(len(snippet_lines) - 1):
        a = snippet_lines[i].strip()
        b = snippet_lines[i + 1].strip()
        if not a or not b:
            continue
        if _is_explicit_marker_line(a) or _is_explicit_marker_line(b):
            continue
        if is_remove_directive(a) or is_remove_directive(b):
            continue
        if len(a) < MIN_CONTEXT_LINE_LENGTH or len(b) < MIN_CONTEXT_LINE_LENGTH:
            continue
        if _is_trivial_line(a) or _is_trivial_line(b):
            continue

        a_idx = initial_index.get(a)
        b_idx = initial_index.get(b)
        if not a_idx or not b_idx:
            continue

        b_set = set(b_idx)
        has_adjacent = any((ai + 1) in b_set for ai in a_idx)
        has_gapped = False

        # If any B occurs after A with at least one line gap, it's also deletion intent.
        for ai in a_idx:
            j = bisect_right(b_idx, ai + 1)
            if j < len(b_idx):
                has_gapped = True
                break

        # Be conservative: if the original file already contains an adjacent A/B pair,
        # treat the snippet as potentially idempotent rather than inferred deletion.
        if has_gapped and not has_adjacent:
            return True

    return False


def expects_changes(edit_snippet: str, initial_code: str) -> bool:
    """Determine if edit_snippet is expected to produce changes.

    Used to distinguish between "already identical (idempotent)" and "apply failed (should-have-changed)".

    Args:
        edit_snippet: Edit snippet.
        initial_code: Original file content.

    Returns:
        True if edit is expected to produce changes, False otherwise.
    """
    concrete = concrete_lines(edit_snippet)

    # Check for remove directive
    has_remove_directive = any(
        line.strip().startswith(pat) for line in concrete for pat in _REMOVE_DIRECTIVE_PATTERNS
    )

    if has_remove_directive:
        # Has remove directive but no changes produced, likely apply failure
        return True

    # Build line set from initial_code (using stripped lines)
    # This enables exact line matching rather than substring search
    initial_lines_set = {line.strip() for line in initial_code.splitlines()}

    # Extract "lines not in initial_code" as new_lines_candidates
    # Lower threshold to 5 chars while excluding common syntax keywords/symbols
    MIN_NEW_LINE_LENGTH = 5
    new_lines_candidates = []
    for line in concrete:
        stripped = line.strip()
        # Filter out empty lines and directive lines
        if not stripped or any(stripped.startswith(pat) for pat in _REMOVE_DIRECTIVE_PATTERNS):
            continue
        # Filter out short lines and common syntax keywords
        if len(stripped) < MIN_NEW_LINE_LENGTH:
            continue
        if _is_trivial_line(stripped):
            continue
        # Check if it's a new line (not in original file's line set)
        if stripped not in initial_lines_set:
            new_lines_candidates.append(stripped)

    # If there are new line candidates not in original file, expect changes
    return len(new_lines_candidates) > 0


# EXPERIMENTAL: Post-check related constants
_MIN_NEW_LINE_LENGTH_FOR_CHECK = 15
_MIN_NEW_LINE_PASS_RATIO = 0.6  # Lower threshold to reduce false positives


def extract_remove_targets(edit_snippet: str) -> list[str]:
    """Extract remove directive target identifiers from edit_snippet.

    Supported formats:
    - // remove FunctionName
    - # remove ClassName

    Args:
        edit_snippet: Edit snippet.

    Returns:
        List of identifiers to remove.
    """
    targets = []
    for line in edit_snippet.splitlines():
        stripped = line.strip()
        for pattern in _REMOVE_DIRECTIVE_PATTERNS:
            if stripped.startswith(pattern):
                identifier = stripped[len(pattern) :].strip()
                if identifier:
                    targets.append(identifier)
                break
    return targets


def _extract_new_lines(edit_snippet: str, initial_code: str) -> list[str]:
    """Extract "new lines" from snippet (lines not in initial_code).

    Args:
        edit_snippet: Edit snippet.
        initial_code: Original file content.

    Returns:
        List of new lines (after strip()).
    """
    initial_lines_set = {line.strip() for line in initial_code.splitlines()}
    concrete = concrete_lines(edit_snippet)
    new_lines = []

    for line in concrete:
        stripped = line.strip()
        if not stripped:
            continue
        if any(stripped.startswith(pat) for pat in _REMOVE_DIRECTIVE_PATTERNS):
            continue
        if len(stripped) < _MIN_NEW_LINE_LENGTH_FOR_CHECK:
            continue
        if _is_trivial_line(stripped):
            continue
        if stripped not in initial_lines_set:
            new_lines.append(stripped)

    return new_lines


def post_check_merged_code(
    edit_snippet: str,
    merged_code: str,
    initial_code: str,
) -> tuple[bool, str | None]:
    """Validate that merged_code matches edit_snippet expectations.

    Validation rules:
    1. New line validation: Non-placeholder, non-directive lines with length >= 15,
       if not in initial_code (i.e., newly added), must appear in merged_code.
       At least 80% of new lines must be present (allowing minor reformatting).
    2. Deletion validation: If there's a // remove X or # remove X directive,
       X (identifier) should not appear in merged_code.
    3. Omission-style deletion validation: if adjacent context lines in edit_snippet
       implied deletion against initial_code, the same omission pattern should not
       still be present in merged_code.

    Args:
        edit_snippet: Edit snippet.
        merged_code: Merged code returned by Relace API.
        initial_code: Original file content.

    Returns:
        (passed, failure_reason): failure_reason is None when passed=True.
    """
    # 1. Deletion validation (use word boundary to avoid substring false positives)
    remove_targets = extract_remove_targets(edit_snippet)
    for target in remove_targets:
        # Use word boundary matching to avoid "Function" matching "FunctionName"
        pattern = rf"\b{re.escape(target)}\b"
        if re.search(pattern, merged_code):
            return False, f"Remove target '{target}' still exists in merged code."

    if _has_omission_style_deletion(edit_snippet, initial_code) and _has_omission_style_deletion(
        edit_snippet, merged_code
    ):
        return False, "Omission-style deletion intent was not reflected in merged code."

    # 3. New line validation
    new_lines = _extract_new_lines(edit_snippet, initial_code)
    if new_lines:
        found_count = sum(1 for line in new_lines if line in merged_code)
        pass_ratio = found_count / len(new_lines)
        if pass_ratio < _MIN_NEW_LINE_PASS_RATIO:
            missing = [line for line in new_lines if line not in merged_code]
            missing_preview = missing[0][:50] if missing else ""
            return (
                False,
                f"Only {found_count}/{len(new_lines)} new lines found in merged code. "
                f"Missing: '{missing_preview}...'",
            )

    return True, None


def validate_syntax_delta(
    initial_code: str,
    merged_code: str,
    file_path: str,
) -> tuple[bool, str | None]:
    """Validate merged_code syntax using delta-check strategy.

    Only fails if initial_code was syntactically valid but merged_code
    is corrupted. This prevents false positives when editing files
    that already contain syntax errors.

    Currently supports Python (.py) files only.

    Args:
        initial_code: Original file content.
        merged_code: Merged code from API.
        file_path: File path (used to detect language by extension).

    Returns:
        (passed, failure_reason): failure_reason is None when passed=True.
    """
    ext = os.path.splitext(file_path)[1].lower()
    if ext != ".py":
        return True, None  # Only Python supported for now

    # Check if initial_code already has syntax error
    initial_has_error = False
    try:
        ast.parse(initial_code)
    except SyntaxError:
        initial_has_error = True

    # Check merged_code
    try:
        ast.parse(merged_code)
        return True, None
    except SyntaxError as e:
        if initial_has_error:
            return True, None  # Original was already broken, don't block
        return False, f"SyntaxError at line {e.lineno}: {e.msg}"


def count_effective_diff_lines(diff: str) -> int:
    """Estimate lines touched from a unified diff.

    Returns max(added_lines, deleted_lines) among non-whitespace-only changes.
    This avoids double-counting (add+delete) while correctly handling pure
    deletions, pure additions, and paired replacements.

    Args:
        diff: Unified diff string.

    Returns:
        Approximate number of effective lines touched.
    """
    added, deleted = count_nonempty_diff_lines(diff)
    return max(added, deleted)


def count_nonempty_diff_lines(diff: str) -> tuple[int, int]:
    """Count non-whitespace additions and deletions in a unified diff."""
    added = 0
    deleted = 0
    for line in diff.splitlines():
        if line.startswith("--- ") or line.startswith("+++ ") or line.startswith("@@"):
            continue
        if line.startswith("+"):
            if line[1:].strip():
                added += 1
        elif line.startswith("-"):
            if line[1:].strip():
                deleted += 1
    return added, deleted


def extract_top_level_symbols(code: str, file_path: str) -> list[str]:
    """Extract top-level symbol names from source code.

    For Python files, uses ast.parse to extract function and class names
    (imports are intentionally excluded).
    For other languages, uses regex fallback patterns.
    Returns empty list on parse failure (does not block the pipeline).

    Args:
        code: Source code text.
        file_path: File path (used to detect language by extension).

    Returns:
        Sorted list of unique top-level symbol names.
    """
    ext = os.path.splitext(file_path)[1].lower()

    if ext == ".py":
        return _extract_python_symbols(code)

    return _extract_symbols_regex(code)


def _extract_python_symbols(code: str) -> list[str]:
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return []

    names: set[str] = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
    return sorted(names)


_SYMBOL_PATTERNS = [
    # Python/JS/TS: def, class, function
    re.compile(r"^(?:export\s+)?(?:async\s+)?(?:def|class|function)\s+(\w+)", re.MULTILINE),
    # Go: func (with optional method receiver), type
    re.compile(r"^func\s+(?:\([^)]*\)\s+)?(\w+)", re.MULTILINE),
    re.compile(r"^type\s+(\w+)\s+", re.MULTILINE),
    # Rust: fn, struct, enum, trait, impl (with optional pub)
    re.compile(r"^(?:pub(?:\([^)]*\))?\s+)?(?:fn|struct|enum|trait|impl)\s+(\w+)", re.MULTILINE),
    # JS/TS: const/let/var assignment (arrow functions, object literals)
    re.compile(r"^(?:export\s+)?(?:const|let|var)\s+(\w+)\s*=", re.MULTILINE),
    # TS: interface
    re.compile(r"^(?:export\s+)?interface\s+(\w+)", re.MULTILINE),
]


def _extract_symbols_regex(code: str) -> list[str]:
    names: set[str] = set()
    for pat in _SYMBOL_PATTERNS:
        for m in pat.finditer(code):
            names.add(m.group(1))
    return sorted(names)


def check_symbol_preservation(
    initial_code: str,
    merged_code: str,
    edit_snippet: str,
    file_path: str,
) -> tuple[bool, str | None]:
    """Check that no top-level symbols were accidentally removed by the merge.

    Compares symbols before and after merge. Symbols explicitly targeted
    by remove directives (``// remove X`` / ``# remove X``) are excluded
    from the check.

    Args:
        initial_code: Original file content.
        merged_code: Merged code from API.
        edit_snippet: Edit snippet (checked for remove directives).
        file_path: File path (used to detect language).

    Returns:
        (passed, failure_reason): failure_reason is None when passed=True.
    """
    ext = os.path.splitext(file_path)[1].lower()
    blocking_exts = {".py", ".js", ".jsx", ".ts", ".tsx", ".go", ".rs"}
    if ext not in blocking_exts:
        label = ext or "<none>"
        return True, f"SYMBOL_GUARD_SKIPPED: ext={label}"

    initial_symbols = set(extract_top_level_symbols(initial_code, file_path))
    merged_symbols = set(extract_top_level_symbols(merged_code, file_path))

    if not initial_symbols:
        return True, None  # Cannot extract symbols, skip check

    disappeared = initial_symbols - merged_symbols
    appeared = merged_symbols - initial_symbols

    if not disappeared:
        return True, None

    # Exclude symbols explicitly targeted by remove directives
    remove_targets = set(extract_remove_targets(edit_snippet))
    unexpected = disappeared - remove_targets

    if not unexpected:
        return True, None

    if appeared:
        disappeared_list = ", ".join(sorted(unexpected))
        appeared_list = ", ".join(sorted(appeared))
        return (
            True,
            "SYMBOL_CHANGE_DETECTED: possible rename/move/extract "
            f"(removed: {disappeared_list}; added: {appeared_list})",
        )

    missing_list = ", ".join(sorted(unexpected))
    return False, f"Symbols unexpectedly removed: {missing_list}"
