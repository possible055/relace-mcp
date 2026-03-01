import atexit
import os
import threading
from collections.abc import Generator
from contextlib import contextmanager
from typing import TYPE_CHECKING

from relace_mcp.lsp.languages.base import LanguageServerConfig
from relace_mcp.lsp.logging import log_lsp_client_created, log_lsp_client_evicted

if TYPE_CHECKING:
    from relace_mcp.lsp.client import LSPClient


def _parse_nonnegative_int_env(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    if value < 0:
        return default
    return value


class LSPClientManager:
    """Process-scoped singleton manager for LSP clients.

    Thread-safe: Uses RLock to protect all operations.
    """

    _instance: "LSPClientManager | None" = None
    _class_lock = threading.Lock()

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._clients: dict[tuple[str, str], LSPClient] = {}
        self._lease_counts: dict[tuple[str, str], int] = {}
        self._max_clients = _parse_nonnegative_int_env("SEARCH_LSP_MAX_CLIENTS", 2)
        atexit.register(self._cleanup_all)

    @classmethod
    def get_instance(cls) -> "LSPClientManager":
        """Get or create the singleton instance."""
        if cls._instance is None:
            with cls._class_lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def _new_client(
        self,
        config: LanguageServerConfig,
        workspace: str,
        timeout_seconds: float | None,
    ) -> "LSPClient":
        from relace_mcp.lsp.client import LSPClient

        return LSPClient(config, workspace, timeout_seconds=timeout_seconds)

    def _cleanup_all(self) -> None:
        """Cleanup all clients."""
        with self._lock:
            for client in list(self._clients.values()):
                try:
                    client.shutdown()
                except Exception:  # nosec B110 - best-effort cleanup
                    pass
            self._clients.clear()
            self._lease_counts.clear()

    def _pop_oldest_idle_client_locked(self) -> tuple[tuple[str, str], "LSPClient"] | None:
        for key in list(self._clients.keys()):
            if self._lease_counts.get(key, 0) != 0:
                continue
            client = self._clients.pop(key)
            self._lease_counts.pop(key, None)
            return (key, client)
        return None

    def _get_or_create_client_locked(
        self,
        config: LanguageServerConfig,
        workspace: str,
        *,
        timeout_seconds: float | None,
        lease: bool,
    ) -> tuple["LSPClient", list[tuple[tuple[str, str], "LSPClient"]]]:
        key = (workspace, config.language_id)
        existing = self._clients.get(key)
        if existing is not None:
            self._clients.pop(key, None)
            self._clients[key] = existing
            if lease:
                self._lease_counts[key] = self._lease_counts.get(key, 0) + 1
            else:
                self._lease_counts.setdefault(key, 0)
            return (existing, [])

        evicted: list[tuple[tuple[str, str], LSPClient]] = []
        if self._max_clients > 0:
            while len(self._clients) >= self._max_clients:
                popped = self._pop_oldest_idle_client_locked()
                if popped is None:
                    break
                evicted.append(popped)

        client = self._new_client(config, workspace, timeout_seconds)
        try:
            client.start()
        except Exception:
            for evicted_key, c in evicted:
                self._clients[evicted_key] = c
                self._lease_counts.setdefault(evicted_key, 0)
            raise

        # Log eviction only after successful start — if start() fails above,
        # evicted clients are restored and no misleading events are emitted.
        for evicted_key, _ in evicted:
            log_lsp_client_evicted(evicted_key[1], evicted_key[0], len(self._clients), "pool_full")

        self._clients[key] = client
        self._lease_counts[key] = 1 if lease else 0
        log_lsp_client_created(config.language_id, workspace, len(self._clients))
        return (client, evicted)

    @contextmanager
    def session(
        self,
        config: LanguageServerConfig,
        workspace: str,
        *,
        timeout_seconds: float | None = None,
    ) -> "Generator[LSPClient, None, None]":
        """Acquire a leased LSP client for a workspace."""
        clients_to_shutdown: list[LSPClient] = []
        key = (workspace, config.language_id)
        with self._lock:
            client, evicted = self._get_or_create_client_locked(
                config,
                workspace,
                timeout_seconds=timeout_seconds,
                lease=True,
            )
            clients_to_shutdown = [c for _, c in evicted]

        for old_client in clients_to_shutdown:
            try:
                old_client.shutdown()
            except Exception:  # nosec B110 - best-effort cleanup
                pass

        try:
            yield client
        finally:
            evicted_in_finally: list[tuple[tuple[str, str], LSPClient]] = []
            with self._lock:
                self._lease_counts[key] = max(0, self._lease_counts.get(key, 0) - 1)
                if self._max_clients > 0:
                    while len(self._clients) > self._max_clients:
                        popped = self._pop_oldest_idle_client_locked()
                        if popped is None:
                            break
                        log_lsp_client_evicted(
                            popped[0][1], popped[0][0], len(self._clients), "pool_full"
                        )
                        evicted_in_finally.append(popped)

            for _, old_client in evicted_in_finally:
                try:
                    old_client.shutdown()
                except Exception:  # nosec B110 - best-effort cleanup
                    pass

    def get_client(
        self,
        config: LanguageServerConfig,
        workspace: str,
        *,
        timeout_seconds: float | None = None,
    ) -> "LSPClient":
        """Get or create a client for the given workspace."""
        clients_to_shutdown: list[LSPClient] = []
        client_to_return: LSPClient

        with self._lock:
            client, evicted = self._get_or_create_client_locked(
                config,
                workspace,
                timeout_seconds=timeout_seconds,
                lease=False,
            )
            client_to_return = client
            clients_to_shutdown = [c for _, c in evicted]

        for old_client in clients_to_shutdown:
            try:
                old_client.shutdown()
            except Exception:  # nosec B110 - best-effort cleanup
                pass

        return client_to_return


__all__ = ["LSPClientManager"]
