from fabric_ai_meta.analyzer.query_guidance import (
    _calc_group_reference,
    _find_join_path,
    _report_plumbing_reason,
    _resolve_base_table,
    _warnings_for_measure,
    guide_query,
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


# Task 3: guide_query orchestration - measure path


def test_guide_query_requires_exactly_one_of_measure_or_column():
    model = _model([])
    assert guide_query(model)["refusal"] is not None
    assert guide_query(model, measure="X", column="Y")["refusal"] is not None


def test_guide_query_measure_not_found():
    model = _model([_table("Financials")])
    result = guide_query(model, measure="Nonexistent")
    assert result["refusal"] == "No measure named 'Nonexistent' in this model."


def test_guide_query_returns_measure_and_warnings():
    sales = _measure("Sales", "SUM('Financials'[Sales])", depends_on_columns=["Financials[Sales]"])
    sales.category = MeasureCategory.ADDITIVE
    ratio = _measure("Gross Margin %", "DIVIDE([Profit], [Sales])", depends_on_measures=["[Profit]", "[Sales]"])
    ratio.category = MeasureCategory.NON_ADDITIVE
    model = _model([_table("Financials", measures=[sales, ratio])])

    result = guide_query(model, measure="Gross Margin %")
    assert result["refusal"] is None
    assert result["measure"]["name"] == "Gross Margin %"
    assert result["measure"]["table"] == "Financials"
    assert any(w["type"] == "ratio" for w in result["warnings"])


def test_guide_query_excludes_report_plumbing_measure():
    icon = _measure("COGS icon", '"data:image/svg+xml,..."')
    model = _model([_table("Formatting", measures=[icon])])

    result = guide_query(model, measure="COGS icon")
    assert result["measure"]["name"] == "COGS icon"
    assert result["excluded"]["reason"] == "report_plumbing"
    assert result["warnings"] == []


# Task 4: guide_query column path and redirect


def test_guide_query_column_not_found():
    model = _model([_table("Financials")])
    result = guide_query(model, column="Nonexistent")
    assert result["refusal"] == "No column named 'Nonexistent' in this model."


def test_guide_query_redirects_wrapped_column_to_its_measure_on_another_table():
    """The wrapper measure deliberately lives on a DIFFERENT table than the
    column - the `_Measures`/`Calculations` pattern both real fixtures use.
    A version of this test that puts the column and its wrapper measure on
    the same table would pass even if the wrapper search were wrongly scoped
    to only that one table - exactly the bug review caught. Do not
    'simplify' this back to a single-table fixture."""
    from fabric_ai_meta.models.metadata import ColumnMeta

    sales_col = ColumnMeta(
        name="Sales", data_type="", description=None, ai_description=None,
        role=None, is_hidden=True, display_folder=None, format_string=None,
        sort_by_column=None,
    )
    financials = _table("Financials")
    financials.columns = [sales_col]
    sales_measure = _measure("Sales", "SUM('Financials'[Sales])", depends_on_columns=["Financials[Sales]"])
    sales_measure.category = MeasureCategory.ADDITIVE
    calculations = _table("Calculations", measures=[sales_measure])
    model = _model([financials, calculations])

    result = guide_query(model, column="Sales")
    assert result["redirect"]["to_measure"] == "Sales"
    assert result["measure"]["name"] == "Sales"
    assert result["measure"]["table"] == "Calculations"  # the MEASURE's table, not the column's


def test_guide_query_column_with_no_wrapper_measure_warns_instead_of_guessing():
    from fabric_ai_meta.models.metadata import ColumnMeta

    ratio_col = ColumnMeta(
        name="co2e_per_revenue_dollar", data_type="double", description=None,
        ai_description=None, role=None, is_hidden=False, display_folder=None,
        format_string=None, sort_by_column=None,
    )
    fact = _table("fact_order_line")
    fact.columns = [ratio_col]
    model = _model([fact])

    result = guide_query(model, column="co2e_per_revenue_dollar")
    assert result["redirect"] is None
    assert any(w["type"] == "unwrapped_column" for w in result["warnings"])


def test_guide_query_column_ambiguous_across_tables_warns_and_uses_first_hit():
    from fabric_ai_meta.models.metadata import ColumnMeta

    def region_col():
        return ColumnMeta(
            name="region", data_type="string", description=None, ai_description=None,
            role=None, is_hidden=False, display_folder=None, format_string=None,
            sort_by_column=None,
        )

    dim_a = _table("dim_customer")
    dim_a.columns = [region_col()]
    dim_b = _table("dim_supplier")
    dim_b.columns = [region_col()]
    model = _model([dim_a, dim_b])

    result = guide_query(model, column="region")
    assert any(w["type"] == "ambiguous_column_name" for w in result["warnings"])


def test_guide_query_wrapper_search_ignores_same_table_decoy_for_different_column():
    """A same-table ADDITIVE wrapper for a DIFFERENT column must not be
    mistaken for the real cross-table wrapper of the requested column - the
    exact `depends_on_columns == [target_dep]` match is what prevents this."""
    from fabric_ai_meta.models.metadata import ColumnMeta

    sales_col = ColumnMeta(
        name="Sales", data_type="", description=None, ai_description=None,
        role=None, is_hidden=True, display_folder=None, format_string=None,
        sort_by_column=None,
    )
    financials = _table("Financials")
    financials.columns = [sales_col]
    # Decoy: an ADDITIVE wrapper on Financials itself, but for "Cost", not "Sales".
    cost_wrapper = _measure("CostWrapper", "SUM('Financials'[Cost])", depends_on_columns=["Financials[Cost]"])
    cost_wrapper.category = MeasureCategory.ADDITIVE
    financials.measures = [cost_wrapper]
    # Real wrapper for "Sales", on a different table.
    sales_wrapper = _measure("SalesWrapper", "SUM('Financials'[Sales])", depends_on_columns=["Financials[Sales]"])
    sales_wrapper.category = MeasureCategory.ADDITIVE
    calculations = _table("Calculations", measures=[sales_wrapper])
    model = _model([financials, calculations])

    result = guide_query(model, column="Sales")
    assert result["redirect"]["to_measure"] == "SalesWrapper"
    assert result["measure"]["table"] == "Calculations"


# Task 5: guide_query dimension resolution


def test_guide_query_dimension_resolved_no_join_needed():
    from fabric_ai_meta.models.metadata import ColumnMeta

    sales = _measure("Sales", "SUM('Financials'[Sales])", depends_on_columns=["Financials[Sales]"])
    financials = _table("Financials", measures=[sales])
    financials.columns = [ColumnMeta(
        name="Segment", data_type="string", description=None, ai_description=None,
        role=None, is_hidden=False, display_folder=None, format_string=None, sort_by_column=None,
    )]
    model = _model([financials])

    result = guide_query(model, measure="Sales", dimensions=["Segment"])
    assert result["dimensions"]["Segment"]["status"] == "resolved"
    assert result["dimensions"]["Segment"]["join_path"] == ["Financials"]


def test_guide_query_dimension_ambiguous_multiple_reachable():
    from fabric_ai_meta.models.metadata import ColumnMeta, RelationshipMeta

    def region_col():
        return ColumnMeta(
            name="region", data_type="string", description=None, ai_description=None,
            role=None, is_hidden=False, display_folder=None, format_string=None, sort_by_column=None,
        )

    fact = _table("fact_order_line", measures=[
        _measure("Revenue", "SUM('fact_order_line'[line_revenue])", depends_on_columns=["fact_order_line[line_revenue]"])
    ])
    dim_customer = _table("dim_customer")
    dim_customer.columns = [region_col()]
    dim_supplier = _table("dim_supplier")
    dim_supplier.columns = [region_col()]
    rels = [
        RelationshipMeta("fact_order_line", "dim_customer_id", "dim_customer", "id", "many-to-one", "single", True),
        RelationshipMeta("fact_order_line", "dim_supplier_id", "dim_supplier", "id", "many-to-one", "single", True),
    ]
    model = _model([fact, dim_customer, dim_supplier], relationships=rels)

    result = guide_query(model, measure="Revenue", dimensions=["region"])
    assert result["dimensions"]["region"]["status"] == "ambiguous"
    assert len(result["dimensions"]["region"]["candidates"]) == 2


def test_guide_query_dimension_unrelated():
    from fabric_ai_meta.models.metadata import ColumnMeta, RelationshipMeta

    fact = _table("Financials", measures=[
        _measure("Sales", "SUM('Financials'[Sales])", depends_on_columns=["Financials[Sales]"])
    ])
    date_table = _table("Date")
    shape_map = _table("Shape map for regions")
    shape_map.columns = [ColumnMeta(
        name="Region", data_type="string", description=None, ai_description=None,
        role=None, is_hidden=False, display_folder=None, format_string=None, sort_by_column=None,
    )]
    rels = [RelationshipMeta("Financials", "Date", "Date", "Date", "many-to-one", "single", True)]
    model = _model([fact, date_table, shape_map], relationships=rels)

    result = guide_query(model, measure="Sales", dimensions=["Region"])
    assert result["dimensions"]["Region"]["status"] == "unrelated"


def test_guide_query_dimension_not_found():
    sales = _measure("Sales", "SUM('Financials'[Sales])", depends_on_columns=["Financials[Sales]"])
    model = _model([_table("Financials", measures=[sales])])
    result = guide_query(model, measure="Sales", dimensions=["Nonexistent"])
    assert result["dimensions"]["Nonexistent"]["status"] == "not_found"
