"""Integration tests for fabric-ai-meta.

Covers:
- Full end-to-end pipeline via MockExtractor
- Acceptance criteria from SPEC.md Section 10 not fully addressed by unit tests
"""

import dataclasses
import json
import os
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from fabric_ai_meta.analyzer.classifier import (
    classify_measure_heuristic,
    classify_table_heuristic,
)
from fabric_ai_meta.analyzer.scorer import score_model
from fabric_ai_meta.auth.entra import (
    FabricEnvironmentError,
    detect_notebook_environment,
    get_credential,
)
from fabric_ai_meta.cli import main
from fabric_ai_meta.generator.export_langchain import to_langchain_tool_definition
from fabric_ai_meta.generator.export_openai import to_openai_function
from fabric_ai_meta.generator.export_semantic_kernel import to_semantic_kernel_plugin
from fabric_ai_meta.generator.schema import generate_ai_ready_schema
from fabric_ai_meta.models.metadata import (
    ColumnMeta,
    ColumnRole,
    MeasureCategory,
    MeasureMeta,
    SemanticModelMeta,
    TableMeta,
    TableType,
)

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


# ---------------------------------------------------------------------------
# Full end-to-end pipeline
# ---------------------------------------------------------------------------


def test_full_pipeline_extract_classify_score(adventure_works_model):
    """Step 1–3: Extract, classify tables and measures, run scorer."""
    model = adventure_works_model

    for table in model.tables:
        table.table_type = classify_table_heuristic(table, model.relationships)
    for table in model.tables:
        for measure in table.measures:
            measure.category = classify_measure_heuristic(measure)

    score, breakdown = score_model(model)
    model.ai_readiness_score = score
    model.scoring_breakdown = breakdown

    assert model.tables[0].table_type != TableType.UNKNOWN
    assert 0.0 <= score <= 1.0
    assert breakdown


def test_full_pipeline_generate_ai_ready_schema(adventure_works_model):
    """Step 4: Generate AI-ready schema after classification + scoring."""
    score, breakdown = score_model(adventure_works_model)
    adventure_works_model.ai_readiness_score = score
    adventure_works_model.scoring_breakdown = breakdown

    schema = generate_ai_ready_schema(adventure_works_model)

    assert set(schema.keys()) == {
        "$schema", "version", "model", "tables", "measures",
        "query_guidance", "scoring",
    }
    raw = json.dumps(schema)
    assert isinstance(json.loads(raw), dict)


def test_full_pipeline_generate_all_framework_exports(adventure_works_model):
    """Step 5: Generate LangChain, OpenAI, and Semantic Kernel exports."""
    lc = to_langchain_tool_definition(adventure_works_model)
    oa = to_openai_function(adventure_works_model)
    sk = to_semantic_kernel_plugin(adventure_works_model)

    for export, label in [(lc, "langchain"), (oa, "openai"), (sk, "semantic_kernel")]:
        raw = json.dumps(export)
        assert isinstance(json.loads(raw), dict), f"{label} not valid JSON"


def test_full_pipeline_output_files_exist_and_are_valid_json(tmp_path):
    """Step 6: CLI analyze --mock produces all expected output files as valid JSON."""
    runner = CliRunner()
    result = runner.invoke(main, [
        "analyze", "Adventure Works",
        "--workspace", "test",
        "--output", str(tmp_path),
        "--mock",
    ])
    assert result.exit_code == 0, f"CLI error: {result.output}"

    slug_dir = tmp_path / "adventure-works"
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
        assert fpath.exists(), f"Missing: {fname}"
        with open(fpath) as f:
            data = json.load(f)
        assert isinstance(data, dict), f"{fname} is not a JSON object"


# ---------------------------------------------------------------------------
# AUTH-01: authenticate via interactive browser login (mocked)
# ---------------------------------------------------------------------------


def test_auth01_get_credential_notebook_returns_none():
    """AUTH-01 / AUTH-02: notebook mode returns None (Fabric ambient credential)."""
    cred = get_credential(method="notebook")
    assert cred is None


@patch("azure.identity.InteractiveBrowserCredential")
def test_auth01_get_credential_interactive_returns_credential(mock_completion):
    """AUTH-01: interactive mode returns an InteractiveBrowserCredential."""
    mock_cred = MagicMock()
    mock_completion.return_value = mock_cred
    cred = get_credential(method="interactive")
    assert cred is mock_cred
    mock_completion.assert_called_once()


