"""Tests for MockExtractor and fixture loading."""

import json
import os

import pytest

from fabric_ai_meta.extractor.mock import MockExtractor
from fabric_ai_meta.models.metadata import SemanticModelMeta, from_dict

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


def test_mock_extractor_returns_semantic_model_meta(adventure_works_model):
    assert isinstance(adventure_works_model, SemanticModelMeta)


def test_adventure_works_table_count(adventure_works_model):
    assert len(adventure_works_model.tables) == 4


def test_adventure_works_table_names(adventure_works_model):
    names = {t.name for t in adventure_works_model.tables}
    assert names == {"FactInternetSales", "DimProduct", "DimCustomer", "DimDate"}


def test_adventure_works_relationship_count(adventure_works_model):
    assert len(adventure_works_model.relationships) == 3


def test_adventure_works_extraction_method(adventure_works_model):
    assert adventure_works_model.extraction_method == "mock"


def test_adventure_works_ai_readiness_score_null(adventure_works_model):
    assert adventure_works_model.ai_readiness_score is None


def test_adventure_works_fact_table_measures(adventure_works_model):
    fact = next(t for t in adventure_works_model.tables if t.name == "FactInternetSales")
    measure_names = {m.name for m in fact.measures}
    assert "[Internet Total Sales]" in measure_names
    assert "[Internet Sales Amount YTD]" in measure_names
    assert "[Internet Distinct Count Customers]" in measure_names


def test_contoso_model_returns_semantic_model_meta(contoso_model):
    assert isinstance(contoso_model, SemanticModelMeta)


def test_contoso_model_table_count(contoso_model):
    assert len(contoso_model.tables) >= 3


def test_contoso_model_measure_count(contoso_model):
    total_measures = sum(len(t.measures) for t in contoso_model.tables)
    assert total_measures >= 5


def test_contoso_model_relationship_count(contoso_model):
    assert len(contoso_model.relationships) >= 2


def test_to_dict_round_trip(adventure_works_model):
    """to_dict() → json.dumps() → json.loads() → from_dict() produces an identical model."""
    original_dict = adventure_works_model.to_dict()
    json_str = json.dumps(original_dict)
    restored_dict = json.loads(json_str)
    restored_model = from_dict(restored_dict)

    assert restored_model.name == adventure_works_model.name
    assert restored_model.workspace == adventure_works_model.workspace
    assert len(restored_model.tables) == len(adventure_works_model.tables)
    assert len(restored_model.relationships) == len(adventure_works_model.relationships)


def test_to_dict_is_json_serializable(adventure_works_model):
    d = adventure_works_model.to_dict()
    result = json.dumps(d)
    assert isinstance(result, str)
    assert len(result) > 0


def test_list_models_returns_model_names():
    """list_models calls fabric.list_datasets and returns model name strings."""
    from unittest.mock import MagicMock

    import pandas as pd

    from fabric_ai_meta.extractor.semantic_link import SemanticLinkExtractor

    mock_fabric = MagicMock()
    mock_df = pd.DataFrame({"Dataset Name": ["Adventure Works", "Contoso Sales"]})
    mock_fabric.list_datasets.return_value = mock_df

    # Bypass __init__ (requires Fabric runtime) by creating instance directly
    extractor = object.__new__(SemanticLinkExtractor)
    extractor.workspace = "test"
    extractor._fabric = mock_fabric

    names = extractor.list_models("test")

    assert "Adventure Works" in names
    assert "Contoso Sales" in names
    assert len(names) == 2


def test_list_models_empty_when_no_datasets():
    """list_models returns empty list when no known column is present."""
    from unittest.mock import MagicMock

    import pandas as pd

    from fabric_ai_meta.extractor.semantic_link import SemanticLinkExtractor

    mock_fabric = MagicMock()
    mock_fabric.list_datasets.return_value = pd.DataFrame()

    extractor = object.__new__(SemanticLinkExtractor)
    extractor.workspace = "test"
    extractor._fabric = mock_fabric

    names = extractor.list_models("test")
    assert names == []


def test_mock_extractor_fixture_path(tmp_path):
    """MockExtractor uses the fixture_path provided at construction."""
    fixture = tmp_path / "model.json"
    fixture.write_text(json.dumps({
        "name": "Test Model",
        "workspace": "Test WS",
        "description": None,
        "tables": [],
        "relationships": [],
        "ai_readiness_score": None,
        "scoring_breakdown": {},
        "extraction_timestamp": None,
        "extraction_method": "mock"
    }))
    extractor = MockExtractor(str(fixture))
    model = extractor.extract("Test Model", "Test WS")
    assert model.name == "Test Model"
    assert model.tables == []


# ── MockExtractor directory mode ─────────────────────────────────────────────


