"""Base LLM client abstraction.

Defines the contract every LLM backend must satisfy and provides shared cache,
cost-tracking, and prompt-construction logic so concrete backends only implement
a single low-level `_raw_call()` against their SDK of choice.
"""

import json
import warnings
from abc import ABC, abstractmethod
from dataclasses import dataclass

from fabric_ai_meta.llm.cache import LLMCache
from fabric_ai_meta.llm.prompts import (
    BATCH_DESCRIPTION_PROMPT,
    DESCRIPTION_GENERATION_PROMPT,
    GRAIN_DETECTION_PROMPT,
    TABLE_CLASSIFICATION_PROMPT,
)
from fabric_ai_meta.models.metadata import (
    RelationshipMeta,
    TableMeta,
    TableType,
)


@dataclass
class LLMCallResult:
    """Normalized result from a single LLM API call.

    Backends populate this from their SDK's response object. `cost_usd` is best-effort:
    backends that cannot compute per-call cost should leave it at 0.0 and rely on the
    base class's token-based fallback estimate.
    """
    text: str
    input_tokens: int
    output_tokens: int
    cost_usd: float = 0.0


class CostLimitExceededError(Exception):
    """Raised when cumulative LLM cost exceeds the configured max_cost_usd."""
    pass


def _try_parse_batch_json(text: str) -> list | None:
    """Attempt to parse a JSON array from LLM output. Returns None on failure."""
    try:
        parsed = json.loads(text.strip())
        if isinstance(parsed, list):
            return parsed
    except (json.JSONDecodeError, ValueError):
        pass
    return None


class BaseLLMClient(ABC):
    """Abstract LLM client. Subclasses implement `_raw_call()` only.

    All public methods (call, classify_table, detect_grain, generate_description,
    generate_descriptions_batch) are concrete and shared across backends. Caching,
    cumulative cost tracking, and budget enforcement live on this class.
    """

    def __init__(
        self,
        cache_enabled: bool = True,
        cache_dir: str = ".fabric-ai-meta-cache",
        max_cost_usd: float | None = None,
    ):
        self.cache = LLMCache(cache_dir) if cache_enabled else None
        self.max_cost_usd = max_cost_usd
        self._total_input_tokens = 0
        self._total_output_tokens = 0
        self._total_cost_usd = 0.0

    @abstractmethod
    def _raw_call(
        self,
        prompt: str,
        max_tokens: int,
        system: str | None = None,
    ) -> LLMCallResult:
        """Backend-specific single API call. Must populate token counts and (best-effort) cost."""

    def _estimate_cost(self) -> float:
        """Cumulative cost so far.

        Backends that report per-call USD (e.g. LiteLLM) populate `_total_cost_usd`
        directly; otherwise fall back to an approximate token-based rate (rough
        Anthropic Sonnet rates: $3 in / $15 out per million tokens).
        """
        if self._total_cost_usd > 0:
            return self._total_cost_usd
        input_cost = self._total_input_tokens * 3.0 / 1_000_000
        output_cost = self._total_output_tokens * 15.0 / 1_000_000
        return input_cost + output_cost

    def _call_with_cache_and_budget(
        self,
        prompt: str,
        max_tokens: int = 1000,
        system: str | None = None,
    ) -> str:
        """Cache-aware, budget-aware wrapper around `_raw_call`.

        Returns the response text. Raises `CostLimitExceededError` after the
        call if `max_cost_usd` was set and the cumulative spend exceeds it.
        """
        if self.cache is not None:
            cache_key = self.cache.make_key(prompt)
            cached = self.cache.get(cache_key)
            if cached is not None:
                return cached

        result = self._raw_call(prompt, max_tokens, system)

        self._total_input_tokens += result.input_tokens
        self._total_output_tokens += result.output_tokens
        self._total_cost_usd += result.cost_usd

        if self.max_cost_usd is not None:
            est = self._estimate_cost()
            if est > self.max_cost_usd:
                raise CostLimitExceededError(
                    f"Cumulative estimated cost ${est:.4f} "
                    f"exceeds limit ${self.max_cost_usd:.2f}"
                )

        if self.cache is not None:
            self.cache.set(cache_key, result.text)

        return result.text

    def call(self, prompt: str, max_tokens: int = 1000, system: str | None = None) -> str:
        """Send a prompt to the backend and return the text response."""
        return self._call_with_cache_and_budget(prompt, max_tokens, system)

    def classify_table(
        self, table: TableMeta, relationships: list[RelationshipMeta]
    ) -> tuple[TableType, float]:
        """Use the LLM to classify an ambiguous table. Returns (TableType, confidence)."""
        column_list = "\n".join(f"  - {c.name} ({c.data_type})" for c in table.columns)

        rel_lines = []
        for r in relationships:
            if r.from_table == table.name:
                rel_lines.append(
                    f"  - {table.name}[{r.from_column}] -> {r.to_table}[{r.to_column}] ({r.cardinality})"
                )
            elif r.to_table == table.name:
                rel_lines.append(
                    f"  - {r.from_table}[{r.from_column}] -> {table.name}[{r.to_column}] ({r.cardinality})"
                )
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
        return TableType(parsed["table_type"]), float(parsed["confidence"])

    def detect_grain(self, table: TableMeta) -> tuple[str, float]:
        """Use the LLM to detect fact table grain. Returns (grain_statement, confidence)."""
        column_list = "\n".join(f"  - {c.name} ({c.data_type})" for c in table.columns)

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
        """Use the LLM to generate a missing description. Returns the description string."""
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

    def generate_descriptions_batch(
        self, items: list[dict], model_name: str, batch_size: int = 15
    ) -> dict[str, str]:
        """Generate descriptions for many items in batches.

        items: list of dicts with id, type, name, parent_table, data_type/dax, siblings.
        Returns {id: description}. On JSON parse failure, retries once; if still fails, skips batch.
        """
        results: dict[str, str] = {}

        for i in range(0, len(items), batch_size):
            batch = items[i : i + batch_size]

            if self.max_cost_usd is not None and self._estimate_cost() >= self.max_cost_usd:
                raise CostLimitExceededError(
                    f"Cost limit ${self.max_cost_usd:.2f} reached before batch {i // batch_size + 1}"
                )

            prompt = BATCH_DESCRIPTION_PROMPT.format(
                model_name=model_name,
                items_json=json.dumps(batch, ensure_ascii=False),
            )

            raw = self.call(prompt, max_tokens=2000)
            parsed = _try_parse_batch_json(raw)

            if parsed is None:
                retry_prompt = prompt + "\nReturn valid JSON array only, no other text."
                raw2 = self.call(retry_prompt, max_tokens=2000)
                parsed = _try_parse_batch_json(raw2)

            if parsed is None:
                warnings.warn(
                    f"Batch {i // batch_size + 1}: JSON parse failed after retry, skipping batch",
                    stacklevel=2,
                )
                continue

            for entry in parsed:
                if "id" in entry and "description" in entry:
                    results[entry["id"]] = entry["description"]

        return results
