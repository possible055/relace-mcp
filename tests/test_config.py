from pathlib import Path

import pytest

from relace_mcp.config import RelaceConfig


class TestRelaceConfigFromEnv:
    def test_missing_api_key_raises(self, clean_env: None) -> None:
        with pytest.raises(RuntimeError, match="RELACE_API_KEY is not set"):
            RelaceConfig.from_env()

    def test_loads_api_key(
        self, clean_env: None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setenv("RELACE_API_KEY", "my-secret-key")
        monkeypatch.setenv("RELACE_BASE_DIR", str(tmp_path))
        config = RelaceConfig.from_env()
        assert config.api_key == "my-secret-key"


class TestRelaceConfigBaseDir:
    def test_missing_base_dir_returns_none(
        self, clean_env: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When RELACE_BASE_DIR is not set, base_dir should be None (resolved at runtime)."""
        monkeypatch.setenv("RELACE_API_KEY", "test-key")
        config = RelaceConfig.from_env()
        assert config.base_dir is None

    def test_base_dir_is_resolved_to_absolute(
        self, clean_env: None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setenv("RELACE_API_KEY", "test-key")
        monkeypatch.setenv("RELACE_BASE_DIR", str(tmp_path))
        config = RelaceConfig.from_env()
        assert config.base_dir == str(tmp_path.resolve())

    def test_nonexistent_base_dir_raises(
        self, clean_env: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("RELACE_API_KEY", "test-key")
        monkeypatch.setenv("RELACE_BASE_DIR", "/nonexistent/path")
        with pytest.raises(RuntimeError, match="does not exist"):
            RelaceConfig.from_env()


class TestRelaceConfigFrozen:
    def test_config_is_frozen(self, mock_config: RelaceConfig) -> None:
        with pytest.raises(AttributeError):
            mock_config.api_key = "new-key"  # type: ignore[misc]
