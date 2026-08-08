"""Heuristic classifier for tables, columns, and measures (SPEC.md Section 6.2)."""

import re

from fabric_ai_meta.models.metadata import (
    ColumnMeta,
    ColumnRole,
    MeasureCategory,
    MeasureMeta,
    RelationshipMeta,
    TableMeta,
    TableType,
)

# Time intelligence DAX functions (spec Section 6.2)
# Note: DATESYTD is the correct DAX spelling; spec lists DATEYTD, both included.
TIME_INTEL_FUNCTIONS = {
    "TOTALYTD", "TOTALQTD", "TOTALMTD", "SAMEPERIODLASTYEAR",
    "DATEYTD", "DATESYTD", "DATESMTD", "DATESQTD",
    "PREVIOUSMONTH", "PREVIOUSQUARTER", "PREVIOUSYEAR",
    "OPENINGBALANCEMONTH", "CLOSINGBALANCEMONTH",
    "OPENINGBALANCEQUARTER", "CLOSINGBALANCEQUARTER",
    "OPENINGBALANCEYEAR", "CLOSINGBALANCEYEAR",
    "PARALLELPERIOD", "DATESINPERIOD", "DATESBETWEEN",
}

SEMI_ADDITIVE_PATTERNS = {
    "LASTDATE", "FIRSTDATE",
    "OPENINGBALANCEMONTH", "CLOSINGBALANCEMONTH",
    "OPENINGBALANCEQUARTER", "CLOSINGBALANCEQUARTER",
}
# ⚠️ Semi-additive = balance-type measures (inventory, account balances).
# DISTINCTCOUNT is NON-additive, cannot be summed across any dimension.
# Do NOT classify DISTINCTCOUNT as semi-additive.

NON_ADDITIVE_INDICATORS = {
    "DIVIDE", "AVERAGE", "AVERAGEX", "DISTINCTCOUNT", "DISTINCTCOUNTNOBLANK",
}

_FACT_NAME_PATTERNS = {"fact", "fct", "sales", "transactions", "events", "orders"}
_DIM_NAME_PATTERNS = {"dim", "dimension", "lookup", "product", "customer", "date", "calendar"}
_NUMERIC_TYPES = {"int64", "double", "decimal"}

# Splits on separators AND camelCase, so `dim_factory` -> {dim, factory} and
# `SalesOrderLarge` -> {sales, order, large}. Plain substring matching made
# `dim_factory` a FACT table, because "fact" is inside "factory".
_TOKEN_RE = re.compile(r"[A-Z]+(?![a-z])|[A-Z][a-z]*|[a-z]+|\d+")


def _name_tokens(name: str) -> set[str]:
    return {t.lower() for t in _TOKEN_RE.findall(name)}


def classify_table_heuristic(
    table: TableMeta, relationships: list[RelationshipMeta]
) -> TableType:
    """
    Rule-based table classification, handles ~70% of cases.

    Fact indicators:
    - Has multiple outbound many-to-one relationships
    - Contains numeric columns likely to be aggregated
    - Table name contains: fact, fct, sales, transactions, events, orders

    Dimension indicators:
    - Has inbound one-to-many relationships
    - Predominantly text/categorical columns
    - Table name contains: dim, dimension, lookup, product, customer, date, calendar

    Bridge indicators:
    - Only has foreign key columns
    - Has exactly 2 many-to-one relationships
    - No measures defined on table

    Configuration indicators:
    - Small row count (< 100 rows)
    - Contains parameter/config-like columns

    Returns TableType.UNKNOWN when no rule matches confidently.
    """
    name_tokens = _name_tokens(table.name)

    # Outbound many-to-one (table is on "many" side, typical of fact tables)
    outbound_many_to_one = [
        r for r in relationships
        if r.from_table == table.name and r.cardinality == "many-to-one"
    ]
    # Inbound (table is on "one" side, typical of dimension tables)
    inbound = [
        r for r in relationships
        if r.to_table == table.name and r.cardinality == "many-to-one"
    ]

    non_key_columns = [
        c for c in table.columns
        if c.role not in (ColumnRole.FOREIGN_KEY, ColumnRole.KEY)
    ]

    # Bridge: only FK/key columns, exactly 2 outbound many-to-one rels, no measures
    if (
        len(outbound_many_to_one) == 2
        and not table.measures
        and len(table.columns) > 0
        and not non_key_columns
    ):
        return TableType.BRIDGE

    # Configuration: very small row count
    if table.row_count_estimate is not None and table.row_count_estimate < 100:
        return TableType.CONFIGURATION

    # Fact indicators
    fact_name_match = bool(name_tokens & _FACT_NAME_PATTERNS)
    has_multiple_outbound = len(outbound_many_to_one) >= 2
    numeric_cols = [c for c in table.columns if c.data_type in _NUMERIC_TYPES]
    has_numeric_cols = len(numeric_cols) >= 2

    if fact_name_match or (has_multiple_outbound and has_numeric_cols):
        return TableType.FACT

    # Dimension indicators
    dim_name_match = bool(name_tokens & _DIM_NAME_PATTERNS)
    has_inbound = len(inbound) >= 1

    if dim_name_match or (has_inbound and not table.measures):
        return TableType.DIMENSION

    return TableType.UNKNOWN