@patch("azure.identity.ClientSecretCredential")
def test_auth01_get_credential_service_principal(mock_completion):
    """AUTH-01: service_principal mode returns a ClientSecretCredential."""
    mock_cred = MagicMock()
    mock_completion.return_value = mock_cred
    cred = get_credential(
        method="service_principal",
        tenant_id="tenant-id",
        client_id="client-id",
        client_secret="client-secret",
    )
    assert cred is mock_cred
    mock_completion.assert_called_once_with(
        tenant_id="tenant-id",
        client_id="client-id",
        client_secret="client-secret",
    )


# ---------------------------------------------------------------------------
# AUTH-02: detect ambient notebook credential
# ---------------------------------------------------------------------------


def test_auth02_detect_notebook_environment_via_env_var(monkeypatch):
    """AUTH-02: FABRIC_NOTEBOOK_ID env var signals notebook runtime."""
    monkeypatch.setenv("FABRIC_NOTEBOOK_ID", "abc-123")
    assert detect_notebook_environment() is True


def test_auth02_detect_notebook_environment_via_ipykernel(monkeypatch):
    """AUTH-02: ipykernel in sys.modules signals Jupyter notebook."""
    import sys
    monkeypatch.setitem(sys.modules, "ipykernel", MagicMock())
    assert detect_notebook_environment() is True


def test_auth02_detect_notebook_environment_false_outside_fabric(monkeypatch):
    """AUTH-02: returns False when no notebook signals are present."""
    import sys
    monkeypatch.delenv("FABRIC_NOTEBOOK_ID", raising=False)
    monkeypatch.delenv("FABRIC_WORKSPACE_ID", raising=False)
    monkeypatch.delitem(sys.modules, "ipykernel", raising=False)
    monkeypatch.delitem(sys.modules, "notebookutils", raising=False)
    assert detect_notebook_environment() is False


def test_auth02_fabric_environment_error_message():
    """FabricEnvironmentError has an informative message with --mock guidance."""
    err = FabricEnvironmentError()
    msg = str(err)
    assert "--mock" in msg
    assert "Fabric" in msg


# ---------------------------------------------------------------------------
# EXT-01: Extraction via mocked SemanticLinkExtractor
# ---------------------------------------------------------------------------


def test_ext01_semantic_link_extractor_import():
    """EXT-01: SemanticLinkExtractor is importable."""
    from fabric_ai_meta.extractor.semantic_link import SemanticLinkExtractor
    assert SemanticLinkExtractor is not None


def test_ext01_mock_extractor_returns_tables_columns_measures(adventure_works_model):
    """EXT-01: Extractor returns model with tables, columns, measures, relationships."""
    model = adventure_works_model
    assert len(model.tables) > 0
    # At least one table has columns
    assert any(len(t.columns) > 0 for t in model.tables)
    # At least one table has measures
    assert any(len(t.measures) > 0 for t in model.tables)
    # Relationships exist
    assert len(model.relationships) > 0


# ---------------------------------------------------------------------------
# EXT-02: Large model handling (100+ tables, 500+ measures)
# ---------------------------------------------------------------------------


def test_ext02_large_model_classification_completes(tmp_path):
    """EXT-02: Classifier handles 100+ tables and 500+ measures without error."""
    # Build a fixture with 100 dimension tables, 5 measures each
    tables = []
    for i in range(100):
        cols = [
            ColumnMeta(
                name=f"Key{i}",
                data_type="int64",
                description=None,
                ai_description=None,
                role=ColumnRole.KEY,
                is_hidden=False,
                display_folder=None,
                format_string=None,
                sort_by_column=None,
            )
        ]
        measures = [
            MeasureMeta(
                name=f"[Measure {i}_{j}]",
                dax_expression=f"SUM(Dim{i}[Key{i}])",
                description=None,
                ai_description=None,
                category=MeasureCategory.UNKNOWN,
                display_folder=None,
                format_string=None,
            )
            for j in range(5)
        ]
        tables.append(
            TableMeta(
                name=f"Dim{i}",
                description=None,
                ai_description=None,
                table_type=TableType.UNKNOWN,
                grain=None,
                columns=cols,
                measures=measures,
            )
        )

    model = SemanticModelMeta(
        name="LargeModel",
        workspace="test",
        description=None,
        tables=tables,
        relationships=[],
    )

    # Should classify all 100 tables without error
    for table in model.tables:
        classify_table_heuristic(table, model.relationships)

    total_measures = sum(len(t.measures) for t in model.tables)
    assert total_measures == 500

    # Score the model
    score, breakdown = score_model(model)
    assert 0.0 <= score <= 1.0


