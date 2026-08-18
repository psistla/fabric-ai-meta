"""Tests for the PBIP / TMDL parser (v1.6).

Asserts against the real Power BI Desktop fixtures under tests/fixtures/pbip/
only (see tests/fixtures/pbip/PROVENANCE.md). Never hand-authored TMDL.
"""

import os

from fabric_ai_meta.models.metadata import TableType

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures", "pbip")
PHO_TABLES = os.path.join(
    FIXTURES, "stix-one-pho.SemanticModel", "definition", "tables"
)
AMAZON_TABLES = os.path.join(
    FIXTURES, "stix-one-pho-amazon.SemanticModel", "definition", "tables"
)
FOOTWEAR_TABLES = os.path.join(
    FIXTURES, "footwear-sustainability.SemanticModel", "definition", "tables"
)
WON_PHO_TABLES = os.path.join(
    FIXTURES, "power-bi-stix-won-pho.SemanticModel", "definition", "tables"
)


def _col(table, name):
    return next(c for c in table.columns if c.name == name)


# ---------------------------------------------------------------------------
# Task 10: tokenizer + table + /// descriptions
# ---------------------------------------------------------------------------

def test_parse_table_quoted_name_and_description():
    from fabric_ai_meta.extractor.pbip import _parse_table_file

    t = _parse_table_file(os.path.join(PHO_TABLES, "Sales Order.tmdl"))
    assert t.name == "Sales Order"           # quoted name, space preserved, unquoted
    assert t.description == "List of sales."  # leading /// at column 0
    assert t.is_hidden is False
    assert t.table_type == TableType.UNKNOWN  # classifier assigns later


def test_parse_table_hidden_bare_name():
    from fabric_ai_meta.extractor.pbip import _parse_table_file

    t = _parse_table_file(os.path.join(PHO_TABLES, "cards.tmdl"))
    assert t.name == "cards"     # bare name
    assert t.is_hidden is True   # table-scope `isHidden` flag
    assert t.description is None  # no /// on this table


# ---------------------------------------------------------------------------
# Task 11: column
# ---------------------------------------------------------------------------

def test_parse_columns_sales_order():
    from fabric_ai_meta.extractor.pbip import _parse_table_file

    t = _parse_table_file(os.path.join(PHO_TABLES, "Sales Order.tmdl"))
    assert [c.name for c in t.columns] == [
        "date", "datetime", "cash_type", "money", "coffee_name"
    ]
    money = _col(t, "money")
    assert money.data_type == "int64"
    assert money.is_hidden is True
    assert money.format_string == "0"
    cash = _col(t, "cash_type")
    assert cash.description == "pstest"   # /// pstest
    assert cash.is_hidden is False


def test_parse_columns_skips_variation_block():
    from fabric_ai_meta.extractor.pbip import _parse_table_file

    t = _parse_table_file(os.path.join(AMAZON_TABLES, "All Items.tmdl"))
    order_date = _col(t, "Order Date")   # quoted name unquoted
    assert order_date.data_type == "datetime"  # TMDL emits `dateTime`, lowercased
    assert order_date.is_hidden is True
    assert order_date.format_string == "Long Date"
    # The nested `variation Variation` block must not leak in as a column.
    assert not any(c.name.startswith("variation") for c in t.columns)


# ---------------------------------------------------------------------------
# Task 12: measure + DAX (single-line and indentation-continuation)
# ---------------------------------------------------------------------------

def _measure(table, name):
    return next(m for m in table.measures if m.name == name)


def test_parse_measure_single_line_keeps_literal():
    from fabric_ai_meta.extractor.pbip import _parse_table_file

    t = _parse_table_file(os.path.join(PHO_TABLES, "Sales Order.tmdl"))
    m = _measure(t, "Coffee YTD")
    assert m.dax_expression == (
        'TOTALYTD(CALCULATE(SUM(SalesOrderLarge[money]), '
        'SalesOrderLarge[coffee_name] = "Hot Chocolate"), SalesOrderLarge[date])'
    )
    assert m.is_hidden is False