def classify_column_role(
    column: ColumnMeta, table: TableMeta, relationships: list[RelationshipMeta]
) -> ColumnRole:
    """
    Heuristic column role detection.

    FK detection: column name matches a relationship's from_column for this table.
    Key detection: name ends with Key, ID, or Id and is not a FK.
    Date detection: data_type == datetime or name is Date / DateKey.
    Sort detection: name contains Sort or Order and is not a numeric type.
    """
    name = column.name
    name_lower = name.lower()

    # FK detection: name appears as from_column in a relationship from this table
    fk_columns_in_rels = {
        r.from_column for r in relationships if r.from_table == table.name
    }
    if name in fk_columns_in_rels:
        return ColumnRole.FOREIGN_KEY

    # Date detection: datetime type or well-known date column names
    if column.data_type == "datetime" or name in ("Date", "DateKey"):
        return ColumnRole.DATE

    # Sort detection: name contains Sort or Order and is not a numeric type
    if ("sort" in name_lower or "order" in name_lower) and column.data_type not in _NUMERIC_TYPES:
        return ColumnRole.SORT

    # Key detection: ends with Key, ID, or Id
    if name.endswith(("Key", "ID", "Id")):
        return ColumnRole.KEY

    # Measure column: numeric type that is not a key
    if column.data_type in _NUMERIC_TYPES:
        return ColumnRole.MEASURE_COLUMN

    return ColumnRole.ATTRIBUTE


def classify_measure_heuristic(measure: MeasureMeta) -> MeasureCategory:
    """
    Heuristic measure category detection from the DAX expression.

    Priority order:
    1. TIME_INTELLIGENCE, any time intelligence function that is not a balance function
    2. NON_ADDITIVE: DISTINCTCOUNT (cannot be summed across any dimension)
    3. SEMI_ADDITIVE, balance-type patterns (LASTDATE, OPENINGBALANCEMONTH, etc.)
    4. NON_ADDITIVE, ratios/averages (DIVIDE, AVERAGE, AVERAGEX)
    5. ADDITIVE: SUM, SUMX, COUNT, COUNTROWS
    6. CALCULATED, expression references another measure via [Measure] syntax
    7. UNKNOWN, fallback
    """
    dax_upper = measure.dax_expression.upper()

    # Extract all DAX function names (word followed by opening paren)
    functions_used = set(re.findall(r'\b([A-Z]+)\s*\(', dax_upper))

    # 1. TIME_INTELLIGENCE, excluding the balance functions. The four
    # OPENING/CLOSINGBALANCE* functions sit in both sets, and while this rule
    # matched them they shadowed rule 3 entirely: no measure could ever be
    # SEMI_ADDITIVE via a balance function, only via LASTDATE/FIRSTDATE.
    # Semi-additive is the more actionable label ("do not SUM across dates"), so
    # a measure using ONLY balance functions falls through to rule 3. A measure
    # that also uses a real time-intelligence function still lands here.
    if functions_used & (TIME_INTEL_FUNCTIONS - SEMI_ADDITIVE_PATTERNS):
        return MeasureCategory.TIME_INTELLIGENCE

    # 2. NON_ADDITIVE: DISTINCTCOUNT before semi-additive check
    if functions_used & {"DISTINCTCOUNT", "DISTINCTCOUNTNOBLANK"}:
        return MeasureCategory.NON_ADDITIVE

    # 3. SEMI_ADDITIVE, balance-type (inventory, account balances)
    if functions_used & SEMI_ADDITIVE_PATTERNS:
        return MeasureCategory.SEMI_ADDITIVE

    # 4. NON_ADDITIVE, ratios, averages
    if functions_used & {"DIVIDE", "AVERAGE", "AVERAGEX"}:
        return MeasureCategory.NON_ADDITIVE

    # 5. ADDITIVE, simple aggregations
    if functions_used & {"SUM", "SUMX", "COUNT", "COUNTROWS", "COUNTA", "COUNTX"}:
        return MeasureCategory.ADDITIVE

    # 6. CALCULATED, references another measure (standalone [Name] not preceded by table)
    measure_refs = re.findall(r'(?<![\'"\w])\[([^\]]+)\]', measure.dax_expression)
    if measure_refs:
        return MeasureCategory.CALCULATED

    return MeasureCategory.UNKNOWN
