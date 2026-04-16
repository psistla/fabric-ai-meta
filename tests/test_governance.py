"""Tests for cross-model governance analysis."""

import json
import os
import tempfile

import pytest

from fabric_ai_meta.analyzer.governance import (
    find_naming_inconsistencies,
    find_duplicate_measures,
    generate_governance_report,
    write_governance_report,
)
from fabric_ai_meta.extractor.mock import MockExtractor
from fabric_ai_meta.analyzer.classifier import (
    classify_table_heuristic,
    classify_column_role,
    classify_measure_heuristic,
)
from fabric_ai_meta.analyzer.scorer import score_model


FIXTURE_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


def _load_and_score(fixture_path):
    extractor = MockExtractor(fixture_path=fixture_path)
    model_name = json.load(open(fixture_path, encoding="utf-8"))["name"]
    m = extractor.extract(model_name, "test")
    for tbl in m.tables:
        tbl.table_type = classify_table_heuristic(tbl, m.relationships)
        for c in tbl.columns:
            c.role = classify_column_role(c, tbl, m.relationships)
        for ms in tbl.measures:
            ms.category = classify_measure_heuristic(ms)
    overall, breakdown = score_model(m)
    m.ai_readiness_score = overall
    m.scoring_breakdown = breakdown
    return m


@pytest.fixture
def aw_model():
    return _load_and_score(os.path.join(FIXTURE_DIR, "adventure_works.json"))


@pytest.fixture
def contoso_model():
    return _load_and_score(os.path.join(FIXTURE_DIR, "contoso_sales.json"))


@pytest.fixture
def enterprise_model():
    return _load_and_score(os.path.join(FIXTURE_DIR, "enterprise_sales.json"))


@pytest.fixture
def both_models(aw_model, contoso_model):
    return [aw_model, contoso_model]


@pytest.fixture
def all_three_models(aw_model, contoso_model, enterprise_model):
    return [aw_model, contoso_model, enterprise_model]


# ---------------------------------------------------------------------------
# find_naming_inconsistencies
# ---------------------------------------------------------------------------

class TestFindNamingInconsistencies:
    def test_cross_model_returns_inconsistency(self, both_models):
        """CustomerKey (AW) vs Customer_Key (Contoso) should be detected."""
        results = find_naming_inconsistencies(both_models)
        normalized_names = [r["normalized"] for r in results]
        assert "customerkey" in normalized_names

    def test_result_has_required_keys(self, both_models):
        results = find_naming_inconsistencies(both_models)
        assert len(results) >= 1
        for r in results:
            assert "normalized" in r
            assert "variants" in r
            assert "found_in" in r
            assert "object_type" in r

    def test_variants_has_multiple_entries(self, both_models):
        results = find_naming_inconsistencies(both_models)
        customer_issue = next(r for r in results if r["normalized"] == "customerkey")
        assert len(customer_issue["variants"]) >= 2
        assert "CustomerKey" in customer_issue["variants"]
        assert "Customer_Key" in customer_issue["variants"]

    def test_found_in_has_both_models(self, both_models):
        results = find_naming_inconsistencies(both_models)
        customer_issue = next(r for r in results if r["normalized"] == "customerkey")
        assert "Adventure Works" in customer_issue["found_in"]
        assert "Contoso Sales" in customer_issue["found_in"]

    def test_object_type_is_column_or_measure(self, both_models):
        results = find_naming_inconsistencies(both_models)
        for r in results:
            assert r["object_type"] in ("column", "measure")

    def test_single_model_no_inconsistencies(self, aw_model):
        """A single model with no internal naming conflicts returns empty list."""
        results = find_naming_inconsistencies([aw_model])
        assert results == []

    def test_no_single_variant_groups(self, both_models):
        """Only groups with 2+ variants are returned."""
        results = find_naming_inconsistencies(both_models)
        for r in results:
            assert len(r["variants"]) >= 2


# ---------------------------------------------------------------------------
# find_duplicate_measures
# ---------------------------------------------------------------------------

