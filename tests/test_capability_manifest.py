import json
import os

from fabric_ai_meta.analyzer.capability_manifest import (
    generate_capability_manifest,
    write_capability_manifest,
)
from fabric_ai_meta.analyzer.pipeline import classify_model_in_place
from fabric_ai_meta.extractor.pbip import PbipExtractor
from fabric_ai_meta.models.metadata import (
    MeasureCategory,
    MeasureMeta,
    SemanticModelMeta,
    TableMeta,
)


def _measure(name, dax, category=MeasureCategory.UNKNOWN, depends_on_measures=(), depends_on_columns=()):
    return MeasureMeta(
        name=name,
        dax_expression=dax,
        description=None,
        ai_description=None,
        category=category,
        display_folder=None,
        format_string=None,
        depends_on_measures=list(depends_on_measures),
        depends_on_columns=list(depends_on_columns),
    )


def _table(name, measures=(), partition="Import"):
    return TableMeta(
        name=name, description=None, ai_description=None,
        table_type=None, grain=None, measures=list(measures),
        source_partition_type=partition,
    )


def _model(tables):
    return SemanticModelMeta(
        name="Test Model", workspace="", description=None,
        tables=list(tables), relationships=[],
    )


def test_clean_measure_is_answerable():
    m = _measure("Sales", "SUM('Financials'[Sales])", depends_on_columns=["Financials[Sales]"])
    model = _model([_table("Financials", measures=[m])])
    manifest = generate_capability_manifest(model)
    entry = manifest["measures"][0]
    assert entry["status"] == "answerable"
    assert entry["warnings"] == []
    assert entry["refused_reason"] is None


def test_semi_additive_measure_is_caveated_not_refused():
    m = _measure(
        "Revenue Month End", "CLOSINGBALANCEMONTH([Revenue], dim_date[date_actual])",
        category=MeasureCategory.SEMI_ADDITIVE, depends_on_measures=["[Revenue]"],
    )
    model = _model([_table("Financials", measures=[m])])
    manifest = generate_capability_manifest(model)
    entry = manifest["measures"][0]
    assert entry["status"] == "answerable_with_caveats"
    assert any(w["type"] == "semi_additive" for w in entry["warnings"])
    assert entry["refused_reason"] is None


def test_report_plumbing_measure_is_refused():
    m = _measure("COGS icon", '"data:image/svg+xml,..."')
    model = _model([_table("Formatting", measures=[m])])
    manifest = generate_capability_manifest(model)
    entry = manifest["measures"][0]
    assert entry["status"] == "refused"
    assert entry["warnings"] == []
    assert entry["refused_reason"] == {"reason": "report_plumbing", "detail": "returns an embedded image (data URI)"}


def test_opaque_calculation_group_is_caveated_not_refused():
    """Locked design decision 2: unlike report-plumbing, an opaque calculation
    group is a warning, never a refusal, even though the underlying
    arithmetic is genuinely unknown - it must match guide_query exactly."""
    calc_group = _table("Time Calculation", partition=None)
    m = _measure(
        "Sales MoM", 'CALCULATE([Sales], \'Time Calculation\'[Time Calculation] = "MoM")',
        depends_on_measures=["[Sales]"],
    )
    real_table = _table("Calculations", measures=[m])
    model = _model([calc_group, real_table])
    manifest = generate_capability_manifest(model)
    entry = next(e for e in manifest["measures"] if e["name"] == "Sales MoM")
    assert entry["status"] == "answerable_with_caveats"
    assert any(w["type"] == "opaque_calculation_group" for w in entry["warnings"])
    assert entry["refused_reason"] is None


def test_summary_counts_match_measures():
    answerable = _measure("Sales", "SUM('Financials'[Sales])", depends_on_columns=["Financials[Sales]"])
    caveated = _measure("Target", "0.09")
    refused = _measure("Icon", '"#F8696B"')
    model = _model([_table("Financials", measures=[answerable, caveated, refused])])
    manifest = generate_capability_manifest(model)
    summary = manifest["summary"]
    assert summary["total_measures"] == 3
    assert summary["answerable"] == 1
    assert summary["answerable_with_caveats"] == 1
    assert summary["refused"] == 1
    assert (summary["answerable"] + summary["answerable_with_caveats"]
            + summary["refused"]) == summary["total_measures"]
    assert len(manifest["measures"]) == 3


