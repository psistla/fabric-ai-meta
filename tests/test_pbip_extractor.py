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