def test_parse_measure_multiline_dax_golden():
    from fabric_ai_meta.extractor.pbip import _parse_table_file

    t = _parse_table_file(os.path.join(PHO_TABLES, "Sales Order.tmdl"))
    m = _measure(t, "Revenue MoM %")
    expected = "\n".join([
        "VAR CurrentRevenue =",
        "    SUM ( 'Sales Order'[money] )",
        "VAR PriorRevenue =",
        "    CALCULATE (",
        "        SUM ( 'Sales Order'[money] ),",
        "        DATEADD ( 'Sales Order'[date], -1, MONTH )",
        "    )",
        "VAR HasBothPeriods =",
        "    NOT ISBLANK ( CurrentRevenue ) && NOT ISBLANK ( PriorRevenue )",
        "VAR Result =",
        "    DIVIDE ( CurrentRevenue - PriorRevenue, PriorRevenue )",
        "RETURN",
        "    IF ( HasBothPeriods, Result )",
    ])
    assert m.dax_expression == expected
    assert m.description == "This measure provides month over month revenue (pstest)."
    assert m.is_hidden is False


def test_parse_measure_hidden_flag():
    from fabric_ai_meta.extractor.pbip import _parse_table_file

    t = _parse_table_file(os.path.join(PHO_TABLES, "Sales Order.tmdl"))
    assert _measure(t, "Revenue 7D Avg").is_hidden is True
    assert [m.name for m in t.measures] == ["Revenue MoM %", "Revenue 7D Avg", "Coffee YTD"]


# ---------------------------------------------------------------------------
# Task 13: relationships + partition mode
# ---------------------------------------------------------------------------

PHO_DEF = os.path.join(FIXTURES, "stix-one-pho.SemanticModel", "definition")


def _rel(rels, from_col, to_col):
    return next(
        r for r in rels
        if r.from_column == from_col and r.to_column == to_col
    )


def test_parse_relationships_inactive_bidirectional_manytomany():
    from fabric_ai_meta.extractor.pbip import _parse_relationships_file

    rels = _parse_relationships_file(os.path.join(PHO_DEF, "relationships.tmdl"))
    r = _rel(rels, "cash_type", "cash_type")
    assert r.from_table == "SalesOrderLarge"
    assert r.to_table == "Sales Order"          # quoted table name unquoted
    assert r.is_active is False                 # isActive: false
    assert r.cross_filter_direction == "both"   # crossFilteringBehavior: bothDirections
    assert r.cardinality == "many-to-many"      # toCardinality: many


def test_parse_relationships_active_defaults():
    from fabric_ai_meta.extractor.pbip import _parse_relationships_file

    rels = _parse_relationships_file(os.path.join(PHO_DEF, "relationships.tmdl"))
    r = _rel(rels, "card", "card")
    assert r.from_table == "SalesOrderLarge"
    assert r.to_table == "cards"
    assert r.is_active is True                  # no isActive line -> active
    assert r.cross_filter_direction == "single"
    assert r.cardinality == "many-to-one"
    assert len(rels) == 6                        # every relationship in the file


def test_parse_partition_mode():
    from fabric_ai_meta.extractor.pbip import _parse_table_file

    t = _parse_table_file(os.path.join(PHO_DEF, "tables", "Sales Order.tmdl"))
    assert t.source_partition_type == "Import"   # partition `mode: import`


# ---------------------------------------------------------------------------
# Quote handling (review findings: quoted/escaped names in refs and splits)
# ---------------------------------------------------------------------------

AMAZON_REL = os.path.join(
    FIXTURES, "stix-one-pho-amazon.SemanticModel", "definition", "relationships.tmdl"
)


def test_relationship_endpoint_unquotes_spaced_column():
    """Real fixture: `fromColumn: 'All Items'.'Order Date'` must yield an
    unquoted column that can match the parsed ColumnMeta.name."""
    from fabric_ai_meta.extractor.pbip import _parse_relationships_file

    rels = _parse_relationships_file(AMAZON_REL)
    r = next(r for r in rels if r.to_table.startswith("LocalDateTable")
             and r.from_table == "All Items" and r.from_column == "Order Date")
    assert r.from_column == "Order Date"   # not "'Order Date'"


def test_split_ref_quotes_and_escaping():
    from fabric_ai_meta.extractor.pbip import _split_ref

    assert _split_ref("SalesOrderLarge.card") == ("SalesOrderLarge", "card")
    assert _split_ref("'All Items'.'Order Date'") == ("All Items", "Order Date")
    assert _split_ref("'Bob''s Data'.card") == ("Bob's Data", "card")
    assert _split_ref("Sales.'Total ='") == ("Sales", "Total =")


