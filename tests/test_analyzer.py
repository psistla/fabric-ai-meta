"""Tests for heuristic classifier, AI readiness scorer (Task 04), DAX parser (Task 05), and governance (Task 13)."""

import pytest

from fabric_ai_meta.analyzer.classifier import (
    classify_measure_heuristic,
    classify_table_heuristic,
)
from fabric_ai_meta.analyzer.dax_parser import build_dependency_graph, parse_measure_dependencies
from fabric_ai_meta.analyzer.governance import (
    find_duplicate_measures,
    find_naming_inconsistencies,
    generate_governance_report,
)
from fabric_ai_meta.analyzer.scorer import SCORING_WEIGHTS, score_model
from fabric_ai_meta.models.metadata import (
    ColumnMeta,
    ColumnRole,
    MeasureCategory,
    MeasureMeta,
    SemanticModelMeta,
    TableMeta,
    TableType,
)


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


# ---------------------------------------------------------------------------
# Governance (Task 13)
# ---------------------------------------------------------------------------

def _make_model(name: str, columns: list[tuple[str, str]], measures: list[tuple[str, str]]) -> SemanticModelMeta:
    """Build a minimal SemanticModelMeta with one table for governance tests."""
    cols = [
        ColumnMeta(
            name=col_name,
            data_type="string",
            description=None,
            ai_description=None,
            role=ColumnRole.ATTRIBUTE,
            is_hidden=False,
            display_folder=None,
            format_string=None,
            sort_by_column=None,
        )
        for col_name, _ in columns
    ]
    meas = [
        MeasureMeta(
            name=meas_name,
            dax_expression=dax,
            description=None,
            ai_description=None,
            category=MeasureCategory.ADDITIVE,
            display_folder=None,
            format_string=None,
        )
        for meas_name, dax in measures
    ]
    table = TableMeta(
        name="Fact",
        description=None,
        ai_description=None,
        table_type=TableType.FACT,
        grain=None,
        columns=cols,
        measures=meas,
    )
    return SemanticModelMeta(name=name, workspace="test", description=None, tables=[table])


def test_find_naming_inconsistencies_detects_divergence():
    """Two models with same concept under different surface forms must be flagged."""
    # "Customer_ID" and "CustomerID" both normalize to "customerid"
    model_a = _make_model("ModelA", [("Customer_ID", "string")], [])
    model_b = _make_model("ModelB", [("CustomerID", "string")], [])
    issues = find_naming_inconsistencies([model_a, model_b])
    normalized_names = [i["normalized"] for i in issues]
    assert "customerid" in normalized_names
    entry = next(i for i in issues if i["normalized"] == "customerid")
    assert "Customer_ID" in entry["variants"]
    assert "CustomerID" in entry["variants"]
    assert "ModelA" in entry["found_in"]
    assert "ModelB" in entry["found_in"]


def test_find_naming_inconsistencies_no_false_positives():
    """Identical column names across models should NOT be reported as inconsistencies."""
    model_a = _make_model("ModelA", [("ProductKey", "int64")], [])
    model_b = _make_model("ModelB", [("ProductKey", "int64")], [])
    issues = find_naming_inconsistencies([model_a, model_b])
    reported_norms = [i["normalized"] for i in issues]
    assert "productkey" not in reported_norms


def test_find_naming_inconsistencies_single_model_no_report():
    """Divergence within a single model is not a cross-model governance issue."""
    model_a = _make_model("ModelA", [("CustomerID", "string"), ("Cust_ID", "string")], [])
    issues = find_naming_inconsistencies([model_a])
    # Should not report because it's only one model
    assert all(len(i["found_in"]) > 1 for i in issues)


def test_find_duplicate_measures_detects_identical_dax():
    """Measures with identical DAX across models are flagged as duplicates."""
    dax = "SUM(FactSales[SalesAmount])"
    model_a = _make_model("ModelA", [], [("[Total Sales]", dax)])
    model_b = _make_model("ModelB", [], [("[Total Revenue]", dax)])
    duplicates = find_duplicate_measures([model_a, model_b])
    assert len(duplicates) == 1
    dup = duplicates[0]
    assert dup["dax_identical"] is True
    assert "ModelA" in dup["found_in"]
    assert "ModelB" in dup["found_in"]


def test_find_duplicate_measures_whitespace_normalized():
    """DAX with different whitespace should still match as duplicate."""
    model_a = _make_model("ModelA", [], [("[Total Sales]", "SUM( FactSales[SalesAmount] )")])
    model_b = _make_model("ModelB", [], [("[Total Sales]", "SUM(FactSales[SalesAmount])")])
    duplicates = find_duplicate_measures([model_a, model_b])
    assert len(duplicates) == 1


def test_find_duplicate_measures_no_false_positives():
    """Different DAX expressions must not be flagged as duplicates."""
    model_a = _make_model("ModelA", [], [("[Sales]", "SUM(FactSales[SalesAmount])")])
    model_b = _make_model("ModelB", [], [("[Units]", "SUM(FactSales[Quantity])")])
    duplicates = find_duplicate_measures([model_a, model_b])
    assert len(duplicates) == 0


def test_generate_governance_report_structure(adventure_works_model, contoso_model):
    """Report must contain all required top-level keys."""
    report = generate_governance_report([adventure_works_model, contoso_model])
    assert set(report.keys()) == {"summary", "naming_issues", "duplicate_measures", "score_ranking"}
    assert report["summary"]["model_count"] == 2
    assert isinstance(report["naming_issues"], list)
    assert isinstance(report["duplicate_measures"], list)
    assert isinstance(report["score_ranking"], list)


def test_generate_governance_report_score_ranking_ordered(adventure_works_model, contoso_model):
    """score_ranking must list models sorted by ai_readiness_score descending."""
    from fabric_ai_meta.analyzer.scorer import score_model as run_score
    for m in [adventure_works_model, contoso_model]:
        score, breakdown = run_score(m)
        m.ai_readiness_score = score
        m.scoring_breakdown = breakdown

    report = generate_governance_report([adventure_works_model, contoso_model])
    scores = [r["ai_readiness_score"] for r in report["score_ranking"] if r["ai_readiness_score"] is not None]
    assert scores == sorted(scores, reverse=True)


def test_generate_governance_report_summary_fields(adventure_works_model, contoso_model):
    """Summary fields are present and model_count is correct."""
    report = generate_governance_report([adventure_works_model, contoso_model])
    summary = report["summary"]
    assert summary["model_count"] == 2
    assert "average_readiness_score" in summary
    assert "lowest_scoring_model" in summary
