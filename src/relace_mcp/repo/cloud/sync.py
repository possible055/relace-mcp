import logging
import uuid
from pathlib import Path
from typing import Any

from ...clients.repo import RelaceRepoClient
from ...config.settings import REPO_SYNC_MAX_FILES
from ..core import (
    SyncState,
    build_cloud_error_details,
    extract_error_fields,
    get_current_git_info,
    get_git_root,
    get_repo_identity,
    load_sync_state,
    log_cloud_event,
    save_sync_state,
)
from ._sync_constants import CODE_EXTENSIONS, SPECIAL_FILENAMES
from ._sync_diff import _compute_diff_operations
from ._sync_discovery import _get_git_tracked_files, _scan_directory
from ._sync_hashing import _compute_file_hashes

logger = logging.getLogger(__name__)


def cloud_sync_logic(
    client: RelaceRepoClient,
    base_dir: str,
    force: bool = False,
    mirror: bool = False,
) -> dict[str, Any]:
    """Synchronize local codebase to Relace Cloud with incremental support.

    Args:
        client: RelaceRepoClient instance.
        base_dir: Base directory to sync.
        force: If True, force full sync ignoring cached state.
        mirror: If True (with force=True), use type="files" to completely
            overwrite cloud repo (removes files not in local).

    Returns:
        Dict containing:
        - repo_id: Repository ID
        - repo_name: Repository name
        - repo_head: New repo head after sync
        - is_incremental: Whether incremental sync was used
        - files_created: Number of new files
        - files_updated: Number of modified files
        - files_deleted: Number of deleted files
        - files_unchanged: Number of unchanged files
        - total_files: Total files in sync
        - local_git_branch: Current git branch name
        - local_git_head: Current git HEAD SHA (first 8 chars)
        - ref_changed: Whether git ref changed since last sync
        - sync_mode: "incremental" | "safe_full" | "mirror_full"
        - deletes_suppressed: Number of delete operations suppressed (safe_full mode)
        - error: Error message if failed (optional)
    """
    trace_id = str(uuid.uuid4())[:8]
    logger.debug("[%s] Starting cloud sync", trace_id)

    original_base_dir = base_dir
    base_dir = str(get_git_root(base_dir))
    if base_dir != original_base_dir:
        logger.debug("[%s] Normalized base_dir to git root", trace_id)

    current_branch, current_head = get_current_git_info(base_dir)
    ref_changed = False
    deletes_suppressed = 0
    local_repo_name, cloud_repo_name, project_fingerprint = get_repo_identity(base_dir)
    if not local_repo_name or not cloud_repo_name:
        result = {
            "trace_id": trace_id,
            "repo_id": None,
            "repo_name": local_repo_name or None,
            "cloud_repo_name": None,
            "repo_head": None,
            "is_incremental": False,
            "files_created": 0,
            "files_updated": 0,
            "files_deleted": 0,
            "files_unchanged": 0,
            "files_skipped": 0,
            "total_files": 0,
            "local_git_branch": current_branch,
            "local_git_head": current_head[:8] if current_head else "",
            "ref_changed": False,
            "sync_mode": "error",
            "deletes_suppressed": 0,
            "error": "Invalid base_dir: cannot derive repository name.",
        }
        log_cloud_event(
            "cloud_sync_error",
            trace_id,
            repo_name=local_repo_name or None,
            cloud_repo_name=None,
            **extract_error_fields(result),
        )
        return result

    log_cloud_event(
        "cloud_sync_start",
        trace_id,
        requested_base_dir=original_base_dir,
        base_dir=base_dir,
        repo_name=local_repo_name,
        cloud_repo_name=cloud_repo_name,
        force=force,
        mirror=mirror,
    )

    try:
        repo_id = client.ensure_repo(cloud_repo_name, trace_id=trace_id)
        logger.debug("[%s] Cloud repo resolved", trace_id)

        cached_state: SyncState | None = None
        if not force:
            cached_state = load_sync_state(base_dir)
            if cached_state and cached_state.repo_id != repo_id:
                logger.warning("[%s] Cached repo_id mismatch, forcing full sync", trace_id)
                cached_state = None

        force_safe_full = False
        diff_state = cached_state
        if cached_state and current_head:
            old_head = cached_state.git_head_sha
            if old_head and old_head != current_head:
                logger.warning(
                    "[%s] Git HEAD changed (%s -> %s), switching to safe full sync",
                    trace_id,
                    old_head[:8],
                    current_head[:8],
                )
                ref_changed = True
                force_safe_full = True

        if mirror and force:
            sync_mode = "mirror_full"
        elif cached_state is None or force_safe_full:
            sync_mode = "safe_full"
        else:
            sync_mode = "incremental"

        logger.debug("[%s] Sync mode: %s", trace_id, sync_mode)
        is_incremental = sync_mode == "incremental"

        files = _get_git_tracked_files(base_dir)
        if files is None:
            logger.debug("[%s] Git not available, using directory scan", trace_id)
            files = _scan_directory(base_dir)
        else:
            files = [
                f
                for f in files
                if Path(f).suffix.lower() in CODE_EXTENSIONS
                or Path(f).name.lower() in SPECIAL_FILENAMES
            ]

        logger.debug("[%s] Found %d files to process", trace_id, len(files))

        files.sort()
        files_found = len(files)
        files_truncated = 0

        if len(files) > REPO_SYNC_MAX_FILES:
            logger.warning(
                "[%s] File count %d exceeds limit %d, truncating",
                trace_id,
                len(files),
                REPO_SYNC_MAX_FILES,
            )
            files_truncated = len(files) - REPO_SYNC_MAX_FILES
            files = files[:REPO_SYNC_MAX_FILES]
        files_selected = len(files)

        logger.debug("[%s] Computing file hashes...", trace_id)
        current_hashes = _compute_file_hashes(base_dir, files)

        operations, new_hashes, new_skipped = _compute_diff_operations(
            base_dir, current_hashes, diff_state
        )

        writes = [op for op in operations if op["type"] == "write"]
        deletes = [op for op in operations if op["type"] == "delete"]

        if sync_mode == "safe_full" and deletes:
            if ref_changed:
                logger.debug(
                    "[%s] Branch switch detected: cleaning %d zombie files from cloud",
                    trace_id,
                    len(deletes),
                )
            else:
                deletes_suppressed = len(deletes)
                logger.warning(
                    "[%s] Safe full sync: suppressing %d delete operations",
                    trace_id,
                    deletes_suppressed,
                )
                operations = [op for op in operations if op["type"] != "delete"]
                deletes = []

        cached_files = cached_state.files if cached_state else {}
        files_created = sum(1 for op in writes if op["filename"] not in cached_files)
        files_updated = sum(1 for op in writes if op["filename"] in cached_files)
        files_deleted = len(deletes)
        files_skipped = len(new_skipped)
        files_unchanged = len(new_hashes) - len(writes) - files_skipped

        logger.debug(
            "[%s] Diff computed: %d created, %d updated, %d deleted, %d unchanged, %d skipped",
            trace_id,
            files_created,
            files_updated,
            files_deleted,
            files_unchanged,
            files_skipped,
        )

        repo_head = ""
        if sync_mode == "mirror_full":
            logger.debug("[%s] Mirror full sync: uploading %d files...", trace_id, len(writes))
            file_contents = [
                {"filename": op["filename"], "content": op["content"]} for op in writes
            ]
            result = client.update_repo_files(repo_id, file_contents, trace_id=trace_id)
            repo_head = str(result.get("repo_head", ""))
            if not file_contents:
                logger.warning(
                    "[%s] Mirror sync with empty file list - cloud repo cleared", trace_id
                )
            logger.debug(
                "[%s] Mirror sync completed, new head=%s",
                trace_id,
                repo_head[:8] if repo_head else "none",
            )
        elif operations:
            logger.debug("[%s] Applying %d operations via update API...", trace_id, len(operations))
            result = client.update_repo(repo_id, operations, trace_id=trace_id)
            repo_head = str(result.get("repo_head", ""))
            logger.debug(
                "[%s] Update completed, new head=%s",
                trace_id,
                repo_head[:8] if repo_head else "none",
            )
        else:
            logger.debug("[%s] No changes detected, skipping update", trace_id)
            repo_head = cached_state.repo_head if cached_state else ""

        new_state = SyncState(
            repo_id=repo_id,
            repo_head=repo_head,
            last_sync="",
            repo_name=local_repo_name,
            cloud_repo_name=cloud_repo_name,
            project_fingerprint=project_fingerprint,
            git_branch=current_branch,
            git_head_sha=current_head,
            files=new_hashes,
            skipped_files=new_skipped,
            files_found=files_found,
            files_selected=files_selected,
            file_limit=REPO_SYNC_MAX_FILES,
            files_truncated=files_truncated,
        )
        state_saved = save_sync_state(base_dir, new_state)

        warnings_list: list[str] = []
        if base_dir != original_base_dir:
            warnings_list.append(
                f"Normalized base_dir to git root: {original_base_dir} -> {base_dir}."
            )
        if files_truncated:
            warnings_list.append(
                f"File count {files_found} exceeded limit {REPO_SYNC_MAX_FILES}; synced first {files_selected} files only."
            )
        if files_skipped:
            warnings_list.append(
                f"Skipped {files_skipped} files (binary/oversize/unreadable); cloud search may miss those files."
            )
        if deletes_suppressed:
            warnings_list.append(
                f"Suppressed {deletes_suppressed} delete operations (safe_full); cloud repo may contain stale files."
            )
        if not state_saved:
            warnings_list.append(
                "Failed to save local sync state; next cloud_search may fail until re-sync."
            )

        result_payload = {
            "trace_id": trace_id,
            "repo_id": repo_id,
            "repo_name": local_repo_name,
            "cloud_repo_name": cloud_repo_name,
            "repo_head": repo_head,
            "is_incremental": is_incremental,
            "files_created": files_created,
            "files_updated": files_updated,
            "files_deleted": files_deleted,
            "files_unchanged": files_unchanged,
            "files_skipped": files_skipped,
            "total_files": len(new_hashes),
            "files_found": files_found,
            "files_selected": files_selected,
            "file_limit": REPO_SYNC_MAX_FILES,
            "files_truncated": files_truncated,
            "local_git_branch": current_branch,
            "local_git_head": current_head[:8] if current_head else "",
            "ref_changed": ref_changed,
            "sync_mode": sync_mode,
            "deletes_suppressed": deletes_suppressed,
            "state_saved": state_saved,
            "warnings": warnings_list,
        }
        log_cloud_event(
            "cloud_sync_complete",
            trace_id,
            repo_id=result_payload.get("repo_id"),
            repo_name=result_payload.get("repo_name"),
            cloud_repo_name=result_payload.get("cloud_repo_name"),
            repo_head=result_payload.get("repo_head"),
            sync_mode=result_payload.get("sync_mode"),
            is_incremental=result_payload.get("is_incremental"),
            files_created=result_payload.get("files_created"),
            files_updated=result_payload.get("files_updated"),
            files_deleted=result_payload.get("files_deleted"),
            files_unchanged=result_payload.get("files_unchanged"),
            files_skipped=result_payload.get("files_skipped"),
            files_found=result_payload.get("files_found"),
            files_selected=result_payload.get("files_selected"),
            files_truncated=result_payload.get("files_truncated"),
            warnings_count=len(warnings_list),
        )
        return result_payload

    except Exception as exc:
        logger.error("[%s] Cloud sync failed: %s", trace_id, exc)
        result = {
            "trace_id": trace_id,
            "repo_id": None,
            "repo_name": local_repo_name,
            "cloud_repo_name": cloud_repo_name,
            "repo_head": None,
            "is_incremental": False,
            "files_created": 0,
            "files_updated": 0,
            "files_deleted": 0,
            "files_unchanged": 0,
            "files_skipped": 0,
            "total_files": 0,
            "local_git_branch": current_branch,
            "local_git_head": current_head[:8] if current_head else "",
            "ref_changed": ref_changed,
            "sync_mode": "error",
            "deletes_suppressed": 0,
            "error": str(exc),
            **build_cloud_error_details(exc),
        }
        log_cloud_event(
            "cloud_sync_error",
            trace_id,
            repo_name=local_repo_name,
            cloud_repo_name=cloud_repo_name,
            **extract_error_fields(result),
        )
        return result
