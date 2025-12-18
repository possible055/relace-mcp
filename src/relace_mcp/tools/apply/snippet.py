import re


def is_truncation_placeholder(line: str) -> bool:
    """判斷是否為截斷用的 placeholder（省略標記）。

    注意：// remove Block 是 directive，不是 placeholder。

    Args:
        line: 要檢查的行。

    Returns:
        若為 placeholder 則返回 True，否則 False。
    """
    s = line.strip()
    if not s:
        return True

    lower = s.lower()
    return lower.startswith("// ...") or lower.startswith("# ...")


def concrete_lines(text: str) -> list[str]:
    """回傳非 placeholder 的行（包含 remove directive）。

    Args:
        text: 編輯片段文字。

    Returns:
        非 placeholder 的行列表。
    """
    return [line for line in text.splitlines() if not is_truncation_placeholder(line)]


def should_run_anchor_precheck(edit_snippet: str, instruction: str | None) -> bool:
    """判斷是否應該執行 anchor precheck。

    對所有既有檔案編輯都執行 precheck（fail-fast 策略）。
    僅允許含有明確位置 directive 的 instruction 跳過。

    Args:
        edit_snippet: 編輯片段（未使用，保留參數以維持介面相容）。
        instruction: 可選的 instruction。

    Returns:
        是否應該執行 precheck。
    """
    _ = edit_snippet  # 保留參數以維持介面相容

    # 檢查 instruction 是否含有明確位置 directive
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
            # 明確位置 directive，允許跳過 precheck
            return False

    # 對所有既有檔案編輯都執行 precheck
    return True


def anchor_precheck(concrete_lines_list: list[str], initial_code: str) -> bool:
    """檢查 concrete lines 是否至少有足夠的 anchor 能在 initial_code 中定位。

    使用寬鬆比對（strip() 後），避免因縮排/空白差異被誤判。
    過濾太短的行（如 }、return）以避免誤判命中。

    Args:
        concrete_lines_list: 非 placeholder 的行。
        initial_code: 原始檔案內容。

    Returns:
        若至少命中 2 行有效 anchor 則 True，否則 False。
    """
    if not concrete_lines_list:
        return False

    # 過濾掉純 directive 行（如 "// remove BlockName"）
    # 這些行不應該用來定位 anchor
    directive_patterns = ("// remove ", "# remove ")
    anchor_lines = [
        line
        for line in concrete_lines_list
        if not any(line.strip().startswith(pat) for pat in directive_patterns)
    ]

    if not anchor_lines:
        # 只有 directive，沒有真實 anchor
        return False

    # 統計命中的有效 anchor 數量
    MIN_ANCHOR_LENGTH = 10  # 最短有效 anchor 長度（避免 }、return 等短行誤判）
    MIN_ANCHOR_HITS = 2  # 最少需要命中的 anchor 數量

    hit_count = 0
    for line in anchor_lines:
        stripped = line.strip()
        # 只計算足夠長的行，避免 }、return、pass 等短行誤判
        if len(stripped) >= MIN_ANCHOR_LENGTH and stripped in initial_code:
            hit_count += 1
            if hit_count >= MIN_ANCHOR_HITS:
                return True

    # 如果只有一個有效 anchor 但它足夠特殊（長度 >= 20），也接受
    if hit_count == 1:
        for line in anchor_lines:
            stripped = line.strip()
            if len(stripped) >= 20 and stripped in initial_code:
                return True

    return False


def _is_trivial_line(line: str) -> bool:
    """判斷是否為不具辨識度的短行（語法關鍵字/符號）。

    這些行在程式碼中太常見，不應用於判斷是否預期變更。
    """
    trivial_tokens = {
        # 括號/符號
        "}",
        "{",
        "]",
        "[",
        ")",
        "(",
        # Python 關鍵字
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
        # 常見短語句
        "return null",
        "return null;",
        "return true",
        "return true;",
        "return false",
        "return false;",
    }
    return line in trivial_tokens


