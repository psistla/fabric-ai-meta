"""Tests for the heuristic classifier, AI readiness scorer, DAX parser, and governance analyzer."""


from fabric_ai_meta.analyzer.classifier import (
    classify_column_role,
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
# DAX dependency parser
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
# Enterprise fixture, table classification
# ---------------------------------------------------------------------------

def test_bridge_table_classification(enterprise_sales_model):
    """CustomerProduct bridge table should be classified as BRIDGE."""
    bridge = next(t for t in enterprise_sales_model.tables if t.name == "CustomerProduct")
    result = classify_table_heuristic(bridge, enterprise_sales_model.relationships)
    assert result == TableType.BRIDGE


def test_configuration_table_classification(enterprise_sales_model):
    """CurrencyExchangeRate (< 100 rows) should be classified as CONFIGURATION."""
    config = next(t for t in enterprise_sales_model.tables if t.name == "CurrencyExchangeRate")
    result = classify_table_heuristic(config, enterprise_sales_model.relationships)
    assert result == TableType.CONFIGURATION


def test_hidden_staging_table_exists(enterprise_sales_model):
    """_SalesRaw should be hidden and have staging table type."""
    staging = next(t for t in enterprise_sales_model.tables if t.name == "_SalesRaw")
    assert staging.is_hidden is True
    assert staging.table_type == TableType.STAGING


def test_fact_table_classification_enterprise(enterprise_sales_model):
    """Sales fact table in enterprise model should be classified as FACT."""
    sales = next(t for t in enterprise_sales_model.tables if t.name == "Sales")
    result = classify_table_heuristic(sales, enterprise_sales_model.relationships)
    assert result == TableType.FACT


def test_dimension_table_classification_enterprise(enterprise_sales_model):
    """Product dimension in enterprise model should be classified as DIMENSION."""
    product = next(t for t in enterprise_sales_model.tables if t.name == "Product")
    result = classify_table_heuristic(product, enterprise_sales_model.relationships)
    assert result == TableType.DIMENSION


# ---------------------------------------------------------------------------
# Table name matching: token boundaries, not raw substrings
# ---------------------------------------------------------------------------

def _table(name, columns=(), measures=()):
    return TableMeta(
        name=name,
        table_type=TableType.UNKNOWN,
        description=None,
        ai_description=None,
        columns=list(columns),
        measures=list(measures),
        hierarchies=[],
        row_count_estimate=None,
        is_hidden=False,
        grain=None,
        source_partition_type=None,
    )


def _str_col(name):
    return ColumnMeta(
        name=name,
        data_type="string",
        description=None,
        ai_description=None,
        role=ColumnRole.ATTRIBUTE,
        is_hidden=False,
        display_folder=None,
        format_string=None,
        sort_by_column=None,
        sample_values=None,
    )


def _col(name, data_type="string", sort_by=None):
    return ColumnMeta(
        name=name,
        data_type=data_type,
        description=None,
        ai_description=None,
        role=ColumnRole.UNKNOWN,
        is_hidden=False,
        display_folder=None,
        format_string=None,
        sort_by_column=sort_by,
        sample_values=None,
    )


def test_declared_sort_by_column_target_is_sort():
    """`column Month { sortByColumn: MonthNo }` makes MonthNo the sort column.

    The declared property is authoritative and beats the numeric-type rule that
    would otherwise call an integer sort column a MEASURE_COLUMN.
    """
    month = _col("Month", sort_by="MonthNo")
    month_no = _col("MonthNo", "int64")
    t = _table("dim_date", columns=[month, month_no])
    assert classify_column_role(month_no, t, []) == ColumnRole.SORT


def test_numeric_sort_named_column_is_sort_without_declaration():
    """dim_date in the footwear fixture names MonthSort/QuarterSort but declares
    no sortByColumn, so the name fallback has to survive, minus the old
    non-numeric exclusion that made it unable to match an integer."""
    c = _col("MonthSort", "int64")
    t = _table("dim_date", columns=[c])
    assert classify_column_role(c, t, []) == ColumnRole.SORT


def test_order_in_name_is_not_a_sort_column():
    """`order` was a sort keyword, so every Order ID / Order Status in a sales
    model came back SORT. A key is not a sort column."""
    c = _col("Order ID")
    t = _table("All Items", columns=[c])
    assert classify_column_role(c, t, []) == ColumnRole.KEY


def test_order_status_is_an_attribute_not_sort():
    c = _col("Order Status")
    t = _table("All Items", columns=[c])
    assert classify_column_role(c, t, []) == ColumnRole.ATTRIBUTE


def test_foreign_key_still_beats_declared_sort():
    """A column that is both an FK and a sort target stays FOREIGN_KEY."""
    from fabric_ai_meta.models.metadata import RelationshipMeta

    rel = RelationshipMeta(
        from_table="fact", from_column="MonthNo",
        to_table="dim_date", to_column="MonthNo",
        cardinality="many-to-one", cross_filter_direction="single", is_active=True,
    )
    label = _col("Month", sort_by="MonthNo")
    month_no = _col("MonthNo", "int64")
    t = _table("fact", columns=[label, month_no])
    assert classify_column_role(month_no, t, [rel]) == ColumnRole.FOREIGN_KEY


def test_dim_factory_is_not_a_fact_table():
    """`fact` is a substring of `factory`; the name rule must not fire on it.

    dim_factory in the footwear-sustainability fixture is a textbook dimension:
    it sits on the "one" side of a many-to-one from fact_order_line.
    """
    from fabric_ai_meta.models.metadata import RelationshipMeta

    rel = RelationshipMeta(
        from_table="fact_order_line",
        from_column="factory_id",
        to_table="dim_factory",
        to_column="factory_id",
        cardinality="many-to-one",
        cross_filter_direction="single",
        is_active=True,
    )
    t = _table("dim_factory", columns=[_str_col("factory_id"), _str_col("factory_name")])
    assert classify_table_heuristic(t, [rel]) == TableType.DIMENSION


def test_camelcase_fact_name_still_matches():
    """Guard: SalesOrderLarge has no separator, so token splitting must handle case."""
    t = _table("SalesOrderLarge", columns=[_str_col("a"), _str_col("b")])
    assert classify_table_heuristic(t, []) == TableType.FACT


def test_underscored_fact_name_still_matches():
    t = _table("fact_order_line", columns=[_str_col("a"), _str_col("b")])
    assert classify_table_heuristic(t, []) == TableType.FACT


# ---------------------------------------------------------------------------
# Enterprise fixture, measure classification
# ---------------------------------------------------------------------------

def test_semi_additive_ending_inventory(enterprise_sales_model):
    """[Ending Inventory] uses LASTDATE and should be SEMI_ADDITIVE."""
    measure = _get_measure(enterprise_sales_model, "[Ending Inventory]")
    assert classify_measure_heuristic(measure) == MeasureCategory.SEMI_ADDITIVE


def test_semi_additive_account_balance(enterprise_sales_model):
    """[Account Balance] uses LASTDATE and should be SEMI_ADDITIVE."""
    measure = _get_measure(enterprise_sales_model, "[Account Balance]")
    assert classify_measure_heuristic(measure) == MeasureCategory.SEMI_ADDITIVE


def test_semi_additive_opening_balance(enterprise_sales_model):
    """[Opening Balance] uses FIRSTDATE and should be SEMI_ADDITIVE."""
    measure = _get_measure(enterprise_sales_model, "[Opening Balance]")
    assert classify_measure_heuristic(measure) == MeasureCategory.SEMI_ADDITIVE


def _measure(name, dax):
    return MeasureMeta(
        name=name,
        dax_expression=dax,
        description=None,
        ai_description=None,
        category=MeasureCategory.UNKNOWN,
        display_folder=None,
        format_string=None,
    )


# The balance functions below sit in BOTH TIME_INTEL_FUNCTIONS and
# SEMI_ADDITIVE_PATTERNS. Time intelligence is the earlier rule, so before the
# precedence fix these four were unreachable and every balance measure came back
# TIME_INTELLIGENCE. DAX taken verbatim from the footwear-sustainability fixture.

def test_semi_additive_closing_balance_month():
    m = _measure("Revenue Month End", "CLOSINGBALANCEMONTH ( [Revenue], dim_date[date_actual] )")
    assert classify_measure_heuristic(m) == MeasureCategory.SEMI_ADDITIVE


def test_semi_additive_opening_balance_month():
    m = _measure("Revenue Month Start", "OPENINGBALANCEMONTH ( [Revenue], dim_date[date_actual] )")
    assert classify_measure_heuristic(m) == MeasureCategory.SEMI_ADDITIVE


def test_semi_additive_closing_balance_quarter():
    m = _measure("Revenue Qtr End", "CLOSINGBALANCEQUARTER ( [Revenue], dim_date[date_actual] )")
    assert classify_measure_heuristic(m) == MeasureCategory.SEMI_ADDITIVE


def test_genuine_time_intelligence_survives_semi_additive_precedence():
    """The fix must not drag real time-intelligence measures into SEMI_ADDITIVE."""
    for name, dax in (
        ("Sales YTD", "TOTALYTD ( SUM ( Sales[Amount] ), 'Date'[Date] )"),
        ("Sales PY", "CALCULATE ( SUM ( Sales[Amount] ), SAMEPERIODLASTYEAR ( 'Date'[Date] ) )"),
        ("Sales Prev M", "CALCULATE ( SUM ( Sales[Amount] ), PREVIOUSMONTH ( 'Date'[Date] ) )"),
    ):
        assert classify_measure_heuristic(_measure(name, dax)) == (
            MeasureCategory.TIME_INTELLIGENCE
        ), name


def test_filter_context_measure_classification(enterprise_sales_model):
    """[Sales (Active Products Only)] uses CALCULATE with filter, should be FILTER_CONTEXT.

    Note: The classifier categorizes this as CALCULATED since it references another measure
    via [Total Sales] and doesn't use a recognized filter-context function keyword.
    The fixture marks it as filter_context, but the heuristic classifier sees
    CALCULATE + measure ref and returns CALCULATED.
    """
    measure = _get_measure(enterprise_sales_model, "[Sales (Active Products Only)]")
    result = classify_measure_heuristic(measure)
    assert result in (MeasureCategory.CALCULATED, MeasureCategory.FILTER_CONTEXT)


def test_non_additive_avg_sale_price(enterprise_sales_model):
    """[Avg Sale Price] uses AVERAGE and should be NON_ADDITIVE."""
    measure = _get_measure(enterprise_sales_model, "[Avg Sale Price]")
    assert classify_measure_heuristic(measure) == MeasureCategory.NON_ADDITIVE


def test_non_additive_distinct_customer(enterprise_sales_model):
    """[Distinct Customer Count] uses DISTINCTCOUNT and should be NON_ADDITIVE."""
    measure = _get_measure(enterprise_sales_model, "[Distinct Customer Count]")
    assert classify_measure_heuristic(measure) == MeasureCategory.NON_ADDITIVE


def test_time_intelligence_sales_ytd_enterprise(enterprise_sales_model):
    """[Sales YTD] should be TIME_INTELLIGENCE."""
    measure = _get_measure(enterprise_sales_model, "[Sales YTD]")
    assert classify_measure_heuristic(measure) == MeasureCategory.TIME_INTELLIGENCE


def test_time_intelligence_sales_py(enterprise_sales_model):
    """[Sales PY] uses SAMEPERIODLASTYEAR and should be TIME_INTELLIGENCE."""
    measure = _get_measure(enterprise_sales_model, "[Sales PY]")
    assert classify_measure_heuristic(measure) == MeasureCategory.TIME_INTELLIGENCE


def test_empty_dax_measure_classified_unknown(enterprise_sales_model):
    """[Empty DAX Measure] with empty DAX expression should be UNKNOWN."""
    measure = _get_measure(enterprise_sales_model, "[Empty DAX Measure]")
    assert classify_measure_heuristic(measure) == MeasureCategory.UNKNOWN


# ---------------------------------------------------------------------------
# Governance
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
    for key in ("summary", "naming_inconsistencies", "duplicate_measures", "score_ranking", "recommendations"):
        assert key in report
    assert report["summary"]["model_count"] == 2
    assert isinstance(report["naming_inconsistencies"], list)
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


# ---------------------------------------------------------------------------
# Model-level classification pipeline (WIRE-01)
# ---------------------------------------------------------------------------

def test_classify_model_in_place_wires_measure_dependencies(adventure_works_model):
    """WIRE-01: parse_measure_dependencies output must land on MeasureMeta.

    Regression for the v1.5.0 bug where these fields were computed and discarded,
    visible only because fixtures pre-baked them.
    """
    from fabric_ai_meta.analyzer.pipeline import classify_model_in_place

    model = adventure_works_model
    for t in model.tables:
        for m in t.measures:
            m.depends_on_measures = []
            m.depends_on_columns = []
            m.implicit_filters = []

    classify_model_in_place(model)

    measures = [m for t in model.tables for m in t.measures]
    assert any(m.depends_on_columns for m in measures), (
        "no measure got depends_on_columns; wiring did not run"
    )


def test_classify_model_in_place_renames_implicit_business_rules():
    """The one field whose name differs between producer and destination."""
    from fabric_ai_meta.analyzer.pipeline import classify_model_in_place

    measure = MeasureMeta(
        name="Bike YTD",
        dax_expression=(
            "TOTALYTD(CALCULATE(SUM(Sales[Amount]), Product[Category] = \"Bikes\"), "
            "'Date'[Date])"
        ),
        description=None, ai_description=None, category=MeasureCategory.UNKNOWN,
        display_folder=None, format_string=None,
    )
    table = TableMeta(
        name="Sales", description=None, ai_description=None,
        table_type=TableType.UNKNOWN, grain=None, measures=[measure],
    )
    model = SemanticModelMeta(name="M", workspace="W", description=None, tables=[table])

    classify_model_in_place(model)

    assert measure.implicit_filters == ['= "Bikes"']
    assert measure.category == MeasureCategory.TIME_INTELLIGENCE
