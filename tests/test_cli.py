"""Tests for the CLI (Task 10 — SPEC.md Section 7.1)."""

import json
import os

import pytest
from click.testing import CliRunner

from fabric_ai_meta.cli import main


FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")
ADVENTURE_WORKS_FIXTURE = os.path.join(FIXTURES_DIR, "adventure_works.json")


@pytest.fixture
def runner():
    return CliRunner()


# ---------------------------------------------------------------------------
# Help smoke tests
# ---------------------------------------------------------------------------

def test_main_help_exits_0(runner):
    result = runner.invoke(main, ["--help"])
    assert result.exit_code == 0
    assert "fabric-ai-meta" in result.output.lower() or "usage" in result.output.lower()


def test_analyze_help_exits_0(runner):
    result = runner.invoke(main, ["analyze", "--help"])
    assert result.exit_code == 0
    assert "model_name" in result.output.lower() or "--workspace" in result.output


def test_auth_help_exits_0(runner):
    result = runner.invoke(main, ["auth", "--help"])
    assert result.exit_code == 0


def test_export_help_exits_0(runner):
    result = runner.invoke(main, ["export", "--help"])
    assert result.exit_code == 0


def test_score_help_exits_0(runner):
    result = runner.invoke(main, ["score", "--help"])
    assert result.exit_code == 0


def test_scan_help_exits_0(runner):
    result = runner.invoke(main, ["scan", "--help"])
    assert result.exit_code == 0


def test_governance_help_exits_0(runner):
    result = runner.invoke(main, ["governance", "--help"])
    assert result.exit_code == 0


# ---------------------------------------------------------------------------
# auth subcommands smoke tests
# ---------------------------------------------------------------------------

def test_auth_status_exits_0(runner):
    result = runner.invoke(main, ["auth", "status"])
    assert result.exit_code == 0


def test_auth_logout_exits_0(runner):
    result = runner.invoke(main, ["auth", "logout"])
    assert result.exit_code == 0


# ---------------------------------------------------------------------------
# analyze --mock end-to-end
# ---------------------------------------------------------------------------

def test_analyze_mock_end_to_end(runner, tmp_path):
    """analyze --mock should run full pipeline and produce output files."""
    result = runner.invoke(main, [
        "analyze", "Adventure Works",
        "--workspace", "test",
        "--output", str(tmp_path),
        "--mock",
    ])
    assert result.exit_code == 0, f"Exit code {result.exit_code}: {result.output}"

    slug_dir = tmp_path / "adventure-works"
    assert slug_dir.exists(), f"Expected output dir {slug_dir}"

    expected_files = [
        "ai-ready-schema.json",
        "langchain-tool.json",
        "openai-function.json",
        "semantic-kernel-plugin.json",
        "readiness-score.json",
        "measure-dependency-graph.json",
        "extraction-raw.json",
    ]
    for fname in expected_files:
        fpath = slug_dir / fname
        assert fpath.exists(), f"Missing output file: {fname}"
        with open(fpath) as f:
            data = json.load(f)
        assert isinstance(data, dict), f"{fname} is not a JSON object"


def test_analyze_mock_ai_ready_schema_structure(runner, tmp_path):
    """ai-ready-schema.json from --mock has required top-level keys."""
    runner.invoke(main, [
        "analyze", "Adventure Works",
        "--workspace", "test",
        "--output", str(tmp_path),
        "--mock",
    ])
    schema_path = tmp_path / "adventure-works" / "ai-ready-schema.json"
    with open(schema_path) as f:
        schema = json.load(f)

    for key in ["$schema", "version", "model", "tables", "measures", "query_guidance", "scoring"]:
        assert key in schema, f"Missing key '{key}' in ai-ready-schema.json"


def test_analyze_mock_readiness_score_valid(runner, tmp_path):
    """readiness-score.json contains a score between 0 and 1."""
    runner.invoke(main, [
        "analyze", "Adventure Works",
        "--workspace", "test",
        "--output", str(tmp_path),
        "--mock",
    ])
    score_path = tmp_path / "adventure-works" / "readiness-score.json"
    with open(score_path) as f:
        data = json.load(f)
    assert "score" in data
    assert 0.0 <= data["score"] <= 1.0


def test_analyze_mock_langchain_export_valid(runner, tmp_path):
    """langchain-tool.json has required keys."""
    runner.invoke(main, [
        "analyze", "Adventure Works",
        "--workspace", "test",
        "--output", str(tmp_path),
        "--mock",
    ])
    lc_path = tmp_path / "adventure-works" / "langchain-tool.json"
    with open(lc_path) as f:
        data = json.load(f)
    assert "name" in data
    assert "description" in data
    assert "parameters" in data


def test_analyze_mock_openai_export_valid(runner, tmp_path):
    """openai-function.json has type == 'function'."""
    runner.invoke(main, [
        "analyze", "Adventure Works",
        "--workspace", "test",
        "--output", str(tmp_path),
        "--mock",
    ])
    oa_path = tmp_path / "adventure-works" / "openai-function.json"
    with open(oa_path) as f:
        data = json.load(f)
    assert data.get("type") == "function"
    assert "required" in data["function"]["parameters"]


def test_analyze_mock_semantic_kernel_export_valid(runner, tmp_path):
    """semantic-kernel-plugin.json has schema_version and functions."""
    runner.invoke(main, [
        "analyze", "Adventure Works",
        "--workspace", "test",
        "--output", str(tmp_path),
        "--mock",
    ])
    sk_path = tmp_path / "adventure-works" / "semantic-kernel-plugin.json"
    with open(sk_path) as f:
        data = json.load(f)
    assert "schema_version" in data
    assert "functions" in data
    assert isinstance(data["functions"], list)


