"""Tests for the CLI."""

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
    import json as _json
    from unittest.mock import MagicMock, patch

    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = _json.dumps({"description": "desc"})
    mock_response.usage.prompt_tokens = 10
    mock_response.usage.completion_tokens = 5

    with patch("fabric_ai_meta.llm.litellm_backend.litellm.completion") as mock_completion:
        mock_completion.return_value = mock_response

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


# ---------------------------------------------------------------------------
# diff command
# ---------------------------------------------------------------------------


def _write_summary(path, models, timestamp="2026-04-01T00:00:00Z"):
    """Write a minimal workspace-summary.json for diff testing."""
    scores = [m["ai_readiness_score"] for m in models if m.get("ai_readiness_score") is not None]
    avg = sum(scores) / len(scores) if scores else None
    data = {
        "$schema": "https://raw.githubusercontent.com/psistla/fabric-ai-meta/master/schemas/workspace-summary/v1.json",
        "version": "1.0",
        "workspace": "test",
        "scan_timestamp": timestamp,
        "model_count": len(models),
        "average_readiness_score": avg,
        "models": models,
        "score_ranking": [m["name"] for m in models],
        "recommendations": [],
    }
    with open(path, "w") as f:
        json.dump(data, f)


def _model_entry(name, score=0.7, tables=4, measures=5):
    return {
        "name": name, "slug": name.lower().replace(" ", "-"),
        "ai_readiness_score": score, "table_count": tables,
        "measure_count": measures, "description_coverage": 0.8,
        "extraction_timestamp": "2026-04-01T00:00:00Z",
        "output_directory": f"{name.lower().replace(' ', '-')}/", "errors": [],
    }


def test_diff_json_exits_zero(runner, tmp_path):
    baseline = str(tmp_path / "baseline.json")
    current = str(tmp_path / "current.json")
    _write_summary(baseline, [_model_entry("A")])
    _write_summary(current, [_model_entry("A"), _model_entry("B")])
    result = runner.invoke(main, ["diff", baseline, current])
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert "summary" in data
    assert "model_deltas" in data


def test_diff_text_format(runner, tmp_path):
    baseline = str(tmp_path / "baseline.json")
    current = str(tmp_path / "current.json")
    _write_summary(baseline, [_model_entry("A", score=0.5)])
    _write_summary(current, [_model_entry("A", score=0.8)])
    result = runner.invoke(main, ["diff", baseline, current, "--format", "text"])
    assert result.exit_code == 0
    assert "Workspace Delta Report" in result.output
    assert "improved" in result.output


def test_diff_output_to_file(runner, tmp_path):
    baseline = str(tmp_path / "baseline.json")
    current = str(tmp_path / "current.json")
    out = str(tmp_path / "delta.json")
    _write_summary(baseline, [_model_entry("A")])
    _write_summary(current, [_model_entry("A")])
    result = runner.invoke(main, ["diff", baseline, current, "--output", out])
    assert result.exit_code == 0
    assert os.path.exists(out)
    data = json.load(open(out))
    assert "summary" in data


def test_diff_missing_file_exits_nonzero(runner, tmp_path):
    baseline = str(tmp_path / "nonexistent.json")
    current = str(tmp_path / "also-nonexistent.json")
    result = runner.invoke(main, ["diff", baseline, current])
    assert result.exit_code != 0


# ---------------------------------------------------------------------------
# Chunk 7: --with-copilot flag wiring
# ---------------------------------------------------------------------------

def test_export_single_passes_with_copilot_to_extractor(monkeypatch):
    """_export_single(..., with_copilot=True) must pass it to extractor.extract."""
    from unittest.mock import MagicMock

    import fabric_ai_meta.cli as cli

    captured_kwargs = {}

    class StubExtractor:
        def extract(self, model_name, workspace, **kwargs):
            captured_kwargs.update(kwargs)
            from fabric_ai_meta.models.metadata import SemanticModelMeta
            return SemanticModelMeta(
                name=model_name, workspace=workspace, description=None,
                tables=[], relationships=[],
                ai_readiness_score=None, scoring_breakdown={},
                extraction_timestamp="2026-01-01T00:00:00Z", extraction_method="mock",
            )

    monkeypatch.setattr(
        "fabric_ai_meta.extractor.mock.MockExtractor",
        lambda fixture_path: StubExtractor()
    )
    monkeypatch.setattr(cli, "_get_fixture_path", lambda name: "/tmp/whatever.json")

    fake_exporter = MagicMock()
    fake_exporter.write.return_value = "/tmp/out/x"

    cli._export_single(
        "Adventure Works", "Production", fake_exporter,
        mock=True, with_copilot=True,
    )
    assert captured_kwargs == {"with_copilot": True}


