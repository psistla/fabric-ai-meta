"""Tests for the Prep for AI config generator and description backfill."""

import json
import os
from unittest.mock import MagicMock, patch

from fabric_ai_meta.analyzer.classifier import (
    classify_column_role,
    classify_measure_heuristic,
    classify_table_heuristic,
)
from fabric_ai_meta.extractor.mock import MockExtractor
from fabric_ai_meta.generator.description_backfill import (
    DescriptionBackfill,
    apply_backfill,
    backfill_descriptions,
)
from fabric_ai_meta.generator.prep_for_ai import generate_prep_for_ai

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


def _load_and_classify(fixture_file: str, model_name: str):
    extractor = MockExtractor(os.path.join(FIXTURES_DIR, fixture_file))
    model = extractor.extract(model_name, "test")
    for table in model.tables:
        table.table_type = classify_table_heuristic(table, model.relationships)
        for col in table.columns:
            col.role = classify_column_role(col, table, model.relationships)
        for measure in table.measures:
            measure.category = classify_measure_heuristic(measure)
    return model


def _make_mock_llm_response(text: str):
    resp = MagicMock()
    resp.choices = [MagicMock()]
    resp.choices[0].message.content = text
    resp.usage.prompt_tokens = 100
    resp.usage.completion_tokens = 50
    return resp


# ── generate_prep_for_ai WITHOUT LLM ────────────────────────────────────────


def _make_prep_llm(mock_completion):
    """Return a mocked FabricLLMClient whose call() returns valid JSON for generate_description
    and plain text for ai_instructions (call() is used for both; generate_description parses JSON)."""
    from fabric_ai_meta.llm.client import FabricLLMClient
    mock_completion.return_value = _make_mock_llm_response(
        json.dumps({"description": "A generated description"})
    )
    return FabricLLMClient(api_key="k", cache_enabled=False)


class TestGeneratePrepForAINoLLM:
    @patch("fabric_ai_meta.llm.litellm_backend.litellm.completion")
    def test_included_tables_non_staging(self, mock_completion):
        llm = _make_prep_llm(mock_completion)
        model = _load_and_classify("adventure_works.json", "Adventure Works")
        config = generate_prep_for_ai(model, llm)

        assert isinstance(config.included_tables, list)
        assert len(config.included_tables) > 0
        from fabric_ai_meta.models.metadata import TableType
        staging_names = {t.name for t in model.tables if t.table_type == TableType.STAGING}
        for name in config.included_tables:
            assert name not in staging_names

    @patch("fabric_ai_meta.llm.litellm_backend.litellm.completion")
    def test_excluded_columns_has_hidden(self, mock_completion):
        llm = _make_prep_llm(mock_completion)
        model = _load_and_classify("adventure_works.json", "Adventure Works")
        config = generate_prep_for_ai(model, llm)

        assert isinstance(config.excluded_columns, dict)
        for cols in config.excluded_columns.values():
            assert len(cols) > 0

    @patch("fabric_ai_meta.llm.litellm_backend.litellm.completion")
    def test_ai_instructions_non_empty_and_within_limit(self, mock_completion):
        llm = _make_prep_llm(mock_completion)
        model = _load_and_classify("adventure_works.json", "Adventure Works")
        config = generate_prep_for_ai(model, llm)

        assert isinstance(config.ai_instructions, str)
        assert len(config.ai_instructions) > 0
        assert len(config.ai_instructions) <= 2000

    @patch("fabric_ai_meta.llm.litellm_backend.litellm.completion")
    def test_verified_answers_non_empty_and_have_required_keys(self, mock_completion):
        llm = _make_prep_llm(mock_completion)
        model = _load_and_classify("adventure_works.json", "Adventure Works")
        config = generate_prep_for_ai(model, llm)

        assert isinstance(config.verified_answers, list)
        assert len(config.verified_answers) > 0
        assert len(config.verified_answers) <= 15
        for ans in config.verified_answers:
            assert "question" in ans
            assert "dax" in ans
            assert "description" in ans

    @patch("fabric_ai_meta.llm.litellm_backend.litellm.completion")
    def test_generated_descriptions_is_dict(self, mock_completion):
        llm = _make_prep_llm(mock_completion)
        model = _load_and_classify("adventure_works.json", "Adventure Works")
        config = generate_prep_for_ai(model, llm)

        assert isinstance(config.generated_descriptions, dict)


# ── generate_prep_for_ai WITH backfill ──────────────────────────────────────


