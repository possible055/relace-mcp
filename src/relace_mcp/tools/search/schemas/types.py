from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class GrepSearchParams:
    """Encapsulates grep_search tool parameters."""

    query: str
    case_sensitive: bool
    include_pattern: str | None
    exclude_pattern: str | None
    base_dir: str
