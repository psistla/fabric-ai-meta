"""Tests for LLM integration: cache, client (mocked via LiteLLM), and prompt templates."""

import json
import os
from unittest.mock import MagicMock, patch

import pytest

from fabric_ai_meta.llm.cache import LLMCache
from fabric_ai_meta.llm.client import CostLimitExceededError, FabricLLMClient
from fabric_ai_meta.llm.prompts import (
    AI_INSTRUCTIONS_PROMPT,
    DESCRIPTION_GENERATION_PROMPT,
    GRAIN_DETECTION_PROMPT,
    TABLE_CLASSIFICATION_PROMPT,
)
from fabric_ai_meta.models.metadata import (
    ColumnMeta,
    ColumnRole,
    RelationshipMeta,
    TableMeta,
    TableType,
)

LITELLM_COMPLETION_PATCH = "fabric_ai_meta.llm.litellm_backend.litellm.completion"


def _make_mock_response(text: str, input_tokens: int = 100, output_tokens: int = 50):
    """Create a mock LiteLLM completion response."""
    response = MagicMock()
    response.choices = [MagicMock()]
    response.choices[0].message.content = text
    response.usage.prompt_tokens = input_tokens
    response.usage.completion_tokens = output_tokens
    return response


# ── Cache tests ──────────────────────────────────────────────────────────────


class TestLLMCache:
    def test_set_and_get_round_trip(self, tmp_path):
        cache = LLMCache(cache_dir=str(tmp_path / "cache"))
        key = cache.make_key("test prompt")
        cache.set(key, "test response")
        assert cache.get(key) == "test response"

    def test_cache_miss_returns_none(self, tmp_path):
        cache = LLMCache(cache_dir=str(tmp_path / "cache"))
        assert cache.get("nonexistent_key") is None

    def test_make_key_deterministic(self):
        cache = LLMCache()
        key1 = cache.make_key("hello world")
        key2 = cache.make_key("hello world")
        assert key1 == key2

    def test_make_key_different_prompts_different_keys(self):
        cache = LLMCache()
        key1 = cache.make_key("prompt A")
        key2 = cache.make_key("prompt B")
        assert key1 != key2

    def test_cache_creates_directory(self, tmp_path):
        cache_dir = str(tmp_path / "new_cache_dir")
        assert not os.path.exists(cache_dir)
        LLMCache(cache_dir=cache_dir)
        assert os.path.isdir(cache_dir)

    def test_cache_overwrites_existing_key(self, tmp_path):
        cache = LLMCache(cache_dir=str(tmp_path / "cache"))
        key = cache.make_key("prompt")
        cache.set(key, "response 1")
        cache.set(key, "response 2")
        assert cache.get(key) == "response 2"


# ── Client tests (mocked LiteLLM) ───────────────────────────────────────────


