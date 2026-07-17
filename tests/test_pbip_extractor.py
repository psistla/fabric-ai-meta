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