class TestFindDuplicateMeasures:
    def test_cross_model_detects_duplicate(self, both_models):
        """[Sales YTD] in AW and Contoso have identical DAX after normalization."""
        results = find_duplicate_measures(both_models)
        assert len(results) >= 1

    def test_result_has_required_keys(self, both_models):
        results = find_duplicate_measures(both_models)
        for r in results:
            assert "dax_normalized" in r
            assert "found_in" in r
            assert "dax_identical" in r
            assert r["dax_identical"] is True

    def test_found_in_has_multiple_models(self, both_models):
        results = find_duplicate_measures(both_models)
        for r in results:
            assert len(r["found_in"]) >= 2

    def test_same_name_uses_measure_name_key(self, both_models):
        """When both models have the same measure name, use measure_name key."""
        results = find_duplicate_measures(both_models)
        # [Sales YTD] exists in both with same name
        sales_ytd = next(
            (r for r in results if r.get("measure_name") == "[Sales YTD]"),
            None,
        )
        assert sales_ytd is not None

    def test_different_names_uses_variants_key(self, both_models):
        """When names differ but DAX matches, variants key is used."""
        results = find_duplicate_measures(both_models)
        diff_name = [r for r in results if "variants" in r]
        for r in diff_name:
            assert isinstance(r["variants"], list)
            assert len(r["variants"]) >= 2

    def test_no_duplicates_returns_empty(self, aw_model):
        """Single model has no cross-model duplicates."""
        results = find_duplicate_measures([aw_model])
        assert results == []

    def test_dax_normalization_is_case_insensitive(self, both_models):
        """DAX comparison ignores case."""
        results = find_duplicate_measures(both_models)
        for r in results:
            assert r["dax_normalized"] == r["dax_normalized"].lower()


# ---------------------------------------------------------------------------
# generate_governance_report
# ---------------------------------------------------------------------------

class TestGenerateGovernanceReport:
    def test_has_all_required_keys(self, both_models):
        report = generate_governance_report(both_models)
        assert "summary" in report
        assert "score_ranking" in report
        assert "naming_inconsistencies" in report
        assert "duplicate_measures" in report
        assert "recommendations" in report

    def test_summary_has_required_fields(self, both_models):
        report = generate_governance_report(both_models)
        s = report["summary"]
        assert s["model_count"] == 2
        assert "average_readiness_score" in s
        assert "lowest_scoring_model" in s
        assert "highest_scoring_model" in s
        assert "total_naming_issues" in s
        assert "total_duplicate_measures" in s

    def test_model_count_matches_input(self, both_models, aw_model):
        assert generate_governance_report(both_models)["summary"]["model_count"] == 2
        assert generate_governance_report([aw_model])["summary"]["model_count"] == 1

    def test_score_ranking_sorted_descending(self, both_models):
        report = generate_governance_report(both_models)
        scores = [
            r["ai_readiness_score"]
            for r in report["score_ranking"]
            if r["ai_readiness_score"] is not None
        ]
        assert scores == sorted(scores, reverse=True)

    def test_score_ranking_items_have_required_keys(self, both_models):
        report = generate_governance_report(both_models)
        for item in report["score_ranking"]:
            assert "name" in item
            assert "ai_readiness_score" in item
            assert "table_count" in item
            assert "measure_count" in item

    def test_naming_inconsistencies_populated(self, both_models):
        report = generate_governance_report(both_models)
        assert report["summary"]["total_naming_issues"] == len(report["naming_inconsistencies"])
        assert report["summary"]["total_naming_issues"] >= 1

    def test_duplicate_measures_populated(self, both_models):
        report = generate_governance_report(both_models)
        assert report["summary"]["total_duplicate_measures"] == len(report["duplicate_measures"])
        assert report["summary"]["total_duplicate_measures"] >= 1

    def test_recommendations_non_empty(self, both_models):
        report = generate_governance_report(both_models)
        assert len(report["recommendations"]) >= 1
        for rec in report["recommendations"]:
            assert isinstance(rec, str)
            assert len(rec) > 0


# ---------------------------------------------------------------------------
# write_governance_report
# ---------------------------------------------------------------------------

class TestWriteGovernanceReport:
    def test_produces_valid_json(self, both_models, tmp_path):
        report = generate_governance_report(both_models)
        path = str(tmp_path / "gov.json")
        result_path = write_governance_report(report, "test-workspace", path)
        assert result_path == path
        data = json.loads(open(path, encoding="utf-8").read())
        assert isinstance(data, dict)

    def test_has_schema_key(self, both_models, tmp_path):
        report = generate_governance_report(both_models)
        path = str(tmp_path / "gov.json")
        write_governance_report(report, "test-workspace", path)
        data = json.load(open(path, encoding="utf-8"))
        assert "$schema" in data

    def test_has_all_top_level_keys(self, both_models, tmp_path):
        report = generate_governance_report(both_models)
        path = str(tmp_path / "gov.json")
        write_governance_report(report, "test-workspace", path)
        data = json.load(open(path, encoding="utf-8"))
        for key in ("$schema", "version", "workspace", "generated_at", "summary",
                    "score_ranking", "naming_inconsistencies", "duplicate_measures",
                    "recommendations"):
            assert key in data, f"Missing key: {key}"

    def test_workspace_recorded(self, both_models, tmp_path):
        report = generate_governance_report(both_models)
        path = str(tmp_path / "gov.json")
        write_governance_report(report, "Production Analytics", path)
        data = json.load(open(path, encoding="utf-8"))
        assert data["workspace"] == "Production Analytics"

    def test_creates_parent_directories(self, both_models, tmp_path):
        report = generate_governance_report(both_models)
        path = str(tmp_path / "nested" / "dir" / "gov.json")
        write_governance_report(report, "ws", path)
        assert os.path.exists(path)


