import hashlib
import json
from pathlib import Path
from unittest.mock import patch

from relace_mcp.observability.events import (
    _NEVER_REDACT_KEYS,
    _SENSITIVE_KEYS,
    _make_placeholder,
    _sanitize_event,
    log_event,
    redact_value,
)


class TestMakePlaceholder:
    def test_format(self) -> None:
        value = "hello world"
        result = _make_placeholder(value)
        expected_hash = hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]
        assert result == f"[REDACTED len={len(value)} sha256={expected_hash}]"

    def test_empty_string(self) -> None:
        result = _make_placeholder("")
        assert result.startswith("[REDACTED len=0")

    def test_deterministic(self) -> None:
        assert _make_placeholder("test") == _make_placeholder("test")

    def test_different_values_different_hash(self) -> None:
        assert _make_placeholder("a") != _make_placeholder("b")


class TestSanitizeEvent:
    def test_sensitive_string_redacted(self) -> None:
        with patch("relace_mcp.config.settings.MCP_LOG_REDACT", True):
            event = {"error": "secret message", "kind": "test"}
            result = _sanitize_event(event)
            assert "REDACTED" in result["error"]
            assert "secret" not in result["error"]
            assert result["kind"] == "test"

    def test_non_sensitive_key_preserved(self) -> None:
        with patch("relace_mcp.config.settings.MCP_LOG_REDACT", True):
            event = {"kind": "test", "level": "info", "latency_ms": 100}
            result = _sanitize_event(event)
            assert result == event

    def test_never_redact_keys_preserved(self) -> None:
        with patch("relace_mcp.config.settings.MCP_LOG_REDACT", True):
            event = {
                "error_type": "ValueError",
                "error_code": "INVALID_PATH",
                "status_code": "404",
                "error": "sensitive details",
            }
            result = _sanitize_event(event)
            assert result["error_type"] == "ValueError"
            assert result["error_code"] == "INVALID_PATH"
            assert result["status_code"] == "404"
            assert "REDACTED" in result["error"]

    def test_numeric_values_preserved(self) -> None:
        with patch("relace_mcp.config.settings.MCP_LOG_REDACT", True):
            event = {"error": 42, "result": True, "message": None}
            result = _sanitize_event(event)
            assert result["error"] == 42
            assert result["result"] is True
            assert result["message"] is None

    def test_nested_dict_redacted(self) -> None:
        with patch("relace_mcp.config.settings.MCP_LOG_REDACT", True):
            event = {"args": {"command": "rm -rf /", "path": "/tmp"}}
            result = _sanitize_event(event)
            assert "REDACTED" in result["args"]["command"]
            assert result["args"]["path"] == "/tmp"

    def test_sensitive_key_with_list_of_strings(self) -> None:
        with patch("relace_mcp.config.settings.MCP_LOG_REDACT", True):
            event = {"command": ["ls", "-la", "/home"]}
            result = _sanitize_event(event)
            assert all("REDACTED" in item for item in result["command"])

    def test_non_sensitive_list_preserved(self) -> None:
        with patch("relace_mcp.config.settings.MCP_LOG_REDACT", True):
            event = {"result_keys": ["status", "data", "count"]}
            result = _sanitize_event(event)
            assert result["result_keys"] == ["status", "data", "count"]

    def test_depth_limit(self) -> None:
        with patch("relace_mcp.config.settings.MCP_LOG_REDACT", True):
            deep: dict = {"a": {}}
            node = deep["a"]
            for _ in range(8):
                node["a"] = {}
                node = node["a"]
            node["error"] = "deep secret"
            result = _sanitize_event(deep)
            assert "[REDACTED depth_limit]" in str(result)

    def test_list_length_limit(self) -> None:
        with patch("relace_mcp.config.settings.MCP_LOG_REDACT", True):
            event = {"tags": list(range(30))}
            result = _sanitize_event(event)
            assert len(result["tags"]) == 21
            assert result["tags"][-1] == "[REDACTED list_len=30]"

    def test_noop_when_redact_false(self) -> None:
        with patch("relace_mcp.config.settings.MCP_LOG_REDACT", False):
            event = {"error": "secret", "traceback": "tb"}
            result = _sanitize_event(event)
            assert result == event

    def test_file_path_keys_never_in_sensitive_set(self) -> None:
        path_keys = {"file_path", "workspace", "base_dir", "path", "cwd", "rel_path"}
        assert not path_keys & _SENSITIVE_KEYS

    def test_placeholder_includes_sha256(self) -> None:
        with patch("relace_mcp.config.settings.MCP_LOG_REDACT", True):
            event = {"error": "my secret error"}
            result = _sanitize_event(event)
            assert "sha256=" in result["error"]
            expected_hash = hashlib.sha256(b"my secret error").hexdigest()[:12]
            assert expected_hash in result["error"]


