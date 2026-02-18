from unittest.mock import MagicMock, patch

import pytest

from relace_mcp.repo.local.backend import (
    ExternalCLIError,
    _parse_chunkhound_text,
    check_backend_health,
    chunkhound_search,
)

SAMPLE_OUTPUT = """\
=== Semantic Search Results ===

[INFO] Query: 'authentication'
[INFO] Results: 3 of 50 (showing 1-3)

[1] src/auth.py
[INFO] Score: 0.880
[INFO] Lines 10-30
```
def authenticate(user):
    pass
```

[2] src/login.py
[INFO] Score: 0.720
[INFO] Lines 5-15
```
def login():
    pass
```

[3] src/utils.py
[INFO] Score: 0.250
[INFO] Lines 1-5
```
def helper():
    pass
```
"""

SAMPLE_OUTPUT_NO_INFO = """\
=== Semantic Search Results ===

Query: 'test query'
Results: 2 of 10 (showing 1-2)

[1] src/main.py
Score: 0.900
Lines 1-20
```
code here
```

[2] src/other.py
Score: 0.600
Lines 5-10
```
more code
```
"""


class TestParseChunkhoundText:
    def test_parses_multiple_results(self):
        results = _parse_chunkhound_text(SAMPLE_OUTPUT, threshold=0.3)
        assert len(results) == 2
        assert results[0] == {"filename": "src/auth.py", "score": 0.880}
        assert results[1] == {"filename": "src/login.py", "score": 0.720}

    def test_filters_by_threshold(self):
        results = _parse_chunkhound_text(SAMPLE_OUTPUT, threshold=0.8)
        assert len(results) == 1
        assert results[0]["filename"] == "src/auth.py"

    def test_parses_output_without_info_prefix(self):
        results = _parse_chunkhound_text(SAMPLE_OUTPUT_NO_INFO, threshold=0.3)
        assert len(results) == 2
        assert results[0] == {"filename": "src/main.py", "score": 0.900}
        assert results[1] == {"filename": "src/other.py", "score": 0.600}

    def test_empty_output_returns_empty(self):
        assert _parse_chunkhound_text("", threshold=0.3) == []

    def test_no_results_message_returns_empty(self):
        output = "=== Semantic Search Results ===\nResults: 0 of 0\nNo results found."
        assert _parse_chunkhound_text(output, threshold=0.3) == []

    def test_zero_of_message_returns_empty(self):
        output = "Results: 0 of 0 (showing 0-0)"
        assert _parse_chunkhound_text(output, threshold=0.3) == []

    def test_incompatible_format_raises_error(self):
        output = "[1] src/file.py\nWeirdField: something\n[2] src/other.py\nWeirdField: else\n"
        with pytest.raises(RuntimeError, match="incompatible"):
            _parse_chunkhound_text(output, threshold=0.3)

    def test_partial_score_missing_does_not_raise(self):
        output = (
            "[1] src/a.py\nScore: 0.800\n```\ncode\n```\n"
            "[2] src/b.py\nNoScore: here\n```\ncode\n```\n"
        )
        results = _parse_chunkhound_text(output, threshold=0.3)
        assert len(results) == 1
        assert results[0] == {"filename": "src/a.py", "score": 0.800}

    def test_all_below_threshold_returns_empty(self):
        results = _parse_chunkhound_text(SAMPLE_OUTPUT, threshold=0.99)
        assert results == []


class TestChunkhoundSearch:
    @patch("relace_mcp.repo.local.backend.subprocess.run")
    def test_successful_search(self, mock_run: MagicMock):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=SAMPLE_OUTPUT,
            stderr="",
        )

        results = chunkhound_search("authentication", base_dir="/project", limit=5)

        assert len(results) == 2
        assert results[0] == {"filename": "src/auth.py", "score": 0.880}
        mock_run.assert_called_once()
        call_args = mock_run.call_args
        assert call_args[1]["cwd"] == "/project"
        cmd = call_args[0][0]
        assert "--page-size" in cmd
        assert "5" in cmd

    @patch("relace_mcp.repo.local.backend.subprocess.run")
    def test_empty_output_returns_empty_list(self, mock_run: MagicMock):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="",
            stderr="",
        )

        results = chunkhound_search("query", base_dir="/project")
        assert results == []

    @patch("relace_mcp.repo.local.backend.subprocess.run")
    def test_cli_not_found_raises_error(self, mock_run: MagicMock):
        mock_run.side_effect = FileNotFoundError("chunkhound not found")

        with pytest.raises(RuntimeError) as exc_info:
            chunkhound_search("query", base_dir="/project")

        assert "not found" in str(exc_info.value).lower()

    @patch("relace_mcp.repo.local.backend.subprocess.run")
    def test_cli_timeout_raises_error(self, mock_run: MagicMock):
        import subprocess

        mock_run.side_effect = subprocess.TimeoutExpired(cmd="chunkhound", timeout=120)

        with pytest.raises(RuntimeError) as exc_info:
            chunkhound_search("query", base_dir="/project")

        assert "timeout" in str(exc_info.value).lower()

    @patch("relace_mcp.repo.local.backend._ensure_chunkhound_index")
    @patch("relace_mcp.repo.local.backend.subprocess.run")
    def test_auto_index_on_not_indexed_error(
        self, mock_run: MagicMock, mock_ensure_chunkhound_index: MagicMock
    ):
        mock_run.side_effect = [
            MagicMock(returncode=1, stdout="", stderr="not indexed"),
            MagicMock(
                returncode=0,
                stdout=SAMPLE_OUTPUT,
                stderr="",
            ),
        ]

        results = chunkhound_search("query", base_dir="/project")

        mock_ensure_chunkhound_index.assert_called_once()
        assert len(results) == 2

    @patch("relace_mcp.repo.local.backend._ensure_chunkhound_index")
    @patch("relace_mcp.repo.local.backend.subprocess.run")
    def test_auto_index_on_database_not_found_output(
        self, mock_run: MagicMock, mock_ensure_chunkhound_index: MagicMock
    ):
        mock_run.side_effect = [
            MagicMock(
                returncode=1,
                stdout=(
                    "[ERROR] [red][ERROR][/red] Database not found at /project/.chunkhound/db\n"
                    "[INFO] [blue][INFO][/blue] Run 'chunkhound index' to create the database first"
                ),
                stderr="",
            ),
            MagicMock(
                returncode=0,
                stdout=SAMPLE_OUTPUT,
                stderr="",
            ),
        ]

        results = chunkhound_search("query", base_dir="/project")

        mock_ensure_chunkhound_index.assert_called_once()
        assert len(results) == 2


class TestChunkhoundHealthCheck:
    @patch("relace_mcp.repo.local.backend._run_cli_text")
    @patch("relace_mcp.repo.local.backend.shutil.which")
    def test_database_not_found_is_treated_as_index_missing(
        self, mock_which: MagicMock, mock_run_cli_text: MagicMock
    ):
        mock_which.return_value = "/usr/bin/chunkhound"
        mock_run_cli_text.side_effect = RuntimeError(
            "chunkhound error (exit 1): Database not found at /project/.chunkhound/db"
        )

        with pytest.raises(ExternalCLIError) as exc_info:
            check_backend_health("chunkhound", "/project")

        assert exc_info.value.kind == "index_missing"
