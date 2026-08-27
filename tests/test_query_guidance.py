from fabric_ai_meta.analyzer.query_guidance import _find_join_path, _resolve_base_table
from fabric_ai_meta.models.metadata import MeasureMeta, MeasureCategory, RelationshipMeta


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
