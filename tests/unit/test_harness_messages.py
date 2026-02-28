from typing import Any

from relace_mcp.tools.search.harness.messages import MessageHistoryMixin


class ConcreteMessageHistory(MessageHistoryMixin):
    pass


def _make_assistant_tc(tc_id: str, func_name: str = "test") -> dict[str, Any]:
    return {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {"id": tc_id, "type": "function", "function": {"name": func_name, "arguments": "{}"}}
        ],
    }


def _make_tool_result(tc_id: str, content: str = "ok") -> dict[str, Any]:
    return {"role": "tool", "tool_call_id": tc_id, "content": content}


class TestSanitizeAssistantMessage:
    def setup_method(self) -> None:
        self.mixin = ConcreteMessageHistory()

    def test_keeps_allowed_fields(self) -> None:
        msg = {"role": "assistant", "content": "hello", "tool_calls": [], "name": "bot"}
        result = self.mixin._sanitize_assistant_message(msg)
        assert result == msg

    def test_filters_disallowed_fields(self) -> None:
        msg = {
            "role": "assistant",
            "content": "hi",
            "refusal": None,
            "annotations": [],
            "audio": {},
            "function_call": {},
        }
        result = self.mixin._sanitize_assistant_message(msg)
        assert set(result.keys()) == {"role", "content"}

    def test_removes_none_values(self) -> None:
        msg = {"role": "assistant", "content": None, "tool_calls": []}
        result = self.mixin._sanitize_assistant_message(msg)
        assert "content" not in result
        assert result == {"role": "assistant", "tool_calls": []}


class TestRepairToolCallIntegrity:
    def setup_method(self) -> None:
        self.mixin = ConcreteMessageHistory()

    def test_no_repair_needed(self) -> None:
        messages: list[dict[str, Any]] = [
            _make_assistant_tc("tc1"),
            _make_tool_result("tc1"),
        ]
        original_len = len(messages)
        self.mixin._repair_tool_call_integrity(messages, "test-trace")
        assert len(messages) == original_len

    def test_injects_error_for_missing_results(self) -> None:
        messages: list[dict[str, Any]] = [
            _make_assistant_tc("tc1"),
            _make_assistant_tc("tc2"),
            _make_tool_result("tc1"),
            # tc2 result missing
        ]
        self.mixin._repair_tool_call_integrity(messages, "test-trace")
        # Should inject one error result for tc2
        tool_msgs = [m for m in messages if m.get("role") == "tool"]
        assert len(tool_msgs) == 2
        injected = [m for m in tool_msgs if m["tool_call_id"] == "tc2"]
        assert len(injected) == 1
        assert "interrupted" in injected[0]["content"].lower() or "Error" in injected[0]["content"]

    def test_empty_messages(self) -> None:
        messages: list[dict[str, Any]] = []
        self.mixin._repair_tool_call_integrity(messages, "test-trace")
        assert messages == []

    def test_assistant_without_tool_calls(self) -> None:
        messages: list[dict[str, Any]] = [
            {"role": "assistant", "content": "just text"},
        ]
        original_len = len(messages)
        self.mixin._repair_tool_call_integrity(messages, "test-trace")
        assert len(messages) == original_len


