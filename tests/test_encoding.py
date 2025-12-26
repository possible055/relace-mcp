"""Tests for encoding detection and project encoding handling."""

from pathlib import Path
from unittest.mock import patch

from relace_mcp.tools.apply.encoding import (
    detect_project_encoding,
)
from relace_mcp.tools.apply.file_io import (
    get_project_encoding,
    read_text_with_fallback,
    set_project_encoding,
)


class TestDetectProjectEncoding:
    """Test project encoding detection."""

    def test_returns_none_for_utf8_only_project(self, tmp_path: Path) -> None:
        """Should return None when project only has UTF-8 files."""
        # Create UTF-8 files
        (tmp_path / "main.py").write_text("# UTF-8 file\nprint('hello')\n", encoding="utf-8")
        (tmp_path / "utils.py").write_text("def foo(): pass\n", encoding="utf-8")

        result = detect_project_encoding(tmp_path, sample_limit=10)
        assert result is None

    def test_detects_gbk_dominant_project(self, tmp_path: Path) -> None:
        """Should detect GBK when majority of files use it."""
        # Create GBK files with Chinese content that is clearly simplified Chinese
        # Use characters that are unique to GB encoding (not in Big5)
        for i in range(5):
            # 简体 characters like 国、学、电 are GBK-specific
            content = f"# 简体中文注释 国学电脑 {i}\ndef func_{i}(): pass\n# 这是测试文件\n"
            (tmp_path / f"file_{i}.py").write_bytes(content.encode("gbk"))

        result = detect_project_encoding(tmp_path, sample_limit=10)
        # charset_normalizer may detect as gb2312, gbk, or gb18030
        # In some cases with short content it might detect as big5 due to overlap
        assert result is not None
        # Accept any CJK encoding detection as valid (the key is detecting non-UTF-8)
        assert result.lower() in ("gbk", "gb2312", "gb18030", "big5")

    def test_detects_big5_project(self, tmp_path: Path) -> None:
        """Should detect Big5 for Traditional Chinese projects."""
        # Create Big5 files with Traditional Chinese content
        for i in range(3):
            content = f"# 繁體中文註解 {i}\ndef func_{i}(): pass\n"
            (tmp_path / f"file_{i}.py").write_bytes(content.encode("big5"))

        result = detect_project_encoding(tmp_path, sample_limit=10)
        assert result is not None
        assert "big5" in result.lower()

    def test_skips_hidden_directories(self, tmp_path: Path) -> None:
        """Should skip files in hidden directories."""
        # Create GBK file in hidden directory
        hidden_dir = tmp_path / ".hidden"
        hidden_dir.mkdir()
        (hidden_dir / "file.py").write_bytes("# 中文".encode("gbk"))

        # Create UTF-8 file in visible directory
        (tmp_path / "main.py").write_text("# UTF-8\n", encoding="utf-8")

        result = detect_project_encoding(tmp_path, sample_limit=10)
        # Should only see UTF-8 file, so return None
        assert result is None

    def test_skips_node_modules(self, tmp_path: Path) -> None:
        """Should skip node_modules directory."""
        # Create GBK files in node_modules
        nm_dir = tmp_path / "node_modules" / "some_pkg"
        nm_dir.mkdir(parents=True)
        (nm_dir / "index.js").write_bytes("// 中文".encode("gbk"))

        # Create UTF-8 file in src
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        (src_dir / "main.py").write_text("# UTF-8\n", encoding="utf-8")

        result = detect_project_encoding(tmp_path, sample_limit=10)
        assert result is None

    def test_respects_sample_limit(self, tmp_path: Path) -> None:
        """Should stop sampling after reaching limit."""
        # Create many files
        for i in range(50):
            (tmp_path / f"file_{i}.py").write_text(f"# file {i}\n", encoding="utf-8")

        # With low sample limit, should still work
        result = detect_project_encoding(tmp_path, sample_limit=5)
        assert result is None  # All UTF-8

    def test_empty_directory_returns_none(self, tmp_path: Path) -> None:
        """Should return None for empty directory."""
        result = detect_project_encoding(tmp_path, sample_limit=10)
        assert result is None

    def test_only_samples_known_extensions(self, tmp_path: Path) -> None:
        """Should only sample files with known text extensions."""
        # Create GBK file with unknown extension
        (tmp_path / "data.xyz").write_bytes("# 中文".encode("gbk"))
        # Create UTF-8 file with known extension
        (tmp_path / "main.py").write_text("# UTF-8\n", encoding="utf-8")

        result = detect_project_encoding(tmp_path, sample_limit=10)
        assert result is None  # Should only see UTF-8 .py file


