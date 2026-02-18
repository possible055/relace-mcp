from unittest.mock import patch

from relace_mcp.repo.local.backend import codanna_search

CODANNA_ENVELOPE = {
    "type": "result",
    "status": "success",
    "code": "OK",
    "exit_code": 0,
    "message": "Found 2 symbol(s) with context",
    "data": [
        {
            "symbol": {
                "id": 1,
                "name": "authenticate",
                "kind": "Function",
                "file_path": "src/auth.py",
                "signature": "def authenticate(user)",
            },
            "score": 0.88,
            "context": {
                "file_path": "src/auth.py",
                "relationships": {},
            },
        },
        {
            "symbol": {
                "id": 2,
                "name": "login",
                "kind": "Function",
                "file_path": "src/login.py",
                "signature": "def login()",
            },
            "score": 0.72,
            "context": {
                "file_path": "src/login.py",
                "relationships": {},
            },
        },
    ],
    "meta": {
        "schema_version": "1.0.0",
        "entity_type": "symbol",
        "count": 2,
    },
}


class TestCodannaSearch:
    @patch("relace_mcp.repo.local.backend._run_cli_json")
    def test_parses_envelope_data_field(self, mock_run):
        mock_run.return_value = CODANNA_ENVELOPE
        results = codanna_search("auth", base_dir="/tmp/repo")
        assert len(results) == 2
        assert results[0] == {"filename": "src/auth.py", "score": 0.88}
        assert results[1] == {"filename": "src/login.py", "score": 0.72}

    @patch("relace_mcp.repo.local.backend._run_cli_json")
    def test_returns_empty_on_none(self, mock_run):
        mock_run.return_value = None
        results = codanna_search("query", base_dir="/tmp/repo")
        assert results == []

    @patch("relace_mcp.repo.local.backend._run_cli_json")
    def test_returns_empty_when_data_missing(self, mock_run):
        mock_run.return_value = {"type": "result", "status": "success"}
        results = codanna_search("query", base_dir="/tmp/repo")
        assert results == []

    @patch("relace_mcp.repo.local.backend._run_cli_json")
    def test_returns_empty_on_empty_data(self, mock_run):
        mock_run.return_value = {"data": []}
        results = codanna_search("query", base_dir="/tmp/repo")
        assert results == []

    @patch("relace_mcp.repo.local.backend._run_cli_json")
    def test_falls_back_to_context_file_path(self, mock_run):
        mock_run.return_value = {
            "data": [
                {
                    "score": 0.9,
                    "context": {"file_path": "src/fallback.py"},
                }
            ]
        }
        results = codanna_search("query", base_dir="/tmp/repo")
        assert len(results) == 1
        assert results[0]["filename"] == "src/fallback.py"

    @patch("relace_mcp.repo.local.backend._run_cli_json")
    def test_skips_items_without_file_path(self, mock_run):
        mock_run.return_value = {
            "data": [
                {"score": 0.9, "symbol": {"name": "orphan"}},
                {
                    "score": 0.8,
                    "symbol": {"file_path": "src/good.py"},
                },
            ]
        }
        results = codanna_search("query", base_dir="/tmp/repo")
        assert len(results) == 1
        assert results[0]["filename"] == "src/good.py"

    @patch("relace_mcp.repo.local.backend._run_cli_json")
    def test_handles_invalid_score(self, mock_run):
        mock_run.return_value = {
            "data": [
                {
                    "symbol": {"file_path": "src/a.py"},
                    "score": "not_a_number",
                }
            ]
        }
        results = codanna_search("query", base_dir="/tmp/repo")
        assert len(results) == 1
        assert results[0]["score"] == 0.0