class TestRedactValueSafeMode:
    def test_short_string_redacted(self) -> None:
        with patch("relace_mcp.config.settings.MCP_LOG_REDACT", True):
            result = redact_value("short")
            assert "REDACTED" in result
            assert "short" not in result

    def test_empty_string_passthrough(self) -> None:
        with patch("relace_mcp.config.settings.MCP_LOG_REDACT", True):
            assert redact_value("") == ""

    def test_full_mode_truncates(self) -> None:
        with patch("relace_mcp.config.settings.MCP_LOG_REDACT", False):
            long = "x" * 500
            result = redact_value(long, max_len=100)
            assert len(result) <= 100
            assert result.startswith("x")

    def test_full_mode_short_passthrough(self) -> None:
        with patch("relace_mcp.config.settings.MCP_LOG_REDACT", False):
            short = "hello"
            assert redact_value(short, max_len=200) == short


class TestLogEventCentralizedSanitization:
    def test_sensitive_fields_redacted_in_safe_mode(self, tmp_path: Path) -> None:
        log_file = tmp_path / "test.log"
        with (
            patch("relace_mcp.config.settings.MCP_LOGGING", True),
            patch("relace_mcp.config.settings.MCP_LOG_REDACT", True),
            patch("relace_mcp.config.settings.LOG_PATH", log_file),
        ):
            log_event(
                {
                    "kind": "test_event",
                    "level": "info",
                    "error": "secret password here",
                    "error_type": "AuthError",
                    "file_path": "/repo/main.py",
                }
            )
        logged = json.loads(log_file.read_text(encoding="utf-8").strip())
        assert "REDACTED" in logged["error"]
        assert "secret" not in logged["error"]
        assert logged["error_type"] == "AuthError"
        assert logged["file_path"] == "/repo/main.py"

    def test_non_serializable_handled(self, tmp_path: Path) -> None:
        log_file = tmp_path / "test.log"
        with (
            patch("relace_mcp.config.settings.MCP_LOGGING", True),
            patch("relace_mcp.config.settings.MCP_LOG_REDACT", False),
            patch("relace_mcp.config.settings.LOG_PATH", log_file),
        ):
            from pathlib import PurePosixPath

            log_event(
                {
                    "kind": "test_event",
                    "level": "info",
                    "some_path": PurePosixPath("/foo/bar"),
                }
            )
        assert log_file.exists()
        logged = json.loads(log_file.read_text(encoding="utf-8").strip())
        assert logged["some_path"] == "/foo/bar"

    def test_apply_event_no_code_leak(self, tmp_path: Path) -> None:
        log_file = tmp_path / "test.log"
        with (
            patch("relace_mcp.config.settings.MCP_LOGGING", True),
            patch("relace_mcp.config.settings.MCP_LOG_REDACT", True),
            patch("relace_mcp.config.settings.LOG_PATH", log_file),
        ):
            log_event(
                {
                    "kind": "apply_success",
                    "level": "info",
                    "edit_snippet_preview": "def secret_func():\n    pass",
                    "instruction": "Add a secret function",
                    "file_path": "/repo/main.py",
                    "latency_ms": 123,
                }
            )
        logged = json.loads(log_file.read_text(encoding="utf-8").strip())
        assert "secret" not in logged["edit_snippet_preview"]
        assert "secret" not in logged["instruction"]
        assert "REDACTED" in logged["edit_snippet_preview"]
        assert "REDACTED" in logged["instruction"]
        assert logged["file_path"] == "/repo/main.py"
        assert logged["latency_ms"] == 123

    def test_tool_call_args_redacted(self, tmp_path: Path) -> None:
        log_file = tmp_path / "test.log"
        with (
            patch("relace_mcp.config.settings.MCP_LOGGING", True),
            patch("relace_mcp.config.settings.MCP_LOG_REDACT", True),
            patch("relace_mcp.config.settings.LOG_PATH", log_file),
        ):
            log_event(
                {
                    "kind": "tool_call",
                    "level": "debug",
                    "args": {"query": "TOPSECRET", "path": "/tmp/a.py"},
                    "result_preview": "found 3 matches in secret file",
                    "success": True,
                }
            )
        logged = json.loads(log_file.read_text(encoding="utf-8").strip())
        assert "TOPSECRET" not in logged["args"]["query"]
        assert "REDACTED" in logged["args"]["query"]
        assert logged["args"]["path"] == "/tmp/a.py"
        assert "REDACTED" in logged["result_preview"]
        assert logged["success"] is True


class TestKeySetIntegrity:
    def test_sensitive_keys_lowercase(self) -> None:
        for key in _SENSITIVE_KEYS:
            assert key == key.lower(), f"Key {key!r} should be lowercase"

    def test_never_redact_keys_lowercase(self) -> None:
        for key in _NEVER_REDACT_KEYS:
            assert key == key.lower(), f"Key {key!r} should be lowercase"

    def test_no_overlap(self) -> None:
        overlap = _SENSITIVE_KEYS & _NEVER_REDACT_KEYS
        assert not overlap, f"Overlap between sensitive and never-redact: {overlap}"
