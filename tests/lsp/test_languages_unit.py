from pathlib import Path

import pytest

from relace_mcp.lsp.languages import clear_lsp_cache, get_lsp_languages


class TestGetLspLanguages:
    def test_detects_languages_from_files(self, tmp_path: Path) -> None:
        clear_lsp_cache(tmp_path)

        (tmp_path / "a.py").write_text("print('x')\n")
        (tmp_path / "b.ts").write_text("export const x = 1\n")
        (tmp_path / "c.go").write_text("package main\n")
        (tmp_path / "d.rs").write_text("fn main() {}\n")

        languages = get_lsp_languages(tmp_path)
        assert "python" in languages
        assert "typescript" in languages
        assert "go" in languages
        assert "rust" in languages

    def test_ignores_node_modules(self, tmp_path: Path) -> None:
        clear_lsp_cache(tmp_path)

        (tmp_path / "node_modules").mkdir()
        (tmp_path / "node_modules" / "x.ts").write_text("export {}\n")

        languages = get_lsp_languages(tmp_path)
        assert "typescript" not in languages


class TestDetectAvailableLspServers:
    def test_detects_installed_servers(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should detect servers that are available in PATH."""
        from relace_mcp.lsp.languages import detect_available_lsp_servers

        # Mock shutil.which to simulate basedpyright being installed
        def mock_which(cmd: str) -> str | None:
            if cmd == "basedpyright-langserver":
                return "/usr/bin/basedpyright-langserver"
            return None

        monkeypatch.setattr("shutil.which", mock_which)

        result = detect_available_lsp_servers()
        assert "python" in result

    def test_returns_empty_when_no_servers(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should return empty set when no LSP servers are installed."""
        from relace_mcp.lsp.languages import detect_available_lsp_servers

        monkeypatch.setattr("shutil.which", lambda cmd: None)

        result = detect_available_lsp_servers()
        assert result == frozenset()
