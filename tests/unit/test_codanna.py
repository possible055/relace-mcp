from unittest.mock import MagicMock, patch

import pytest

from relace_mcp.repo.local.backend import ExternalCLIError
from relace_mcp.repo.local.backend.codanna import (
    _codanna_health_probe,
    _ensure_codanna_index,
    codanna_auto_reindex,
    codanna_search,
)

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


class TestCodannaAutoReindex:
    @patch("relace_mcp.repo.local.backend.codanna._get_git_head")
    def test_skipped_not_git_repo(self, mock_head):
        mock_head.return_value = None
        result = codanna_auto_reindex("/tmp/repo")
        assert result == {"action": "skipped", "reason": "not a git repo"}

    @patch("relace_mcp.repo.local.backend.codanna._read_indexed_head")
    @patch("relace_mcp.repo.local.backend.codanna._get_git_head")
    def test_skipped_index_up_to_date(self, mock_head, mock_read):
        mock_head.return_value = "abc123"
        mock_read.return_value = "abc123"
        result = codanna_auto_reindex("/tmp/repo")
        assert result == {"action": "skipped", "reason": "index up to date"}

    @patch("relace_mcp.repo.local.backend.codanna._write_indexed_head")
    @patch("relace_mcp.repo.local.backend.codanna._ensure_codanna_index")
    @patch("relace_mcp.repo.local.backend.codanna._read_indexed_head")
    @patch("relace_mcp.repo.local.backend.codanna._get_git_head")
    def test_reindexed_stale_head(self, mock_head, mock_read, mock_ensure, mock_write):
        mock_head.return_value = "newhead"
        mock_read.return_value = "oldhead"
        result = codanna_auto_reindex("/tmp/repo")
        mock_ensure.assert_called_once()
        mock_write.assert_called_once_with("/tmp/repo", "newhead", ".codanna/last_indexed_head")
        assert result == {"action": "reindexed", "old_head": "oldhead", "new_head": "newhead"}

    @patch("relace_mcp.repo.local.backend.codanna._ensure_codanna_index")
    @patch("relace_mcp.repo.local.backend.codanna._read_indexed_head")
    @patch("relace_mcp.repo.local.backend.codanna._get_git_head")
    def test_error_on_reindex_failure(self, mock_head, mock_read, mock_ensure):
        mock_head.return_value = "newhead"
        mock_read.return_value = None
        mock_ensure.side_effect = RuntimeError("codanna index failed: db error")
        result = codanna_auto_reindex("/tmp/repo")
        assert result["action"] == "error"
        assert "codanna index failed" in result["message"]

    @patch("relace_mcp.repo.local.backend.codanna._ensure_codanna_index")
    @patch("relace_mcp.repo.local.backend.codanna._read_indexed_head")
    @patch("relace_mcp.repo.local.backend.codanna._get_git_head")
    def test_error_on_cli_not_found(self, mock_head, mock_read, mock_ensure):
        mock_head.return_value = "abc123"
        mock_read.return_value = None
        mock_ensure.side_effect = FileNotFoundError("codanna not found")
        result = codanna_auto_reindex("/tmp/repo")
        assert result["action"] == "error"


class TestEnsureCodannaIndex:
    @patch("relace_mcp.repo.local.backend.codanna.subprocess.run")
    def test_runs_init_when_no_dotcodanna(self, mock_run: MagicMock, tmp_path):
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        env = {"LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"}
        _ensure_codanna_index(str(tmp_path), env)
        calls = [call[0][0] for call in mock_run.call_args_list]
        assert ["codanna", "init"] in calls
        assert ["codanna", "index"] in calls

    @patch("relace_mcp.repo.local.backend.codanna.subprocess.run")
    def test_skips_init_when_dotcodanna_exists(self, mock_run: MagicMock, tmp_path):
        (tmp_path / ".codanna").mkdir()
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        env = {"LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"}
        _ensure_codanna_index(str(tmp_path), env)
        calls = [call[0][0] for call in mock_run.call_args_list]
        assert ["codanna", "init"] not in calls
        assert ["codanna", "index"] in calls

    @patch("relace_mcp.repo.local.backend.codanna.subprocess.run")
    def test_raises_on_init_failure(self, mock_run: MagicMock, tmp_path):
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="permission denied")
        env = {}
        with pytest.raises(RuntimeError, match="codanna init failed"):
            _ensure_codanna_index(str(tmp_path), env)

    @patch("relace_mcp.repo.local.backend.codanna.subprocess.run")
    def test_raises_on_index_failure(self, mock_run: MagicMock, tmp_path):
        (tmp_path / ".codanna").mkdir()
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="index error")
        env = {}
        with pytest.raises(RuntimeError, match="codanna index failed"):
            _ensure_codanna_index(str(tmp_path), env)

    @patch("relace_mcp.repo.local.backend.codanna.subprocess.run")
    def test_raises_on_index_timeout(self, mock_run: MagicMock, tmp_path):
        import subprocess

        (tmp_path / ".codanna").mkdir()
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="codanna", timeout=600)
        env = {}
        with pytest.raises(RuntimeError, match="codanna index timeout"):
            _ensure_codanna_index(str(tmp_path), env)

    @patch("relace_mcp.repo.local.backend.codanna.subprocess.run")
    def test_raises_on_cli_not_found(self, mock_run: MagicMock, tmp_path):
        (tmp_path / ".codanna").mkdir()
        mock_run.side_effect = FileNotFoundError("No such file: codanna")
        env = {}
        with pytest.raises(RuntimeError, match="codanna CLI not found"):
            _ensure_codanna_index(str(tmp_path), env)


