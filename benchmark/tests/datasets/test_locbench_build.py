import sys
from pathlib import Path

import pytest

# Add project root to path for benchmark imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from benchmark.cli.build_locbench import (  # noqa: E402
    _build_function_gt_for_file,
    _extract_changed_lines_by_file,
)


class TestExtractChangedLinesByFile:
    def test_records_deleted_and_insertion_anchor(self) -> None:
        patch = """diff --git a/foo.py b/foo.py
index 1111111..2222222 100644
--- a/foo.py
+++ b/foo.py
@@ -10,3 +10,4 @@ def foo():
 line10
-line11
+line11_new
+line12_added
 line13
"""
        changed = _extract_changed_lines_by_file(patch)
        assert changed == {"foo.py": {11}}

    def test_pure_addition_anchors_to_start(self) -> None:
        patch = """diff --git a/foo.py b/foo.py
--- a/foo.py
+++ b/foo.py
@@ -1,0 +1,2 @@
+aaa
+bbb
"""
        changed = _extract_changed_lines_by_file(patch)
        assert changed == {"foo.py": {1}}


class TestBuildFunctionGtForFile:
    def test_builds_function_scopes_and_target_ranges(self, tmp_path: Path) -> None:
        repo_path = tmp_path
        file_path = repo_path / "mod.py"
        file_path.write_text(
            "def foo():\n"
            "    a = 1\n"
            "    return a\n"
            "\n"
            "class Bar:\n"
            "    def baz(self):\n"
            "        b = 2\n"
            "        return b\n",
            encoding="utf-8",
        )

        entries = _build_function_gt_for_file(
            repo_path=repo_path,
            rel_path="mod.py",
            changed_lines={2, 7},
        )
        assert len(entries) == 2

        by_name = {e["function"]: e for e in entries}
        assert "foo" in by_name
        assert "baz" in by_name

        foo = by_name["foo"]
        assert foo["path"] == "mod.py"
        assert foo["class"] is None
        assert foo["range"][0] == 1
        assert foo["range"][1] >= foo["range"][0]
        assert [2, 2] in foo["target_ranges"]
        assert foo["signature"].startswith("def foo(")

        baz = by_name["baz"]
        assert baz["path"] == "mod.py"
        assert baz["class"] == "Bar"
        assert baz["range"][0] == 6
        assert baz["range"][1] >= baz["range"][0]
        assert [7, 7] in baz["target_ranges"]
        assert baz["signature"].startswith("def baz(")


@pytest.mark.parametrize(
    "patch",
    [
        "",
        "diff --git a/a.py b/a.py\n--- /dev/null\n+++ b/a.py\n@@ -0,0 +1,1 @@\n+print('x')\n",
    ],
)
def test_extract_changed_lines_handles_empty_and_new_files(patch: str) -> None:
    changed = _extract_changed_lines_by_file(patch)
    assert isinstance(changed, dict)
