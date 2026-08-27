import json

from fabric_ai_meta.analyzer.agent_readiness import (
    _find_ambiguous_names,
    _find_missing_relationships,
    _find_undescribed,
    _find_unreliable_types,
    assess_agent_readiness,
    write_agent_readiness_report,
)
from fabric_ai_meta.analyzer.scorer import SCORING_WEIGHTS, score_model
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


# --- assess_agent_readiness ---

def test_zero_findings_model_has_empty_report():
    model = _model([_table(
        "Sales", description="Sales fact table",
        columns=[_column("Amount", data_type="double", description="Sale amount")],
        measures=[_measure("Total Sales", description="Sum of sales")],
    )])
    report = assess_agent_readiness(model)
    assert report["summary"]["total_findings"] == 0
    assert report["findings"] == []


def test_findings_sorted_by_weight_descending():
    # Detectors run in a fixed order whose weights already happen to be
    # non-increasing (0.25/0.20 -> 0.15 -> 0.15 -> 0.05), so raw emission
    # order is already sorted before .sort() runs on this fixture - pin the
    # exact expected sequence (not just weight monotonicity) so a real
    # ordering regression is still caught. CustomerKey/sales_amt need their
    # own descriptions here so they don't *also* trip the undescribed
    # detector and blur the one-finding-per-type intent of this fixture.
    model = _model([_table(
        "Sales",
        columns=[
            # missing_relationship 0.15
            _column("CustomerKey", role=ColumnRole.FOREIGN_KEY, description="Customer FK"),
            # ambiguous_name 0.15 + unreliable_type 0.05
            _column("sales_amt", data_type="", description="Sale amount"),
        ],
        measures=[_measure("Total Sales", description=None)],  # undescribed measure 0.20
        description=None,  # undescribed table 0.25
    )])
    report = assess_agent_readiness(model)
    weights = [f["weight"] for f in report["findings"]]
    assert weights == sorted(weights, reverse=True)
    types_in_order = [(f["type"], f["table"], f["column"], f["measure"]) for f in report["findings"]]
    assert types_in_order == [
        ("undescribed", "Sales", None, None),
        ("undescribed", "Sales", None, "Total Sales"),
        ("ambiguous_name", "Sales", "sales_amt", None),
        ("missing_relationship", "Sales", "CustomerKey", None),
        ("unreliable_type", "Sales", "sales_amt", None),
    ]


def test_sort_actually_reorders_out_of_weight_order_findings():
    """Unlike the single-table fixture above, this fixture's raw detector-
    emission order is genuinely NOT already sorted: table A's undescribed
    measure (0.20) is emitted before table B's undescribed table (0.25),
    since _find_undescribed iterates model.tables in order. This proves
    findings.sort(...) is load-bearing - deleting it would fail this test.
    """
    table_a = _table(
        "A", description="A desc", measures=[_measure("Total", description=None)],
    )
    table_b = _table("B", description=None)
    model = _model([table_a, table_b])

    report = assess_agent_readiness(model)

    assert [(f["table"], f["weight"]) for f in report["findings"]] == [
        ("B", 0.25),
        ("A", 0.20),
    ]


def test_summary_counts_match_findings():
    model = _model([_table(
        "Sales",
        columns=[_column("CustomerKey", role=ColumnRole.FOREIGN_KEY)],
    )])
    report = assess_agent_readiness(model)
    summary = report["summary"]
    assert summary["total_findings"] == len(report["findings"])
    assert sum(summary[t] for t in
               ["undescribed", "ambiguous_name", "missing_relationship", "unreliable_type"]
               ) == summary["total_findings"]


def test_score_and_breakdown_match_scorer_directly():
    model = _model([_table("Sales", columns=[_column("Amount")])])
    report = assess_agent_readiness(model)
    expected_score, expected_breakdown = score_model(model)
    assert report["score"] == expected_score
    assert report["breakdown"] == expected_breakdown


def test_top_level_shape():
    model = _model([_table("Sales")])
    report = assess_agent_readiness(model)
    assert report["$schema"] == (
        "https://raw.githubusercontent.com/psistla/fabric-ai-meta/master/"
        "schemas/agent-readiness/v1.json"
    )
    assert report["version"] == "1.0"
    assert report["model"] == "Test Model"
    assert "generated_at" in report


def test_write_agent_readiness_report_writes_valid_json(tmp_path):
    model = _model([_table("Sales", columns=[_column("Amount")])])
    out_path = tmp_path / "agent-readiness.json"

    result_path = write_agent_readiness_report(model, str(out_path))

    assert result_path == str(out_path)
    assert out_path.exists()
    with open(out_path) as f:
        data = json.load(f)
    assert data["model"] == "Test Model"
    assert "findings" in data
