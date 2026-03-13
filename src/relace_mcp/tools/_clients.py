import threading
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..clients.apply import ApplyLLMClient
    from ..clients.repo import RelaceRepoClient
    from ..clients.search import SearchLLMClient


class ToolClients:
    """Thread-safe lazy initialization of LLM/repo client singletons.

    Clients are constructed on first access and reused across tool calls.
    """

    def __init__(self, config: Any) -> None:
        self._config = config

        self._apply_lock = threading.Lock()
        self._apply_inst: ApplyLLMClient | None = None

        self._search_lock = threading.Lock()
        self._search_inst: SearchLLMClient | None = None

        self._repo_lock = threading.Lock()
        self._repo_inst: RelaceRepoClient | None = None

    def get_apply(self) -> "ApplyLLMClient":
        if self._apply_inst is None:
            with self._apply_lock:
                if self._apply_inst is None:
                    from ..clients.apply import ApplyLLMClient

                    self._apply_inst = ApplyLLMClient(self._config)
        return self._apply_inst

    def get_search(self) -> "SearchLLMClient":
        if self._search_inst is None:
            with self._search_lock:
                if self._search_inst is None:
                    from ..clients.search import SearchLLMClient

                    self._search_inst = SearchLLMClient(self._config)
        return self._search_inst

    def get_repo(self) -> "RelaceRepoClient":
        if self._repo_inst is None:
            with self._repo_lock:
                if self._repo_inst is None:
                    from ..clients.repo import RelaceRepoClient

                    self._repo_inst = RelaceRepoClient(self._config)
        return self._repo_inst