# ---------------------------------------------------------------------------
# EXT-03: Sample value extraction returns empty list on error
# ---------------------------------------------------------------------------


def test_ext03_extract_sample_values_returns_empty_on_error():
    """EXT-03: _extract_sample_values returns [] when evaluate_dax raises."""
    from fabric_ai_meta.extractor.semantic_link import SemanticLinkExtractor

    extractor = object.__new__(SemanticLinkExtractor)
    extractor.workspace = "test"
    mock_fabric = MagicMock()
    mock_fabric.evaluate_dax.side_effect = RuntimeError("DAX eval failed")
    extractor._fabric = mock_fabric

    result = extractor._extract_sample_values("TestModel", "DimDate", "Date")
    assert result == []


def test_ext03_extract_sample_values_uses_topn_dax_pattern():
    """EXT-03: evaluate_dax is called with TOPN(10, DISTINCT(...)) pattern."""
    import pandas as pd

    from fabric_ai_meta.extractor.semantic_link import SemanticLinkExtractor

    extractor = object.__new__(SemanticLinkExtractor)
    extractor.workspace = "test"
    mock_fabric = MagicMock()
    mock_fabric.evaluate_dax.return_value = pd.DataFrame({"Date": ["2024-01-01", "2024-01-02"]})
    extractor._fabric = mock_fabric

    result = extractor._extract_sample_values("TestModel", "DimDate", "Date")
    assert len(result) == 2

    call_args = mock_fabric.evaluate_dax.call_args
    dax_query = call_args[0][1]
    assert "TOPN" in dax_query
    assert "DISTINCT" in dax_query
    assert "10" in dax_query


# ---------------------------------------------------------------------------
# ANA-02: Grain detection (via LLM client, mocked)
# ---------------------------------------------------------------------------


@patch("fabric_ai_meta.llm.litellm_backend.litellm.completion")
def test_ana02_detect_grain_returns_natural_language(mock_completion):
    """ANA-02: detect_grain returns a grain statement in natural language."""
    from fabric_ai_meta.llm.client import FabricLLMClient

    mock_client = MagicMock()
    mock_completion.return_value = mock_client
    mock_completion.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content=json.dumps({
            "grain": "one row per internet sales order line item",
            "confidence": 0.92,
        })))],
        usage=MagicMock(prompt_tokens=100, completion_tokens=30),
    )

    llm = FabricLLMClient(api_key="test-key", cache_enabled=False)
    table = TableMeta(
        name="FactInternetSales",
        description=None,
        ai_description=None,
        table_type=TableType.FACT,
        grain=None,
        columns=[
            ColumnMeta(
                name="SalesOrderNumber",
                data_type="string",
                description=None,
                ai_description=None,
                role=ColumnRole.KEY,
                is_hidden=False,
                display_folder=None,
                format_string=None,
                sort_by_column=None,
            )
        ],
    )
    grain, confidence = llm.detect_grain(table)
    assert isinstance(grain, str)
    assert len(grain) > 0
    assert 0.0 <= confidence <= 1.0
    assert "row" in grain.lower() or "order" in grain.lower()


# ---------------------------------------------------------------------------
# LLM-01: Cost tracking under budget
# ---------------------------------------------------------------------------


@patch("fabric_ai_meta.llm.litellm_backend.litellm.completion")
def test_llm01_cost_tracking_under_budget_does_not_raise(mock_completion):
    """LLM-01: Normal usage does not trigger CostLimitExceededError."""
    from fabric_ai_meta.llm.client import FabricLLMClient

    mock_client = MagicMock()
    mock_completion.return_value = mock_client
    mock_completion.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content="response"))],
        usage=MagicMock(prompt_tokens=500, completion_tokens=200),
    )

    client = FabricLLMClient(
        api_key="test-key",
        cache_enabled=False,
        max_cost_usd=1.00,  # $1 budget, 700 tokens is well under $0.20
    )
    result = client.call("analyze this model")
    assert result == "response"