def test_mock_extractor_dir_list_models_returns_both_fixture_names():
    extractor = MockExtractor(fixture_dir=FIXTURES_DIR)
    names = extractor.list_models("any")
    assert "Adventure Works" in names
    assert "Contoso Sales" in names


def test_mock_extractor_dir_list_models_sorted():
    extractor = MockExtractor(fixture_dir=FIXTURES_DIR)
    names = extractor.list_models("any")
    assert names == sorted(names)


def test_mock_extractor_dir_extract_adventure_works():
    extractor = MockExtractor(fixture_dir=FIXTURES_DIR)
    model = extractor.extract("Adventure Works", "any")
    assert model.name == "Adventure Works"
    assert len(model.tables) == 4


def test_mock_extractor_dir_extract_case_insensitive():
    extractor = MockExtractor(fixture_dir=FIXTURES_DIR)
    model = extractor.extract("adventure works", "any")
    assert model.name == "Adventure Works"


def test_mock_extractor_dir_extract_nonexistent_raises():
    extractor = MockExtractor(fixture_dir=FIXTURES_DIR)
    with pytest.raises(FileNotFoundError):
        extractor.extract("Nonexistent Model", "any")


def test_mock_extractor_fixture_path_list_models_single_item():
    extractor = MockExtractor(fixture_path=os.path.join(FIXTURES_DIR, "adventure_works.json"))
    names = extractor.list_models("any")
    assert names == ["Adventure Works"]


def test_mock_extractor_backward_compat_single_file():
    """Single-file usage must still work identically for backward compatibility."""
    extractor = MockExtractor(fixture_path=os.path.join(FIXTURES_DIR, "adventure_works.json"))
    model = extractor.extract("Adventure Works", "test")
    assert isinstance(model, SemanticModelMeta)
    assert len(model.tables) == 4


# ── Enterprise fixture + multi-model (3 fixtures) ──────────────────────────


def test_mock_extractor_dir_list_models_returns_three_fixtures():
    """list_models with fixture_dir picks up all 3 JSON fixtures."""
    extractor = MockExtractor(fixture_dir=FIXTURES_DIR)
    names = extractor.list_models("any")
    assert "Adventure Works" in names
    assert "Contoso Sales" in names
    assert "Enterprise Sales" in names
    assert len(names) == 3


def test_mock_extractor_dir_extract_enterprise_sales():
    """Extracting Enterprise Sales from fixture_dir works."""
    extractor = MockExtractor(fixture_dir=FIXTURES_DIR)
    model = extractor.extract("Enterprise Sales", "any")
    assert model.name == "Enterprise Sales"
    assert len(model.tables) == 14


def test_enterprise_model_has_expected_table_count(enterprise_sales_model):
    """Enterprise model should have 14 tables."""
    assert len(enterprise_sales_model.tables) == 14


def test_enterprise_model_has_expected_measure_count(enterprise_sales_model):
    """Enterprise model should have 20+ measures."""
    total = sum(len(t.measures) for t in enterprise_sales_model.tables)
    assert total >= 20


def test_enterprise_model_has_expected_relationship_count(enterprise_sales_model):
    """Enterprise model should have 10+ relationships."""
    assert len(enterprise_sales_model.relationships) >= 10


def test_enterprise_model_has_hierarchies(enterprise_sales_model):
    """Enterprise model should have 2+ hierarchies."""
    total = sum(len(t.hierarchies) for t in enterprise_sales_model.tables)
    assert total >= 2


def test_enterprise_model_round_trip(enterprise_sales_model):
    """to_dict -> JSON -> from_dict round-trip preserves enterprise model."""
    original_dict = enterprise_sales_model.to_dict()
    json_str = json.dumps(original_dict)
    restored_dict = json.loads(json_str)
    restored_model = from_dict(restored_dict)
    assert restored_model.name == enterprise_sales_model.name
    assert len(restored_model.tables) == len(enterprise_sales_model.tables)
    assert len(restored_model.relationships) == len(enterprise_sales_model.relationships)


def test_semanticmodelmeta_copilot_defaults_to_none_and_is_optional():
    """v1.4.0 adds an optional copilot field; existing constructors must not break."""
    from fabric_ai_meta.models.metadata import SemanticModelMeta

    model = SemanticModelMeta(
        name="X",
        workspace="W",
        description=None,
        tables=[],
        relationships=[],
        ai_readiness_score=None,
        scoring_breakdown={},
        extraction_timestamp="2026-01-01T00:00:00Z",
        extraction_method="mock",
    )
    assert model.copilot is None
    # Round-trip must still work; copilot omitted from input dict
    d = model.to_dict()
    assert "copilot" in d
    assert d["copilot"] is None
