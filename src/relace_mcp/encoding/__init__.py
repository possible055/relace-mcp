from .codec import (
    atomic_write,
    decode_text_best_effort,
    decode_text_with_fallback,
    get_project_encoding,
    read_text_best_effort,
    read_text_with_fallback,
    set_project_encoding,
)
from .exceptions import EncodingDetectionError

__all__ = [
    "EncodingDetectionError",
    "atomic_write",
    "decode_text_best_effort",
    "decode_text_with_fallback",
    "get_project_encoding",
    "read_text_best_effort",
    "read_text_with_fallback",
    "set_project_encoding",
]
