"""Tests for ApplyLLMClient system prompt injection."""

from unittest.mock import patch

import pytest

from relace_mcp.clients import ApplyLLMClient
from relace_mcp.clients.apply import ApplyRequest
from relace_mcp.config import APPLY_SYSTEM_PROMPT, RelaceConfig


class TestApplyClientSystemPrompt:
    """Test conditional system prompt injection based on api_compat."""

    @pytest.fixture
    def mock_config(self, tmp_path) -> RelaceConfig:
        """Create a mock RelaceConfig."""
        return RelaceConfig(api_key="rlc-test-key", base_dir=str(tmp_path))

    def test_system_prompt_injected_for_openai_compat(self, mock_config: RelaceConfig) -> None:
        """System prompt should be injected when api_compat is 'openai'."""
        with patch.dict(
            "os.environ",
            {
                "RELACE_APPLY_PROVIDER": "openai",
                "OPENAI_API_KEY": "sk-test",
            },
        ):
            client = ApplyLLMClient(mock_config)
            # Verify api_compat is 'openai'
            assert client._api_compat == "openai"

            request = ApplyRequest(
                initial_code="def foo():\n    pass\n",
                edit_snippet="def foo():\n    return 42\n",
                instruction="Add return",
            )
            messages = client._build_messages(request)

            # Should have 2 messages: system + user
            assert len(messages) == 2
            assert messages[0]["role"] == "system"
            assert messages[0]["content"] == APPLY_SYSTEM_PROMPT
            assert messages[1]["role"] == "user"
            assert "<code>" in messages[1]["content"]
            assert "<update>" in messages[1]["content"]

    def test_system_prompt_not_injected_for_relace(self, mock_config: RelaceConfig) -> None:
        """System prompt should NOT be injected when api_compat is 'relace'."""
        with patch.dict(
            "os.environ",
            {
                "RELACE_APPLY_PROVIDER": "relace",
            },
            clear=False,
        ):
            client = ApplyLLMClient(mock_config)
            # Verify api_compat is 'relace'
            assert client._api_compat == "relace"

            request = ApplyRequest(
                initial_code="def foo():\n    pass\n",
                edit_snippet="def foo():\n    return 42\n",
                instruction=None,
            )
            messages = client._build_messages(request)

            # Should have only 1 message: user (no system)
            assert len(messages) == 1
            assert messages[0]["role"] == "user"
            assert "<code>" in messages[0]["content"]
            assert "<update>" in messages[0]["content"]

    def test_system_prompt_not_injected_by_default(self, mock_config: RelaceConfig) -> None:
        """System prompt should NOT be injected for default Relace provider."""
        # Default provider is 'relace', so no env override needed
        with patch.dict("os.environ", {}, clear=False):
            # Remove any provider override to test default behavior
            import os

            orig_provider = os.environ.pop("RELACE_APPLY_PROVIDER", None)
            try:
                client = ApplyLLMClient(mock_config)
                # Default api_compat should be 'relace'
                assert client._api_compat == "relace"

                request = ApplyRequest(
                    initial_code="x = 1",
                    edit_snippet="x = 2",
                )
                messages = client._build_messages(request)

                # Should have only 1 message: user
                assert len(messages) == 1
                assert messages[0]["role"] == "user"
            finally:
                if orig_provider is not None:
                    os.environ["RELACE_APPLY_PROVIDER"] = orig_provider

    def test_user_message_format(self, mock_config: RelaceConfig) -> None:
        """User message should contain proper XML tags."""
        with patch.dict("os.environ", {}, clear=False):
            import os

            orig_provider = os.environ.pop("RELACE_APPLY_PROVIDER", None)
            try:
                client = ApplyLLMClient(mock_config)

                request = ApplyRequest(
                    initial_code="original",
                    edit_snippet="updated",
                    instruction="do something",
                )
                messages = client._build_messages(request)

                user_content = messages[-1]["content"]
                assert "<instruction>do something</instruction>" in user_content
                assert "<code>original</code>" in user_content
                assert "<update>updated</update>" in user_content
            finally:
                if orig_provider is not None:
                    os.environ["RELACE_APPLY_PROVIDER"] = orig_provider

    def test_user_message_without_instruction(self, mock_config: RelaceConfig) -> None:
        """User message should not include instruction tag when instruction is None."""
        with patch.dict("os.environ", {}, clear=False):
            import os

            orig_provider = os.environ.pop("RELACE_APPLY_PROVIDER", None)
            try:
                client = ApplyLLMClient(mock_config)

                request = ApplyRequest(
                    initial_code="original",
                    edit_snippet="updated",
                    instruction=None,
                )
                messages = client._build_messages(request)

                user_content = messages[-1]["content"]
                assert "<instruction>" not in user_content
                assert "<code>original</code>" in user_content
                assert "<update>updated</update>" in user_content
            finally:
                if orig_provider is not None:
                    os.environ["RELACE_APPLY_PROVIDER"] = orig_provider
