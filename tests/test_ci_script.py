"""Tests for the CI governance threshold script."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "ci-governance-check.py"


def _write_report(tmp_path: Path, report: dict) -> Path:
    path = tmp_path / "governance-report.json"
    path.write_text(json.dumps(report), encoding="utf-8")
    return path


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
    )


# ---------------------------------------------------------------------------
# Clean reports pass
# ---------------------------------------------------------------------------


def test_clean_report_exits_zero(tmp_path):
    report = {
        "summary": {
            "model_count": 2,
            "total_naming_issues": 0,
            "total_duplicate_measures": 0,
        },
        "score_ranking": [
            {"name": "M1", "ai_readiness_score": 0.85},
            {"name": "M2", "ai_readiness_score": 0.78},
        ],
    }
    path = _write_report(tmp_path, report)
    result = _run(str(path), "--max-naming-issues", "5",
                  "--min-score", "0.7", "--max-duplicate-measures", "0")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PASS" in result.stdout


def test_no_thresholds_passes(tmp_path):
    """With no thresholds set, any report should pass."""
    report = {"summary": {"model_count": 1, "total_naming_issues": 99}}
    path = _write_report(tmp_path, report)
    result = _run(str(path))
    assert result.returncode == 0, result.stdout + result.stderr


# ---------------------------------------------------------------------------
# Threshold breaches fail
# ---------------------------------------------------------------------------


def test_naming_issues_above_threshold_fails(tmp_path):
    report = {
        "summary": {"model_count": 1, "total_naming_issues": 10},
        "score_ranking": [{"name": "M1", "ai_readiness_score": 0.9}],
    }
    path = _write_report(tmp_path, report)
    result = _run(str(path), "--max-naming-issues", "5")
    assert result.returncode == 1
    assert "FAIL" in result.stdout
    assert "naming inconsistencies = 10" in result.stdout


def test_duplicate_measures_above_threshold_fails(tmp_path):
    report = {
        "summary": {"model_count": 1, "total_duplicate_measures": 3},
        "score_ranking": [{"name": "M1", "ai_readiness_score": 0.9}],
    }
    path = _write_report(tmp_path, report)
    result = _run(str(path), "--max-duplicate-measures", "0")
    assert result.returncode == 1
    assert "duplicate measures = 3" in result.stdout


def test_average_score_below_threshold_fails(tmp_path):
    report = {
        "summary": {"model_count": 2},
        "score_ranking": [
            {"name": "M1", "ai_readiness_score": 0.4},
            {"name": "M2", "ai_readiness_score": 0.5},
        ],
    }
    path = _write_report(tmp_path, report)
    result = _run(str(path), "--min-score", "0.7")
    assert result.returncode == 1
    assert "average score" in result.stdout


def test_average_score_at_exact_threshold_passes(tmp_path):
    report = {
        "summary": {"model_count": 2},
        "score_ranking": [
            {"name": "M1", "ai_readiness_score": 0.7},
            {"name": "M2", "ai_readiness_score": 0.7},
        ],
    }
    path = _write_report(tmp_path, report)
    result = _run(str(path), "--min-score", "0.7")
    assert result.returncode == 0


def test_unscored_models_excluded_from_average(tmp_path):
    """Models with ai_readiness_score = None must not skew the average."""
    report = {
        "summary": {"model_count": 3},
        "score_ranking": [
            {"name": "M1", "ai_readiness_score": 0.9},
            {"name": "M2", "ai_readiness_score": None},
            {"name": "M3", "ai_readiness_score": 0.85},
        ],
    }
    path = _write_report(tmp_path, report)
    result = _run(str(path), "--min-score", "0.8")
    assert result.returncode == 0, result.stdout


def test_no_scored_models_with_min_score_fails(tmp_path):
    report = {
        "summary": {"model_count": 1},
        "score_ranking": [{"name": "M1", "ai_readiness_score": None}],
    }
    path = _write_report(tmp_path, report)
    result = _run(str(path), "--min-score", "0.5")
    assert result.returncode == 1
    assert "no models had a score" in result.stdout


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


def test_missing_file_exits_one(tmp_path):
    result = _run(str(tmp_path / "does-not-exist.json"))
    assert result.returncode == 1
    assert "not found" in result.stderr.lower()


def test_invalid_json_exits_one(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text("{ not json", encoding="utf-8")
    result = _run(str(path))
    assert result.returncode == 1
    assert "valid json" in result.stderr.lower()


def test_invalid_min_score_exits_one(tmp_path):
    path = _write_report(tmp_path, {"summary": {"model_count": 0}})
    result = _run(str(path), "--min-score", "1.5")
    assert result.returncode == 1
    assert "min-score" in result.stderr.lower()


# ---------------------------------------------------------------------------
# In-process tests of the evaluate() function
# ---------------------------------------------------------------------------


@pytest.fixture
def script_module():
    """Load the script as a module so we can call evaluate() directly."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("ci_governance_check", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_evaluate_pass(script_module):
    report = {
        "summary": {"model_count": 1, "total_naming_issues": 0,
                    "total_duplicate_measures": 0},
        "score_ranking": [{"name": "M", "ai_readiness_score": 0.9}],
    }
    passed, messages = script_module.evaluate(
        report, max_naming_issues=5, max_duplicate_measures=0, min_score=0.7
    )
    assert passed is True
    assert any("OK" in m for m in messages)


def test_evaluate_fail_on_score(script_module):
    report = {
        "summary": {"model_count": 1, "total_naming_issues": 0},
        "score_ranking": [{"name": "M", "ai_readiness_score": 0.5}],
    }
    passed, messages = script_module.evaluate(
        report, max_naming_issues=None, max_duplicate_measures=None, min_score=0.7
    )
    assert passed is False
    assert any("FAIL" in m and "average score" in m for m in messages)


def test_compute_average_score_returns_none_for_empty(script_module):
    assert script_module.compute_average_score({"score_ranking": []}) is None
    assert script_module.compute_average_score({}) is None
