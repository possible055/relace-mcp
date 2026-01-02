import logging
import os
from dataclasses import dataclass

from .compat import getenv_with_fallback
from .settings import DEFAULT_PROVIDER_BASE_URLS, OPENAI_PROVIDER, RELACE_PROVIDER

logger = logging.getLogger(__name__)


def _normalize_base_url(base_url: str) -> str:
    base_url = base_url.strip()
    if not base_url:
        return base_url

    base_url = base_url.rstrip("/")
    if base_url.endswith("/chat/completions"):
        base_url = base_url[: -len("/chat/completions")].rstrip("/")
    return base_url


def _derive_display_name(provider: str) -> str:
    if provider == RELACE_PROVIDER:
        return "Relace"
    return provider.replace("_", " ").title()


@dataclass(frozen=True)
class ProviderConfig:
    provider: str
    api_compat: str
    base_url: str
    model: str
    api_key: str
    timeout_seconds: float
    display_name: str


def create_provider_config(
    prefix: str,
    *,
    default_base_url: str,
    default_model: str,
    default_timeout: float,
    relace_api_key: str,
) -> ProviderConfig:
    """Create provider configuration from environment variables.

    Reads and validates all provider-related environment variables at config layer.
    Supports deprecated RELACE_* prefixed variables for backward compatibility.

    Args:
        prefix: Environment variable prefix (e.g., "SEARCH" or "APPLY").
        default_base_url: Default base URL if not specified.
        default_model: Default model if not specified.
        default_timeout: Default timeout in seconds.
        relace_api_key: API key from RelaceConfig (used when provider is relace).

    Returns:
        Validated ProviderConfig ready for use.

    Raises:
        RuntimeError: Configuration validation failed (missing API key, invalid combo).
    """
    # Environment variable names
    provider_env = f"{prefix}_PROVIDER"
    base_url_env = f"{prefix}_ENDPOINT"
    model_env = f"{prefix}_MODEL"
    api_key_env = f"{prefix}_API_KEY"

    # Deprecated names (RELACE_* prefix)
    deprecated_provider_env = f"RELACE_{prefix}_PROVIDER"
    deprecated_base_url_env = f"RELACE_{prefix}_ENDPOINT"
    deprecated_model_env = f"RELACE_{prefix}_MODEL"
    deprecated_api_key_env = f"RELACE_{prefix}_API_KEY"

    # Parse provider
    raw_provider = getenv_with_fallback(provider_env, deprecated_provider_env).strip()
    provider = (raw_provider if raw_provider else RELACE_PROVIDER).lower()

    # Derive API compatibility mode
    api_compat = RELACE_PROVIDER if provider == RELACE_PROVIDER else OPENAI_PROVIDER

    # Parse base URL
    base_url = getenv_with_fallback(base_url_env, deprecated_base_url_env).strip()
    if not base_url:
        base_url = DEFAULT_PROVIDER_BASE_URLS.get(provider, default_base_url)
    base_url = _normalize_base_url(base_url)

    # Parse model
    model = getenv_with_fallback(model_env, deprecated_model_env).strip()
    if not model:
        model = "gpt-4o" if provider == OPENAI_PROVIDER else default_model

    # Validate provider/model combination
    if provider != RELACE_PROVIDER and model.startswith("relace-"):
        raise RuntimeError(
            f"Model '{model}' appears to be a Relace-specific model, "
            f"but provider is set to '{provider}'. "
            f"Please set {model_env} to a model supported by your provider."
        )

    # Parse API key
    api_key = getenv_with_fallback(api_key_env, deprecated_api_key_env).strip()

    if not api_key:
        if api_compat == RELACE_PROVIDER:
            api_key = relace_api_key
        elif provider == OPENAI_PROVIDER:
            api_key = os.getenv("OPENAI_API_KEY", "").strip()
            if not api_key:
                raise RuntimeError(f"OPENAI_API_KEY is not set when {provider_env}=openai.")
        else:
            # Derive API key env from provider name (e.g., openrouter -> OPENROUTER_API_KEY)
            derived_env = "".join(ch if ch.isalnum() else "_" for ch in provider.upper()).strip("_")
            derived_env = f"{derived_env}_API_KEY" if derived_env else ""
            if derived_env:
                api_key = os.getenv(derived_env, "").strip()

            if not api_key:
                raise RuntimeError(
                    f"No API key found for {provider_env}={provider}. "
                    f"Set {api_key_env} or export {derived_env}."
                )

    return ProviderConfig(
        provider=provider,
        api_compat=api_compat,
        base_url=base_url,
        model=model,
        api_key=api_key,
        timeout_seconds=default_timeout,
        display_name=_derive_display_name(provider),
    )