class TestCodannaSearchAutoRetry:
    @patch("relace_mcp.repo.local.backend.codanna._ensure_codanna_index")
    @patch("relace_mcp.repo.local.backend.codanna._run_cli_json")
    def test_auto_index_on_index_missing_error(self, mock_run, mock_ensure):
        mock_run.side_effect = [
            RuntimeError("codanna error (exit 1): index not found"),
            {"data": [{"symbol": {"file_path": "src/a.py"}, "score": 0.9}]},
        ]
        results = codanna_search("query", base_dir="/tmp/repo")
        mock_ensure.assert_called_once()
        assert len(results) == 1
        assert results[0]["filename"] == "src/a.py"

    @patch("relace_mcp.repo.local.backend.codanna._run_cli_json")
    def test_raises_on_retry_still_missing(self, mock_run):
        mock_run.side_effect = RuntimeError("codanna error (exit 1): index missing")
        with pytest.raises(ExternalCLIError) as exc_info:
            codanna_search("query", base_dir="/tmp/repo", _retry=True)
        assert exc_info.value.kind == "index_missing"

    @patch("relace_mcp.repo.local.backend.codanna._ensure_codanna_index")
    @patch("relace_mcp.repo.local.backend.codanna._run_cli_json")
    def test_auto_index_failure_raises_external_cli_error(self, mock_run, mock_ensure):
        mock_run.side_effect = RuntimeError("codanna error (exit 1): index not found")
        mock_ensure.side_effect = RuntimeError("codanna index failed: disk full")
        with pytest.raises(ExternalCLIError) as exc_info:
            codanna_search("query", base_dir="/tmp/repo")
        assert exc_info.value.kind == "index_missing"
        assert "auto-index failed" in str(exc_info.value).lower()


class TestCodannaHealthProbeHeadPersistence:
    @patch("relace_mcp.repo.local.backend.codanna._write_indexed_head")
    @patch("relace_mcp.repo.local.backend.codanna._get_git_head")
    @patch("relace_mcp.repo.local.backend.codanna._ensure_codanna_index")
    @patch("relace_mcp.repo.local.backend.codanna._run_cli_json")
    def test_writes_head_after_auto_index(self, mock_run, mock_ensure, mock_head, mock_write):
        mock_run.side_effect = RuntimeError("codanna error (exit 1): index not found")
        mock_head.return_value = "deadbeef"
        _codanna_health_probe("/tmp/repo")
        mock_ensure.assert_called_once()
        mock_write.assert_called_once_with("/tmp/repo", "deadbeef", ".codanna/last_indexed_head")

    @patch("relace_mcp.repo.local.backend.codanna._write_indexed_head")
    @patch("relace_mcp.repo.local.backend.codanna._get_git_head")
    @patch("relace_mcp.repo.local.backend.codanna._ensure_codanna_index")
    @patch("relace_mcp.repo.local.backend.codanna._run_cli_json")
    def test_no_write_when_not_git_repo(self, mock_run, mock_ensure, mock_head, mock_write):
        mock_run.side_effect = RuntimeError("codanna error (exit 1): index not found")
        mock_head.return_value = None
        _codanna_health_probe("/tmp/repo")
        mock_write.assert_not_called()


class TestCodannaSearch:
    @patch("relace_mcp.repo.local.backend.codanna._run_cli_json")
    def test_parses_envelope_data_field(self, mock_run):
        mock_run.return_value = CODANNA_ENVELOPE
        results = codanna_search("auth", base_dir="/tmp/repo")
        assert len(results) == 2
        assert results[0] == {"filename": "src/auth.py", "score": 0.88}
        assert results[1] == {"filename": "src/login.py", "score": 0.72}

    @patch("relace_mcp.repo.local.backend.codanna._run_cli_json")
    def test_returns_empty_on_none(self, mock_run):
        mock_run.return_value = None
        results = codanna_search("query", base_dir="/tmp/repo")
        assert results == []

    @patch("relace_mcp.repo.local.backend.codanna._run_cli_json")
    def test_returns_empty_when_data_missing(self, mock_run):
        mock_run.return_value = {"type": "result", "status": "success"}
        results = codanna_search("query", base_dir="/tmp/repo")
        assert results == []

    @patch("relace_mcp.repo.local.backend.codanna._run_cli_json")
    def test_returns_empty_on_empty_data(self, mock_run):
        mock_run.return_value = {"data": []}
        results = codanna_search("query", base_dir="/tmp/repo")
        assert results == []

    @patch("relace_mcp.repo.local.backend.codanna._run_cli_json")
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

    @patch("relace_mcp.repo.local.backend.codanna._run_cli_json")
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

    @patch("relace_mcp.repo.local.backend.codanna._run_cli_json")
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