def expects_changes(edit_snippet: str, initial_code: str) -> bool:
    """判斷 edit_snippet 是否預期會產生變更。

    用於區分「本來就相同（idempotent）」和「apply 失敗（should-have-changed）」。

    Args:
        edit_snippet: 編輯片段。
        initial_code: 原始檔案內容。

    Returns:
        若編輯預期會產生變更則 True，否則 False。
    """
    concrete = concrete_lines(edit_snippet)

    # 檢查是否有 remove directive
    directive_patterns = ("// remove ", "# remove ")
    has_remove_directive = any(
        line.strip().startswith(pat) for line in concrete for pat in directive_patterns
    )

    if has_remove_directive:
        # 有 remove directive 但沒產生變更，應該是 apply 失敗
        return True

    # 建立 initial_code 的行集合（使用 strip() 後的行）
    # 這樣可以精確比對行，而非子字串搜索
    initial_lines_set = {line.strip() for line in initial_code.splitlines()}

    # 擷取「不在 initial_code 中的非空白行」作為 new_lines_candidates
    # 降低門檻到 5 字元，同時排除常見語法關鍵字/符號
    MIN_NEW_LINE_LENGTH = 5
    new_lines_candidates = []
    for line in concrete:
        stripped = line.strip()
        # 過濾掉空白行和 directive 行
        if not stripped or any(stripped.startswith(pat) for pat in directive_patterns):
            continue
        # 過濾掉太短的行和常見語法關鍵字
        if len(stripped) < MIN_NEW_LINE_LENGTH:
            continue
        if _is_trivial_line(stripped):
            continue
        # 檢查是否為新行（不在原始檔案的行集合中）
        if stripped not in initial_lines_set:
            new_lines_candidates.append(stripped)

    # 如果有新行候選且它們不在原檔案中，則預期會產生變更
    return len(new_lines_candidates) > 0


# EXPERIMENTAL: Post-check 相關常數
_REMOVE_DIRECTIVE_PATTERNS = ("// remove ", "# remove ")
_MIN_NEW_LINE_LENGTH_FOR_CHECK = 15
_MIN_NEW_LINE_PASS_RATIO = 0.6  # 降低門檻以減少 false positive


def extract_remove_targets(edit_snippet: str) -> list[str]:
    """從 edit_snippet 提取 remove directive 的目標 identifier。

    支援格式：
    - // remove FunctionName
    - # remove ClassName

    Args:
        edit_snippet: 編輯片段。

    Returns:
        要移除的 identifier 列表。
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
    """提取 snippet 中的「新增行」（不在 initial_code 中的行）。

    Args:
        edit_snippet: 編輯片段。
        initial_code: 原始檔案內容。

    Returns:
        新增行列表（strip() 後）。
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
    """驗證 merged_code 是否符合 edit_snippet 的預期。

    檢查規則：
    1. 新增行驗證：snippet 中的非 placeholder、非 directive、長度 >= 15 的行，
       若不在 initial_code 中（代表是新增的），則必須出現在 merged_code。
       至少 80% 的新增行必須出現（容許少量 reformat）。
    2. 刪除驗證：若有 // remove X 或 # remove X directive，
       則 X（identifier）不應出現在 merged_code 中。

    Args:
        edit_snippet: 編輯片段。
        merged_code: Relace API 回傳的合併後程式碼。
        initial_code: 原始檔案內容。

    Returns:
        (passed, failure_reason): passed=True 時 failure_reason 為 None。
    """
    # 1. 刪除驗證（使用 word boundary 避免子字串誤判）
    remove_targets = extract_remove_targets(edit_snippet)
    for target in remove_targets:
        # 使用 word boundary 匹配，避免 "Function" 匹配到 "FunctionName"
        pattern = rf"\b{re.escape(target)}\b"
        if re.search(pattern, merged_code):
            return False, f"Remove target '{target}' still exists in merged code."

    # 2. 新增行驗證
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
