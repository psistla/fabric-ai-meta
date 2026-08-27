from fabric_ai_meta.analyzer.agent_readiness import (
    _find_ambiguous_names,
    _find_missing_relationships,
    _find_undescribed,
    _find_unreliable_types,
)
from fabric_ai_meta.analyzer.scorer import SCORING_WEIGHTS
from fabric_ai_meta.models.metadata import (
    ColumnMeta,
    ColumnRole,
    MeasureCategory,
    MeasureMeta,
    RelationshipMeta,
    SemanticModelMeta,
    TableMeta,
)


def _column(name, data_type="string", description=None, role=ColumnRole.ATTRIBUTE):
    return ColumnMeta(
        name=name, data_type=data_type, description=description, ai_description=None,
        role=role, is_hidden=False, display_folder=None, format_string=None,
        sort_by_column=None,
    )


def _measure(name, description=None):
    return MeasureMeta(
        name=name, dax_expression="1", description=description, ai_description=None,
        category=MeasureCategory.UNKNOWN, display_folder=None, format_string=None,
    )


def _table(name, columns=(), measures=(), description=None):
    return TableMeta(
        name=name, description=description, ai_description=None,
        table_type=None, grain=None, columns=list(columns), measures=list(measures),
    )


def _model(tables, relationships=()):
    return SemanticModelMeta(
        name="Test Model", workspace="", description=None,
        tables=list(tables), relationships=list(relationships),
    )


# --- _find_undescribed ---

def test_undescribed_table_is_flagged():
    model = _model([_table("Sales", description=None)])
    findings = _find_undescribed(model)
    assert any(f["type"] == "undescribed" and f["table"] == "Sales" and f["column"] is None
               and f["measure"] is None for f in findings)


def test_undescribed_column_is_flagged():
    model = _model([_table(
        "Sales", description="Sales fact table",
        columns=[_column("Amount", description=None)],
    )])
    findings = _find_undescribed(model)
    assert any(f["column"] == "Amount" for f in findings)


def test_undescribed_measure_uses_measure_documentation_weight():
    model = _model([_table("Sales", measures=[_measure("Total Sales", description=None)])])
    findings = _find_undescribed(model)
    entry = next(f for f in findings if f["measure"] == "Total Sales")
    assert entry["weight"] == SCORING_WEIGHTS["measure_documentation"]


def test_described_objects_produce_no_findings():
    model = _model([_table(
        "Sales", description="Sales fact table",
        columns=[_column("Amount", description="Sale amount")],
        measures=[_measure("Total Sales", description="Sum of sales")],
    )])
    assert _find_undescribed(model) == []


# --- _find_ambiguous_names ---

def test_underscore_column_name_is_flagged():
    model = _model([_table("Sales", columns=[_column("sales_amount")])])
    findings = _find_ambiguous_names(model)
    assert any(f["column"] == "sales_amount" for f in findings)


def test_clean_name_produces_no_finding():
    model = _model([_table("Sales", columns=[_column("SalesAmount")])])
    assert _find_ambiguous_names(model) == []


def test_ambiguous_measure_name_is_flagged():
    model = _model([_table("Sales", measures=[_measure("YTD_Sales")])])
    findings = _find_ambiguous_names(model)
    assert any(f["measure"] == "YTD_Sales" for f in findings)


# --- _find_missing_relationships ---

def test_unmatched_fk_is_flagged():
    model = _model([_table(
        "Sales", columns=[_column("CustomerKey", role=ColumnRole.FOREIGN_KEY)],
    )])
    findings = _find_missing_relationships(model)
    assert any(f["table"] == "Sales" and f["column"] == "CustomerKey" for f in findings)


def test_matched_fk_produces_no_finding():
    model = _model(
        [_table("Sales", columns=[_column("CustomerKey", role=ColumnRole.FOREIGN_KEY)])],
        relationships=[RelationshipMeta(
            from_table="Sales", from_column="CustomerKey",
            to_table="Customer", to_column="CustomerKey",
            cardinality="many-to-one", cross_filter_direction="single", is_active=True,
        )],
    )
    assert _find_missing_relationships(model) == []


def test_non_fk_column_is_never_flagged():
    model = _model([_table("Sales", columns=[_column("Notes", role=ColumnRole.ATTRIBUTE)])])
    assert _find_missing_relationships(model) == []


# --- _find_unreliable_types ---

def test_empty_data_type_is_flagged():
    model = _model([_table("Calculations", columns=[_column("Margin", data_type="")])])
    findings = _find_unreliable_types(model)
    assert any(f["column"] == "Margin" for f in findings)
    assert findings[0]["type"] == "unreliable_type"


def test_typed_column_produces_no_finding():
    model = _model([_table("Sales", columns=[_column("Amount", data_type="double")])])
    assert _find_unreliable_types(model) == []