def test_export_copilot_cli_invocation_populates_copilot_via_mock(tmp_path, monkeypatch):
    """`fabric-ai-meta export copilot Adventure --mock` implicitly passes with_copilot=True
    and writes the copilot/ tree to disk."""
    from click.testing import CliRunner

    import fabric_ai_meta.cli as cli
    from fabric_ai_meta.cli import main
    from fabric_ai_meta.config import Config, ExtractionConfig, OutputConfig
    monkeypatch.setattr(cli, "load_config", lambda: Config(
        extraction=ExtractionConfig(default_workspace="W"),
        output=OutputConfig(output_dir=str(tmp_path)),
    ))

    runner = CliRunner()
    result = runner.invoke(main, ["export", "copilot", "Adventure Works", "--mock"])

    assert result.exit_code == 0, result.output
    assert (tmp_path / "adventure-works" / "copilot" / "Instructions" / "instructions.md").exists()


def test_export_langchain_cli_does_not_pass_with_copilot(monkeypatch, tmp_path):
    """Non-copilot exporters must not trigger Copilot extraction."""
    from click.testing import CliRunner

    import fabric_ai_meta.cli as cli
    from fabric_ai_meta.config import Config, ExtractionConfig, OutputConfig

    captured = {}
    class StubExtractor:
        def extract(self, model_name, workspace, **kwargs):
            captured.update(kwargs)
            from fabric_ai_meta.models.metadata import SemanticModelMeta
            return SemanticModelMeta(
                name=model_name, workspace=workspace, description=None,
                tables=[], relationships=[],
                ai_readiness_score=None, scoring_breakdown={},
                extraction_timestamp="2026-01-01T00:00:00Z", extraction_method="mock",
            )

    monkeypatch.setattr(
        "fabric_ai_meta.extractor.mock.MockExtractor",
        lambda fixture_path: StubExtractor()
    )
    monkeypatch.setattr(cli, "load_config", lambda: Config(
        extraction=ExtractionConfig(default_workspace="W"),
        output=OutputConfig(output_dir=str(tmp_path)),
    ))

    from fabric_ai_meta.cli import main
    runner = CliRunner()
    runner.invoke(main, ["export", "langchain", "Adventure Works", "--mock"])
    assert captured.get("with_copilot") is False


def test_analyze_with_copilot_flag_passes_to_extractor(monkeypatch, tmp_path):
    from click.testing import CliRunner

    import fabric_ai_meta.cli as cli
    from fabric_ai_meta.cli import main
    from fabric_ai_meta.config import Config, ExtractionConfig, OutputConfig

    captured = {}

    class StubExtractor:
        def extract(self, model_name, workspace, **kwargs):
            captured.update(kwargs)
            from fabric_ai_meta.models.metadata import SemanticModelMeta
            return SemanticModelMeta(
                name=model_name, workspace=workspace, description=None,
                tables=[], relationships=[],
                ai_readiness_score=None, scoring_breakdown={},
                extraction_timestamp="2026-01-01T00:00:00Z", extraction_method="mock",
            )

    monkeypatch.setattr(
        "fabric_ai_meta.extractor.mock.MockExtractor",
        lambda fixture_path: StubExtractor()
    )
    monkeypatch.setattr(cli, "load_config", lambda: Config(
        extraction=ExtractionConfig(default_workspace="W"),
        output=OutputConfig(output_dir=str(tmp_path)),
    ))

    runner = CliRunner()
    result = runner.invoke(main, [
        "analyze", "Adventure Works", "--mock", "--with-copilot",
    ])
    assert result.exit_code == 0, result.output
    assert captured.get("with_copilot") is True