@patch("fabric_ai_meta.llm.litellm_backend.litellm.completion")
def test_llm01_token_usage_tracked_per_call(mock_completion):
    """LLM-01: Cumulative token usage is tracked across calls."""
    from fabric_ai_meta.llm.client import FabricLLMClient

    mock_client = MagicMock()
    mock_completion.return_value = mock_client
    mock_completion.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content="ok"))],
        usage=MagicMock(prompt_tokens=100, completion_tokens=50),
    )

    client = FabricLLMClient(api_key="test-key", cache_enabled=False)
    client.call("call 1")
    client.call("call 2")
    client.call("call 3")

    assert client._total_input_tokens == 300
    assert client._total_output_tokens == 150


# ---------------------------------------------------------------------------
# LLM-02: Cache avoids redundant API calls
# ---------------------------------------------------------------------------


@patch("fabric_ai_meta.llm.litellm_backend.litellm.completion")
def test_llm02_cache_prevents_redundant_api_calls(mock_completion, tmp_path):
    """LLM-02: Identical prompts use cached response, no extra API call."""
    from fabric_ai_meta.llm.client import FabricLLMClient

    mock_client = MagicMock()
    mock_completion.return_value = mock_client
    mock_completion.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content="cached"))],
        usage=MagicMock(prompt_tokens=50, completion_tokens=20),
    )

    client = FabricLLMClient(
        api_key="test-key",
        cache_enabled=True,
        cache_dir=str(tmp_path / "cache"),
    )
    r1 = client.call("same prompt")
    r2 = client.call("same prompt")
    r3 = client.call("same prompt")

    assert r1 == r2 == r3 == "cached"
    assert mock_completion.call_count == 1


# ---------------------------------------------------------------------------
# DESC-01: Generate missing descriptions via LLM
# ---------------------------------------------------------------------------


@patch("fabric_ai_meta.llm.litellm_backend.litellm.completion")
def test_desc01_generate_description_for_column(mock_completion):
    """DESC-01: generate_description produces a non-empty description for a column."""
    from fabric_ai_meta.llm.client import FabricLLMClient

    mock_client = MagicMock()
    mock_completion.return_value = mock_client
    mock_completion.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content=json.dumps({
            "description": "The unique identifier for each customer record"
        })))],
        usage=MagicMock(prompt_tokens=80, completion_tokens=25),
    )

    client = FabricLLMClient(api_key="test-key", cache_enabled=False)
    desc = client.generate_description(
        obj_type="column",
        name="CustomerKey",
        context={
            "parent_table": "DimCustomer",
            "data_type": "int64",
            "sibling_descriptions": "FirstName: Customer first name",
        },
    )
    assert isinstance(desc, str)
    assert len(desc) > 0


@patch("fabric_ai_meta.llm.litellm_backend.litellm.completion")
def test_desc01_generate_description_for_measure(mock_completion):
    """DESC-01: generate_description works for a measure object type."""
    from fabric_ai_meta.llm.client import FabricLLMClient

    mock_client = MagicMock()
    mock_completion.return_value = mock_client
    mock_completion.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content=json.dumps({
            "description": "Total revenue from all internet sales channels"
        })))],
        usage=MagicMock(prompt_tokens=90, completion_tokens=20),
    )

    client = FabricLLMClient(api_key="test-key", cache_enabled=False)
    desc = client.generate_description(
        obj_type="measure",
        name="Internet Total Sales",
        context={
            "parent_table": "FactInternetSales",
            "dax": "SUM(FactInternetSales[SalesAmount])",
            "sibling_descriptions": "",
        },
    )
    assert isinstance(desc, str)
    assert len(desc) <= 150  # spec: max 150 chars


# ---------------------------------------------------------------------------
# CLI-03: export commands produce outputs (via analyze --mock)
# ---------------------------------------------------------------------------


def test_cli03_analyze_mock_produces_langchain_export(tmp_path):
    """CLI-03: analyze --mock writes langchain-tool.json with required keys."""
    runner = CliRunner()
    runner.invoke(main, [
        "analyze", "Adventure Works",
        "--workspace", "test",
        "--output", str(tmp_path),
        "--mock",
    ])
    path = tmp_path / "adventure-works" / "langchain-tool.json"
    assert path.exists()
    data = json.loads(path.read_text())
    assert "name" in data
    assert "description" in data
    assert "parameters" in data
    assert "metadata" in data


