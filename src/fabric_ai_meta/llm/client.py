"""Claude API wrapper for LLM-assisted metadata analysis."""

import json
import os

import anthropic

from fabric_ai_meta.llm.cache import LLMCache
from fabric_ai_meta.llm.prompts import (
    TABLE_CLASSIFICATION_PROMPT,
    GRAIN_DETECTION_PROMPT,
    DESCRIPTION_GENERATION_PROMPT,
)
from fabric_ai_meta.models.metadata import (
    TableMeta,
    TableType,
    RelationshipMeta,
)

# Token budget management
# Claude Sonnet (claude-sonnet-4-6) actual context window: 200,000 tokens
# We use 190,000 as a conservative operational budget (leaves headroom for system prompt overhead)
MAX_CONTEXT_TOKENS = 190_000   # Conservative budget — actual window is 200K
RESERVED_FOR_RESPONSE = 8_000
MAX_MODEL_CONTEXT = MAX_CONTEXT_TOKENS - RESERVED_FOR_RESPONSE  # 182,000 tokens for input

ANTHROPIC_MODEL = "claude-sonnet-4-6"  # Current production model string as of March 2026


class CostLimitExceededError(Exception):
    """Raised when cumulative LLM cost exceeds the configured max_cost_usd."""
    pass


class FabricLLMClient:
    """Client for Claude API interactions with caching and cost tracking."""

    def __init__(
        self,
        api_key: str | None = None,
        cache_enabled: bool = True,
        cache_dir: str = ".fabric-ai-meta-cache",
        max_cost_usd: float | None = None,
    ):
        resolved_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        self.client = anthropic.Anthropic(api_key=resolved_key)
        self.cache = LLMCache(cache_dir) if cache_enabled else None
        self.max_cost_usd = max_cost_usd

        # Cumulative token usage tracking
        self._total_input_tokens = 0
        self._total_output_tokens = 0

    def call(self, prompt: str, max_tokens: int = 1000, system: str | None = None) -> str:
        """Send a prompt to Claude and return the text response.

        Checks cache first, tracks token usage, and enforces cost limits.
        """
        # Check cache
        if self.cache is not None:
            cache_key = self.cache.make_key(prompt)
            cached = self.cache.get(cache_key)
            if cached is not None:
                return cached

        # Build messages
        messages = [{"role": "user", "content": prompt}]

        # Build API call kwargs
        kwargs = {
            "model": ANTHROPIC_MODEL,
            "max_tokens": max_tokens,
            "messages": messages,
        }
        if system is not None:
            kwargs["system"] = system

        response = self.client.messages.create(**kwargs)

        # Track token usage
        self._total_input_tokens += response.usage.input_tokens
        self._total_output_tokens += response.usage.output_tokens

        # Check cost limit
        if self.max_cost_usd is not None:
            estimated_cost = self._estimate_cost()
            if estimated_cost > self.max_cost_usd:
                raise CostLimitExceededError(
                    f"Cumulative estimated cost ${estimated_cost:.4f} "
                    f"exceeds limit ${self.max_cost_usd:.2f}"
                )

        # Extract text from response
        result = response.content[0].text

        # Store in cache
        if self.cache is not None:
            self.cache.set(cache_key, result)

        return result

    def _estimate_cost(self) -> float:
        """Estimate cumulative cost based on token usage.

        Pricing is approximate and may change — see console.anthropic.com for current rates.
        """
        # Approximate rates as of spec authoring (verify before release)
        input_cost = self._total_input_tokens * 3.0 / 1_000_000
        output_cost = self._total_output_tokens * 15.0 / 1_000_000
        return input_cost + output_cost

    def classify_table(
        self, table: TableMeta, relationships: list[RelationshipMeta]
    ) -> tuple[TableType, float]:
        """Use LLM to classify an ambiguous table. Returns (TableType, confidence)."""
        column_list = "\n".join(
            f"  - {c.name} — {c.data_type}" for c in table.columns
        )

        rel_lines = []
        for r in relationships:
            if r.from_table == table.name:
                rel_lines.append(f"  - {table.name}[{r.from_column}] → {r.to_table}[{r.to_column}] ({r.cardinality})")
            elif r.to_table == table.name:
                rel_lines.append(f"  - {r.from_table}[{r.from_column}] → {table.name}[{r.to_column}] ({r.cardinality})")
        relationship_summary = "\n".join(rel_lines) if rel_lines else "No relationships found."

        possible_types = ", ".join(t.value for t in TableType if t != TableType.UNKNOWN)

        prompt = TABLE_CLASSIFICATION_PROMPT.format(
            table_name=table.name,
            column_list=column_list,
            relationship_summary=relationship_summary,
            possible_types=possible_types,
        )

        result_text = self.call(prompt)
        parsed = json.loads(result_text)
        table_type = TableType(parsed["table_type"])
        confidence = float(parsed["confidence"])
        return table_type, confidence

    def detect_grain(self, table: TableMeta) -> tuple[str, float]:
        """Use LLM to detect fact table grain. Returns (grain_statement, confidence)."""
        column_list = "\n".join(
            f"  - {c.name} — {c.data_type}" for c in table.columns
        )

        sample_lines = []
        for c in table.columns:
            if c.sample_values:
                sample_lines.append(f"  - {c.name}: {c.sample_values[:5]}")
        sample_values = "\n".join(sample_lines) if sample_lines else "No sample values available."

        prompt = GRAIN_DETECTION_PROMPT.format(
            table_name=table.name,
            column_list=column_list,
            row_count=table.row_count_estimate or "Unknown",
            sample_values=sample_values,
        )

        result_text = self.call(prompt)
        parsed = json.loads(result_text)
        return parsed["grain"], float(parsed["confidence"])

    def generate_description(self, obj_type: str, name: str, context: dict) -> str:
        """Use LLM to generate a missing description. Returns the description string."""
        parent_table = context.get("parent_table", "N/A")

        type_info = ""
        if "data_type" in context:
            type_info = f"Data type: {context['data_type']}"
        elif "dax" in context:
            type_info = f"DAX expression: {context['dax']}"

        sibling_context = context.get("sibling_descriptions", "None available.")

        prompt = DESCRIPTION_GENERATION_PROMPT.format(
            obj_type=obj_type,
            name=name,
            parent_table=parent_table,
            type_info=type_info,
            sibling_context=sibling_context,
        )

        result_text = self.call(prompt)
        parsed = json.loads(result_text)
        return parsed["description"]