def test_zero_measures_model_has_empty_manifest():
    model = _model([_table("EmptyTable", measures=[])])
    manifest = generate_capability_manifest(model)
    assert manifest["summary"] == {
        "total_measures": 0, "answerable": 0,
        "answerable_with_caveats": 0, "refused": 0,
    }
    assert manifest["measures"] == []


def test_top_level_shape():
    model = _model([_table("Financials", measures=[])])
    manifest = generate_capability_manifest(model)
    assert manifest["$schema"] == (
        "https://raw.githubusercontent.com/psistla/fabric-ai-meta/master/"
        "schemas/capability-manifest/v1.json"
    )
    assert manifest["version"] == "1.0"
    assert manifest["model"] == "Test Model"
    assert "generated_at" in manifest


def test_write_capability_manifest_writes_valid_json(tmp_path):
    m = _measure("Sales", "SUM('Financials'[Sales])", depends_on_columns=["Financials[Sales]"])
    model = _model([_table("Financials", measures=[m])])
    out_path = tmp_path / "capability-manifest.json"

    result_path = write_capability_manifest(model, str(out_path))

    assert result_path == str(out_path)
    assert out_path.exists()
    with open(out_path) as f:
        data = json.load(f)
    assert data["model"] == "Test Model"
    assert data["summary"]["total_measures"] == 1


# Integration tests against real PBIP fixtures

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures", "pbip")


def _load(folder):
    ex = PbipExtractor(f"{FIXTURES}/{folder}.SemanticModel")
    model = ex.extract(ex.list_models("")[0], "")
    classify_model_in_place(model)
    return model


def _entry(manifest, name):
    return next(e for e in manifest["measures"] if e["name"] == name)


def test_won_pho_cogs_icon_is_refused():
    manifest = generate_capability_manifest(_load("power-bi-stix-won-pho"))
    entry = _entry(manifest, "COGS icon")
    assert entry["table"] == "Formatting"
    assert entry["status"] == "refused"
    assert entry["refused_reason"]["reason"] == "report_plumbing"


def test_won_pho_sales_mom_is_caveated_not_refused():
    manifest = generate_capability_manifest(_load("power-bi-stix-won-pho"))
    entry = _entry(manifest, "Sales MoM")
    assert entry["table"] == "Calculations"
    assert entry["status"] == "answerable_with_caveats"
    assert any(w["type"] == "opaque_calculation_group" for w in entry["warnings"])


def test_won_pho_title_total_sales_inherits_the_known_gap():
    """GAP: pinned, matching query_guidance's own pinned characterization
    test (test_gap_title_total_sales_not_excluded_as_plumbing). This measure
    is a display string ("Total sales: " & FORMAT([Sales], ...)) but
    _report_plumbing_reason does not catch a FORMAT() call embedded
    mid-concatenation, so it is NOT refused here either. Do not "fix" this
    in capability_manifest.py alone - it must stay in sync with
    query_guidance.py, or the two features will disagree."""
    manifest = generate_capability_manifest(_load("power-bi-stix-won-pho"))
    entry = _entry(manifest, "Title total sales")
    assert entry["status"] != "refused"


def test_footwear_carbon_intensity_is_caveated_ratio():
    manifest = generate_capability_manifest(_load("footwear-sustainability"))
    entry = _entry(manifest, "Carbon Intensity")
    assert entry["status"] == "answerable_with_caveats"
    assert any(w["type"] == "ratio" for w in entry["warnings"])


def test_footwear_revenue_month_end_is_caveated_semi_additive():
    manifest = generate_capability_manifest(_load("footwear-sustainability"))
    entry = _entry(manifest, "Revenue Month End")
    assert entry["status"] == "answerable_with_caveats"
    assert any(w["type"] == "semi_additive" for w in entry["warnings"])


def test_footwear_carbon_intensity_target_is_caveated_hardcoded():
    manifest = generate_capability_manifest(_load("footwear-sustainability"))
    entry = _entry(manifest, "Carbon Intensity Target")
    assert entry["status"] == "answerable_with_caveats"
    assert any(w["type"] == "hardcoded_literal" for w in entry["warnings"])
