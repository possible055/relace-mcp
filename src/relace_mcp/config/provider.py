import logging
from dataclasses import dataclass

from .settings import RELACE_PROVIDER

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
    *,
    label: str,
    raw_provider: str,
    raw_api_key: str,
    raw_endpoint: str,
    raw_model: str,
    default_endpoint: str,
    default_model: str,
    timeout: float,
    relace_api_key: str | None,
) -> ProviderConfig:
    """Create provider configuration from pre-read values.

    Args:
        label: Human-readable label for error messages (e.g., "APPLY", "SEARCH").
        raw_provider: Raw provider string from env (empty = relace).
        raw_api_key: Raw API key from env.
        raw_endpoint: Raw endpoint URL from env.
        raw_model: Raw model name from env.
        default_endpoint: Default endpoint for Relace provider.
        default_model: Default model for Relace provider.
        timeout: Request timeout in seconds.
        relace_api_key: API key from RelaceConfig (used when provider is relace).

    Raises:
        RuntimeError: Configuration validation failed.
    """
    provider = (raw_provider.strip() or RELACE_PROVIDER).lower()

    # API compatibility: relace vs openai-compatible
    api_compat = RELACE_PROVIDER if provider == RELACE_PROVIDER else "openai"

    # Resolve endpoint
    base_url = raw_endpoint.strip()
    if not base_url:
        if provider != RELACE_PROVIDER:
            raise RuntimeError(
                f"{label}_ENDPOINT is required when using {label}_PROVIDER={provider}. "
                f"Set {label}_ENDPOINT to your provider's API endpoint."
            )
        base_url = default_endpoint
    base_url = _normalize_base_url(base_url)

    # Resolve model
    model = raw_model.strip() or default_model

    # Validate provider/model combination
    if provider != RELACE_PROVIDER and (model == "auto" or model.startswith("relace-")):
        raise RuntimeError(
            f"Model '{model}' is a Relace-specific model, "
            f"but provider is set to '{provider}'. "
            f"Please set {label}_MODEL to a model supported by your provider."
        )

    # Resolve API key
    api_key = raw_api_key.strip()

    if not api_key:
        if api_compat == RELACE_PROVIDER:
            api_key = relace_api_key or ""
            if not api_key:
                raise RuntimeError(
                    f"RELACE_API_KEY is required when using {label}_PROVIDER=relace (default). "
                    f"Set RELACE_API_KEY or switch to a different provider via {label}_PROVIDER."
                )
        else:
            raise RuntimeError(
                f"No API key found for {label}_PROVIDER={provider}. Set {label}_API_KEY."
            )

    return ProviderConfig(
        provider=provider,
        api_compat=api_compat,
        base_url=base_url,
        model=model,
        api_key=api_key,
        timeout_seconds=timeout,
        display_name=_derive_display_name(provider),
    )
