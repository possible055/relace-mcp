import difflib
import json
import logging
import os
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastmcp import FastMCP

from .config import LOG_PATH, MAX_LOG_SIZE_BYTES, RelaceConfig
from .relace_client import RelaceClient

logger = logging.getLogger(__name__)

# 限制檔案大小為 10MB，避免記憶體耗盡
MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024


def _rotate_log_if_needed() -> None:
    """若 log 檔案超過大小上限，進行 rotation。"""
    try:
        if LOG_PATH.exists() and LOG_PATH.stat().st_size > MAX_LOG_SIZE_BYTES:
            rotated_path = LOG_PATH.with_suffix(
                f".{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}.log"
            )
            LOG_PATH.rename(rotated_path)
            logger.info("Rotated log file to %s", rotated_path)
    except Exception as exc:
        logger.warning("Failed to rotate log file: %s", exc)


def _log_event(event: dict[str, Any]) -> None:
    """將單筆 JSON event 寫入本地 log，失敗時不影響主流程。"""
    try:
        if "timestamp" not in event:
            event["timestamp"] = datetime.now(UTC).isoformat()
        if "trace_id" not in event:
            event["trace_id"] = str(uuid.uuid4())[:8]
        if "level" not in event:
            event["level"] = "info" if event.get("kind", "").endswith("success") else "error"

        if LOG_PATH.is_dir():
            logger.warning("Log path is a directory, skipping log write: %s", LOG_PATH)
            return
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

        _rotate_log_if_needed()

        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")
    except Exception as exc:
        logger.warning("Failed to write Relace log: %s", exc)


def _validate_file_path(file_path: str, base_dir: str) -> Path:
    """驗證並解析檔案路徑，防止路徑遍歷攻擊。

    Args:
        file_path: 要驗證的檔案路徑。
        base_dir: 基礎目錄，限制存取範圍。

    Returns:
        解析後的 Path 物件。

    Raises:
        RuntimeError: 若路徑無效或超出允許範圍。
    """
    if not file_path or not file_path.strip():
        raise RuntimeError("file_path cannot be empty")

    try:
        resolved = Path(file_path).resolve()
    except (OSError, ValueError) as exc:
        raise RuntimeError(f"Invalid file path: {file_path}") from exc

    # 確保檔案在 base_dir 中
    base_resolved = Path(base_dir).resolve()
    try:
        resolved.relative_to(base_resolved)
    except ValueError as exc:
        raise RuntimeError(
            f"Access denied: {file_path} is outside allowed directory {base_dir}"
        ) from exc

    return resolved


