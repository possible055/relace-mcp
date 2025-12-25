from .apply import ApplyLLMClient, ApplyRequest, ApplyResponse
from .exceptions import RelaceAPIError, RelaceNetworkError, RelaceTimeoutError
from .repo import RelaceRepoClient
from .search import SearchLLMClient

# Backward-compatible aliases (deprecated, will be removed in a future version)
RelaceApplyClient = ApplyLLMClient
RelaceSearchClient = SearchLLMClient

__all__ = [
    # New names
    "ApplyLLMClient",
    "SearchLLMClient",
    # Data classes
    "ApplyRequest",
    "ApplyResponse",
    # Relace-only client (cloud features)
    "RelaceRepoClient",
    # Exceptions
    "RelaceAPIError",
    "RelaceNetworkError",
    "RelaceTimeoutError",
    # Deprecated aliases (backward compatibility)
    "RelaceApplyClient",
    "RelaceSearchClient",
]
