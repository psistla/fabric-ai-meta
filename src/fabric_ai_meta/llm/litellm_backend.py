"""LiteLLM-backed implementation of `BaseLLMClient`.

LiteLLM normalizes prompts, JSON mode, retries, and cost tracking across 100+
providers including Anthropic, OpenAI, Google Gemini, xAI Grok, Mistral, Cohere,
AWS Bedrock, Azure OpenAI, Google Vertex AI, and any OpenAI-compatible endpoint
(Groq, Together, Fireworks, Ollama, LM Studio, vLLM, etc.).

The `litellm` import is lazy so the package stays optional. Install with
`pip install 'fabric-ai-meta[llm]'`.
"""

import os

from fabric_ai_meta.llm.base import BaseLLMClient, LLMCallResult

try:
    import litellm  # type: ignore[import-not-found]
except ImportError:
    litellm = None  # type: ignore[assignment]


DEFAULT_MODELS_BY_PROVIDER: dict[str, str | None] = {
    "anthropic": "claude-sonnet-4-6",
    "openai": "gpt-4o",
    "google": "gemini-2.5-pro",
    "xai": "grok-4",
    "mistral": "mistral-large-latest",
    "cohere": "command-r-plus",
    "bedrock": "anthropic.claude-sonnet-4-v1:0",
    "azure": None,                          # azure requires explicit deployment name
    "vertex": "gemini-2.5-pro",
    "openai-compatible": None,              # caller must supply model
}


PROVIDER_API_KEY_ENV_VARS: dict[str, str | None] = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "google": "GEMINI_API_KEY",
    "xai": "XAI_API_KEY",
    "mistral": "MISTRAL_API_KEY",
    "cohere": "COHERE_API_KEY",
    "bedrock": None,                        # uses AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY
    "azure": "AZURE_OPENAI_API_KEY",
    "vertex": None,                         # uses GOOGLE_APPLICATION_CREDENTIALS
    "openai-compatible": "OPENAI_COMPATIBLE_API_KEY",
}


_LITELLM_PROVIDER_PREFIX: dict[str, str] = {
    "anthropic": "anthropic",
    "openai": "openai",
    "google": "gemini",
    "xai": "xai",
    "mistral": "mistral",
    "cohere": "cohere",
    "bedrock": "bedrock",
    "azure": "azure",
    "vertex": "vertex_ai",
    "openai-compatible": "openai",          # routed via api_base
}


class UnsupportedProviderError(Exception):
    """Raised when `cfg.llm.provider` is not in the supported provider list."""


def build_litellm_model_string(provider: str, model: str | None) -> str:
    """Map (provider, model) onto LiteLLM's `provider/model` string format.

    Azure deployments and openai-compatible hosts both require an explicit model.
    """
    if provider not in _LITELLM_PROVIDER_PREFIX:
        raise UnsupportedProviderError(
            f"Unknown LLM provider '{provider}'. "
            f"Supported: {sorted(_LITELLM_PROVIDER_PREFIX)}."
        )

    resolved_model = model or DEFAULT_MODELS_BY_PROVIDER.get(provider)
    if resolved_model is None:
        raise UnsupportedProviderError(
            f"Provider '{provider}' requires an explicit model name in config."
        )

    return f"{_LITELLM_PROVIDER_PREFIX[provider]}/{resolved_model}"


def resolve_api_key(provider: str, override_env: str | None = None) -> str | None:
    """Look up the API key for a provider from environment variables.

    `override_env` (e.g. `cfg.llm.api_key_env`) wins if set. Returns None for
    providers that authenticate via SDK-native mechanisms (Bedrock via AWS env,
    Vertex via GOOGLE_APPLICATION_CREDENTIALS).
    """
    env_var = override_env or PROVIDER_API_KEY_ENV_VARS.get(provider)
    if env_var is None:
        return None
    return os.environ.get(env_var)


_STRUCTURED_JSON_PROMPT_MARKERS = (
    '"table_type"',
    '"grain"',
    '"description"',
    "Return valid JSON",
)


def _is_structured_json_prompt(prompt: str) -> bool:
    """Heuristic: did the prompt ask for a JSON response?

    All structured prompts (classify_table, detect_grain, generate_description,
    generate_descriptions_batch) request JSON, so we flip on `response_format`
    when LiteLLM supports it for the chosen provider.
    """
    return any(marker in prompt for marker in _STRUCTURED_JSON_PROMPT_MARKERS)


