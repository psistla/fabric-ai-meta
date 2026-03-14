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
