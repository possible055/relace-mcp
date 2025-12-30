"""Tests for the new LSP module."""

from relace_mcp.lsp.languages import LANGUAGE_CONFIGS, PYTHON_CONFIG, get_config_for_file
from relace_mcp.lsp.languages.base import LanguageServerConfig
from relace_mcp.lsp.protocol import MessageBuffer, decode_header, decode_message, encode_message
from relace_mcp.lsp.types import Location, LSPError


class TestLocation:
    """Tests for Location dataclass."""

    def test_to_grep_format_within_base_dir(self) -> None:
        loc = Location(uri="file:///home/user/project/src/main.py", line=10, character=5)
        result = loc.to_grep_format("/home/user/project")
        assert result == "/repo/src/main.py:11:6"

    def test_to_grep_format_outside_base_dir(self) -> None:
        loc = Location(uri="file:///other/path/file.py", line=0, character=0)
        result = loc.to_grep_format("/home/user/project")
        assert result == "/other/path/file.py:1:1"

    def test_to_grep_format_trailing_slash(self) -> None:
        loc = Location(uri="file:///home/user/project/lib.py", line=5, character=3)
        result = loc.to_grep_format("/home/user/project/")
        assert result == "/repo/lib.py:6:4"

    def test_to_grep_format_windows_drive_letter(self) -> None:
        loc = Location(uri="file:///C:/Users/me/project/src/main.py", line=10, character=5)
        result = loc.to_grep_format("C:/Users/me/project")
        assert result == "/repo/src/main.py:11:6"

    def test_to_grep_format_windows_backslashes_base_dir(self) -> None:
        loc = Location(uri="file:///C:/Users/me/project/src/main.py", line=0, character=0)
        result = loc.to_grep_format(r"C:\Users\me\project")
        assert result == "/repo/src/main.py:1:1"

    def test_to_grep_format_windows_outside_base_dir(self) -> None:
        loc = Location(uri="file:///C:/Other/file.py", line=0, character=0)
        result = loc.to_grep_format("C:/Users/me/project")
        assert result == "C:/Other/file.py:1:1"


class TestLSPError:
    """Tests for LSPError exception."""

    def test_str_without_code(self) -> None:
        err = LSPError("Something went wrong")
        assert str(err) == "LSP Error: Something went wrong"

    def test_str_with_code(self) -> None:
        err = LSPError("Method not found", code=-32601)
        assert str(err) == "LSP Error -32601: Method not found"


class TestProtocol:
    """Tests for JSON-RPC protocol encoding/decoding."""

    def test_encode_message(self) -> None:
        content = {"jsonrpc": "2.0", "id": 1, "method": "test"}
        data = encode_message(content)
        assert data.startswith(b"Content-Length: ")
        assert b"\r\n\r\n" in data
        assert b'"jsonrpc": "2.0"' in data

    def test_decode_header_complete(self) -> None:
        data = b"Content-Length: 42\r\n\r\n"
        result = decode_header(data)
        assert result is not None
        content_length, header_end = result
        assert content_length == 42
        assert header_end == len(data)

    def test_decode_header_incomplete(self) -> None:
        data = b"Content-Length: 42\r\n"
        result = decode_header(data)
        assert result is None

    def test_decode_message_valid(self) -> None:
        body = b'{"jsonrpc": "2.0", "id": 1}'
        result = decode_message(body)
        assert result is not None
        assert result["jsonrpc"] == "2.0"
        assert result["id"] == 1

    def test_decode_message_invalid(self) -> None:
        body = b"not json"
        result = decode_message(body)
        assert result is None


class TestMessageBuffer:
    """Tests for MessageBuffer."""

    def test_parse_complete_message(self) -> None:
        buf = MessageBuffer()
        content = b'{"jsonrpc": "2.0", "id": 1}'
        header = f"Content-Length: {len(content)}\r\n\r\n".encode("ascii")
        buf.append(header + content)

        msg = buf.try_parse_message()
        assert msg is not None
        assert msg["id"] == 1

    def test_parse_incomplete_header(self) -> None:
        buf = MessageBuffer()
        buf.append(b"Content-Length: 10\r\n")

        msg = buf.try_parse_message()
        assert msg is None

    def test_parse_incomplete_body(self) -> None:
        buf = MessageBuffer()
        buf.append(b"Content-Length: 100\r\n\r\n{}")

        msg = buf.try_parse_message()
        assert msg is None

    def test_parse_multiple_messages(self) -> None:
        buf = MessageBuffer()

        # Add two messages
        for i in range(2):
            content = f'{{"id": {i}}}'.encode()
            header = f"Content-Length: {len(content)}\r\n\r\n".encode("ascii")
            buf.append(header + content)

        msg1 = buf.try_parse_message()
        assert msg1 is not None
        assert msg1["id"] == 0

        msg2 = buf.try_parse_message()
        assert msg2 is not None
        assert msg2["id"] == 1

        msg3 = buf.try_parse_message()
        assert msg3 is None


class TestLanguageServerConfig:
    """Tests for LanguageServerConfig."""

    def test_matches_file(self) -> None:
        config = LanguageServerConfig(
            language_id="python",
            file_extensions=(".py", ".pyi"),
            command=["test"],
        )
        assert config.matches_file("test.py") is True
        assert config.matches_file("stub.pyi") is True
        assert config.matches_file("test.js") is False
        assert config.matches_file("/path/to/module.py") is True


class TestPythonConfig:
    """Tests for Python language server configuration."""

    def test_python_config_exists(self) -> None:
        assert PYTHON_CONFIG is not None
        assert PYTHON_CONFIG.language_id == "python"
        assert ".py" in PYTHON_CONFIG.file_extensions
        assert "basedpyright-langserver" in PYTHON_CONFIG.command[0]

    def test_language_configs_registry(self) -> None:
        assert "python" in LANGUAGE_CONFIGS
        assert LANGUAGE_CONFIGS["python"] is PYTHON_CONFIG


class TestGetConfigForFile:
    """Tests for get_config_for_file helper."""

    def test_python_file(self) -> None:
        config = get_config_for_file("test.py")
        assert config is not None
        assert config.language_id == "python"

    def test_pyi_file(self) -> None:
        config = get_config_for_file("types.pyi")
        assert config is not None
        assert config.language_id == "python"

    def test_unsupported_file(self) -> None:
        config = get_config_for_file("test.js")
        assert config is None

    def test_path_with_directory(self) -> None:
        config = get_config_for_file("/path/to/module.py")
        assert config is not None
        assert config.language_id == "python"
