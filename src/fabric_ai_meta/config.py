"""Configuration management for fabric-ai-meta.

Loads settings from a TOML file (default: .fabric-ai-meta.toml).
Falls back to built-in defaults if the file is not found.
"""

import sys
from dataclasses import dataclass, field


@dataclass
class AuthConfig:
    method: str = "interactive"          # "interactive", "service_principal", "notebook"
    tenant_id: str | None = None         # Required for service_principal
    client_id: str | None = None         # Required for service_principal
    client_secret: str | None = None     # Required for service_principal


@dataclass
class ExtractionConfig:
    default_workspace: str = "Production Analytics"
    include_sample_values: bool = True
    sample_value_count: int = 10
    extraction_method: str = "semantic_link"   # "semantic_link" or "xmla"


@dataclass
class LLMConfig:
    provider: str = "anthropic"
    model: str = "claude-sonnet-4-6"
    api_key_env: str = "ANTHROPIC_API_KEY"
    cache_enabled: bool = True
    cache_dir: str = ".fabric-ai-meta-cache"
    max_cost_per_run: float = 5.00
    # Provider-specific extras (consumed by the LiteLLM backend)
    base_url: str | None = None              # openai-compatible hosts (Groq, Together, Ollama, vLLM)
    azure_endpoint: str | None = None        # Azure OpenAI resource endpoint
    azure_api_version: str | None = None     # Azure OpenAI API version
    vertex_project: str | None = None        # Google Vertex AI project ID
    vertex_location: str | None = None       # Google Vertex AI region


@dataclass
class OutputConfig:
    default_format: str = "json"
    output_dir: str = "./output"
    include_raw_extraction: bool = False


@dataclass
class ScoringWeightsConfig:
    description_coverage: float = 0.25
    measure_documentation: float = 0.20
    relationship_completeness: float = 0.15
    naming_consistency: float = 0.15
    sample_values_available: float = 0.10
    business_rules_documented: float = 0.15


@dataclass
class ScoringConfig:
    weights: ScoringWeightsConfig = field(default_factory=ScoringWeightsConfig)


@dataclass
class Config:
    auth: AuthConfig = field(default_factory=AuthConfig)
    extraction: ExtractionConfig = field(default_factory=ExtractionConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    output: OutputConfig = field(default_factory=OutputConfig)
    scoring: ScoringConfig = field(default_factory=ScoringConfig)


def load_config(path: str = ".fabric-ai-meta.toml") -> Config:
    """Load configuration from a TOML file.

    Falls back to all defaults if the file is not found.
    Uses tomllib (stdlib in Python 3.11+) or tomli as a backport for 3.10.

    Args:
        path: Path to the TOML config file.

    Returns:
        A fully populated Config object.
    """
    if sys.version_info >= (3, 11):
        import tomllib
    else:
        try:
            import tomllib
        except ImportError:
            import tomli as tomllib  # type: ignore[no-redef]

    try:
        with open(path, "rb") as fh:
            data = tomllib.load(fh)
    except FileNotFoundError:
        return Config()

    auth_data = data.get("auth", {})
    ext_data = data.get("extraction", {})
    llm_data = data.get("llm", {})
    out_data = data.get("output", {})
    scoring_data = data.get("scoring", {})
    weights_data = scoring_data.get("weights", {})

    return Config(
        auth=AuthConfig(
            method=auth_data.get("method", "interactive"),
            tenant_id=auth_data.get("tenant_id"),
            client_id=auth_data.get("client_id"),
            client_secret=auth_data.get("client_secret"),
        ),
        extraction=ExtractionConfig(
            default_workspace=ext_data.get("default_workspace", "Production Analytics"),
            include_sample_values=ext_data.get("include_sample_values", True),
            sample_value_count=ext_data.get("sample_value_count", 10),
            extraction_method=ext_data.get("extraction_method", "semantic_link"),
        ),
        llm=LLMConfig(
            provider=llm_data.get("provider", "anthropic"),
            model=llm_data.get("model", "claude-sonnet-4-6"),
            api_key_env=llm_data.get("api_key_env", "ANTHROPIC_API_KEY"),
            cache_enabled=llm_data.get("cache_enabled", True),
            cache_dir=llm_data.get("cache_dir", ".fabric-ai-meta-cache"),
            max_cost_per_run=llm_data.get("max_cost_per_run", 5.00),
            base_url=llm_data.get("base_url"),
            azure_endpoint=llm_data.get("azure_endpoint"),
            azure_api_version=llm_data.get("azure_api_version"),
            vertex_project=llm_data.get("vertex_project"),
            vertex_location=llm_data.get("vertex_location"),
        ),
        output=OutputConfig(
            default_format=out_data.get("default_format", "json"),
            output_dir=out_data.get("output_dir", "./output"),
            include_raw_extraction=out_data.get("include_raw_extraction", False),
        ),
        scoring=ScoringConfig(
            weights=ScoringWeightsConfig(
                description_coverage=weights_data.get("description_coverage", 0.25),
                measure_documentation=weights_data.get("measure_documentation", 0.20),
                relationship_completeness=weights_data.get("relationship_completeness", 0.15),
                naming_consistency=weights_data.get("naming_consistency", 0.15),
                sample_values_available=weights_data.get("sample_values_available", 0.10),
                business_rules_documented=weights_data.get("business_rules_documented", 0.15),
            )
        ),
    )
