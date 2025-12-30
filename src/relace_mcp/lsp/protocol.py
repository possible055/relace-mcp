import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

# LSP Header constants
CONTENT_LENGTH = "Content-Length"
HEADER_SEPARATOR = "\r\n\r\n"
HEADER_LINE_SEPARATOR = "\r\n"


def encode_message(content: dict[str, Any]) -> bytes:
    """Encode a JSON-RPC message with LSP headers.

    Args:
        content: The JSON-RPC message content.

    Returns:
        Bytes ready to be sent to the language server.
    """
    body = json.dumps(content, ensure_ascii=False)
    body_bytes = body.encode("utf-8")
    header = f"{CONTENT_LENGTH}: {len(body_bytes)}{HEADER_SEPARATOR}"
    return header.encode("ascii") + body_bytes


def decode_header(data: bytes) -> tuple[int, int] | None:
    """Parse LSP header to extract content length.

    Args:
        data: Raw bytes that may contain a complete header.

    Returns:
        Tuple of (content_length, header_end_offset) if complete header found,
        None otherwise.
    """
    try:
        text = data.decode("ascii", errors="replace")
    except Exception:
        return None

    sep_idx = text.find(HEADER_SEPARATOR)
    if sep_idx == -1:
        return None

    header_part = text[:sep_idx]
    content_length = None

    for line in header_part.split(HEADER_LINE_SEPARATOR):
        if line.startswith(CONTENT_LENGTH):
            try:
                value = int(line.split(":", 1)[1].strip())
                if value > 0:
                    content_length = value
            except (ValueError, IndexError):
                pass

    if content_length is None:
        return None

    header_end = sep_idx + len(HEADER_SEPARATOR)
    return content_length, header_end


def decode_message(body: bytes) -> dict[str, Any] | None:
    """Decode a JSON-RPC message body.

    Args:
        body: Raw bytes of the message body.

    Returns:
        Parsed JSON-RPC message or None if parsing fails.
    """
    try:
        result: dict[str, Any] = json.loads(body.decode("utf-8"))
        return result
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        logger.warning("Failed to decode LSP message: %s", e)
        return None


class MessageBuffer:
    """Buffer for accumulating and parsing LSP messages from a stream."""

    def __init__(self) -> None:
        self._buffer = b""

    def append(self, data: bytes) -> None:
        """Append data to the buffer."""
        self._buffer += data

    def try_parse_message(self) -> dict[str, Any] | None:
        """Try to parse a complete message from the buffer.

        Returns:
            Parsed message if complete, None if more data needed.
        """
        header_info = decode_header(self._buffer)
        if header_info is None:
            return None

        content_length, header_end = header_info
        total_length = header_end + content_length

        if len(self._buffer) < total_length:
            return None

        body = self._buffer[header_end:total_length]
        self._buffer = self._buffer[total_length:]

        return decode_message(body)

    def clear(self) -> None:
        """Clear the buffer."""
        self._buffer = b""