class TestGeneratePrepForAIWithBackfill:
    @patch("fabric_ai_meta.llm.litellm_backend.litellm.completion")
    def test_backfill_populates_generated_descriptions(self, mock_completion):
        mock_client = MagicMock()
        mock_completion.return_value = mock_client
        mock_completion.return_value = _make_mock_llm_response("instructions")

        model = _load_and_classify("adventure_works.json", "Adventure Works")
        from fabric_ai_meta.llm.client import FabricLLMClient
        llm = FabricLLMClient(api_key="k", cache_enabled=False)

        backfill = DescriptionBackfill(
            column_descriptions={"FactInternetSales": {"SalesAmount": "Total sale revenue"}}
        )
        config = generate_prep_for_ai(model, llm, backfill=backfill)

        assert config.generated_descriptions == {"FactInternetSales": {"SalesAmount": "Total sale revenue"}}

    @patch("fabric_ai_meta.llm.litellm_backend.litellm.completion")
    def test_no_backfill_uses_llm_descriptions(self, mock_completion):
        llm = _make_prep_llm(mock_completion)
        model = _load_and_classify("adventure_works.json", "Adventure Works")
        for table in model.tables:
            table.description = None
            for col in table.columns:
                col.description = None

        config = generate_prep_for_ai(model, llm, backfill=None)

        assert isinstance(config.generated_descriptions, dict)


# ── backfill_descriptions ────────────────────────────────────────────────────


class TestBackfillDescriptions:
    @patch("fabric_ai_meta.llm.litellm_backend.litellm.completion")
    def test_returns_populated_backfill(self, mock_completion):
        model = _load_and_classify("adventure_works.json", "Adventure Works")
        # Clear descriptions so items are collected
        for table in model.tables:
            table.description = None
            table.ai_description = None
            for col in table.columns:
                col.description = None
                col.ai_description = None

        # Build expected response matching the ids that will be generated
        from fabric_ai_meta.llm.client import FabricLLMClient

        def make_response(*args, **kwargs):
            msgs = kwargs.get("messages", [])
            # User message is the last entry (system, if any, comes first)
            prompt_text = msgs[-1]["content"] if msgs else ""
            import re
            match = re.search(r"Items:\n(\[.*?\])\n\n", prompt_text, re.DOTALL)
            if match:
                items = json.loads(match.group(1))
                result = [{"id": item["id"], "description": f"Desc for {item['name']}"} for item in items]
            else:
                result = []
            return _make_mock_llm_response(json.dumps(result))

        mock_completion.side_effect = make_response

        llm = FabricLLMClient(api_key="k", cache_enabled=False)
        backfill = backfill_descriptions(model, llm)

        assert isinstance(backfill, DescriptionBackfill)
        # Should have some descriptions (tables or columns)
        total = (
            len(backfill.table_descriptions)
            + sum(len(v) for v in backfill.column_descriptions.values())
            + sum(len(v) for v in backfill.measure_descriptions.values())
        )
        assert total > 0

    @patch("fabric_ai_meta.llm.litellm_backend.litellm.completion")
    def test_apply_backfill_sets_ai_description(self, mock_completion):
        mock_completion.return_value = _make_mock_llm_response("[]")

        model = _load_and_classify("adventure_works.json", "Adventure Works")

        backfill = DescriptionBackfill(
            table_descriptions={"FactInternetSales": "Internet sales fact table"},
            column_descriptions={"FactInternetSales": {"SalesAmount": "Revenue from sale"}},
            measure_descriptions={},
        )
        apply_backfill(model, backfill)

        fact = next(t for t in model.tables if t.name == "FactInternetSales")
        assert fact.ai_description == "Internet sales fact table"
        sales_amount = next(c for c in fact.columns if c.name == "SalesAmount")
        assert sales_amount.ai_description == "Revenue from sale"

    @patch("fabric_ai_meta.llm.litellm_backend.litellm.completion")
    def test_already_described_items_excluded(self, mock_completion):
        # We'll track what items are sent to the LLM
        captured_items = []

        def capture_response(*args, **kwargs):
            msgs = kwargs.get("messages", [])
            prompt = msgs[-1]["content"] if msgs else ""
            import re
            match = re.search(r"Items:\n(\[.*?\])\n\n", prompt, re.DOTALL)
            if match:
                captured_items.extend(json.loads(match.group(1)))
            return _make_mock_llm_response("[]")

        mock_completion.side_effect = capture_response

        model = _load_and_classify("adventure_works.json", "Adventure Works")
        # FactInternetSales already has descriptions, should NOT appear in items
        fact = next(t for t in model.tables if t.name == "FactInternetSales")
        fact.description = "Has a description"

        from fabric_ai_meta.llm.client import FabricLLMClient
        llm = FabricLLMClient(api_key="k", cache_enabled=False)
        backfill_descriptions(model, llm)

        table_ids = [item["id"] for item in captured_items if item["type"] == "table"]
        assert "table:FactInternetSales" not in table_ids
