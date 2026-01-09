import re
from dataclasses import dataclass
from enum import Enum


class QueryType(str, Enum):
    BUG_FIX = "bug_fix"
    FEATURE = "feature"
    REFACTOR = "refactor"
    PERFORMANCE = "performance"
    CONFIG = "config"
    DOC = "documentation"
    TEST = "test"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class _Pattern:
    query_type: QueryType
    patterns: tuple[str, ...]
    weight: float = 1.0


_CLASSIFICATION_RULES: list[_Pattern] = [
    # Bug fix patterns
    _Pattern(
        QueryType.BUG_FIX,
        (
            r"\b(bug|fix|error|exception|crash|fail|broken|issue|problem)\b",
            r"\b(traceback|stacktrace|typeerror|valueerror|keyerror|attributeerror)\b",
            r"\b(doesn'?t work|not working|wrong|incorrect|unexpected)\b",
            r"\b(regression|hotfix)\b",
        ),
        weight=1.5,
    ),
    # Feature patterns
    _Pattern(
        QueryType.FEATURE,
        (
            r"\b(add|implement|create|support|enable|allow|introduce)\b",
            r"\b(feature|enhancement|new|capability)\b",
            r"\b(want|need|should|could|would like)\b",
        ),
        weight=1.0,
    ),
    # Refactor patterns
    _Pattern(
        QueryType.REFACTOR,
        (
            r"\b(refactor|restructure|reorganize|clean\s*up|simplify)\b",
            r"\b(extract|rename|move|split|merge|consolidate)\b",
            r"\b(deprecate|remove|delete)\b",
        ),
        weight=1.2,
    ),
    # Performance patterns
    _Pattern(
        QueryType.PERFORMANCE,
        (
            r"\b(performance|optimize|speed|fast|slow|efficient|memory)\b",
            r"\b(bottleneck|latency|throughput|cache|parallel)\b",
            r"\b(profile|benchmark)\b",
        ),
        weight=1.3,
    ),
    # Config patterns
    _Pattern(
        QueryType.CONFIG,
        (
            r"\b(config|configuration|setting|option|parameter|environment)\b",
            r"\b(\.env|\.yaml|\.json|\.toml|\.ini)\b",
            r"\b(default|override|customize)\b",
        ),
        weight=1.0,
    ),
    # Documentation patterns
    _Pattern(
        QueryType.DOC,
        (
            r"\b(doc|documentation|readme|docstring|comment)\b",
            r"\b(explain|describe|clarify|document)\b",
            r"\b(usage|example|tutorial|guide)\b",
        ),
        weight=0.8,
    ),
    # Test patterns
    _Pattern(
        QueryType.TEST,
        (
            r"\b(tests?|unittest|pytest|spec|coverage)\b",
            r"\bunit\s+tests?\b",
            r"\b(mock|fixture|assertion|expect)\b",
            r"\b(ci|continuous integration)\b",
        ),
        weight=1.0,
    ),
]


def classify_query(query: str) -> QueryType:
    """Classify a query into one of the predefined types.

    Uses pattern matching with weighted scoring to determine the most
    likely query type based on keywords and phrases in the query text.

    Args:
        query: The query text (typically issue title + body).

    Returns:
        The classified QueryType enum value.
    """
    if not query or not query.strip():
        return QueryType.UNKNOWN

    query_lower = query.lower()
    scores: dict[QueryType, float] = {}

    for rule in _CLASSIFICATION_RULES:
        score = 0.0
        for pattern in rule.patterns:
            matches = re.findall(pattern, query_lower, re.IGNORECASE)
            score += len(matches) * rule.weight

        if score > 0:
            scores[rule.query_type] = score

    if not scores:
        return QueryType.UNKNOWN

    # Return the type with highest score
    best_type = max(scores, key=lambda t: scores[t])
    return best_type


def classify_query_str(query: str) -> str:
    """Classify a query and return the string value."""
    return classify_query(query).value
