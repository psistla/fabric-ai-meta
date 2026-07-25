"""Tests for the MCP server tool functions.

These tests bypass the MCP protocol and call the underlying tool functions
directly. They do not require the optional ``mcp`` dependency to be installed.
"""

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from fabric_ai_meta import mcp_server
from fabric_ai_meta.cli import main
from fabric_ai_meta.mcp_server import (
    TOOLS,
    analyze_model,
    diff_summaries,
    generate_schema,
    governance_report,
    list_models,
    score_model,
)

WORKSPACE = "test-workspace"


# ---------------------------------------------------------------------------
# Module import / surface
# ---------------------------------------------------------------------------

def test_module_imports_without_mcp_installed():
    """Importing the module must succeed even when 'mcp' is not installed."""
    assert mcp_server is not None
    assert callable(mcp_server.run)


def test_tools_tuple_lists_six_callables():
    assert len(TOOLS) == 6
    for fn in TOOLS:
        assert callable(fn)


def test_tools_have_docstrings():
    for fn in TOOLS:
        assert fn.__doc__ and fn.__doc__.strip()


# ---------------------------------------------------------------------------
# list_models
# ---------------------------------------------------------------------------

def test_list_models_returns_fixture_set():
    result = list_models(workspace=WORKSPACE)
    assert "models" in result
    assert isinstance(result["models"], list)
    assert len(result["models"]) >= 3
    assert result["workspace"] == WORKSPACE


# ---------------------------------------------------------------------------
# analyze_model
# ---------------------------------------------------------------------------

def test_analyze_model_returns_expected_structure():
    result = analyze_model(model_name="Adventure Works", workspace=WORKSPACE)
    assert "score" in result
    assert "breakdown" in result
    assert "table_count" in result
    assert "measure_count" in result
    assert isinstance(result["table_count"], int)
    assert isinstance(result["measure_count"], int)
    assert 0.0 <= result["score"] <= 1.0


# ---------------------------------------------------------------------------
# score_model
# ---------------------------------------------------------------------------

def test_score_model_returns_score_in_unit_interval():
    result = score_model(model_name="Adventure Works", workspace=WORKSPACE)
    assert "score" in result
    assert 0.0 <= result["score"] <= 1.0
    assert isinstance(result["breakdown"], dict)


def test_score_model_breakdown_weights_present():
    result = score_model(model_name="Adventure Works", workspace=WORKSPACE)
    expected_keys = {
        "description_coverage",
        "measure_documentation",
        "relationship_completeness",
        "naming_consistency",
        "sample_values_available",
        "business_rules_documented",
    }
    assert expected_keys.issubset(set(result["breakdown"].keys()))


# ---------------------------------------------------------------------------
# generate_schema
# ---------------------------------------------------------------------------

def test_generate_schema_returns_ai_ready_dict():
    schema = generate_schema(model_name="Adventure Works", workspace=WORKSPACE)
    assert "tables" in schema
    assert "measures" in schema
    assert "scoring" in schema
    assert isinstance(schema["tables"], list)


# ---------------------------------------------------------------------------
# governance_report
# ---------------------------------------------------------------------------

def test_governance_report_returns_expected_keys():
    report = governance_report(workspace=WORKSPACE)
    assert "summary" in report
    assert "naming_inconsistencies" in report
    assert "duplicate_measures" in report
    assert "score_ranking" in report
    assert isinstance(report["naming_inconsistencies"], list)


def test_governance_report_graph_necessity_param():
    off = governance_report(workspace=WORKSPACE)
    assert "graph_necessity" not in off
    on = governance_report(workspace=WORKSPACE, graph_necessity=True)
    assert "graph_necessity" in on
    # questions must use real model vocabulary, otherwise coverage is too low to
    # earn "strong" (see test_low_coverage_questions_downgrade_confidence)
    strong = governance_report(
        workspace=WORKSPACE, graph_necessity=True,
        questions=["FactInternetSales by DimProduct and DimCustomer"],
    )
    assert strong["graph_necessity"][0]["confidence"] == "strong"


# ---------------------------------------------------------------------------
# diff_summaries
# ---------------------------------------------------------------------------

