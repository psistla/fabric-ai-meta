"""LLM integration: provider-neutral client built on LiteLLM."""

from fabric_ai_meta.llm.base import (
    BaseLLMClient,
    CostLimitExceededError,
    LLMCallResult,
)
from fabric_ai_meta.llm.client import FabricLLMClient
from fabric_ai_meta.llm.litellm_backend import (
    DEFAULT_MODELS_BY_PROVIDER,
    PROVIDER_API_KEY_ENV_VARS,
    LiteLLMBackend,
    UnsupportedProviderError,
)


def load_llm_client(config) -> BaseLLMClient:
    """Build an LLM client from a Config (or LLMConfig) instance.

    Returns a `LiteLLMBackend` (via `FabricLLMClient`) wired with the provider,
    model, cache settings, cost budget, and provider-specific extras (Azure
    endpoint, Vertex project, OpenAI-compatible base URL, etc.) declared in the
    config. The returned object satisfies `BaseLLMClient`, so all five public
    methods (call, classify_table, detect_grain, generate_description,
    generate_descriptions_batch) are available regardless of provider.

    Accepts either a top-level `Config` or its `.llm` subfield directly.
    """
    llm_cfg = getattr(config, "llm", config)
    return FabricLLMClient(config=llm_cfg)


__all__ = [
    "BaseLLMClient",
    "CostLimitExceededError",
    "DEFAULT_MODELS_BY_PROVIDER",
    "FabricLLMClient",
    "LLMCallResult",
    "LiteLLMBackend",
    "PROVIDER_API_KEY_ENV_VARS",
    "UnsupportedProviderError",
    "load_llm_client",
]