def test_cli03_analyze_mock_produces_openai_export(tmp_path):
    """CLI-03: analyze --mock writes openai-function.json with required keys."""
    runner = CliRunner()
    runner.invoke(main, [
        "analyze", "Adventure Works",
        "--workspace", "test",
        "--output", str(tmp_path),
        "--mock",
    ])
    path = tmp_path / "adventure-works" / "openai-function.json"
    assert path.exists()
    data = json.loads(path.read_text())
    assert data.get("type") == "function"
    assert "question" in data["function"]["parameters"]["required"]


def test_cli03_analyze_mock_produces_semantic_kernel_export(tmp_path):
    """CLI-03: analyze --mock writes semantic-kernel-plugin.json with required keys."""
    runner = CliRunner()
    runner.invoke(main, [
        "analyze", "Adventure Works",
        "--workspace", "test",
        "--output", str(tmp_path),
        "--mock",
    ])
    path = tmp_path / "adventure-works" / "semantic-kernel-plugin.json"
    assert path.exists()
    data = json.loads(path.read_text())
    assert data.get("schema_version") == "v1"
    assert isinstance(data.get("functions"), list)


def test_cli03_export_commands_require_fabric_runtime():
    """CLI-03: export subcommands raise FabricEnvironmentError outside Fabric."""
    runner = CliRunner()
    for cmd in ["langchain", "openai", "semantic-kernel"]:
        result = runner.invoke(main, ["export", cmd, "SomeModel", "--workspace", "test"])
        # Should either raise FabricEnvironmentError (exit 1) or show error in output
        assert result.exit_code != 0 or "Fabric" in result.output


# ---------------------------------------------------------------------------
# BULK-01: Scan command with --mock produces workspace-summary.json
# ---------------------------------------------------------------------------


def test_bulk01_scan_mock_produces_workspace_summary(tmp_path):
    """BULK-01: scan --mock writes workspace-summary.json with model entries."""
    runner = CliRunner()
    result = runner.invoke(main, [
        "scan",
        "--workspace", "test",
        "--output", str(tmp_path),
        "--mock",
    ])
    assert result.exit_code == 0, f"scan failed: {result.output}"
    summary_path = tmp_path / "workspace-summary.json"
    assert summary_path.exists(), "workspace-summary.json not written"
    data = json.loads(summary_path.read_text())
    assert "workspace" in data
    assert "models" in data
    assert isinstance(data["models"], list)
    assert len(data["models"]) > 0


def test_bulk01_scan_mock_each_model_has_score(tmp_path):
    """BULK-01: Each model entry in workspace-summary.json has a score field."""
    runner = CliRunner()
    runner.invoke(main, [
        "scan",
        "--workspace", "test",
        "--output", str(tmp_path),
        "--mock",
    ])
    data = json.loads((tmp_path / "workspace-summary.json").read_text())
    for entry in data["models"]:
        assert "name" in entry
        assert "ai_readiness_score" in entry
        assert "errors" in entry


# ---------------------------------------------------------------------------
# GOV-01/02/03: Governance (quick integration check using both fixtures)
# ---------------------------------------------------------------------------


def test_gov01_02_03_governance_report_via_library(adventure_works_model, contoso_model):
    """GOV-01/02/03: generate_governance_report produces a complete report dict."""
    from fabric_ai_meta.analyzer.governance import generate_governance_report

    report = generate_governance_report([adventure_works_model, contoso_model])
    assert "summary" in report                               # GOV-03
    assert "naming_inconsistencies" in report                # GOV-01
    assert "duplicate_measures" in report                    # GOV-02
    assert "score_ranking" in report                         # GOV-03
    assert report["summary"]["model_count"] == 2
    assert isinstance(report["naming_inconsistencies"], list)
    assert isinstance(report["duplicate_measures"], list)
    assert isinstance(report["score_ranking"], list)


def test_gov_governance_cli_requires_fabric_runtime():
    """governance CLI command raises FabricEnvironmentError outside Fabric notebook."""
    runner = CliRunner()
    result = runner.invoke(main, ["governance", "--workspace", "test"])
    # Outside Fabric, the command must fail (FabricEnvironmentError)
    assert result.exit_code != 0


