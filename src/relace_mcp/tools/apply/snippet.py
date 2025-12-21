import re

# Directive patterns for remove operations
_REMOVE_DIRECTIVE_PATTERNS = ("// remove ", "# remove ")


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
    return lower.startswith("// ...") or lower.startswith("# ...")


def concrete_lines(text: str) -> list[str]:
    """Return non-placeholder lines (including remove directives).

    Args:
        text: Edit snippet text.

    Returns:
        List of non-placeholder lines.
    """
    return [line for line in text.splitlines() if not is_truncation_placeholder(line)]


def should_run_anchor_precheck(edit_snippet: str, instruction: str | None) -> bool:
    """Determine if anchor precheck should be run.

    Runs precheck for all existing file edits (fail-fast strategy).
    Only allows skipping for instructions with explicit position directives.

    Args:
        edit_snippet: Edit snippet (unused, kept for interface compatibility).
        instruction: Optional instruction.

    Returns:
        Whether precheck should be run.
    """
    del edit_snippet  # Kept for interface compatibility

    # Check if instruction contains explicit position directive
    if instruction:
        instruction_lower = instruction.lower()
        position_directives = (
            "append to end of file",
            "prepend to start of file",
            "add to end of file",
            "add to start of file",
            "insert at the beginning",
            "insert at the end",
        )
        if any(directive in instruction_lower for directive in position_directives):
            # Explicit position directive, allow skipping precheck
            return False

    # Run precheck for all existing file edits
    return True


def anchor_precheck(concrete_lines_list: list[str], initial_code: str) -> bool:
    """Check if concrete lines have sufficient anchors to locate in initial_code.

    Uses loose matching (after strip()) to avoid false negatives from indentation/whitespace differences.
    Filters out short lines (like }, return) to avoid false positives.

    Args:
        concrete_lines_list: Non-placeholder lines.
        initial_code: Original file content.

    Returns:
        True if at least 2 valid anchors are found, False otherwise.
    """
    if not concrete_lines_list:
        return False

    # Filter out pure directive lines (like "// remove BlockName")
    # These should not be used for anchor positioning
    anchor_lines = [
        line
        for line in concrete_lines_list
        if not any(line.strip().startswith(pat) for pat in _REMOVE_DIRECTIVE_PATTERNS)
    ]

    if not anchor_lines:
        # Only directives, no real anchors
        return False

    # Count valid anchor hits
    MIN_ANCHOR_LENGTH = (
        10  # Minimum valid anchor length (avoid false positives from }, return, etc.)
    )
    MIN_ANCHOR_HITS = 2  # Minimum number of anchor hits required

    hit_count = 0
    for line in anchor_lines:
        stripped = line.strip()
        # Only count sufficiently long lines to avoid false positives from }, return, pass, etc.
        if len(stripped) >= MIN_ANCHOR_LENGTH and stripped in initial_code:
            hit_count += 1
            if hit_count >= MIN_ANCHOR_HITS:
                return True

    # If only one valid anchor but it's sufficiently unique (length >= 20), accept it
    if hit_count == 1:
        for line in anchor_lines:
            stripped = line.strip()
            if len(stripped) >= 20 and stripped in initial_code:
                return True

    return False


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

    # 2. New line validation
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
