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
    assert order_date.data_type == "dateTime"
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