# ---------------------------------------------------------------------------
# Prep for AI (PREP-01/02/03) integration via CLI
# ---------------------------------------------------------------------------


def test_prep_config_json_serializable_end_to_end(adventure_works_model):
    """PREP-01/02/03: PrepForAIConfig from adventure_works is JSON-serializable."""
    from fabric_ai_meta.generator.prep_for_ai import generate_prep_for_ai

    llm = MagicMock()
    llm.call.return_value = "Use [Internet Total Sales] for revenue questions. Filter by DimDate for time analysis."
    llm.generate_description.return_value = "Auto-generated description."

    config = generate_prep_for_ai(adventure_works_model, llm)
    raw = json.dumps(dataclasses.asdict(config))
    parsed = json.loads(raw)

    assert len(parsed["included_tables"]) > 0  # PREP-01
    assert len(parsed["ai_instructions"]) > 0  # PREP-02
    assert isinstance(parsed["verified_answers"], list)  # PREP-03


# ---------------------------------------------------------------------------
# Named pipeline integration tests (spec requirement: test_full_pipeline_*)
# ---------------------------------------------------------------------------


def test_full_pipeline_complete_e2e(adventure_works_model, tmp_path):
    """Integrated end-to-end: extract, classify, score, generate all exports, write schema."""
    from fabric_ai_meta.analyzer.classifier import (
        classify_column_role,
        classify_measure_heuristic,
        classify_table_heuristic,
    )
    from fabric_ai_meta.analyzer.scorer import score_model
    from fabric_ai_meta.generator.export_langchain import to_langchain_tool_definition
    from fabric_ai_meta.generator.export_openai import to_openai_function
    from fabric_ai_meta.generator.export_semantic_kernel import to_semantic_kernel_plugin
    from fabric_ai_meta.generator.schema import generate_ai_ready_schema, write_schema_to_file

    model = adventure_works_model
    for tbl in model.tables:
        tbl.table_type = classify_table_heuristic(tbl, model.relationships)
        for c in tbl.columns:
            c.role = classify_column_role(c, tbl, model.relationships)
        for ms in tbl.measures:
            ms.category = classify_measure_heuristic(ms)

    score, breakdown = score_model(model)
    model.ai_readiness_score = score
    model.scoring_breakdown = breakdown

    assert 0.0 <= score <= 1.0
    assert breakdown

    schema = generate_ai_ready_schema(model)
    assert "$schema" in schema

    lc = to_langchain_tool_definition(model)
    oa = to_openai_function(model)
    sk = to_semantic_kernel_plugin(model)

    for export in (lc, oa, sk):
        assert json.loads(json.dumps(export))  # must be JSON-serializable

    out_path = write_schema_to_file(model, str(tmp_path / "ai-ready-schema.json"))
    assert os.path.exists(out_path)


def test_full_pipeline_prep_for_ai_cli(adventure_works_model, tmp_path):
    """Prep-for-AI config + verified answers (without LLM), via CLI."""
    runner = CliRunner()
    result = runner.invoke(main, [
        "export", "prep-for-ai", "Adventure Works",
        "--workspace", "test",
        "--output", str(tmp_path),
        "--mock",
    ])
    assert result.exit_code == 0, f"export prep-for-ai failed: {result.output}"

    config_path = tmp_path / "adventure-works" / "prep-for-ai-config.json"
    assert config_path.exists()
    data = json.loads(config_path.read_text(encoding="utf-8"))

    assert len(data["included_tables"]) > 0         # PREP-01
    assert len(data["ai_instructions"]) > 0         # PREP-02
    assert isinstance(data["verified_answers"], list)  # PREP-03
    assert len(data["verified_answers"]) > 0


def test_full_pipeline_scan(tmp_path):
    """BULK-01: Bulk scan across fixtures → workspace-summary.json."""
    runner = CliRunner()
    result = runner.invoke(main, [
        "scan",
        "--workspace", "test",
        "--output", str(tmp_path),
        "--mock",
    ])
    assert result.exit_code == 0, f"scan failed: {result.output}"

    summary_path = tmp_path / "workspace-summary.json"
    assert summary_path.exists()
    data = json.loads(summary_path.read_text())

    assert data["model_count"] >= 2
    assert "score_ranking" in data
    assert isinstance(data["score_ranking"], list)
    scores = [m["ai_readiness_score"] for m in data["models"] if m["ai_readiness_score"] is not None]
    assert len(scores) > 0