def test_unquote_collapses_doubled_quotes():
    from fabric_ai_meta.extractor.pbip import _unquote

    assert _unquote("'Bob''s Data'") == "Bob's Data"
    assert _unquote("cards") == "cards"
    assert _unquote("'Sales Order'") == "Sales Order"


# ---------------------------------------------------------------------------
# Chunk 4: PbipExtractor (Tasks 14-18)
# ---------------------------------------------------------------------------

PHO_SM = os.path.join(FIXTURES, "stix-one-pho.SemanticModel")
AMAZON_SM = os.path.join(FIXTURES, "stix-one-pho-amazon.SemanticModel")


def test_pbip_list_models_single_semanticmodel_dir():
    from fabric_ai_meta.extractor.pbip import PbipExtractor

    assert PbipExtractor(PHO_SM).list_models("ignored") == ["stix-one-pho"]


def test_pbip_list_models_dir_of_dirs_sorted():
    from fabric_ai_meta.extractor.pbip import PbipExtractor

    assert PbipExtractor(FIXTURES).list_models("ignored") == [
        "city-sustainability",
        "footwear-sustainability",
        "power-bi-stix-won-pho",
        "stix-one-pho",
        "stix-one-pho-amazon",
    ]


def test_pbip_invalid_path_raises():
    import pytest

    from fabric_ai_meta.extractor.pbip import PbipExtractor
    with pytest.raises(ValueError, match="SemanticModel"):
        PbipExtractor(os.path.dirname(__file__))  # tests/ has no *.SemanticModel


def test_pbip_extract_skips_auto_date_tables():
    from fabric_ai_meta.extractor.pbip import PbipExtractor

    m = PbipExtractor(FIXTURES).extract("stix-one-pho", "ws")
    assert [t.name for t in m.tables] == ["Sales Order", "SalesOrderLarge", "cards"]
    assert m.extraction_method == "pbip"
    # date-table relationships dropped, only the two user relationships remain
    assert len(m.relationships) == 2
    assert all(
        not r.to_table.startswith(("LocalDateTable", "DateTableTemplate"))
        and not r.from_table.startswith(("LocalDateTable", "DateTableTemplate"))
        for r in m.relationships
    )


def test_pbip_extract_amazon_single_table():
    from fabric_ai_meta.extractor.pbip import PbipExtractor

    m = PbipExtractor(FIXTURES).extract("stix-one-pho-amazon", "ws")
    assert [t.name for t in m.tables] == ["All Items"]


def test_parse_column_reads_sort_by_column():
    """TMDL declares `sortByColumn`; the parser was dropping it on the floor."""
    from fabric_ai_meta.extractor.pbip import _parse_table_file

    tmpl = next(
        f for f in os.listdir(FOOTWEAR_TABLES) if f.startswith("DateTableTemplate_")
    )
    t = _parse_table_file(os.path.join(FOOTWEAR_TABLES, tmpl))
    by_sort = {c.name: c.sort_by_column for c in t.columns if c.sort_by_column}
    assert by_sort == {
        'Month = FORMAT([Date], "MMMM")': "MonthNo",
        'Quarter = "Qtr " & [QuarterNo]': "QuarterNo",
    }
    assert _col(t, "Date").sort_by_column is None  # not declared, stays None


def test_declared_sort_target_is_defeated_by_calculated_column_names():
    """Known limitation, pinned so it is not mistaken for working.

    Every column in Power BI's auto date tables is calculated, and `--pbip` parses
    a calculated column's name as the whole `Name = DAX` header. So the declared
    target "MonthNo" never matches the column actually called
    `MonthNo = MONTH([Date])`, and the sortByColumn link cannot resolve on this
    path. The declared lookup does work wherever names are clean (the sempy path,
    and non-calculated columns). Fixing this means fixing calculated-column name
    parsing, which is a separate pre-existing defect.
    """
    from fabric_ai_meta.extractor.pbip import _parse_table_file

    tmpl = next(
        f for f in os.listdir(FOOTWEAR_TABLES) if f.startswith("DateTableTemplate_")
    )
    t = _parse_table_file(os.path.join(FOOTWEAR_TABLES, tmpl))
    names = {c.name for c in t.columns}
    targets = {c.sort_by_column for c in t.columns if c.sort_by_column}
    assert targets and not (targets & names)  # declared, but unresolvable here


