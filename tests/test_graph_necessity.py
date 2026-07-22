"""Tests for the graph-necessity advisor."""

from fabric_ai_meta.analyzer.graph_necessity import (
    PRESSURE_THRESHOLDS,
    PRESSURE_WEIGHTS,
    _bridge_m2m_presence,
    _multi_fact_complexity,
    _relationship_graph_depth,
    _resolve_questions,
    _workload_hop_pressure,
)
from fabric_ai_meta.models.metadata import (
    ColumnMeta,
    ColumnRole,
    MeasureCategory,
    MeasureMeta,
    RelationshipMeta,
    SemanticModelMeta,
    TableMeta,
    TableType,
)


def _col(n):
    return ColumnMeta(name=n, data_type="string", description=None, ai_description=None,
                      role=ColumnRole.UNKNOWN, is_hidden=False, display_folder=None,
                      format_string=None, sort_by_column=None)


def _measure(name, cols):
    return MeasureMeta(name=name, dax_expression="", description=None, ai_description=None,
                       category=MeasureCategory.UNKNOWN, display_folder=None,
                       format_string=None, depends_on_columns=list(cols))


def _table(name, ttype=TableType.DIMENSION, columns=(), measures=()):
    return TableMeta(name=name, description=None, ai_description=None, table_type=ttype,
                     grain=None, columns=[_col(c) for c in columns], measures=list(measures))


def _rel(a, b, cardinality="many-to-one", active=True):
    return RelationshipMeta(from_table=a, from_column="K", to_table=b, to_column="K",
                            cardinality=cardinality, cross_filter_direction="single",
                            is_active=active)


def _model(tables, relationships=()):
    return SemanticModelMeta(
        name="m", workspace="w", description=None,
        tables=list(tables), relationships=list(relationships),
    )


def test_pressure_weights_sum_to_one():
    assert abs(sum(PRESSURE_WEIGHTS.values()) - 1.0) < 1e-9
    assert set(PRESSURE_WEIGHTS) == {
        "workload_hop_pressure",
        "bridge_m2m_presence",
        "relationship_graph_depth",
        "multi_fact_complexity",
    }


def test_pressure_threshold_keys():
    # guards against a typo surfacing as a KeyError deep in Task 4
    assert set(PRESSURE_THRESHOLDS) == {"optional_at", "warranted_at"}


def test_bridge_presence_counts_m2m_and_bridge_tables():
    # 1 m2m relationship -> count 1 -> min(1, 1/2) = 0.5
    m = _model(
        [_table("F", TableType.FACT), _table("D"), _table("Br", TableType.BRIDGE)],
        [_rel("F", "D"), _rel("F", "Br", cardinality="many-to-many")],
    )
    assert _bridge_m2m_presence(m) == 0.5
    # a clean star scores 0
    star = _model([_table("F", TableType.FACT), _table("D")], [_rel("F", "D")])
    assert _bridge_m2m_presence(star) == 0.0


def test_relationship_graph_depth_star_is_zero_snowflake_positive():
    star = _model([_table("F", TableType.FACT), _table("D1"), _table("D2")],
                  [_rel("F", "D1"), _rel("F", "D2")])
    assert _relationship_graph_depth(star) == 0.0  # diameter 2 -> 0
    # 5 nodes / 4 edges in a chain -> diameter 4 -> min(max(0, 4-2), 3)/3 = 0.67
    snowflake = _model(
        [_table("F", TableType.FACT), _table("D"), _table("Sub"), _table("Sub2"), _table("Sub3")],
        [_rel("F", "D"), _rel("D", "Sub"), _rel("Sub", "Sub2"), _rel("Sub2", "Sub3")],
    )
    assert _relationship_graph_depth(snowflake) == round(2 / 3, 2)  # 0.67


def test_relationship_graph_depth_ignores_disconnected_orphans():
    # F-D connected (diameter 1, <=2 nodes component -> 0), plus two orphans
    m = _model(
        [_table("F", TableType.FACT), _table("D"), _table("Orphan1"), _table("Orphan2")],
        [_rel("F", "D")],
    )
    depth = _relationship_graph_depth(m)
    assert 0.0 <= depth <= 1.0
    assert depth == 0.0  # largest component has 2 nodes -> 0


def test_multi_fact_complexity():
    one = _model([_table("F", TableType.FACT), _table("D")])
    assert _multi_fact_complexity(one) == 0.0
    two = _model([_table("F1", TableType.FACT), _table("F2", TableType.FACT)])
    assert _multi_fact_complexity(two) == 0.5
    three = _model([_table("F1", TableType.FACT), _table("F2", TableType.FACT),
                    _table("F3", TableType.FACT)])
    assert _multi_fact_complexity(three) == 1.0


def test_workload_hop_pressure_fraction_and_drop():
    assert _workload_hop_pressure([]) is None  # no questions -> drop
    assert _workload_hop_pressure([{"A"}, {"A", "B"}]) == 0.0  # all <=2 tables
    assert _workload_hop_pressure([{"A", "B", "C"}, {"A"}]) == 0.5


def test_resolve_prefers_supplied_questions_then_measures():
    m = _model(
        [_table("FactSales", TableType.FACT, columns=["Amount"],
                measures=[_measure("Total", ["FactSales[Amount]"])]),
         _table("DimDate", columns=["Date"])],
        [_rel("FactSales", "DimDate")],
    )
    # supplied questions -> source 'questions', strong
    sets, source, matched = _resolve_questions(m, ["sales by date"])
    assert source == "questions"
    # measures fallback when no questions
    sets, source, matched = _resolve_questions(m, None)
    assert source == "measures"
    assert sets == [{"FactSales"}]  # Total resolves to FactSales only
    # empty list falls through (NOT 'questions')
    sets, source, matched = _resolve_questions(m, [])
    assert source == "measures"


def test_resolve_returns_none_when_no_usable_questions():
    # measure-of-measure only (empty depends_on_columns) -> no usable questions
    m = _model([_table("F", TableType.FACT, measures=[_measure("Ratio", [])])])
    sets, source, matched = _resolve_questions(m, None)
    assert source is None
    assert sets == []
