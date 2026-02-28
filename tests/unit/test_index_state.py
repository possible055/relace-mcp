import sys
import time
from pathlib import Path

import pytest

from relace_mcp.repo.backends.index_state import (
    _CHUNKHOUND_DIRTY_TS_FILE,
    _CHUNKHOUND_HEAD_FILE,
    _CODANNA_DIRTY_TS_FILE,
    _CODANNA_HEAD_FILE,
    _read_dirty_ts,
    _read_indexed_head,
    _write_dirty_ts,
    _write_indexed_head,
)


class TestReadIndexedHead:
    def test_returns_content_when_file_exists(self, tmp_path: Path) -> None:
        head_file = _CHUNKHOUND_HEAD_FILE
        path = tmp_path / head_file
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("abc123\n")
        assert _read_indexed_head(str(tmp_path), head_file) == "abc123"

    def test_returns_none_when_file_missing(self, tmp_path: Path) -> None:
        assert _read_indexed_head(str(tmp_path), _CHUNKHOUND_HEAD_FILE) is None

    def test_returns_empty_string_for_empty_file(self, tmp_path: Path) -> None:
        head_file = _CODANNA_HEAD_FILE
        path = tmp_path / head_file
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("")
        assert _read_indexed_head(str(tmp_path), head_file) == ""

    def test_strips_whitespace(self, tmp_path: Path) -> None:
        head_file = _CHUNKHOUND_HEAD_FILE
        path = tmp_path / head_file
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("  deadbeef  \n")
        assert _read_indexed_head(str(tmp_path), head_file) == "deadbeef"


class TestWriteIndexedHead:
    def test_creates_dirs_and_writes(self, tmp_path: Path) -> None:
        head_file = _CHUNKHOUND_HEAD_FILE
        _write_indexed_head(str(tmp_path), "abc123", head_file)
        path = tmp_path / head_file
        assert path.exists()
        assert path.read_text() == "abc123"

    def test_overwrites_existing(self, tmp_path: Path) -> None:
        head_file = _CODANNA_HEAD_FILE
        _write_indexed_head(str(tmp_path), "old", head_file)
        _write_indexed_head(str(tmp_path), "new", head_file)
        path = tmp_path / head_file
        assert path.read_text() == "new"

    def test_roundtrip_read_write(self, tmp_path: Path) -> None:
        head_file = _CHUNKHOUND_HEAD_FILE
        _write_indexed_head(str(tmp_path), "round_trip_value", head_file)
        assert _read_indexed_head(str(tmp_path), head_file) == "round_trip_value"


class TestReadDirtyTs:
    def test_returns_float_when_valid(self, tmp_path: Path) -> None:
        ts_file = _CHUNKHOUND_DIRTY_TS_FILE
        path = tmp_path / ts_file
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("1700000000.123")
        result = _read_dirty_ts(str(tmp_path), ts_file)
        assert result is not None
        assert abs(result - 1700000000.123) < 0.001

    def test_returns_none_when_file_missing(self, tmp_path: Path) -> None:
        assert _read_dirty_ts(str(tmp_path), _CODANNA_DIRTY_TS_FILE) is None

    def test_returns_none_for_invalid_content(self, tmp_path: Path) -> None:
        ts_file = _CHUNKHOUND_DIRTY_TS_FILE
        path = tmp_path / ts_file
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("not-a-number")
        assert _read_dirty_ts(str(tmp_path), ts_file) is None

    def test_returns_none_for_empty_file(self, tmp_path: Path) -> None:
        ts_file = _CODANNA_DIRTY_TS_FILE
        path = tmp_path / ts_file
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("")
        assert _read_dirty_ts(str(tmp_path), ts_file) is None


class TestWriteDirtyTs:
    def test_creates_dirs_and_writes_timestamp(self, tmp_path: Path) -> None:
        ts_file = _CHUNKHOUND_DIRTY_TS_FILE
        before = time.time()
        _write_dirty_ts(str(tmp_path), ts_file)
        after = time.time()

        path = tmp_path / ts_file
        assert path.exists()
        written_ts = float(path.read_text())
        assert before <= written_ts <= after

    def test_roundtrip_write_read(self, tmp_path: Path) -> None:
        ts_file = _CODANNA_DIRTY_TS_FILE
        _write_dirty_ts(str(tmp_path), ts_file)
        result = _read_dirty_ts(str(tmp_path), ts_file)
        assert result is not None
        # Should be a recent timestamp
        assert abs(result - time.time()) < 5


class TestReadTextSafe:
    """Tests for _read_text_safe used by indexing_status."""

    def test_returns_content_for_regular_file(self, tmp_path: Path) -> None:
        from relace_mcp.tools import _read_text_safe

        f = tmp_path / "test.txt"
        f.write_text("hello")
        assert _read_text_safe(f) == "hello"

    def test_returns_none_for_missing_file(self, tmp_path: Path) -> None:
        from relace_mcp.tools import _read_text_safe

        assert _read_text_safe(tmp_path / "missing.txt") is None

    def test_returns_none_for_empty_file(self, tmp_path: Path) -> None:
        from relace_mcp.tools import _read_text_safe

        f = tmp_path / "empty.txt"
        f.write_text("")
        assert _read_text_safe(f) is None

    @pytest.mark.skipif(sys.platform == "win32", reason="symlinks may require privileges")
    def test_returns_none_for_symlink(self, tmp_path: Path) -> None:
        from relace_mcp.tools import _read_text_safe

        target = tmp_path / "target.txt"
        target.write_text("secret")
        link = tmp_path / "link.txt"
        link.symlink_to(target)
        assert _read_text_safe(link) is None