class TestFabricLLMClient:
    @patch(LITELLM_COMPLETION_PATCH)
    def test_call_returns_response_text(self, mock_completion, tmp_path):
        mock_completion.return_value = _make_mock_response("hello")

        client = FabricLLMClient(
            api_key="test-key",
            cache_enabled=True,
            cache_dir=str(tmp_path / "cache"),
        )
        result = client.call("test prompt")
        assert result == "hello"
        mock_completion.assert_called_once()

    @patch(LITELLM_COMPLETION_PATCH)
    def test_call_uses_cache(self, mock_completion, tmp_path):
        mock_completion.return_value = _make_mock_response("cached result")

        client = FabricLLMClient(
            api_key="test-key",
            cache_enabled=True,
            cache_dir=str(tmp_path / "cache"),
        )

        result1 = client.call("same prompt")
        assert result1 == "cached result"
        assert mock_completion.call_count == 1

        result2 = client.call("same prompt")
        assert result2 == "cached result"
        assert mock_completion.call_count == 1

    @patch(LITELLM_COMPLETION_PATCH)
    def test_call_without_cache(self, mock_completion, tmp_path):
        mock_completion.return_value = _make_mock_response("no cache")

        client = FabricLLMClient(api_key="test-key", cache_enabled=False)
        result = client.call("test prompt")
        assert result == "no cache"

    @patch(LITELLM_COMPLETION_PATCH)
    def test_cost_limit_exceeded(self, mock_completion, tmp_path):
        mock_completion.return_value = _make_mock_response(
            "expensive", input_tokens=1_000_000, output_tokens=500_000
        )

        client = FabricLLMClient(
            api_key="test-key",
            cache_enabled=False,
            max_cost_usd=0.01,
        )
        with pytest.raises(CostLimitExceededError):
            client.call("expensive prompt")

    @patch(LITELLM_COMPLETION_PATCH)
    def test_classify_table(self, mock_completion, tmp_path):
        mock_completion.return_value = _make_mock_response(
            json.dumps({"table_type": "fact", "confidence": 0.95, "reasoning": "Has measures and FK columns"})
        )

        client = FabricLLMClient(api_key="test-key", cache_enabled=False)

        table = TableMeta(
            name="FactSales",
            description=None,
            ai_description=None,
            table_type=TableType.UNKNOWN,
            grain=None,
            columns=[
                ColumnMeta(name="SalesAmount", data_type="double", description=None,
                           ai_description=None, role=ColumnRole.MEASURE_COLUMN,
                           is_hidden=False, display_folder=None, format_string=None,
                           sort_by_column=None),
            ],
        )
        relationships = [
            RelationshipMeta(
                from_table="FactSales", from_column="ProductKey",
                to_table="DimProduct", to_column="ProductKey",
                cardinality="many-to-one", cross_filter_direction="single",
                is_active=True,
            )
        ]

        table_type, confidence = client.classify_table(table, relationships)
        assert table_type == TableType.FACT
        assert confidence == 0.95

    @patch(LITELLM_COMPLETION_PATCH)
    def test_detect_grain(self, mock_completion, tmp_path):
        mock_completion.return_value = _make_mock_response(
            json.dumps({"grain": "one row per sales order line item", "confidence": 0.9})
        )

        client = FabricLLMClient(api_key="test-key", cache_enabled=False)

        table = TableMeta(
            name="FactSales",
            description=None,
            ai_description=None,
            table_type=TableType.FACT,
            grain=None,
            columns=[
                ColumnMeta(name="SalesOrderNumber", data_type="string", description=None,
                           ai_description=None, role=ColumnRole.KEY,
                           is_hidden=False, display_folder=None, format_string=None,
                           sort_by_column=None),
            ],
        )

        grain, confidence = client.detect_grain(table)
        assert grain == "one row per sales order line item"
        assert confidence == 0.9

    @patch(LITELLM_COMPLETION_PATCH)
    def test_generate_description(self, mock_completion, tmp_path):
        mock_completion.return_value = _make_mock_response(
            json.dumps({"description": "Total revenue from internet sales channels"})
        )

        client = FabricLLMClient(api_key="test-key", cache_enabled=False)

        desc = client.generate_description(
            obj_type="measure",
            name="Internet Total Sales",
            context={
                "parent_table": "FactInternetSales",
                "dax": "SUM(FactInternetSales[SalesAmount])",
                "sibling_descriptions": "OrderQuantity: Number of items ordered",
            },
        )
        assert desc == "Total revenue from internet sales channels"

    @patch(LITELLM_COMPLETION_PATCH)
    def test_token_tracking_accumulates(self, mock_completion, tmp_path):
        mock_completion.return_value = _make_mock_response(
            "ok", input_tokens=200, output_tokens=100
        )

        client = FabricLLMClient(api_key="test-key", cache_enabled=False)
        client.call("prompt 1")
        client.call("prompt 2")

        assert client._total_input_tokens == 400
        assert client._total_output_tokens == 200


# ── Prompt template tests ────────────────────────────────────────────────────


class TestPromptTemplates:
    def test_table_classification_prompt_has_placeholders(self):
        assert "{table_name}" in TABLE_CLASSIFICATION_PROMPT
        assert "{column_list}" in TABLE_CLASSIFICATION_PROMPT
        assert "{relationship_summary}" in TABLE_CLASSIFICATION_PROMPT
        assert "{possible_types}" in TABLE_CLASSIFICATION_PROMPT

    def test_grain_detection_prompt_has_placeholders(self):
        assert "{table_name}" in GRAIN_DETECTION_PROMPT
        assert "{column_list}" in GRAIN_DETECTION_PROMPT
        assert "{row_count}" in GRAIN_DETECTION_PROMPT
        assert "{sample_values}" in GRAIN_DETECTION_PROMPT

    def test_description_generation_prompt_has_placeholders(self):
        assert "{obj_type}" in DESCRIPTION_GENERATION_PROMPT
        assert "{name}" in DESCRIPTION_GENERATION_PROMPT
        assert "{parent_table}" in DESCRIPTION_GENERATION_PROMPT

    def test_ai_instructions_prompt_has_placeholders(self):
        assert "{model_name}" in AI_INSTRUCTIONS_PROMPT
        assert "{table_summary}" in AI_INSTRUCTIONS_PROMPT
        assert "{measure_summary}" in AI_INSTRUCTIONS_PROMPT
        assert "{relationship_summary}" in AI_INSTRUCTIONS_PROMPT

    def test_table_classification_prompt_formats_without_error(self):
        result = TABLE_CLASSIFICATION_PROMPT.format(
            table_name="TestTable",
            column_list="  - Col1, string",
            relationship_summary="No relationships.",
            possible_types="fact, dimension",
        )
        assert "TestTable" in result

    def test_batch_description_prompt_has_placeholders(self):
        from fabric_ai_meta.llm.prompts import BATCH_DESCRIPTION_PROMPT
        assert "{model_name}" in BATCH_DESCRIPTION_PROMPT
        assert "{items_json}" in BATCH_DESCRIPTION_PROMPT