def test_pbip_declared_sort_columns_classify_as_sort():
    """End to end: the declared target becomes SORT rather than MEASURE_COLUMN."""
    from fabric_ai_meta.analyzer.pipeline import classify_model_in_place
    from fabric_ai_meta.extractor.pbip import PbipExtractor
    from fabric_ai_meta.models.metadata import ColumnRole

    m = PbipExtractor(FIXTURES).extract("footwear-sustainability", "ws")
    classify_model_in_place(m)
    dim_date = next(t for t in m.tables if t.name == "dim_date")
    roles = {c.name: c.role for c in dim_date.columns}
    # named *Sort, no sortByColumn declared anywhere in dim_date
    for name in ("QuarterSort", "MonthSort", "DayOfWeekSort", "WeekSort"):
        assert roles[name] is ColumnRole.SORT, name


def test_pbip_footwear_star_schema_classification():
    """The one fixture with a full star schema and real balance-pattern DAX.

    Guards the two precedence fixes together: `dim_factory` must not be a FACT
    table (the `fact` substring lives inside `factory`), and the OPENING/CLOSING
    balance measures must be SEMI_ADDITIVE rather than TIME_INTELLIGENCE.
    """
    from fabric_ai_meta.analyzer.pipeline import classify_model_in_place
    from fabric_ai_meta.extractor.pbip import PbipExtractor
    from fabric_ai_meta.models.metadata import MeasureCategory

    m = PbipExtractor(FIXTURES).extract("footwear-sustainability", "ws")
    classify_model_in_place(m)
    types = {t.name: t.table_type for t in m.tables}
    assert types["fact_order_line"] is TableType.FACT
    for dim in ("dim_factory", "dim_customer", "dim_product", "dim_supplier"):
        assert types[dim] is TableType.DIMENSION, dim

    cats = {x.name: x.category for t in m.tables for x in t.measures}
    for name in ("Revenue Month End", "Revenue Month Start", "Revenue on Last Day"):
        assert cats[name] is MeasureCategory.SEMI_ADDITIVE, name


def test_pbip_datetime_columns_classify_as_date():
    """TMDL spells the type `dateTime`; the classifier tests lowercase `datetime`.

    Without normalizing at the extractor boundary every date column on the pbip
    path fell through to ATTRIBUTE, and `Order Date` to SORT (the sort rule sees
    the substring "order" first).
    """
    from fabric_ai_meta.analyzer.pipeline import classify_model_in_place
    from fabric_ai_meta.extractor.pbip import PbipExtractor
    from fabric_ai_meta.models.metadata import ColumnRole

    for model_name in ("stix-one-pho", "stix-one-pho-amazon"):
        m = PbipExtractor(FIXTURES).extract(model_name, "ws")
        classify_model_in_place(m)
        dates = [
            c
            for t in m.tables
            for c in t.columns
            if c.data_type == "datetime"
        ]
        assert dates, f"{model_name} has no datetime columns to check"
        assert all(c.role is ColumnRole.DATE for c in dates), [
            (c.name, c.role) for c in dates if c.role is not ColumnRole.DATE
        ]


# ---------------------------------------------------------------------------
# Characterization tests: the DAX-authored model (power-bi-stix-won-pho).
#
# These assert what the extractor does TODAY, not what it should do. Each one
# pins a known gap so it stays visible and cannot regress silently. When a gap is
# fixed the test here fails, which is the point: it reports the improvement.
# ---------------------------------------------------------------------------

def _won_pho():
    from fabric_ai_meta.analyzer.pipeline import classify_model_in_place
    from fabric_ai_meta.extractor.pbip import PbipExtractor

    m = PbipExtractor(FIXTURES).extract("power-bi-stix-won-pho", "ws")
    classify_model_in_place(m)
    return m


def test_gap_calculated_table_columns_have_no_data_type():
    """GAP: 58 of 60 columns extract with an empty data_type.

    Power BI does not serialize `dataType` for the columns of a DAX-defined
    calculated table; the type comes from the expression. This whole model is
    built that way (`SELECTCOLUMNS` over inline values), so almost nothing has a
    type. TMDL does carry `summarizeBy`, which states whether a column is
    aggregatable, and the parser does not read it.
    """
    m = _won_pho()
    cols = [c for t in m.tables for c in t.columns]
    untyped = [c for c in cols if c.data_type == ""]
    assert len(untyped) == 58
    assert len(cols) == 60


