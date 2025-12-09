from pathlib import Path

import pytest

from relace_mcp.config import DEFAULT_LOG_PATH, RelaceConfig


class TestRelaceConfigFromEnv:
    """Test RelaceConfig.from_env() behavior."""

    def test_missing_api_key_raises(self, clean_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should raise RuntimeError when RELACE_API_KEY is not set."""
        with pytest.raises(RuntimeError, match="RELACE_API_KEY is not set"):
            RelaceConfig.from_env()

    def test_loads_api_key(self, clean_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should load API key from environment."""
        monkeypatch.setenv("RELACE_API_KEY", "my-secret-key")
        config = RelaceConfig.from_env()
        assert config.api_key == "my-secret-key"

    def test_default_endpoint(self, clean_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should use default endpoint when not specified."""
        monkeypatch.setenv("RELACE_API_KEY", "test-key")
        config = RelaceConfig.from_env()
        assert config.endpoint == "https://instantapply.endpoint.relace.run/v1/code/apply"

    def test_custom_endpoint(self, clean_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should use custom endpoint when specified."""
        monkeypatch.setenv("RELACE_API_KEY", "test-key")
        monkeypatch.setenv("RELACE_ENDPOINT", "https://custom.api/v2")
        config = RelaceConfig.from_env()
        assert config.endpoint == "https://custom.api/v2"

    def test_default_model(self, clean_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should use default model when not specified."""
        monkeypatch.setenv("RELACE_API_KEY", "test-key")
        config = RelaceConfig.from_env()
        assert config.model == "relace-apply-3"

    def test_custom_model(self, clean_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should use custom model when specified."""
        monkeypatch.setenv("RELACE_API_KEY", "test-key")
        monkeypatch.setenv("RELACE_MODEL", "relace-apply-4")
        config = RelaceConfig.from_env()
        assert config.model == "relace-apply-4"

    def test_default_log_path(self, clean_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should use default absolute log path when not specified."""
        monkeypatch.setenv("RELACE_API_KEY", "test-key")
        config = RelaceConfig.from_env()
        assert config.log_path == DEFAULT_LOG_PATH
        assert Path(config.log_path).is_absolute()

    def test_custom_log_path(self, clean_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should use custom log path when specified."""
        monkeypatch.setenv("RELACE_API_KEY", "test-key")
        monkeypatch.setenv("RELACE_LOG_PATH", "/var/log/relace.log")
        config = RelaceConfig.from_env()
        assert config.log_path == "/var/log/relace.log"


class TestRelaceConfigTimeout:
    """Test timeout configuration behavior."""

    def test_default_timeout(self, clean_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should use 60 second default timeout."""
        monkeypatch.setenv("RELACE_API_KEY", "test-key")
        config = RelaceConfig.from_env()
        assert config.timeout == 60.0

    def test_custom_timeout(self, clean_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should parse custom timeout value."""
        monkeypatch.setenv("RELACE_API_KEY", "test-key")
        monkeypatch.setenv("RELACE_TIMEOUT", "120.5")
        config = RelaceConfig.from_env()
        assert config.timeout == 120.5

    def test_invalid_timeout_falls_back_to_default(
        self, clean_env: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Should fall back to default timeout when value is invalid."""
        monkeypatch.setenv("RELACE_API_KEY", "test-key")
        monkeypatch.setenv("RELACE_TIMEOUT", "not-a-number")
        config = RelaceConfig.from_env()
        assert config.timeout == 60.0

    def test_negative_timeout_falls_back_to_default(
        self, clean_env: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Should fall back to default timeout when value is negative."""
        monkeypatch.setenv("RELACE_API_KEY", "test-key")
        monkeypatch.setenv("RELACE_TIMEOUT", "-10")
        config = RelaceConfig.from_env()
        assert config.timeout == 60.0

    def test_zero_timeout_falls_back_to_default(
        self, clean_env: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Should fall back to default timeout when value is zero."""
        monkeypatch.setenv("RELACE_API_KEY", "test-key")
        monkeypatch.setenv("RELACE_TIMEOUT", "0")
        config = RelaceConfig.from_env()
        assert config.timeout == 60.0


class TestRelaceConfigBaseDir:
    """Test base_dir configuration behavior."""

    def test_default_base_dir_is_cwd(
        self, clean_env: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Should default base_dir to current working directory."""
        monkeypatch.setenv("RELACE_API_KEY", "test-key")
        config = RelaceConfig.from_env()
        import os

        assert config.base_dir == os.getcwd()

    def test_base_dir_is_resolved_to_absolute(
        self,
        clean_env: None,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """Should resolve base_dir to absolute path."""
        monkeypatch.setenv("RELACE_API_KEY", "test-key")
        monkeypatch.setenv("RELACE_BASE_DIR", str(tmp_path))
        config = RelaceConfig.from_env()
        assert config.base_dir == str(tmp_path.resolve())

    def test_base_dir_with_relative_path(
        self, clean_env: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Should resolve relative base_dir to absolute path."""
        monkeypatch.setenv("RELACE_API_KEY", "test-key")
        monkeypatch.setenv("RELACE_BASE_DIR", ".")
        config = RelaceConfig.from_env()
        # 確保是絕對路徑
        assert config.base_dir is not None
        assert Path(config.base_dir).is_absolute()


class TestRelaceConfigStrictMode:
    """Test strict_mode configuration behavior."""

    def test_strict_mode_disabled_by_default(
        self, clean_env: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Should have strict_mode disabled by default."""
        monkeypatch.setenv("RELACE_API_KEY", "test-key")
        config = RelaceConfig.from_env()
        assert config.strict_mode is False

    def test_strict_mode_enabled(
        self, clean_env: None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Should enable strict_mode when set to true."""
        monkeypatch.setenv("RELACE_API_KEY", "test-key")
        monkeypatch.setenv("RELACE_BASE_DIR", str(tmp_path))
        monkeypatch.setenv("RELACE_STRICT_MODE", "true")
        config = RelaceConfig.from_env()
        assert config.strict_mode is True

    def test_strict_mode_requires_base_dir(
        self, clean_env: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Should raise when strict_mode is enabled but base_dir not set."""
        monkeypatch.setenv("RELACE_API_KEY", "test-key")
        monkeypatch.setenv("RELACE_STRICT_MODE", "true")
        with pytest.raises(RuntimeError, match="RELACE_BASE_DIR is not set"):
            RelaceConfig.from_env()


class TestRelaceConfigRetry:
    """Test retry configuration behavior."""

    def test_default_max_retries(self, clean_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should use 3 as default max_retries."""
        monkeypatch.setenv("RELACE_API_KEY", "test-key")
        config = RelaceConfig.from_env()
        assert config.max_retries == 3

    def test_custom_max_retries(self, clean_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should parse custom max_retries value."""
        monkeypatch.setenv("RELACE_API_KEY", "test-key")
        monkeypatch.setenv("RELACE_MAX_RETRIES", "5")
        config = RelaceConfig.from_env()
        assert config.max_retries == 5

    def test_default_retry_base_delay(
        self, clean_env: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Should use 1.0 as default retry_base_delay."""
        monkeypatch.setenv("RELACE_API_KEY", "test-key")
        config = RelaceConfig.from_env()
        assert config.retry_base_delay == 1.0

    def test_custom_retry_base_delay(
        self, clean_env: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Should parse custom retry_base_delay value."""
        monkeypatch.setenv("RELACE_API_KEY", "test-key")
        monkeypatch.setenv("RELACE_RETRY_BASE_DELAY", "2.5")
        config = RelaceConfig.from_env()
        assert config.retry_base_delay == 2.5


class TestRelaceConfigFrozen:
    """Test that RelaceConfig is immutable."""

    def test_config_is_frozen(self, mock_config: RelaceConfig) -> None:
        """Should raise error when trying to modify config."""
        with pytest.raises(AttributeError):
            mock_config.api_key = "new-key"  # type: ignore[misc]

    def test_config_is_hashable(self, mock_config: RelaceConfig) -> None:
        """Frozen dataclass should be hashable."""
        # Should not raise
        hash(mock_config)


class TestRelaceConfigFullEnv:
    """Test with all environment variables set."""

    def test_loads_all_custom_values(self, full_env: dict[str, str], tmp_path: Path) -> None:
        """Should load all custom values from environment."""
        config = RelaceConfig.from_env()

        assert config.api_key == "env-test-api-key"
        assert config.endpoint == "https://env-test.relace.run/api"
        assert config.model == "relace-apply-test"
        assert config.log_path == str(tmp_path / "env_test.log")
        assert config.timeout == 45.0
        assert config.base_dir is not None
        assert Path(config.base_dir).resolve() == tmp_path.resolve()
        assert config.strict_mode is False
        assert config.max_retries == 5
        assert config.retry_base_delay == 2.0
