"""LLM client used by the analyzer and generator modules.

`FabricLLMClient` is kept as the public name for backward compatibility. Under
the hood it is a `LiteLLMBackend` subclass so existing call sites
(`FabricLLMClient(api_key="...")`) keep working while users gain access to
every provider LiteLLM supports through `cfg.llm.provider`.
"""

from fabric_ai_meta.llm.base import (
    BaseLLMClient,
    CostLimitExceededError,
    LLMCallResult,
)
from fabric_ai_meta.llm.litellm_backend import LiteLLMBackend

# Module-level constants kept for external consumers and for legacy code paths.
# Claude Sonnet 4.6 has a 1,000,000-token context window; 950k leaves headroom.
MAX_CONTEXT_TOKENS = 950_000
RESERVED_FOR_RESPONSE = 8_000
MAX_MODEL_CONTEXT = MAX_CONTEXT_TOKENS - RESERVED_FOR_RESPONSE  # 942,000 tokens for input

ANTHROPIC_MODEL = "claude-sonnet-4-6"


class FabricLLMClient(LiteLLMBackend):
    """LLM client for fabric-ai-meta.

    Defaults to the Anthropic Claude provider so existing user code that does
    `FabricLLMClient(api_key=...)` keeps targeting Claude with no config change.
    Pass a `config` (an `LLMConfig`) to select a different provider/model.
    """

    def __init__(
        self,
        api_key: str | None = None,
        cache_enabled: bool | None = None,
        cache_dir: str | None = None,
        max_cost_usd: float | None = None,
        config=None,
    ):
        super().__init__(
            config=config,
            api_key=api_key,
            cache_enabled=cache_enabled,
            cache_dir=cache_dir,
            max_cost_usd=max_cost_usd,
        )


__all__ = [
    "FabricLLMClient",
    "BaseLLMClient",
    "LiteLLMBackend",
    "LLMCallResult",
    "CostLimitExceededError",
    "ANTHROPIC_MODEL",
    "MAX_CONTEXT_TOKENS",
    "MAX_MODEL_CONTEXT",
    "RESERVED_FOR_RESPONSE",
]
