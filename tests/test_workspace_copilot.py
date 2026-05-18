"""Integration tests for Copilot signals in scan output and governance reports."""

import json
import os

import pytest
from click.testing import CliRunner

from fabric_ai_meta.cli import main


@pytest.fixture
def runner():
    return CliRunner()


def _read_summary(output_dir: str) -> dict:
    with open(os.path.join(output_dir, "workspace-summary.json"), encoding="utf-8") as f:
        return json.load(f)


def test_scan_without_copilot_flag_omits_signals(runner, tmp_path):
    out = tmp_path / "out"
    result = runner.invoke(main, [
        "scan", "--workspace", "test-ws", "--mock", "-o", str(out),
    ])
    assert result.exit_code == 0, result.output
    summary = _read_summary(str(out))
    assert "copilot_summary" not in summary
    for m in summary["models"]:
        assert "copilot" not in m


def test_scan_with_copilot_flag_includes_signals(runner, tmp_path):
    out = tmp_path / "out"
    result = runner.invoke(main, [
        "scan", "--workspace", "test-ws", "--mock", "--with-copilot",
        "-o", str(out),
    ])
    assert result.exit_code == 0, result.output
    summary = _read_summary(str(out))

    assert "copilot_summary" in summary
    rollup = summary["copilot_summary"]
    assert "models_with_copilot" in rollup
    assert "models_without_ai_instructions" in rollup
    assert "total_verified_answers" in rollup

    # Every model must have a `copilot` block when the flag is set.
    for m in summary["models"]:
        assert "copilot" in m
        sig = m["copilot"]
        # Schema shape:
        for key in (
            "has_ai_instructions",
            "ai_instructions_length",
            "verified_answer_count",
            "ai_data_schema_table_count",
            "example_prompt_count",
            "copilot_enabled",
            "copilot_version",
        ):
            assert key in sig


def test_scan_with_copilot_identifies_models_with_artifacts(runner, tmp_path):
    """Adventure Works + Enterprise Sales fixtures ship Copilot sidecars; Contoso does not."""
    out = tmp_path / "out"
    result = runner.invoke(main, [
        "scan", "--workspace", "test-ws", "--mock", "--with-copilot",
        "-o", str(out),
    ])
    assert result.exit_code == 0, result.output
    summary = _read_summary(str(out))

    # At least one model has AI Instructions (Adventure Works sidecar does).
    with_instructions = [
        m["name"] for m in summary["models"]
        if m["copilot"]["has_ai_instructions"]
    ]
    assert with_instructions, "expected at least one mock model with AI Instructions"

    # At least one model lacks AI Instructions (Contoso Sales has no sidecar).
    missing = summary["copilot_summary"]["models_without_ai_instructions"]
    assert missing, "expected at least one model without AI Instructions"

    # Aggregate verified answer count is the sum across models.
    expected_total = sum(m["copilot"]["verified_answer_count"] for m in summary["models"])
    assert summary["copilot_summary"]["total_verified_answers"] == expected_total


def test_governance_with_copilot_includes_completeness_section(runner, tmp_path):
    out = tmp_path / "out"
    report_path = out / "gov.json"
    result = runner.invoke(main, [
        "governance", "--workspace", "test-ws", "--mock", "--with-copilot",
        "-o", str(out), "--report", str(report_path),
    ])
    assert result.exit_code == 0, result.output
    with open(report_path, encoding="utf-8") as f:
        report = json.load(f)
    assert "copilot_completeness" in report
    cc = report["copilot_completeness"]
    assert "per_model_signals" in cc
    assert "models_without_ai_instructions" in cc
    # When AI Instructions are missing, a recommendation must surface them.
    if cc["models_without_ai_instructions"]:
        flagged = cc["models_without_ai_instructions"][0]
        assert any(flagged in r for r in report["recommendations"])


def test_governance_without_copilot_flag_omits_completeness(runner, tmp_path):
    out = tmp_path / "out"
    report_path = out / "gov.json"
    result = runner.invoke(main, [
        "governance", "--workspace", "test-ws", "--mock",
        "-o", str(out), "--report", str(report_path),
    ])
    assert result.exit_code == 0, result.output
    with open(report_path, encoding="utf-8") as f:
        report = json.load(f)
    assert "copilot_completeness" not in report


def test_governance_with_copilot_output_validates_against_schema(runner, tmp_path):
    import jsonschema

    out = tmp_path / "out"
    report_path = out / "gov.json"
    runner.invoke(main, [
        "governance", "--workspace", "test-ws", "--mock", "--with-copilot",
        "-o", str(out), "--report", str(report_path),
    ])
    with open(report_path, encoding="utf-8") as f:
        report = json.load(f)
    schema_path = os.path.join(
        os.path.dirname(__file__), "..", "schemas", "governance-report", "v1.json"
    )
    with open(schema_path, encoding="utf-8") as f:
        schema = json.load(f)
    jsonschema.validate(report, schema)


def test_scan_with_copilot_output_validates_against_schema(runner, tmp_path):
    """workspace-summary.json (with copilot fields) validates against JSON Schema."""
    import jsonschema

    out = tmp_path / "out"
    result = runner.invoke(main, [
        "scan", "--workspace", "test-ws", "--mock", "--with-copilot",
        "-o", str(out),
    ])
    assert result.exit_code == 0, result.output
    summary = _read_summary(str(out))
    schema_path = os.path.join(
        os.path.dirname(__file__), "..", "schemas", "workspace-summary", "v1.json"
    )
    with open(schema_path, encoding="utf-8") as f:
        schema = json.load(f)
    jsonschema.validate(summary, schema)