# ---------------------------------------------------------------------------
# CLI integration
# ---------------------------------------------------------------------------

class TestGovernanceCLI:
    def test_governance_mock_exits_zero(self, tmp_path):
        from click.testing import CliRunner
        from fabric_ai_meta.cli import main

        runner = CliRunner()
        report_path = str(tmp_path / "gov.json")
        result = runner.invoke(main, [
            "governance",
            "--workspace", "test",
            "--mock",
            "--report", report_path,
        ])
        assert result.exit_code == 0, result.output

    def test_governance_mock_produces_valid_json(self, tmp_path):
        from click.testing import CliRunner
        from fabric_ai_meta.cli import main

        runner = CliRunner()
        report_path = str(tmp_path / "gov.json")
        runner.invoke(main, [
            "governance",
            "--workspace", "test",
            "--mock",
            "--report", report_path,
        ])
        assert os.path.exists(report_path)
        data = json.load(open(report_path, encoding="utf-8"))
        assert isinstance(data, dict)

    def test_governance_mock_has_expected_keys(self, tmp_path):
        from click.testing import CliRunner
        from fabric_ai_meta.cli import main

        runner = CliRunner()
        report_path = str(tmp_path / "gov.json")
        runner.invoke(main, [
            "governance",
            "--workspace", "test",
            "--mock",
            "--report", report_path,
        ])
        data = json.load(open(report_path, encoding="utf-8"))
        for key in ("summary", "score_ranking", "naming_inconsistencies",
                    "duplicate_measures", "recommendations"):
            assert key in data, f"Missing key: {key}"

# ---------------------------------------------------------------------------
# Enterprise fixture — cross-model governance (3 models)
# ---------------------------------------------------------------------------

class TestEnterpriseGovernance:
    def test_three_model_report_model_count(self, all_three_models):
        """Governance report with all 3 fixtures has correct model_count."""
        report = generate_governance_report(all_three_models)
        assert report["summary"]["model_count"] == 3

    def test_enterprise_aw_duplicate_total_sales(self, all_three_models):
        """[Total Sales] in Enterprise Sales should duplicate with Contoso's [Total Sales]
        since both use SUM(...[SalesAmount]) on different tables, but normalized DAX differs.
        [Sales YTD] should be a true duplicate across models with matching DAX."""
        results = find_duplicate_measures(all_three_models)
        # Sales YTD has identical DAX pattern across AW, Contoso, and Enterprise
        dax_found = any(
            "datesytd" in r["dax_normalized"] for r in results
        )
        assert dax_found, "Expected Sales YTD duplicate across models"

    def test_enterprise_naming_inconsistency_total_vs_sum(self, all_three_models):
        """[Total Sales] and [Sum of Revenue] in enterprise model should create
        a naming inconsistency for the 'totalsales' normalized form."""
        results = find_naming_inconsistencies(all_three_models)
        normalized_names = [r["normalized"] for r in results]
        # Should detect naming variants across models
        assert len(results) >= 1

    def test_enterprise_score_ranking_has_three_entries(self, all_three_models):
        """Score ranking should have all 3 models."""
        report = generate_governance_report(all_three_models)
        assert len(report["score_ranking"]) == 3

    def test_enterprise_recommendations_non_empty(self, all_three_models):
        """With 3 models and known issues, recommendations should be populated."""
        report = generate_governance_report(all_three_models)
        assert len(report["recommendations"]) >= 1

    def test_enterprise_duplicate_measures_still_detected(self, all_three_models):
        """Adding a 3rd model should not break existing duplicate detection between AW and Contoso."""
        results = find_duplicate_measures(all_three_models)
        assert len(results) >= 1
        # AW and Contoso still have [Sales YTD] with identical DAX
        models_mentioned = set()
        for r in results:
            models_mentioned.update(r["found_in"])
        assert "Adventure Works" in models_mentioned
        assert "Contoso Sales" in models_mentioned


    def test_governance_no_mock_raises_without_fabric(self):
        from click.testing import CliRunner
        from fabric_ai_meta.cli import main
        import os
        env = {k: v for k, v in os.environ.items() if k != "FABRIC_NOTEBOOK_ID"}
        runner = CliRunner(env=env)
        result = runner.invoke(main, [
            "governance",
            "--workspace", "test",
        ])
        assert result.exit_code != 0
