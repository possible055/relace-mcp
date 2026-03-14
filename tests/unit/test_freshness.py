from unittest.mock import patch

from relace_mcp.repo.freshness import classify_local_index_freshness


class TestClassifyLocalIndexFreshness:
    def test_missing_when_index_dir_absent(self, tmp_path):
        result = classify_local_index_freshness(str(tmp_path), "codanna")
        assert result.freshness == "missing"
        assert result.hints_usable is False
        assert result.reason == "index_dir_missing"

    def test_stale_when_dir_exists_but_marker_absent(self, tmp_path):
        (tmp_path / ".codanna").mkdir()
        result = classify_local_index_freshness(str(tmp_path), "codanna")
        assert result.freshness == "stale"
        assert result.hints_usable is True
        assert result.refresh_recommended is True
        assert result.reason == "last_indexed_head_missing"

    def test_fresh_when_marker_matches_head(self, tmp_path):
        codanna_dir = tmp_path / ".codanna"
        codanna_dir.mkdir()
        marker = codanna_dir / "last_indexed_head"
        marker.write_text("abc123")

        with (
            patch(
                "relace_mcp.repo.freshness.get_current_git_info", return_value=("main", "abc123")
            ),
            patch("relace_mcp.repo.freshness.is_git_dirty", return_value=False),
        ):
            result = classify_local_index_freshness(str(tmp_path), "codanna")

        assert result.freshness == "fresh"
        assert result.hints_usable is True

    def test_stale_when_marker_differs_from_head(self, tmp_path):
        codanna_dir = tmp_path / ".codanna"
        codanna_dir.mkdir()
        marker = codanna_dir / "last_indexed_head"
        marker.write_text("oldhead")

        with (
            patch(
                "relace_mcp.repo.freshness.get_current_git_info", return_value=("main", "newhead")
            ),
            patch("relace_mcp.repo.freshness.is_git_dirty", return_value=False),
        ):
            result = classify_local_index_freshness(str(tmp_path), "codanna")

        assert result.freshness == "stale"
        assert result.hints_usable is True
        assert result.reason == "git_head_changed"

    def test_chunkhound_stale_when_dir_exists_but_marker_absent(self, tmp_path):
        (tmp_path / ".chunkhound").mkdir()
        result = classify_local_index_freshness(str(tmp_path), "chunkhound")
        assert result.freshness == "stale"
        assert result.hints_usable is True
        assert result.reason == "last_indexed_head_missing"

    def test_missing_when_chunkhound_dir_absent(self, tmp_path):
        result = classify_local_index_freshness(str(tmp_path), "chunkhound")
        assert result.freshness == "missing"
        assert result.hints_usable is False