def test_full_pipeline_governance(tmp_path):
    """GOV-01/02/03: Governance analysis → governance-report.json."""
    runner = CliRunner()
    report_path = str(tmp_path / "governance-report.json")
    result = runner.invoke(main, [
        "governance",
        "--workspace", "test",
        "--mock",
        "--report", report_path,
    ])
    assert result.exit_code == 0, f"governance failed: {result.output}"

    assert os.path.exists(report_path)
    data = json.loads(open(report_path, encoding="utf-8").read())

    assert "$schema" in data
    assert "summary" in data
    assert "score_ranking" in data
    assert "naming_inconsistencies" in data
    assert "duplicate_measures" in data
    assert "recommendations" in data
    assert data["summary"]["model_count"] >= 2


# ---------------------------------------------------------------------------
# Public API exports
# ---------------------------------------------------------------------------


class TestPublicAPIExports:
    """Verify all public names are importable from fabric_ai_meta directly."""

    def test_all_public_names_importable(self):
        import fabric_ai_meta

        for name in fabric_ai_meta.__all__:
            assert hasattr(fabric_ai_meta, name), f"{name} listed in __all__ but not importable"

    def test_all_matches_actual_exports(self):
        import fabric_ai_meta

        exported_attrs = {
            name for name in dir(fabric_ai_meta)
            if not name.startswith("_") or name == "__version__"
        }
        all_set = set(fabric_ai_meta.__all__)
        # Every name in __all__ must exist as an attribute
        missing = all_set - exported_attrs
        assert not missing, f"Names in __all__ but not exported: {missing}"

    def test_core_imports_work(self):
        from fabric_ai_meta import (
            __version__,
            generate_ai_ready_schema,
            score_model,
            to_openai_function,
        )

        assert __version__ == "1.5.0"
        assert callable(score_model)
        assert callable(generate_ai_ready_schema)
        assert callable(to_openai_function)

    def test_all_count(self):
        import fabric_ai_meta

        # 1 version + 10 data model + 5 copilot + 2 extractors + 8 analysis
        # + 6 generators + 4 exporter plugin contract + 4 writeback descriptions
        # + 5 writeback copilot (v1.5.0) = 45
        assert len(fabric_ai_meta.__all__) == 45


# ---------------------------------------------------------------------------
# JSON Schema validation
# ---------------------------------------------------------------------------

SCHEMAS_DIR = os.path.join(os.path.dirname(__file__), "..", "schemas")