class TestSetProjectEncoding:
    """Test project encoding setter/getter."""

    def teardown_method(self) -> None:
        """Reset project encoding after each test."""
        set_project_encoding(None)

    def test_set_and_get_encoding(self) -> None:
        """Should set and retrieve project encoding."""
        set_project_encoding("gbk")
        assert get_project_encoding() == "gbk"

    def test_normalizes_to_lowercase(self) -> None:
        """Should normalize encoding to lowercase."""
        set_project_encoding("GBK")
        assert get_project_encoding() == "gbk"

        set_project_encoding("Big5")
        assert get_project_encoding() == "big5"

    def test_none_clears_encoding(self) -> None:
        """Should clear encoding when set to None."""
        set_project_encoding("gbk")
        set_project_encoding(None)
        assert get_project_encoding() is None


class TestReadTextWithFallbackProjectEncoding:
    """Test read_text_with_fallback with project encoding."""

    def teardown_method(self) -> None:
        """Reset project encoding after each test."""
        set_project_encoding(None)

    def test_reads_gbk_file_with_project_encoding(self, tmp_path: Path) -> None:
        """Should successfully read GBK file when project encoding is set."""
        gbk_file = tmp_path / "test.py"
        content = "# 这是中文注释\nprint('你好')\n"
        gbk_file.write_bytes(content.encode("gbk"))

        set_project_encoding("gbk")
        read_content, detected_enc = read_text_with_fallback(gbk_file)

        assert read_content == content
        assert detected_enc == "gbk"

    def test_reads_big5_file_with_project_encoding(self, tmp_path: Path) -> None:
        """Should successfully read Big5 file when project encoding is set."""
        big5_file = tmp_path / "test.py"
        content = "# 繁體中文\nprint('世界')\n"
        big5_file.write_bytes(content.encode("big5"))

        set_project_encoding("big5")
        read_content, detected_enc = read_text_with_fallback(big5_file)

        assert read_content == content
        assert detected_enc == "big5"

    def test_falls_back_to_utf8_for_ascii(self, tmp_path: Path) -> None:
        """ASCII files should be detected as UTF-8."""
        ascii_file = tmp_path / "test.py"
        content = "# ASCII only\nprint('hello')\n"
        # Use binary write to avoid platform-dependent newline conversion
        ascii_file.write_bytes(content.encode("utf-8"))

        # Even with GBK as project encoding, ASCII works with both
        set_project_encoding("gbk")
        read_content, detected_enc = read_text_with_fallback(ascii_file)

        assert read_content == content
        # GBK can decode ASCII, so it will be detected as GBK (since it's tried first)
        assert detected_enc in ("gbk", "utf-8")


class TestEnvironmentVariableEncoding:
    """Test RELACE_DEFAULT_ENCODING environment variable."""

    def test_config_picks_up_env_encoding(self) -> None:
        """Should read encoding from environment variable."""
        with patch.dict("os.environ", {"RELACE_DEFAULT_ENCODING": "big5"}):
            # Need to reload to pick up patched env
            import importlib

            import relace_mcp.config.settings as settings_module

            importlib.reload(settings_module)
            assert settings_module.RELACE_DEFAULT_ENCODING == "big5"

    def test_config_defaults_to_none(self) -> None:
        """Should default to None when env var not set."""
        with patch.dict("os.environ", {}, clear=False):
            # Remove the env var if it exists
            import os

            os.environ.pop("RELACE_DEFAULT_ENCODING", None)
            import importlib

            import relace_mcp.config.settings as settings_module

            importlib.reload(settings_module)
            assert settings_module.RELACE_DEFAULT_ENCODING is None