class LiteLLMBackend(BaseLLMClient):
    """Multi-provider LLM client routed through LiteLLM.

    Reads `provider`, `model`, `api_key_env`, `base_url`, `azure_endpoint`,
    `azure_api_version`, `vertex_project`, and `vertex_location` from the
    optional `config` argument (an `LLMConfig`) or falls back to per-argument
    overrides. The `api_key` argument, when supplied, takes precedence over
    the resolved env var.
    """

    def __init__(
        self,
        config=None,
        api_key: str | None = None,
        cache_enabled: bool | None = None,
        cache_dir: str | None = None,
        max_cost_usd: float | None = None,
        provider: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
        azure_endpoint: str | None = None,
        azure_api_version: str | None = None,
        vertex_project: str | None = None,
        vertex_location: str | None = None,
    ):
        if litellm is None:
            raise ImportError(
                "LiteLLM is not installed. Install with: pip install 'fabric-ai-meta[llm]'"
            )

        # Explicit kwargs win over config values; config supplies fallbacks.
        cfg_provider = getattr(config, "provider", None) if config is not None else None
        cfg_model = getattr(config, "model", None) if config is not None else None
        cfg_cache_enabled = getattr(config, "cache_enabled", None) if config is not None else None
        cfg_cache_dir = getattr(config, "cache_dir", None) if config is not None else None
        cfg_max_cost_usd = getattr(config, "max_cost_per_run", None) if config is not None else None
        cfg_base_url = getattr(config, "base_url", None) if config is not None else None
        cfg_azure_endpoint = getattr(config, "azure_endpoint", None) if config is not None else None
        cfg_azure_api_version = getattr(config, "azure_api_version", None) if config is not None else None
        cfg_vertex_project = getattr(config, "vertex_project", None) if config is not None else None
        cfg_vertex_location = getattr(config, "vertex_location", None) if config is not None else None
        api_key_env_override = getattr(config, "api_key_env", None) if config is not None else None

        provider = provider if provider is not None else (cfg_provider or "anthropic")
        model = model if model is not None else cfg_model
        cache_enabled = cache_enabled if cache_enabled is not None else (cfg_cache_enabled if cfg_cache_enabled is not None else True)
        cache_dir = cache_dir if cache_dir is not None else (cfg_cache_dir or ".fabric-ai-meta-cache")
        max_cost_usd = max_cost_usd if max_cost_usd is not None else cfg_max_cost_usd
        base_url = base_url if base_url is not None else cfg_base_url
        azure_endpoint = azure_endpoint if azure_endpoint is not None else cfg_azure_endpoint
        azure_api_version = azure_api_version if azure_api_version is not None else cfg_azure_api_version
        vertex_project = vertex_project if vertex_project is not None else cfg_vertex_project
        vertex_location = vertex_location if vertex_location is not None else cfg_vertex_location

        super().__init__(
            cache_enabled=cache_enabled,
            cache_dir=cache_dir,
            max_cost_usd=max_cost_usd,
        )

        self.provider = provider
        self.model = model
        self.litellm_model = build_litellm_model_string(provider, model)
        self.api_key = api_key or resolve_api_key(provider, api_key_env_override)
        self.base_url = base_url
        self.azure_endpoint = azure_endpoint
        self.azure_api_version = azure_api_version
        self.vertex_project = vertex_project
        self.vertex_location = vertex_location

    def _build_litellm_kwargs(self, prompt: str, max_tokens: int, system: str | None) -> dict:
        messages: list[dict] = []
        if system is not None:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        kwargs: dict = {
            "model": self.litellm_model,
            "messages": messages,
            "max_tokens": max_tokens,
        }

        if self.api_key is not None:
            kwargs["api_key"] = self.api_key
        if self.base_url is not None:
            kwargs["api_base"] = self.base_url
        if self.provider == "azure":
            if self.azure_endpoint is not None:
                kwargs["api_base"] = self.azure_endpoint
            if self.azure_api_version is not None:
                kwargs["api_version"] = self.azure_api_version
        if self.provider == "vertex":
            if self.vertex_project is not None:
                kwargs["vertex_project"] = self.vertex_project
            if self.vertex_location is not None:
                kwargs["vertex_location"] = self.vertex_location

        if _is_structured_json_prompt(prompt):
            kwargs["response_format"] = {"type": "json_object"}

        return kwargs

    def _raw_call(
        self,
        prompt: str,
        max_tokens: int,
        system: str | None = None,
    ) -> LLMCallResult:
        kwargs = self._build_litellm_kwargs(prompt, max_tokens, system)
        response = litellm.completion(**kwargs)

        text = response.choices[0].message.content or ""
        usage = getattr(response, "usage", None)
        input_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
        output_tokens = int(getattr(usage, "completion_tokens", 0) or 0)

        cost_usd = 0.0
        try:
            cost_usd = float(litellm.completion_cost(completion_response=response) or 0.0)
        except Exception:
            cost_usd = 0.0

        return LLMCallResult(
            text=text,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost_usd,
        )
