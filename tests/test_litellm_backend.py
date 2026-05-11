"""Tests for the LiteLLM-backed multi-provider LLM client."""

import json
from unittest.mock import MagicMock, patch

import pytest

from fabric_ai_meta.config import LLMConfig
from fabric_ai_meta.llm import load_llm_client
from fabric_ai_meta.llm.base import BaseLLMClient, CostLimitExceededError
from fabric_ai_meta.llm.litellm_backend import (
    DEFAULT_MODELS_BY_PROVIDER,
    PROVIDER_API_KEY_ENV_VARS,
    LiteLLMBackend,
    UnsupportedProviderError,
    build_litellm_model_string,
    resolve_api_key,
)

COMPLETION_PATCH = "fabric_ai_meta.llm.litellm_backend.litellm.completion"


def _make_litellm_response(text: str, input_tokens: int = 100, output_tokens: int = 50):
    response = MagicMock()
    response.choices = [MagicMock()]
    response.choices[0].message.content = text
    response.usage.prompt_tokens = input_tokens
    response.usage.completion_tokens = output_tokens
    return response


# ── build_litellm_model_string ──────────────────────────────────────────────


class TestModelStringDispatch:
    @pytest.mark.parametrize("provider,model,expected", [
        ("anthropic", "claude-sonnet-4-6", "anthropic/claude-sonnet-4-6"),
        ("openai", "gpt-4o", "openai/gpt-4o"),
        ("google", "gemini-2.5-pro", "gemini/gemini-2.5-pro"),
        ("xai", "grok-4", "xai/grok-4"),
        ("mistral", "mistral-large-latest", "mistral/mistral-large-latest"),
        ("cohere", "command-r-plus", "cohere/command-r-plus"),
        ("bedrock", "anthropic.claude-sonnet-4-v1:0", "bedrock/anthropic.claude-sonnet-4-v1:0"),
        ("azure", "my-deployment", "azure/my-deployment"),
        ("vertex", "gemini-2.5-pro", "vertex_ai/gemini-2.5-pro"),
        ("openai-compatible", "llama3.1", "openai/llama3.1"),
    ])
    def test_provider_to_litellm_string(self, provider, model, expected):
        assert build_litellm_model_string(provider, model) == expected

    def test_provider_with_default_model(self):
        assert build_litellm_model_string("anthropic", None) == "anthropic/claude-sonnet-4-6"
        assert build_litellm_model_string("openai", None) == "openai/gpt-4o"

    def test_unknown_provider_raises(self):
        with pytest.raises(UnsupportedProviderError):
            build_litellm_model_string("not-a-provider", "some-model")

    def test_azure_without_model_raises(self):
        with pytest.raises(UnsupportedProviderError):
            build_litellm_model_string("azure", None)

    def test_openai_compatible_without_model_raises(self):
        with pytest.raises(UnsupportedProviderError):
            build_litellm_model_string("openai-compatible", None)


# ── resolve_api_key ─────────────────────────────────────────────────────────


class TestApiKeyResolution:
    def test_anthropic_reads_anthropic_api_key(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "ant-key")
        assert resolve_api_key("anthropic") == "ant-key"

    def test_openai_reads_openai_api_key(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "oai-key")
        assert resolve_api_key("openai") == "oai-key"

    def test_google_reads_gemini_api_key(self, monkeypatch):
        monkeypatch.setenv("GEMINI_API_KEY", "gem-key")
        assert resolve_api_key("google") == "gem-key"

    def test_xai_reads_xai_api_key(self, monkeypatch):
        monkeypatch.setenv("XAI_API_KEY", "xai-key")
        assert resolve_api_key("xai") == "xai-key"

    def test_bedrock_returns_none(self):
        # Bedrock uses AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY natively
        assert resolve_api_key("bedrock") is None

    def test_vertex_returns_none(self):
        # Vertex uses GOOGLE_APPLICATION_CREDENTIALS
        assert resolve_api_key("vertex") is None

    def test_override_env_takes_precedence(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "default-key")
        monkeypatch.setenv("CUSTOM_KEY", "custom-value")
        assert resolve_api_key("anthropic", override_env="CUSTOM_KEY") == "custom-value"

    def test_all_providers_in_default_models_map(self):
        # Every provider in DEFAULT_MODELS_BY_PROVIDER has an entry in
        # PROVIDER_API_KEY_ENV_VARS (even if None).
        assert set(DEFAULT_MODELS_BY_PROVIDER) == set(PROVIDER_API_KEY_ENV_VARS)