def test_diff_summaries_returns_delta_for_identical_inputs():
    summary = {
        "workspace": "ws",
        "scan_timestamp": "2026-01-01T00:00:00Z",
        "model_count": 1,
        "average_readiness_score": 0.75,
        "models": [
            {"name": "M1", "ai_readiness_score": 0.75, "table_count": 3,
             "measure_count": 5, "description_coverage": 0.5},
        ],
    }
    payload = json.dumps(summary)
    delta = diff_summaries(baseline_json=payload, current_json=payload)
    assert "summary" in delta
    assert delta["summary"]["model_count_change"] == 0
    assert delta["summary"]["average_score_change"] == 0


def test_diff_summaries_detects_added_model():
    baseline = {
        "scan_timestamp": "2026-01-01T00:00:00Z",
        "model_count": 1,
        "average_readiness_score": 0.5,
        "models": [
            {"name": "M1", "ai_readiness_score": 0.5, "table_count": 1,
             "measure_count": 1, "description_coverage": 0.5},
        ],
    }
    current = {
        "scan_timestamp": "2026-02-01T00:00:00Z",
        "model_count": 2,
        "average_readiness_score": 0.6,
        "models": baseline["models"] + [
            {"name": "M2", "ai_readiness_score": 0.7, "table_count": 2,
             "measure_count": 3, "description_coverage": 0.8},
        ],
    }
    delta = diff_summaries(baseline_json=json.dumps(baseline),
                           current_json=json.dumps(current))
    assert "M2" in delta["summary"]["models_added"]
    assert delta["summary"]["model_count_change"] == 1


def test_diff_summaries_returns_error_for_invalid_json():
    delta = diff_summaries(baseline_json="not json", current_json="{}")
    assert "error" in delta


# ---------------------------------------------------------------------------
# Error handling: tools never raise, they return {"error": ...}
# ---------------------------------------------------------------------------

def test_unknown_pbip_model_returns_error_not_substitution():
    """An unrecognised model name errors instead of falling back to a sample."""
    result = analyze_model(model_name="Nonexistent", workspace=WORKSPACE)
    assert "error" in result


# ---------------------------------------------------------------------------
# build_server: only runs when 'mcp' is installed; otherwise raises ImportError
# ---------------------------------------------------------------------------

def test_build_server_raises_clear_error_when_mcp_missing():
    """If mcp is not installed, build_server() must raise an ImportError with install hint."""
    try:
        import mcp  # noqa: F401
    except ImportError:
        with pytest.raises(ImportError, match="fabric-ai-meta\\[mcp\\]"):
            mcp_server.build_server()
    else:
        # mcp is installed, just verify build_server returns something with a tool method
        server = mcp_server.build_server()
        assert server is not None


# ---------------------------------------------------------------------------
# CLI: serve --help and missing-mcp error path
# ---------------------------------------------------------------------------

def test_cli_serve_help():
    runner = CliRunner()
    result = runner.invoke(main, ["serve", "--help"])
    assert result.exit_code == 0
    assert "transport" in result.output.lower()


def test_cli_serve_without_mcp_exits_nonzero():
    """If mcp is not installed, `serve` exits 1 with a clear install hint."""
    try:
        import mcp  # noqa: F401
        pytest.skip("mcp is installed; this test only validates the missing-dep path")
    except ImportError:
        pass

    runner = CliRunner()
    result = runner.invoke(main, ["serve"])
    assert result.exit_code != 0
    assert "fabric-ai-meta[mcp]" in result.output


PBIP_DIR = str(Path(__file__).resolve().parent / "fixtures" / "pbip")


def test_mcp_tools_read_a_real_pbip_model():
    from fabric_ai_meta.mcp_server import (
        analyze_model,
        generate_schema,
        governance_report,
        list_models,
        score_model,
    )
    names = list_models(workspace="", pbip=PBIP_DIR)
    assert "error" not in names
    assert "stix-one-pho" in names["models"]

    for fn in (analyze_model, score_model, generate_schema):
        result = fn(model_name="stix-one-pho", workspace="", pbip=PBIP_DIR)
        assert "error" not in result, result

    assert "error" not in governance_report(workspace="", pbip=PBIP_DIR)


def test_mcp_defaults_to_bundled_samples():
    from fabric_ai_meta.mcp_server import list_models
    result = list_models(workspace="Production Analytics")
    assert "Adventure Works" in result["models"]