def test_score_mock_single_model(runner):
    """score --mock MODEL_NAME should print a score table and exit 0."""
    result = runner.invoke(main, [
        "score", "Adventure Works",
        "--workspace", "test",
        "--mock",
    ])
    assert result.exit_code == 0


def test_analyze_mock_extraction_raw_matches_model(runner, tmp_path):
    """extraction-raw.json round-trips back to a valid SemanticModelMeta."""
    from fabric_ai_meta.models.metadata import from_dict

    runner.invoke(main, [
        "analyze", "Adventure Works",
        "--workspace", "test",
        "--output", str(tmp_path),
        "--mock",
    ])
    raw_path = tmp_path / "adventure-works" / "extraction-raw.json"
    with open(raw_path) as f:
        raw = json.load(f)
    model = from_dict(raw)
    assert len(model.tables) > 0


# ---------------------------------------------------------------------------
# scan --mock end-to-end
# ---------------------------------------------------------------------------

def test_scan_mock_exits_0(runner, tmp_path):
    result = runner.invoke(main, [
        "scan", "--workspace", "test", "--output", str(tmp_path), "--mock",
    ])
    assert result.exit_code == 0, f"Exit {result.exit_code}: {result.output}"


def test_scan_mock_produces_model_subdirs(runner, tmp_path):
    runner.invoke(main, [
        "scan", "--workspace", "test", "--output", str(tmp_path), "--mock",
    ])
    slugs = {d for d in os.listdir(tmp_path) if (tmp_path / d).is_dir()}
    assert "adventure-works" in slugs
    assert "contoso-sales" in slugs


def test_scan_mock_workspace_summary_exists_and_valid_json(runner, tmp_path):
    runner.invoke(main, [
        "scan", "--workspace", "test", "--output", str(tmp_path), "--mock",
    ])
    summary_path = tmp_path / "workspace-summary.json"
    assert summary_path.exists(), "workspace-summary.json not found"
    with open(summary_path) as f:
        data = json.load(f)
    assert isinstance(data, dict)


def test_scan_mock_workspace_summary_top_level_keys(runner, tmp_path):
    runner.invoke(main, [
        "scan", "--workspace", "test", "--output", str(tmp_path), "--mock",
    ])
    with open(tmp_path / "workspace-summary.json") as f:
        data = json.load(f)
    for key in ["$schema", "version", "workspace", "scan_timestamp",
                "model_count", "average_readiness_score", "models",
                "score_ranking", "recommendations"]:
        assert key in data, f"Missing key '{key}' in workspace-summary.json"


def test_scan_mock_model_count_matches_fixtures(runner, tmp_path):
    runner.invoke(main, [
        "scan", "--workspace", "test", "--output", str(tmp_path), "--mock",
    ])
    with open(tmp_path / "workspace-summary.json") as f:
        data = json.load(f)
    assert data["model_count"] == 3


def test_scan_mock_score_ranking_sorted_descending(runner, tmp_path):
    runner.invoke(main, [
        "scan", "--workspace", "test", "--output", str(tmp_path), "--mock",
    ])
    with open(tmp_path / "workspace-summary.json") as f:
        data = json.load(f)
    ranking = data["score_ranking"]
    scores = {m["name"]: m["ai_readiness_score"] for m in data["models"] if m["ai_readiness_score"] is not None}
    ranked_scores = [scores[n] for n in ranking if n in scores]
    assert ranked_scores == sorted(ranked_scores, reverse=True)


def test_scan_mock_per_model_fields(runner, tmp_path):
    runner.invoke(main, [
        "scan", "--workspace", "test", "--output", str(tmp_path), "--mock",
    ])
    with open(tmp_path / "workspace-summary.json") as f:
        data = json.load(f)
    for model in data["models"]:
        for key in ["name", "slug", "ai_readiness_score", "table_count",
                    "measure_count", "description_coverage", "output_directory", "errors"]:
            assert key in model, f"Model entry missing key '{key}'"


# ---------------------------------------------------------------------------
# export prep-for-ai --mock
# ---------------------------------------------------------------------------

def test_export_prep_for_ai_mock_exits_0(runner, tmp_path):
    from unittest.mock import patch, MagicMock
    import json as _json

    mock_response = MagicMock()
    mock_response.content = [MagicMock(text=_json.dumps({"description": "desc"}))]
    mock_response.usage.input_tokens = 10
    mock_response.usage.output_tokens = 5

    with patch("fabric_ai_meta.llm.client.anthropic.Anthropic") as mock_cls:
        mock_client = MagicMock()
        mock_cls.return_value = mock_client
        mock_client.messages.create.return_value = mock_response

        result = runner.invoke(main, [
            "export", "prep-for-ai", "Adventure Works",
            "--workspace", "test",
            "--output", str(tmp_path),
            "--mock",
        ])
    assert result.exit_code == 0, f"Exit {result.exit_code}: {result.output}"
    out_file = tmp_path / "adventure-works" / "prep-for-ai-config.json"
    assert out_file.exists()
    with open(out_file) as f:
        data = json.load(f)
    for key in ["included_tables", "excluded_columns", "ai_instructions",
                "verified_answers", "generated_descriptions"]:
        assert key in data, f"Missing key '{key}' in prep-for-ai-config.json"
