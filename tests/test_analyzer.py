"""Tests for heuristic classifier, AI readiness scorer (Task 04), and DAX parser (Task 05)."""

import pytest

from fabric_ai_meta.analyzer.classifier import (
    classify_measure_heuristic,
    classify_table_heuristic,
)
from fabric_ai_meta.analyzer.dax_parser import build_dependency_graph, parse_measure_dependencies
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


# ---------------------------------------------------------------------------
# DAX dependency parser (Task 05)
# ---------------------------------------------------------------------------

def _all_measures_dict(model):
    return {m.name: m.dax_expression for t in model.tables for m in t.measures}


def _get_measure(model, name):
    for t in model.tables:
        for m in t.measures:
            if m.name == name:
                return m
    raise KeyError(f"Measure not found: {name}")


def test_ytd_depends_on_total_sales(adventure_works_model):
    """[Internet Sales Amount YTD] must depend on [Internet Total Sales]."""
    m = _get_measure(adventure_works_model, "[Internet Sales Amount YTD]")
    result = parse_measure_dependencies(m.name, m.dax_expression, _all_measures_dict(adventure_works_model))
    assert "[Internet Total Sales]" in result["depends_on_measures"]


def test_ytd_column_refs(adventure_works_model):
    """Column refs for YTD measure should include DimDate[Date]."""
    m = _get_measure(adventure_works_model, "[Internet Sales Amount YTD]")
    result = parse_measure_dependencies(m.name, m.dax_expression, _all_measures_dict(adventure_works_model))
    assert "DimDate[Date]" in result["depends_on_columns"]


def test_ytd_ti_and_filter_functions(adventure_works_model):
    """YTD measure should report DATESYTD as TI function and CALCULATE as filter mod."""
    m = _get_measure(adventure_works_model, "[Internet Sales Amount YTD]")
    result = parse_measure_dependencies(m.name, m.dax_expression, _all_measures_dict(adventure_works_model))
    assert "DATESYTD" in result["time_intelligence_functions"]
    assert "CALCULATE" in result["filter_modifications"]


def test_additive_measure_no_measure_deps(adventure_works_model):
    """[Internet Total Sales] has no measure dependencies and one column ref."""
    m = _get_measure(adventure_works_model, "[Internet Total Sales]")
    result = parse_measure_dependencies(m.name, m.dax_expression, _all_measures_dict(adventure_works_model))
    assert result["depends_on_measures"] == []
    assert "FactInternetSales[SalesAmount]" in result["depends_on_columns"]


def test_distinct_count_no_measure_deps(adventure_works_model):
    """[Internet Distinct Count Customers] has no measure dependencies."""
    m = _get_measure(adventure_works_model, "[Internet Distinct Count Customers]")
    result = parse_measure_dependencies(m.name, m.dax_expression, _all_measures_dict(adventure_works_model))
    assert result["depends_on_measures"] == []
    assert "FactInternetSales[CustomerKey]" in result["depends_on_columns"]


def test_build_dependency_graph_structure(adventure_works_model):
    """build_dependency_graph returns a dict keyed by measure name with required keys."""
    all_measures = [m for t in adventure_works_model.tables for m in t.measures]
    graph = build_dependency_graph(all_measures)
    assert set(graph.keys()) == {m.name for m in all_measures}
    expected_keys = {
        "measure_name",
        "depends_on_measures",
        "depends_on_columns",
        "time_intelligence_functions",
        "filter_modifications",
        "implicit_business_rules",
    }
    for entry in graph.values():
        assert set(entry.keys()) == expected_keys


def test_build_dependency_graph_ytd_entry(adventure_works_model):
    """Graph entry for YTD measure reflects correct dependencies."""
    all_measures = [m for t in adventure_works_model.tables for m in t.measures]
    graph = build_dependency_graph(all_measures)
    ytd_entry = graph["[Internet Sales Amount YTD]"]
    assert "[Internet Total Sales]" in ytd_entry["depends_on_measures"]
    assert "DimDate[Date]" in ytd_entry["depends_on_columns"]
