import os
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import TextIO

from ...config.settings import LOG_DIR

try:
    import fcntl
except ImportError:  # pragma: no cover
    fcntl = None  # type: ignore[assignment]

try:
    import msvcrt
except ImportError:  # pragma: no cover
    msvcrt = None  # type: ignore[assignment]

_LOCK_DIR = LOG_DIR / "index-locks"


@dataclass(slots=True)
class BackendIndexLease:
    backend: str
    base_dir: str
    lock_path: str
    acquired: bool
    reason: str | None = None
    _handle: TextIO | None = None
    _lockless: bool = False

    def release(self) -> None:
        handle = self._handle
        self._handle = None
        if handle is None:
            return
        try:
            _unlock_handle(handle)
        finally:
            handle.close()


@dataclass(frozen=True, slots=True)
class BackendIndexRunResult:
    status: str
    reason: str | None = None
    lock_path: str | None = None


def supports_backend_index_locking() -> bool:
    return fcntl is not None or msvcrt is not None


def try_acquire_backend_index_lock(base_dir: str, backend: str) -> BackendIndexLease:
    lock_path = _build_lock_path(base_dir, backend)

    if not supports_backend_index_locking():
        return BackendIndexLease(
            backend=backend,
            base_dir=base_dir,
            lock_path=lock_path,
            acquired=True,
            reason="locking_unavailable",
            _lockless=True,
        )

    try:
        _LOCK_DIR.mkdir(parents=True, exist_ok=True)
        handle = Path(lock_path).open("a+", encoding="utf-8")
    except OSError as exc:
        return BackendIndexLease(
            backend=backend,
            base_dir=base_dir,
            lock_path=lock_path,
            acquired=False,
            reason=f"lock_error:{exc}",
        )

    try:
        _lock_handle_nonblocking(handle)
    except BlockingIOError:
        handle.close()
        return BackendIndexLease(
            backend=backend,
            base_dir=base_dir,
            lock_path=lock_path,
            acquired=False,
            reason="lock_held",
        )
    except OSError as exc:
        handle.close()
        return BackendIndexLease(
            backend=backend,
            base_dir=base_dir,
            lock_path=lock_path,
            acquired=False,
            reason=f"lock_error:{exc}",
        )

    handle.seek(0)
    handle.truncate()
    handle.write(f"pid={os.getpid()}\nbackend={backend}\nbase_dir={base_dir}\n")
    handle.flush()

    return BackendIndexLease(
        backend=backend,
        base_dir=base_dir,
        lock_path=lock_path,
        acquired=True,
        _handle=handle,
    )


def _build_lock_path(base_dir: str, backend: str) -> str:
    digest = sha256(os.path.realpath(base_dir).encode("utf-8")).hexdigest()[:16]
    return str(_LOCK_DIR / f"{backend}-{digest}.lock")


def _lock_handle_nonblocking(handle: TextIO) -> None:
    if fcntl is not None:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        return

    if msvcrt is None:  # pragma: no cover
        raise OSError("backend index locking is unavailable on this platform")

    handle.seek(0)
    handle.write("\0")
    handle.flush()
    handle.seek(0)
    try:
        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError as exc:
        raise BlockingIOError(str(exc)) from exc


def _unlock_handle(handle: TextIO) -> None:
    if fcntl is not None:
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        return

    if msvcrt is None:  # pragma: no cover
        return

    handle.seek(0)
    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
