import os
import re
from dataclasses import dataclass
from pathlib import Path

import pytest

from relace_mcp.tools.search.harness.observed import ObservedFilesMixin


@dataclass
class _Cfg:
    base_dir: str | None


class _DummyObserved(ObservedFilesMixin):
    def __init__(self, base_dir: str) -> None:
        self._config = _Cfg(base_dir=base_dir)
        self._observed_files: dict[str, list[list[int]]] = {}
        self._view_line_re = re.compile(r"^(\d+)\s")


def test_record_grep_results_uses_first_line_number(tmp_path: Path) -> None:
    dummy = _DummyObserved(str(tmp_path))
    dummy._record_grep_results("foo.py:12:bar:34:baz")

    expected = str((tmp_path / "foo.py").resolve())
    assert dummy._observed_files == {expected: [[12, 12]]}


def test_record_grep_results_strips_dot_slash_prefix(tmp_path: Path) -> None:
    dummy = _DummyObserved(str(tmp_path))
    dummy._record_grep_results("./src/main.py:1:hello")

    expected = str((tmp_path / "src" / "main.py").resolve())
    assert dummy._observed_files == {expected: [[1, 1]]}


@pytest.mark.skipif(os.name == "nt", reason="Windows treats ':' specially in paths")
def test_record_grep_results_handles_colon_in_path(tmp_path: Path) -> None:
    dummy = _DummyObserved(str(tmp_path))
    dummy._record_grep_results("foo:bar.py:7:hello")

    expected = str((tmp_path / "foo:bar.py").resolve())
    assert dummy._observed_files == {expected: [[7, 7]]}
