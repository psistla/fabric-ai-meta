"""Configuration management for fabric-ai-meta.

Loads settings from a TOML file (default: .fabric-ai-meta.toml).
Falls back to built-in defaults if the file is not found.
"""

from dataclasses import dataclass, field, fields
from typing import TypeVar


@dataclass
class ExtractionConfig:
    default_workspace: str = "Production Analytics"


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
    output_dir: str = "./output"


_Section = TypeVar("_Section", ExtractionConfig, LLMConfig, OutputConfig)


@dataclass
class Config:
    extraction: ExtractionConfig = field(default_factory=ExtractionConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    output: OutputConfig = field(default_factory=OutputConfig)


def load_config(path: str = ".fabric-ai-meta.toml") -> Config:
    """Load configuration from a TOML file.

    Falls back to all defaults if the file is not found.
    Uses tomllib (stdlib in Python 3.11+) or tomli as a backport for 3.10.

    Args:
        path: Path to the TOML config file.

    Returns:
        A fully populated Config object.
    """
    try:
        import tomllib
    except ImportError:
        import tomli as tomllib  # type: ignore[no-redef]

    try:
        with open(path, "rb") as fh:
            data = tomllib.load(fh)
    except FileNotFoundError:
        return Config()

    return Config(
        extraction=_section(ExtractionConfig, data.get("extraction", {})),
        llm=_section(LLMConfig, data.get("llm", {})),
        output=_section(OutputConfig, data.get("output", {})),
    )


def _section(cls: type[_Section], table: dict) -> _Section:
    """Build one config dataclass from its TOML table.

    Keys the dataclass does not declare are ignored, so a config file written
    for an older release keeps loading. Defaults come from the dataclass itself.
    """
    known = {f.name for f in fields(cls)}
    return cls(**{k: v for k, v in table.items() if k in known})