def _apply_file_logic(
    client: RelaceClient,
    file_path: str,
    edit_snippet: str,
    instruction: str | None,
    base_dir: str,
) -> str:
    """Core logic for fast_apply (testable independently).

    Args:
        client: Relace API client.
        file_path: Target file path.
        edit_snippet: Code snippet to apply, using abbreviation comments.
        instruction: Optional natural language instruction.
        base_dir: Base directory restriction.

    Returns:
        A message with UDiff showing changes made.
    """
    started_at = datetime.now(UTC)
    trace_id = str(uuid.uuid4())[:8]

    if not edit_snippet or not edit_snippet.strip():
        raise RuntimeError("edit_snippet cannot be empty")

    try:
        resolved_path = _validate_file_path(file_path, base_dir)

        # New file: write directly without calling API
        if not resolved_path.exists():
            resolved_path.parent.mkdir(parents=True, exist_ok=True)
            resolved_path.write_text(edit_snippet, encoding="utf-8")

            _log_event(
                {
                    "kind": "create_success",
                    "level": "info",
                    "trace_id": trace_id,
                    "file_path": str(resolved_path),
                    "file_size_bytes": resolved_path.stat().st_size,
                }
            )
            logger.info("[%s] Created new file %s", trace_id, resolved_path)
            return f"Created {resolved_path} ({resolved_path.stat().st_size} bytes)"

        # Existing file: check size and read
        file_size = resolved_path.stat().st_size
        if file_size > MAX_FILE_SIZE_BYTES:
            raise RuntimeError(
                f"File too large ({file_size} bytes). Maximum allowed: {MAX_FILE_SIZE_BYTES} bytes"
            )

        try:
            initial_code = resolved_path.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise RuntimeError(
                f"File is not valid UTF-8 encoding: {file_path}. "
                "Only UTF-8 encoded text files are supported."
            ) from exc

        # Call Relace API
        relace_metadata = {
            "source": "fastmcp",
            "tool": "fast_apply",
            "file_path": str(resolved_path),
            "trace_id": trace_id,
        }

        result = client.apply(
            initial_code=initial_code,
            edit_snippet=edit_snippet,
            instruction=instruction,
            relace_metadata=relace_metadata,
            stream=False,
        )

        merged_code = result.get("mergedCode")
        usage = result.get("usage", {})

        if not isinstance(merged_code, str):
            raise RuntimeError("Relace API did not return 'mergedCode'")

        # Generate UDiff for agent verification
        diff = "".join(
            difflib.unified_diff(
                initial_code.splitlines(keepends=True),
                merged_code.splitlines(keepends=True),
                fromfile="before",
                tofile="after",
            )
        )

        latency_ms = int((datetime.now(UTC) - started_at).total_seconds() * 1000)

        # No changes detected
        if not diff:
            logger.info("[%s] No changes made to %s", trace_id, resolved_path)
            return "No changes made"

        # Write merged code
        if not os.access(resolved_path, os.W_OK):
            raise RuntimeError(f"File is not writable: {file_path}")

        resolved_path.write_text(merged_code, encoding="utf-8")

        _log_event(
            {
                "kind": "apply_success",
                "level": "info",
                "trace_id": trace_id,
                "started_at": started_at.isoformat(),
                "latency_ms": latency_ms,
                "file_path": str(resolved_path),
                "file_size_bytes": file_size,
                "instruction": instruction,
                "edit_snippet_preview": edit_snippet[:200],
                "usage": usage,
            }
        )
        logger.info(
            "[%s] Applied Relace edit to %s (latency=%dms)",
            trace_id,
            resolved_path,
            latency_ms,
        )

        return f"Applied code changes using Relace API.\n\nChanges made:\n{diff}"

    except Exception as exc:
        latency_ms = int((datetime.now(UTC) - started_at).total_seconds() * 1000)
        _log_event(
            {
                "kind": "apply_error",
                "level": "error",
                "trace_id": trace_id,
                "started_at": started_at.isoformat(),
                "latency_ms": latency_ms,
                "file_path": file_path,
                "instruction": instruction,
                "edit_snippet_preview": (edit_snippet or "")[:200],
                "error": str(exc),
            }
        )
        logger.error("[%s] Relace apply failed for %s: %s", trace_id, file_path, exc)
        raise


def register_tools(mcp: FastMCP, config: RelaceConfig) -> None:
    """Register Relace tools to the FastMCP instance."""
    client = RelaceClient(config)

    @mcp.tool
    def fast_apply(
        file_path: str,
        edit_snippet: str,
        instruction: str | None = None,
    ) -> str:
        """Use this tool to propose an edit to an existing file or create a new file.

        If you are performing an edit follow these formatting rules:
        - Abbreviate sections of the code in your response that will remain the same
          by replacing those sections with a comment like "// ... rest of code ...",
          "// ... keep existing code ...", "// ... code remains the same".
        - Be precise with the location of these comments within your edit snippet.
          A less intelligent model will use the context clues you provide to accurately
          merge your edit snippet.
        - If applicable, it can help to include some concise information about the
          specific code segments you wish to retain "// ... keep calculateTotalFunction ...".
        - If you plan on deleting a section, you must provide the context to delete it.
          Some options:
          1. If the initial code is `Block 1 / Block 2 / Block 3`, and you want to remove
             Block 2, you would output `// ... keep existing code ... / Block 1 / Block 3 /
             // ... rest of code ...`.
          2. If the initial code is `code / Block / code`, and you want to remove Block,
             you can also specify `// ... keep existing code ... / // remove Block /
             // ... rest of code ...`.
        - You must use the comment format applicable to the specific code provided to
          express these truncations.
        - Preserve the indentation and code structure of exactly how you believe the
          final code will look (do not output lines that will not be in the final code
          after they are merged).
        - Be as length efficient as possible without omitting key context.

        To create a new file, simply specify the content of the file in the `edit_snippet` field.

        Args:
            file_path: The target file to modify. You must use an absolute path (UTF-8).
            edit_snippet: Only include the exact code lines that need modification.
                Do not include any code that stays the same - those sections should be
                marked with comments appropriate for the language, like:
                `// ... existing code ...`
            instruction: A single sentence instruction describing the edit to be made.
                This helps guide the apply model in merging the changes correctly.
                Use first person perspective and focus on clarifying any ambiguous
                aspects of the edit. Keep it brief and avoid repeating information
                from previous messages.
        """
        return _apply_file_logic(
            client=client,
            file_path=file_path,
            edit_snippet=edit_snippet,
            instruction=instruction,
            base_dir=config.base_dir,
        )

    _ = fast_apply