class TestTruncateMessages:
    def setup_method(self) -> None:
        self.mixin = ConcreteMessageHistory()

    def test_short_history_unchanged(self) -> None:
        messages = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "hi"},
            _make_assistant_tc("tc1"),
            _make_tool_result("tc1"),
        ]
        result = self.mixin._truncate_messages(messages)
        assert result == messages

    def test_exactly_8_messages_unchanged(self) -> None:
        messages = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "hi"},
        ]
        for i in range(3):
            messages.append(_make_assistant_tc(f"tc{i}"))
            messages.append(_make_tool_result(f"tc{i}"))
        assert len(messages) == 8
        result = self.mixin._truncate_messages(messages)
        assert result == messages

    def test_long_history_truncated_keeps_system_and_user(self) -> None:
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "hi"},
        ]
        for i in range(10):
            messages.append(_make_assistant_tc(f"tc{i}"))
            messages.append(_make_tool_result(f"tc{i}"))
        assert len(messages) == 22

        result = self.mixin._truncate_messages(messages)
        # Should keep system + user
        assert result[0]["role"] == "system"
        assert result[1]["role"] == "user"
        # Should be shorter than original
        assert len(result) < len(messages)
        # Should keep recent blocks (last few tc)
        tool_ids = [m["tool_call_id"] for m in result if m.get("role") == "tool"]
        # The last tc should always be present
        assert "tc9" in tool_ids

    def test_keeps_at_least_one_block(self) -> None:
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "hi"},
        ]
        # One massive block with many tool results
        tc = _make_assistant_tc("tc0")
        tc["tool_calls"] = [
            {"id": f"tc0_{i}", "type": "function", "function": {"name": "t", "arguments": "{}"}}
            for i in range(20)
        ]
        messages.append(tc)
        for i in range(20):
            messages.append(_make_tool_result(f"tc0_{i}"))

        result = self.mixin._truncate_messages(messages)
        # Must keep system + user + at least the block
        assert len(result) >= 3

    def test_orphan_tool_messages_discarded(self) -> None:
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "hi"},
        ]
        # Add an orphan tool message (no preceding assistant) followed by normal blocks
        for i in range(6):
            messages.append(_make_assistant_tc(f"tc{i}"))
            messages.append(_make_tool_result(f"tc{i}"))
        # Insert orphan tool at position 2 (right after system+user)
        messages.insert(2, _make_tool_result("orphan"))
        assert len(messages) > 8

        result = self.mixin._truncate_messages(messages)
        # Orphan tool message should not appear in result
        orphan_msgs = [m for m in result if m.get("tool_call_id") == "orphan"]
        assert orphan_msgs == []

    def test_user_message_in_conversation_treated_as_block(self) -> None:
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "hi"},
        ]
        for i in range(5):
            messages.append(_make_assistant_tc(f"tc{i}"))
            messages.append(_make_tool_result(f"tc{i}"))
        # Insert an extra user message mid-conversation
        messages.insert(6, {"role": "user", "content": "followup"})
        assert len(messages) > 8

        result = self.mixin._truncate_messages(messages)
        # System + user header must be preserved
        assert result[0]["role"] == "system"
        assert result[1]["role"] == "user"
        # Should be truncated
        assert len(result) < len(messages)


class TestAppendToolResultsToMessages:
    def setup_method(self) -> None:
        self.mixin = ConcreteMessageHistory()

    def test_string_result_appended(self) -> None:
        messages: list[dict[str, Any]] = []
        self.mixin._append_tool_results_to_messages(
            messages, [("tc1", "grep_search", "found: line 1")]
        )
        assert len(messages) == 1
        assert messages[0]["role"] == "tool"
        assert messages[0]["tool_call_id"] == "tc1"
        assert "found: line 1" in messages[0]["content"]

    def test_dict_result_serialized(self) -> None:
        messages: list[dict[str, Any]] = []
        self.mixin._append_tool_results_to_messages(
            messages, [("tc1", "view_file", {"lines": ["a", "b"]})]
        )
        assert '"lines"' in messages[0]["content"]

    def test_unknown_tool_uses_default_limit(self) -> None:
        messages: list[dict[str, Any]] = []
        self.mixin._append_tool_results_to_messages(
            messages, [("tc1", "unknown_tool_xyz", "short")]
        )
        assert len(messages) == 1
        assert messages[0]["content"] == "short"

    def test_multiple_results(self) -> None:
        messages: list[dict[str, Any]] = []
        results = [
            ("tc1", "view_file", "content1"),
            ("tc2", "grep_search", "content2"),
            ("tc3", "bash", "content3"),
        ]
        self.mixin._append_tool_results_to_messages(messages, results)
        assert len(messages) == 3
        assert [m["tool_call_id"] for m in messages] == ["tc1", "tc2", "tc3"]