def test_gap_numeric_columns_misread_as_attributes():
    """GAP: consequence of the above. Sales/Profit/COGS are not MEASURE_COLUMN.

    `_NUMERIC_TYPES` cannot match an empty type, so every figure in the fact
    table falls through to ATTRIBUTE. TMDL marks each of these `summarizeBy: sum`.
    """
    from fabric_ai_meta.models.metadata import ColumnRole

    m = _won_pho()
    fin = next(t for t in m.tables if t.name == "Financials")
    roles = {c.name: c.role for c in fin.columns}
    for name in ("Sales", "Profit", "COGS", "Units Sold"):
        assert roles[name] is ColumnRole.ATTRIBUTE, name


def test_gap_obvious_fact_table_classifies_unknown():
    """GAP: `Financials` is a fact table and its own /// comment says so.

    classify_table_heuristic needs either a fact keyword in the name or
    (multiple outbound rels AND numeric columns). The name is `Financials`, and
    the numeric test cannot fire without data types, so it lands UNKNOWN.
    """
    m = _won_pho()
    fin = next(t for t in m.tables if t.name == "Financials")
    assert fin.description is not None and "fact" in fin.description.lower()
    assert fin.table_type is TableType.UNKNOWN


def test_gap_calculation_group_yields_no_measures():
    """GAP: calculation groups are out of scope (see CLAUDE.md constraint 5).

    `Time Calculation` is a real calculationGroup. It parses to a table with no
    measures and no marker, so a consumer cannot tell an unsupported construct
    from an empty table. The limitation is documented; the output is silent.
    """
    m = _won_pho()
    tc = next(t for t in m.tables if t.name == "Time Calculation")
    assert tc.measures == []
    assert tc.table_type is TableType.UNKNOWN


def test_won_pho_shape_is_stable():
    """Baseline for the whole model, so any parser change shows up here."""
    m = _won_pho()
    assert len(m.tables) == 14
    assert len(m.relationships) == 1
    assert sum(len(t.measures) for t in m.tables) == 65
    assert sum(1 for t in m.tables if t.grain) == 0


def test_pbip_copilot_present_absent_and_miscased(tmp_path):
    import shutil

    from fabric_ai_meta.extractor.pbip import PbipExtractor

    # present (real fixture has a Copilot/ folder)
    m = PbipExtractor(FIXTURES).extract("stix-one-pho", "ws", with_copilot=True)
    assert m.copilot is not None
    assert m.copilot.signals()["verified_answer_count"] == 2

    # absent
    m2 = PbipExtractor(FIXTURES).extract("stix-one-pho-amazon", "ws", with_copilot=True)
    assert m2.copilot is None

    # miscased: copy the model with a lowercase copilot/ dir; must still be found.
    # (.platform is copied too, so the model keeps its displayName, not "Copy".)
    dst = tmp_path / "Copy.SemanticModel"
    shutil.copytree(PHO_SM, dst)
    shutil.move(str(dst / "Copilot"), str(dst / "copilot"))
    ext = PbipExtractor(str(dst))
    m3 = ext.extract(ext.list_models("ws")[0], "ws", with_copilot=True)
    assert m3.copilot is not None


def test_pbip_roundtrip_preserves_copilot():
    from fabric_ai_meta.extractor.pbip import PbipExtractor
    from fabric_ai_meta.models.metadata import from_dict

    m = PbipExtractor(FIXTURES).extract("stix-one-pho", "ws", with_copilot=True)
    back = from_dict(m.to_dict())
    assert back.copilot is not None
    assert back.copilot.signals() == m.copilot.signals()
    assert [t.name for t in back.tables] == [t.name for t in m.tables]


def test_parse_measure_backtick_fenced_dax():
    """TMDL wraps an expression in ``` when it must be read verbatim.

    The fence opens on the declaration line, the body sits one level deeper,
    and the closing fence is alone on its own line. Neither fence line is part
    of the expression.
    """
    from fabric_ai_meta.extractor.pbip import _parse_table_file

    t = _parse_table_file(os.path.join(WON_PHO_TABLES, "Calculations.tmdl"))
    m = _measure(t, "Some value")
    assert m.dax_expression == "        SUM(Map[RandomValue])"