# ── LiteLLMBackend wiring ───────────────────────────────────────────────────


class TestLiteLLMBackend:
    @patch(COMPLETION_PATCH)
    def test_default_provider_is_anthropic(self, mock_completion):
        mock_completion.return_value = _make_litellm_response("ok")
        client = LiteLLMBackend(api_key="k", cache_enabled=False)
        assert client.provider == "anthropic"
        assert client.litellm_model == "anthropic/claude-sonnet-4-6"

    @patch(COMPLETION_PATCH)
    def test_openai_provider_dispatch(self, mock_completion):
        mock_completion.return_value = _make_litellm_response("ok")
        cfg = LLMConfig(provider="openai", model="gpt-4o")
        client = LiteLLMBackend(config=cfg, api_key="k", cache_enabled=False)
        client.call("test")
        called_kwargs = mock_completion.call_args.kwargs
        assert called_kwargs["model"] == "openai/gpt-4o"
        assert called_kwargs["api_key"] == "k"

    @patch(COMPLETION_PATCH)
    def test_openai_compatible_routes_with_base_url(self, mock_completion):
        mock_completion.return_value = _make_litellm_response("ok")
        cfg = LLMConfig(
            provider="openai-compatible",
            model="llama3.1",
            base_url="http://localhost:11434",
        )
        client = LiteLLMBackend(config=cfg, api_key="dummy", cache_enabled=False)
        client.call("test")
        called_kwargs = mock_completion.call_args.kwargs
        assert called_kwargs["model"] == "openai/llama3.1"
        assert called_kwargs["api_base"] == "http://localhost:11434"

    @patch(COMPLETION_PATCH)
    def test_azure_passes_endpoint_and_api_version(self, mock_completion):
        mock_completion.return_value = _make_litellm_response("ok")
        cfg = LLMConfig(
            provider="azure",
            model="my-deployment",
            azure_endpoint="https://my.openai.azure.com",
            azure_api_version="2024-02-15-preview",
        )
        client = LiteLLMBackend(config=cfg, api_key="k", cache_enabled=False)
        client.call("test")
        called_kwargs = mock_completion.call_args.kwargs
        assert called_kwargs["api_base"] == "https://my.openai.azure.com"
        assert called_kwargs["api_version"] == "2024-02-15-preview"

    @patch(COMPLETION_PATCH)
    def test_vertex_passes_project_and_location(self, mock_completion):
        mock_completion.return_value = _make_litellm_response("ok")
        cfg = LLMConfig(
            provider="vertex",
            model="gemini-2.5-pro",
            vertex_project="my-project",
            vertex_location="us-central1",
        )
        client = LiteLLMBackend(config=cfg, cache_enabled=False)
        client.call("test")
        called_kwargs = mock_completion.call_args.kwargs
        assert called_kwargs["model"] == "vertex_ai/gemini-2.5-pro"
        assert called_kwargs["vertex_project"] == "my-project"
        assert called_kwargs["vertex_location"] == "us-central1"

    @patch(COMPLETION_PATCH)
    def test_json_mode_for_structured_prompt(self, mock_completion):
        mock_completion.return_value = _make_litellm_response(
            json.dumps({"description": "test"})
        )
        client = LiteLLMBackend(api_key="k", cache_enabled=False)
        prompt = 'Return JSON with key "description"'
        client.call(prompt)
        called_kwargs = mock_completion.call_args.kwargs
        assert called_kwargs.get("response_format") == {"type": "json_object"}

    @patch(COMPLETION_PATCH)
    def test_no_json_mode_for_freeform_prompt(self, mock_completion):
        mock_completion.return_value = _make_litellm_response("plain text")
        client = LiteLLMBackend(api_key="k", cache_enabled=False)
        client.call("Summarize this paragraph in one sentence.")
        called_kwargs = mock_completion.call_args.kwargs
        assert "response_format" not in called_kwargs

    @patch(COMPLETION_PATCH)
    def test_cache_hit_skips_completion(self, mock_completion, tmp_path):
        mock_completion.return_value = _make_litellm_response("cached")
        client = LiteLLMBackend(
            api_key="k",
            cache_enabled=True,
            cache_dir=str(tmp_path / "cache"),
        )
        client.call("identical prompt")
        client.call("identical prompt")
        assert mock_completion.call_count == 1

    @patch(COMPLETION_PATCH)
    def test_cost_limit_raises(self, mock_completion):
        mock_completion.return_value = _make_litellm_response(
            "expensive", input_tokens=1_000_000, output_tokens=500_000
        )
        client = LiteLLMBackend(
            api_key="k",
            cache_enabled=False,
            max_cost_usd=0.01,
        )
        with pytest.raises(CostLimitExceededError):
            client.call("expensive prompt")

    @patch(COMPLETION_PATCH)
    def test_system_prompt_prepended_as_system_message(self, mock_completion):
        mock_completion.return_value = _make_litellm_response("ok")
        client = LiteLLMBackend(api_key="k", cache_enabled=False)
        client.call("user content", system="you are a helpful analyst")
        called_kwargs = mock_completion.call_args.kwargs
        messages = called_kwargs["messages"]
        assert messages[0] == {"role": "system", "content": "you are a helpful analyst"}
        assert messages[1] == {"role": "user", "content": "user content"}

    @patch(COMPLETION_PATCH)
    def test_token_counts_accumulate(self, mock_completion):
        mock_completion.return_value = _make_litellm_response("ok", input_tokens=120, output_tokens=80)
        client = LiteLLMBackend(api_key="k", cache_enabled=False)
        client.call("call 1")
        client.call("call 2")
        assert client._total_input_tokens == 240
        assert client._total_output_tokens == 160

    @patch(COMPLETION_PATCH)
    def test_litellm_completion_cost_is_used_when_available(self, mock_completion):
        mock_completion.return_value = _make_litellm_response("ok")
        with patch(
            "fabric_ai_meta.llm.litellm_backend.litellm.completion_cost",
            return_value=0.42,
        ):
            client = LiteLLMBackend(api_key="k", cache_enabled=False)
            client.call("prompt")
            assert client._total_cost_usd == pytest.approx(0.42)


