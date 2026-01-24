import json
from unittest.mock import MagicMock, patch

import pytest

from relace_mcp.repo.local.backend import (
    _parse_chunkhound_results,
    chunkhound_search,
)


class TestParseResults:
    def test_parses_results_list_format(self):
        data = {
            "results": [
                {"file_path": "src/main.py", "similarity_score": 0.85},
                {"file_path": "src/utils.py", "similarity_score": 0.72},
            ]
        }
        results = _parse_chunkhound_results(data, threshold=0.3)
        assert len(results) == 2
        assert results[0] == {"filename": "src/main.py", "score": 0.85}
        assert results[1] == {"filename": "src/utils.py", "score": 0.72}

    def test_parses_chunks_format(self):
        data = {
            "chunks": [
                {"path": "lib/auth.py", "score": 0.90},
            ]
        }
        results = _parse_chunkhound_results(data, threshold=0.3)
        assert len(results) == 1
        assert results[0] == {"filename": "lib/auth.py", "score": 0.90}

    def test_parses_list_directly(self):
        data = [
            {"filename": "test.py", "score": 0.60},
        ]
        results = _parse_chunkhound_results(data, threshold=0.3)
        assert len(results) == 1
        assert results[0] == {"filename": "test.py", "score": 0.60}

    def test_filters_by_threshold(self):
        data = {
            "results": [
                {"file_path": "high.py", "similarity_score": 0.80},
                {"file_path": "low.py", "similarity_score": 0.20},
            ]
        }
        results = _parse_chunkhound_results(data, threshold=0.5)
        assert len(results) == 1
        assert results[0]["filename"] == "high.py"

    def test_handles_missing_fields(self):
        data = {
            "results": [
                {"file_path": "valid.py", "similarity_score": 0.70},
                {"other_field": "no_path"},
                {},
            ]
        }
        results = _parse_chunkhound_results(data, threshold=0.3)
        assert len(results) == 1
        assert results[0]["filename"] == "valid.py"

    def test_handles_invalid_score(self):
        data = {
            "results": [
                {"file_path": "test.py", "similarity_score": "invalid"},
            ]
        }
        results = _parse_chunkhound_results(data, threshold=0.0)
        assert len(results) == 1
        assert results[0]["score"] == 0.0

    def test_empty_data_returns_empty(self):
        assert _parse_chunkhound_results({}, threshold=0.3) == []
        assert _parse_chunkhound_results([], threshold=0.3) == []
        assert _parse_chunkhound_results(None, threshold=0.3) == []


class TestChunkhoundSearch:
    @patch("relace_mcp.repo.local.backend.subprocess.run")
    def test_successful_search(self, mock_run: MagicMock):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps(
                {
                    "results": [
                        {"file_path": "src/auth.py", "similarity_score": 0.88},
                    ]
                }
            ),
            stderr="",
        )

        results = chunkhound_search("authentication", base_dir="/project", limit=5)

        assert len(results) == 1
        assert results[0] == {"filename": "src/auth.py", "score": 0.88}
        mock_run.assert_called_once()
        call_args = mock_run.call_args
        assert call_args[1]["cwd"] == "/project"

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

    @patch("relace_mcp.repo.local.backend.subprocess.run")
    def test_json_parse_error_raises_error(self, mock_run: MagicMock):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="not valid json",
            stderr="",
        )

        with pytest.raises(RuntimeError) as exc_info:
            chunkhound_search("query", base_dir="/project")

        assert "json" in str(exc_info.value).lower()

    @patch("relace_mcp.repo.local.backend._ensure_chunkhound_index")
    @patch("relace_mcp.repo.local.backend.subprocess.run")
    def test_auto_index_on_not_indexed_error(
        self, mock_run: MagicMock, mock_ensure_chunkhound_index: MagicMock
    ):
        mock_run.side_effect = [
            MagicMock(returncode=1, stdout="", stderr="not indexed"),
            MagicMock(
                returncode=0,
                stdout=json.dumps({"results": [{"file_path": "a.py", "similarity_score": 0.5}]}),
                stderr="",
            ),
        ]

        results = chunkhound_search("query", base_dir="/project")

        mock_ensure_chunkhound_index.assert_called_once()
        assert len(results) == 1