# ── generate_descriptions_batch tests ───────────────────────────────────────


class TestGenerateDescriptionsBatch:
    def _make_items(self, n: int) -> list[dict]:
        return [
            {
                "id": f"column:Sales:Col{i}",
                "type": "column",
                "name": f"Col{i}",
                "parent_table": "Sales",
                "data_type": "string",
                "siblings": "Col0, Col1",
            }
            for i in range(n)
        ]

    @patch(LITELLM_COMPLETION_PATCH)
    def test_returns_descriptions_mapped_by_id(self, mock_completion, tmp_path):
        items = self._make_items(3)
        expected = [{"id": item["id"], "description": f"Desc {i}"} for i, item in enumerate(items)]
        mock_completion.return_value = _make_mock_response(json.dumps(expected))

        client = FabricLLMClient(api_key="k", cache_enabled=False)
        result = client.generate_descriptions_batch(items, "TestModel")

        assert len(result) == 3
        for item in items:
            assert item["id"] in result

    @patch(LITELLM_COMPLETION_PATCH)
    def test_batches_split_correctly(self, mock_completion, tmp_path):
        items = self._make_items(30)
        mock_completion.side_effect = lambda *a, **kw: _make_mock_response("[]")

        client = FabricLLMClient(api_key="k", cache_enabled=False)
        client.generate_descriptions_batch(items, "TestModel", batch_size=15)

        assert mock_completion.call_count == 2

    @patch(LITELLM_COMPLETION_PATCH)
    def test_parse_failure_retries_then_skips(self, mock_completion, tmp_path):
        items_bad = self._make_items(2)
        items_good = self._make_items(1)
        items_good[0]["id"] = "column:Sales:GoodCol"
        all_items = items_bad + items_good

        mock_completion.side_effect = [
            _make_mock_response("not valid json"),
            _make_mock_response("still not json"),
            _make_mock_response(json.dumps([{"id": "column:Sales:GoodCol", "description": "Good"}])),
        ]

        client = FabricLLMClient(api_key="k", cache_enabled=False)
        import warnings
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            result = client.generate_descriptions_batch(all_items, "TestModel", batch_size=2)

        assert "column:Sales:GoodCol" in result
        assert result["column:Sales:GoodCol"] == "Good"
        assert len(w) == 1
        assert "skipping batch" in str(w[0].message).lower()

    @patch(LITELLM_COMPLETION_PATCH)
    def test_id_round_trip(self, mock_completion, tmp_path):
        items = [
            {"id": "table:DimProduct", "type": "table", "name": "DimProduct",
             "parent_table": "DimProduct", "siblings": ""},
            {"id": "column:Sales:Amount", "type": "column", "name": "Amount",
             "parent_table": "Sales", "data_type": "decimal", "siblings": ""},
            {"id": "measure:Sales:Total Sales", "type": "measure", "name": "Total Sales",
             "parent_table": "Sales", "dax": "SUM(Sales[Amount])", "siblings": ""},
        ]
        expected = [{"id": item["id"], "description": f"Desc for {item['name']}"} for item in items]
        mock_completion.return_value = _make_mock_response(json.dumps(expected))

        client = FabricLLMClient(api_key="k", cache_enabled=False)
        result = client.generate_descriptions_batch(items, "TestModel")

        assert result["table:DimProduct"] == "Desc for DimProduct"
        assert result["column:Sales:Amount"] == "Desc for Amount"
        assert result["measure:Sales:Total Sales"] == "Desc for Total Sales"