# ── load_llm_client factory ─────────────────────────────────────────────────


class TestLoadLLMClient:
    @patch(COMPLETION_PATCH)
    def test_returns_base_llm_client_instance(self, mock_completion):
        mock_completion.return_value = _make_litellm_response("ok")
        cfg = LLMConfig()
        client = load_llm_client(cfg)
        assert isinstance(client, BaseLLMClient)

    @patch(COMPLETION_PATCH)
    def test_accepts_full_config_or_llm_subconfig(self, mock_completion):
        mock_completion.return_value = _make_litellm_response("ok")
        from fabric_ai_meta.config import Config

        c1 = load_llm_client(LLMConfig(provider="openai", model="gpt-4o"))
        c2 = load_llm_client(Config(llm=LLMConfig(provider="openai", model="gpt-4o")))
        assert c1.litellm_model == "openai/gpt-4o"
        assert c2.litellm_model == "openai/gpt-4o"

    @patch(COMPLETION_PATCH)
    def test_factory_threads_provider_extras(self, mock_completion):
        mock_completion.return_value = _make_litellm_response("ok")
        cfg = LLMConfig(
            provider="openai-compatible",
            model="qwen2.5",
            base_url="http://localhost:8000/v1",
            cache_enabled=False,
        )
        client = load_llm_client(cfg)
        client.call("test")
        called_kwargs = mock_completion.call_args.kwargs
        assert called_kwargs["api_base"] == "http://localhost:8000/v1"
