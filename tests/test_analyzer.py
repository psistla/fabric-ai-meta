"""Tests for heuristic classifier and AI readiness scorer (Task 04)."""

import pytest

from fabric_ai_meta.analyzer.classifier import (
    classify_measure_heuristic,
    classify_table_heuristic,
)
from fabric_ai_meta.analyzer.scorer import SCORING_WEIGHTS, score_model
from fabric_ai_meta.models.metadata import MeasureCategory, TableType


# ---------------------------------------------------------------------------
# Table classification
# ---------------------------------------------------------------------------

def test_fact_table_classification(adventure_works_model):
    fact = next(t for t in adventure_works_model.tables if t.name == "FactInternetSales")
    result = classify_table_heuristic(fact, adventure_works_model.relationships)
    assert result == TableType.FACT


def test_dim_product_classification(adventure_works_model):
    dim = next(t for t in adventure_works_model.tables if t.name == "DimProduct")
    result = classify_table_heuristic(dim, adventure_works_model.relationships)
    assert result == TableType.DIMENSION


def test_all_table_classifications(adventure_works_model):
    expected = {
        "FactInternetSales": TableType.FACT,
        "DimProduct": TableType.DIMENSION,
        "DimCustomer": TableType.DIMENSION,
        "DimDate": TableType.DIMENSION,
    }
    for table in adventure_works_model.tables:
        result = classify_table_heuristic(table, adventure_works_model.relationships)
        assert result == expected[table.name], (
            f"{table.name}: expected {expected[table.name]}, got {result}"
        )


# ---------------------------------------------------------------------------
# Measure classification
# ---------------------------------------------------------------------------

def _get_measure(model, measure_name):
    for table in model.tables:
        for m in table.measures:
            if m.name == measure_name:
                return m
    raise KeyError(f"Measure not found: {measure_name}")


def test_additive_measure_classification(adventure_works_model):
    measure = _get_measure(adventure_works_model, "[Internet Total Sales]")
    assert classify_measure_heuristic(measure) == MeasureCategory.ADDITIVE


def test_time_intelligence_measure_classification(adventure_works_model):
    measure = _get_measure(adventure_works_model, "[Internet Sales Amount YTD]")
    assert classify_measure_heuristic(measure) == MeasureCategory.TIME_INTELLIGENCE


def test_non_additive_measure_classification(adventure_works_model):
    measure = _get_measure(adventure_works_model, "[Internet Distinct Count Customers]")
    assert classify_measure_heuristic(measure) == MeasureCategory.NON_ADDITIVE


# ---------------------------------------------------------------------------
# Scorer
# ---------------------------------------------------------------------------

def test_scorer_returns_float_in_range(adventure_works_model):
    score, breakdown = score_model(adventure_works_model)
    assert isinstance(score, float)
    assert 0.0 <= score <= 1.0


def test_scorer_breakdown_keys_match_weights(adventure_works_model):
    _score, breakdown = score_model(adventure_works_model)
    assert set(breakdown.keys()) == set(SCORING_WEIGHTS.keys())


def test_scorer_breakdown_values_in_range(adventure_works_model):
    _score, breakdown = score_model(adventure_works_model)
    for key, value in breakdown.items():
        assert 0.0 <= value <= 1.0, f"{key} = {value} is out of [0, 1] range"


def test_scoring_weights_sum_to_one():
    total = sum(SCORING_WEIGHTS.values())
    assert abs(total - 1.0) < 1e-9, f"SCORING_WEIGHTS sum = {total}"


def test_scorer_second_fixture(contoso_model):
    """Scorer must work on any SemanticModelMeta, not just Adventure Works."""
    score, breakdown = score_model(contoso_model)
    assert 0.0 <= score <= 1.0
    assert set(breakdown.keys()) == set(SCORING_WEIGHTS.keys())
