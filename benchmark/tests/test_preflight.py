from dataclasses import dataclass
from unittest.mock import patch

import pytest

from benchmark.runner.preflight import check_retrieval_backend

_GIT_HEAD = "abcdef1234567890abcdef1234567890abcdef12"


# ── helpers ──────────────────────────────────────────────────────────────────


@dataclass
class _FakeSyncState:
    git_head_sha: str = _GIT_HEAD


def _patch_git_head(head: str = _GIT_HEAD):
    return patch(
        "benchmark.runner.preflight.get_current_git_info",
        return_value=("main", head),
    )


def _patch_indexed_head(head: str | None):
    return patch(
        "benchmark.runner.preflight._read_indexed_head",
        return_value=head,
    )


def _patch_sync_state(state=None):
    return patch(
        "benchmark.runner.preflight.load_sync_state",
        return_value=state,
    )


# ── backend=none ─────────────────────────────────────────────────────────────


def test_none_backend_returns_immediately():
    info = check_retrieval_backend("none", "/tmp/repo")
    assert info == {"backend": "none"}


# ── backend=chunkhound / codanna (local CLI) ────────────────────────────────


@pytest.mark.parametrize("backend", ["chunkhound", "codanna"])
def test_local_cli_not_found(backend):
    with patch("benchmark.runner.preflight.shutil.which", return_value=None):
        with pytest.raises(RuntimeError, match="CLI not found"):
            check_retrieval_backend(backend, "/tmp/repo")


@pytest.mark.parametrize("backend", ["chunkhound", "codanna"])
def test_local_index_missing(backend):
    with (
        patch("benchmark.runner.preflight.shutil.which", return_value="/usr/bin/" + backend),
        _patch_git_head(),
        _patch_indexed_head(None),
    ):
        with pytest.raises(RuntimeError, match="index not found"):
            check_retrieval_backend(backend, "/tmp/repo")


@pytest.mark.parametrize("backend", ["chunkhound", "codanna"])
def test_local_index_stale(backend):
    with (
        patch("benchmark.runner.preflight.shutil.which", return_value="/usr/bin/" + backend),
        _patch_git_head(_GIT_HEAD),
        _patch_indexed_head("0000000000000000000000000000000000000000"),
    ):
        with pytest.raises(RuntimeError, match="index stale"):
            check_retrieval_backend(backend, "/tmp/repo")


@pytest.mark.parametrize("backend", ["chunkhound", "codanna"])
def test_local_happy_path(backend):
    with (
        patch("benchmark.runner.preflight.shutil.which", return_value="/usr/bin/" + backend),
        _patch_git_head(_GIT_HEAD),
        _patch_indexed_head(_GIT_HEAD),
    ):
        info = check_retrieval_backend(backend, "/tmp/repo")
        assert info["backend"] == backend
        assert info["cli_ok"] is True
        assert info["index_ok"] is True
        assert info["stale"] is False
        assert "error" not in info


# ── backend=relace ───────────────────────────────────────────────────────────


def test_relace_no_sync_state():
    with _patch_git_head(), _patch_sync_state(None):
        with pytest.raises(RuntimeError, match="No cloud sync state"):
            check_retrieval_backend("relace", "/tmp/repo")


def test_relace_stale_sync():
    stale_state = _FakeSyncState(git_head_sha="0000000000000000000000000000000000000000")
    with _patch_git_head(_GIT_HEAD), _patch_sync_state(stale_state):
        with pytest.raises(RuntimeError, match="Cloud sync stale"):
            check_retrieval_backend("relace", "/tmp/repo")


def test_relace_happy_path():
    state = _FakeSyncState(git_head_sha=_GIT_HEAD)
    with _patch_git_head(_GIT_HEAD), _patch_sync_state(state):
        info = check_retrieval_backend("relace", "/tmp/repo")
        assert info["backend"] == "relace"
        assert info["stale"] is False
        assert "error" not in info


# ── backend=auto ─────────────────────────────────────────────────────────────


def test_auto_resolves_to_local_cli():
    def fake_which(name):
        return "/usr/bin/codanna" if name == "codanna" else None

    with (
        patch("benchmark.runner.preflight.shutil.which", side_effect=fake_which),
        _patch_git_head(_GIT_HEAD),
        _patch_indexed_head(_GIT_HEAD),
    ):
        info = check_retrieval_backend("auto", "/tmp/repo")
        assert info["backend"] == "codanna"


def test_auto_falls_back_to_relace():
    state = _FakeSyncState(git_head_sha=_GIT_HEAD)
    with (
        patch("benchmark.runner.preflight.shutil.which", return_value=None),
        _patch_git_head(_GIT_HEAD),
        _patch_sync_state(state),
    ):
        info = check_retrieval_backend("auto", "/tmp/repo")
        assert info["backend"] == "relace"