class TestSchemaValidation:
    """Validate that generated outputs conform to their JSON Schema files."""

    def test_ai_ready_schema_validates(self, adventure_works_model):
        """generate_ai_ready_schema output validates against schemas/v1.json."""
        import jsonschema

        output = generate_ai_ready_schema(adventure_works_model)
        with open(os.path.join(SCHEMAS_DIR, "v1.json")) as f:
            schema = json.load(f)
        jsonschema.validate(output, schema)

    def test_ai_ready_schema_validates_enterprise(self, enterprise_sales_model):
        """AI-ready schema validates for the larger enterprise fixture."""
        import jsonschema

        output = generate_ai_ready_schema(enterprise_sales_model)
        with open(os.path.join(SCHEMAS_DIR, "v1.json")) as f:
            schema = json.load(f)
        jsonschema.validate(output, schema)

    def test_workspace_summary_validates(self, tmp_path):
        """scan --mock workspace-summary.json validates against its schema."""
        import jsonschema

        runner = CliRunner()
        runner.invoke(main, [
            "scan", "--workspace", "test", "--output", str(tmp_path), "--mock",
        ])
        with open(tmp_path / "workspace-summary.json") as f:
            output = json.load(f)
        with open(os.path.join(SCHEMAS_DIR, "workspace-summary", "v1.json")) as f:
            schema = json.load(f)
        jsonschema.validate(output, schema)

    def test_governance_report_validates(self, tmp_path):
        """governance --mock report validates against its schema."""
        import jsonschema

        runner = CliRunner()
        report_path = str(tmp_path / "gov.json")
        runner.invoke(main, [
            "governance", "--workspace", "test", "--mock", "--report", report_path,
        ])
        with open(report_path) as f:
            output = json.load(f)
        with open(os.path.join(SCHEMAS_DIR, "governance-report", "v1.json")) as f:
            schema = json.load(f)
        jsonschema.validate(output, schema)

    def test_prep_for_ai_validates(self, tmp_path):
        """export prep-for-ai --mock output validates against its schema."""
        import jsonschema

        runner = CliRunner()
        runner.invoke(main, [
            "export", "prep-for-ai", "Adventure Works",
            "--workspace", "test", "--output", str(tmp_path), "--mock",
        ])
        output_path = tmp_path / "adventure-works" / "prep-for-ai-config.json"
        with open(output_path) as f:
            output = json.load(f)
        with open(os.path.join(SCHEMAS_DIR, "prep-for-ai", "v1.json")) as f:
            schema = json.load(f)
        jsonschema.validate(output, schema)

    def test_schema_files_are_valid_json_schema(self):
        """All schema files are syntactically valid JSON Schema Draft 2020-12."""
        schema_paths = [
            os.path.join(SCHEMAS_DIR, "v1.json"),
            os.path.join(SCHEMAS_DIR, "workspace-summary", "v1.json"),
            os.path.join(SCHEMAS_DIR, "governance-report", "v1.json"),
            os.path.join(SCHEMAS_DIR, "prep-for-ai", "v1.json"),
        ]
        for path in schema_paths:
            with open(path) as f:
                schema = json.load(f)
            assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
            assert "$id" in schema

    def test_schema_ids_match_source_references(self):
        """$id in each schema matches the URL used in source code output."""
        expected = {
            os.path.join(SCHEMAS_DIR, "v1.json"): "https://raw.githubusercontent.com/psistla/fabric-ai-meta/master/schemas/v1.json",
            os.path.join(SCHEMAS_DIR, "workspace-summary", "v1.json"): "https://raw.githubusercontent.com/psistla/fabric-ai-meta/master/schemas/workspace-summary/v1.json",
            os.path.join(SCHEMAS_DIR, "governance-report", "v1.json"): "https://raw.githubusercontent.com/psistla/fabric-ai-meta/master/schemas/governance-report/v1.json",
            os.path.join(SCHEMAS_DIR, "prep-for-ai", "v1.json"): "https://raw.githubusercontent.com/psistla/fabric-ai-meta/master/schemas/prep-for-ai/v1.json",
        }
        for path, expected_id in expected.items():
            with open(path) as f:
                schema = json.load(f)
            assert schema["$id"] == expected_id, f"{path}: $id mismatch"


# ---------------------------------------------------------------------------
# WIRE-02: _export_single classifies before writing
# ---------------------------------------------------------------------------

def test_export_single_classifies_before_writing(monkeypatch):
    """WIRE-02: _export_single extracted and wrote without ever classifying.

    Real Fabric mode emitted category "unknown" for every measure. Mock fixtures
    hid it by pre-baking category, so this builds an UNKNOWN model, drives the
    real export path, and asserts the model the exporter received was classified.
    """
    measure = MeasureMeta(
        name="Total Sales",
        dax_expression="SUM(Sales[Amount])",
        description=None, ai_description=None,
        category=MeasureCategory.UNKNOWN,   # as a real extractor leaves it
        display_folder=None, format_string=None,
    )
    table = TableMeta(
        name="Sales", description=None, ai_description=None,
        table_type=TableType.UNKNOWN, grain=None, measures=[measure],
    )
    model = SemanticModelMeta(name="M", workspace="W", description=None, tables=[table])

    class _StubExtractor:
        def extract(self, model_name, workspace, *, with_copilot=False):
            return model

        def list_models(self, workspace):
            return ["M"]

    monkeypatch.setattr(
        "fabric_ai_meta.extractor.factory._build_extractor",
        lambda **kw: _StubExtractor(),
    )

    # Drive the real export path.
    from fabric_ai_meta.cli import _export_single
    from fabric_ai_meta.generator.builtin_exporters import BUILTIN_EXPORTERS

    exporter_cls = next(e for e in BUILTIN_EXPORTERS if e.name == "langchain")
    _export_single("M", "W", exporter_cls(), mock=True)

    assert measure.category != MeasureCategory.UNKNOWN, (
        "_export_single wrote without classifying; measure category stayed UNKNOWN"
    )
