from fabric_ai_meta.analyzer.query_guidance import (
    _calc_group_reference,
    _find_join_path,
    _report_plumbing_reason,
    _resolve_base_table,
    _warnings_for_measure,
)
from fabric_ai_meta.models.metadata import (
    MeasureCategory,
    MeasureMeta,
    RelationshipMeta,
    SemanticModelMeta,
    TableMeta,
)


def _measure(name, dax, depends_on_measures=(), depends_on_columns=()):
    return MeasureMeta(
        name=name,
        dax_expression=dax,
        description=None,
        ai_description=None,
        category=MeasureCategory.UNKNOWN,
        display_folder=None,
        format_string=None,
        depends_on_measures=list(depends_on_measures),
        depends_on_columns=list(depends_on_columns),
    )


def test_resolve_base_table_direct_column_ref():
    m = _measure("Sales", "SUM('Financials'[Sales])", depends_on_columns=["Financials[Sales]"])
    assert _resolve_base_table(m, {"Sales": m}) == "Financials"


def test_resolve_base_table_prefers_measure_ref_over_own_column_ref():
    # [Sales YTD] = TOTALYTD([Sales], 'Date'[Date]) - the literal column ref here is the
    # *filter argument*, not the aggregated table. Must not resolve to "Date".
    sales = _measure("Sales", "SUM('Financials'[Sales])", depends_on_columns=["Financials[Sales]"])
    ytd = _measure(
        "Sales YTD", "TOTALYTD([Sales], 'Date'[Date])",
        depends_on_measures=["[Sales]"], depends_on_columns=["Date[Date]"],
    )
    assert _resolve_base_table(ytd, {"Sales": sales, "Sales YTD": ytd}) == "Financials"


def test_resolve_base_table_multi_hop():
    base = _measure("Revenue", "SUM('fact'[amt])", depends_on_columns=["fact[amt]"])
    mid = _measure("Ratio", "DIVIDE([Revenue],[Revenue])", depends_on_measures=["[Revenue]"])
    top = _measure("Top", "[Ratio] * 2", depends_on_measures=["[Ratio]"])
    by_name = {"Revenue": base, "Ratio": mid, "Top": top}
    assert _resolve_base_table(top, by_name) == "fact"


def test_resolve_base_table_unresolvable_returns_none():
    orphan = _measure("Mystery", "1 + 1")
    assert _resolve_base_table(orphan, {"Mystery": orphan}) is None


def test_find_join_path_same_table_is_no_join():
    assert _find_join_path([], "fact", "fact") == ["fact"]


def test_find_join_path_single_hop():
    rels = [RelationshipMeta("fact", "dim_id", "dim", "id", "many-to-one", "single", True)]
    assert _find_join_path(rels, "fact", "dim") == ["fact", "dim"]


def test_find_join_path_ignores_inactive_relationship():
    rels = [RelationshipMeta("fact", "dim_id", "dim", "id", "many-to-one", "single", False)]
    assert _find_join_path(rels, "fact", "dim") is None


def test_find_join_path_unreachable():
    rels = [RelationshipMeta("fact", "date_id", "date", "id", "many-to-one", "single", True)]
    assert _find_join_path(rels, "fact", "unrelated_table") is None


def test_resolve_base_table_dangling_measure_ref_falls_back_to_own_columns():
    # A measure ref that doesn't exist in measures_by_name must not silently
    # return None when the node has its own columns to fall back to.
    m = _measure(
        "Weird", "[Ghost] + 1", depends_on_measures=["[Ghost]"],
        depends_on_columns=["Financials[Sales]"],
    )
    assert _resolve_base_table(m, {"Weird": m}) == "Financials"


def test_resolve_base_table_diamond_dependency_not_corrupted_by_sibling_seen():
    # Top depends on two branches (A, B) that both resolve through a shared
    # measure C. Processing A first must not "claim" C in a way that makes
    # B wrongly think it has no resolvable ref and fall back to B's own
    # (irrelevant) column reference.
    c = _measure("C", "SUM('TrueTable'[amt])", depends_on_columns=["TrueTable[amt]"])
    a = _measure("A", "[C] * 1", depends_on_measures=["[C]"])
    b = _measure(
        "B", "TOTALYTD([C], 'WrongTable'[Date])",
        depends_on_measures=["[C]"], depends_on_columns=["WrongTable[Date]"],
    )
    top = _measure("Top", "[A] + [B]", depends_on_measures=["[A]", "[B]"])
    by_name = {"C": c, "A": a, "B": b, "Top": top}
    assert _resolve_base_table(top, by_name) == "TrueTable"


# Task 2: Measure lookup and warning detectors


def _table(name, measures=(), partition="Import"):
    return TableMeta(
        name=name, description=None, ai_description=None,
        table_type=None, grain=None, measures=list(measures),
        source_partition_type=partition,
    )


def _model(tables, relationships=()):
    return SemanticModelMeta(
        name="t", workspace="", description=None,
        tables=list(tables), relationships=list(relationships),
    )


def test_report_plumbing_data_uri():
    assert _report_plumbing_reason('"data:image/svg+xml,..."') == "returns an embedded image (data URI)"


def test_report_plumbing_whole_string_literal():
    assert _report_plumbing_reason('"#F8696B"') == "returns a fixed string literal"


def test_report_plumbing_format_call():
    assert _report_plumbing_reason('FORMAT([Sales], "$#,##0")') == "returns a formatted display string"


def test_report_plumbing_not_flagged_for_real_measure():
    assert _report_plumbing_reason("SUM('Financials'[Sales])") is None


def test_calc_group_reference_detected_via_missing_partition():
    calc_group = _table("Time Calculation", partition=None)
    real_table = _table("Financials")
    model = _model([calc_group, real_table])
    dax = 'CALCULATE([Sales], \'Time Calculation\'[Time Calculation] = "MoM")'
    assert _calc_group_reference(model, dax) == "Time Calculation"


def test_calc_group_reference_ignores_real_column_filter():
    real_table = _table("Financials")
    model = _model([real_table])
    dax = "CALCULATE([Sales], 'Financials'[Discount Band] = \"High\")"
    assert _calc_group_reference(model, dax) is None


def test_warnings_semi_additive():
    m = _measure(
        "Revenue Month End", "CLOSINGBALANCEMONTH([Revenue], dim_date[date_actual])",
        depends_on_measures=["[Revenue]"],
    )
    m.category = MeasureCategory.SEMI_ADDITIVE
    warnings = _warnings_for_measure(_model([]), m)
    assert any(w["type"] == "semi_additive" for w in warnings)


def test_warnings_ratio():
    m = _measure("Gross Margin %", "DIVIDE([Profit], [Sales])", depends_on_measures=["[Profit]", "[Sales]"])
    m.category = MeasureCategory.NON_ADDITIVE
    warnings = _warnings_for_measure(_model([]), m)
    assert any(w["type"] == "ratio" for w in warnings)


def test_warnings_hardcoded_literal():
    m = _measure("Carbon Intensity Target", "0.09")
    warnings = _warnings_for_measure(_model([]), m)
    assert any(w["type"] == "hardcoded_literal" for w in warnings)
