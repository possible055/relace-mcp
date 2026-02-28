import json

import pytest

from relace_mcp.lsp.protocol import (
    MAX_MESSAGE_BUFFER_BYTES,
    MessageBuffer,
    decode_header,
    decode_message,
    encode_message,
)


class TestEncodeMessage:
    def test_non_ascii_content_length_is_byte_count(self) -> None:
        content = {"text": "日本語テスト"}
        encoded = encode_message(content)
        # Parse header to verify Content-Length matches body bytes
        header_end = encoded.index(b"\r\n\r\n") + 4
        body = encoded[header_end:]
        header_text = encoded[:header_end].decode("ascii")
        cl = int(header_text.split(":")[1].split("\r\n")[0].strip())
        assert cl == len(body)
        # Verify body decodes correctly
        assert json.loads(body.decode("utf-8"))["text"] == "日本語テスト"

    def test_roundtrip_encode_decode(self) -> None:
        content = {"jsonrpc": "2.0", "id": 42, "method": "test", "params": {"key": "value"}}
        encoded = encode_message(content)
        header_info = decode_header(encoded)
        assert header_info is not None
        cl, offset = header_info
        body = encoded[offset : offset + cl]
        result = decode_message(body)
        assert result == content


class TestDecodeHeader:
    def test_zero_content_length_returns_none(self) -> None:
        data = b"Content-Length: 0\r\n\r\n"
        assert decode_header(data) is None

    def test_negative_content_length_returns_none(self) -> None:
        data = b"Content-Length: -5\r\n\r\n"
        assert decode_header(data) is None

    def test_non_numeric_content_length_returns_none(self) -> None:
        data = b"Content-Length: abc\r\n\r\n"
        assert decode_header(data) is None

    def test_multiple_header_lines(self) -> None:
        data = b"Content-Type: application/json\r\nContent-Length: 50\r\n\r\n"
        result = decode_header(data)
        assert result is not None
        cl, _ = result
        assert cl == 50

    def test_garbage_data_returns_none(self) -> None:
        assert decode_header(b"not a header at all") is None

    def test_empty_data_returns_none(self) -> None:
        assert decode_header(b"") is None

    def test_missing_content_length_header(self) -> None:
        data = b"Content-Type: text/plain\r\n\r\n"
        assert decode_header(data) is None


class TestDecodeMessage:
    def test_invalid_utf8_returns_none(self) -> None:
        assert decode_message(b"\xff\xfe\x00\x80") is None

    def test_valid_json(self) -> None:
        body = b'{"jsonrpc": "2.0", "id": 1}'
        result = decode_message(body)
        assert result is not None
        assert result["id"] == 1

    def test_invalid_json_returns_none(self) -> None:
        assert decode_message(b"{broken json}") is None


class TestMessageBufferEdgeCases:
    def test_buffer_overflow_raises(self) -> None:
        buf = MessageBuffer()
        # Feed data without a valid header separator to trigger overflow
        buf.append(b"X" * (MAX_MESSAGE_BUFFER_BYTES + 1))
        with pytest.raises(ValueError, match="exceeded"):
            buf.try_parse_message()

    def test_oversized_content_length_raises(self) -> None:
        buf = MessageBuffer()
        huge_cl = MAX_MESSAGE_BUFFER_BYTES + 1
        header = f"Content-Length: {huge_cl}\r\n\r\n".encode("ascii")
        buf.append(header)
        with pytest.raises(ValueError, match="too large"):
            buf.try_parse_message()

    def test_clear_resets_buffer(self) -> None:
        buf = MessageBuffer()
        content = b'{"id": 1}'
        header = f"Content-Length: {len(content)}\r\n\r\n".encode("ascii")
        buf.append(header + content)
        buf.clear()
        assert buf.try_parse_message() is None

    def test_chunked_arrival(self) -> None:
        buf = MessageBuffer()
        content = b'{"id": 99}'
        header = f"Content-Length: {len(content)}\r\n\r\n".encode("ascii")
        full = header + content

        # Feed byte by byte
        for i in range(len(full) - 1):
            buf.append(full[i : i + 1])
            assert buf.try_parse_message() is None

        buf.append(full[-1:])
        msg = buf.try_parse_message()
        assert msg is not None
        assert msg["id"] == 99

    def test_invalid_body_returns_none(self) -> None:
        buf = MessageBuffer()
        bad_body = b"not json at all!!"
        header = f"Content-Length: {len(bad_body)}\r\n\r\n".encode("ascii")
        buf.append(header + bad_body)
        assert buf.try_parse_message() is None

    def test_buffer_below_limit_no_raise(self) -> None:
        buf = MessageBuffer()
        buf.append(b"X" * 1000)
        # Should return None without raising
        assert buf.try_parse_message() is None
