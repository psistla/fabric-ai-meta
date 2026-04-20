"""Tests for the description writeback module."""

import json

import pytest
from click.testing import CliRunner

from fabric_ai_meta.cli import main
from fabric_ai_meta.writeback.description_writer import (
    DescriptionWriter,
    MockWriter,
    SemanticLinkWriter,
    WritebackResult,
)

SAMPLE_DESCRIPTIONS = {
    "Sales": {
        "__table__": "Fact table of sales transactions.",
        "OrderID": "Unique identifier for each sales order.",
        "Amount": "Net sale amount in USD.",
    },
    "Customer": {
        "__table__": "Dimension of customer accounts.",
        "CustomerKey": "Surrogate key for the customer.",
    },
}


@pytest.fixture
def runner():
    return CliRunner()


def _write_config(tmp_path, descriptions):
    config = {
        "model_name": "TestModel",
        "included_tables": list(descriptions.keys()),
        "excluded_columns": {},
        "ai_instructions": "Test instructions.",
        "verified_answers": [],
        "generated_descriptions": descriptions,
    }
    path = tmp_path / "prep-for-ai-config.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    return path


def test_mockwriter_returns_correct_counts():
    writer = MockWriter()
    result = writer.apply_descriptions(
        model_name="TestModel",
        workspace="test-ws",
        descriptions=SAMPLE_DESCRIPTIONS,
    )
    assert result.tables_updated == 2
    assert result.columns_updated == 3
    assert result.measures_updated == 0
    assert result.total_changes == 5


def test_mockwriter_dry_run_always_true():
    writer = MockWriter()
    result_default = writer.apply_descriptions("M", "ws", SAMPLE_DESCRIPTIONS)
    result_explicit = writer.apply_descriptions(
        "M", "ws", SAMPLE_DESCRIPTIONS, dry_run=False
    )
    assert result_default.dry_run is True
    assert result_explicit.dry_run is True


def test_writeback_result_is_json_serializable():
    writer = MockWriter()
    result = writer.apply_descriptions("M", "ws", SAMPLE_DESCRIPTIONS)
    payload = json.dumps(result.to_dict())
    parsed = json.loads(payload)
    assert parsed["total_changes"] == 5
    assert isinstance(parsed["changes"], list)


def test_changes_have_correct_structure():
    writer = MockWriter()
    result = writer.apply_descriptions("M", "ws", SAMPLE_DESCRIPTIONS)
    required_keys = {"type", "table", "object", "old_description", "new_description"}
    for change in result.changes:
        assert required_keys.issubset(change.keys())
        assert change["type"] in {"table", "column", "measure"}

    table_changes = [c for c in result.changes if c["type"] == "table"]
    column_changes = [c for c in result.changes if c["type"] == "column"]
    assert len(table_changes) == 2
    assert len(column_changes) == 3
    assert {c["table"] for c in table_changes} == {"Sales", "Customer"}


def test_empty_descriptions_zero_changes():
    writer = MockWriter()
    result = writer.apply_descriptions("M", "ws", {})
    assert result.total_changes == 0
    assert result.tables_updated == 0
    assert result.columns_updated == 0
    assert result.changes == []
    assert result.errors == []


def test_descriptionwriter_is_abstract():
    with pytest.raises(TypeError):
        DescriptionWriter()  # type: ignore[abstract]


def test_semanticlinkwriter_subclass():
    assert issubclass(SemanticLinkWriter, DescriptionWriter)
    assert issubclass(MockWriter, DescriptionWriter)


def test_cli_apply_descriptions_mock_exits_zero(runner, tmp_path):
    config_path = _write_config(tmp_path, SAMPLE_DESCRIPTIONS)
    result = runner.invoke(main, [
        "apply-descriptions", str(config_path),
        "--workspace", "test-ws",
        "--mock",
    ])
    assert result.exit_code == 0, result.output
    assert "tables=2" in result.output
    assert "columns=3" in result.output


def test_cli_apply_descriptions_mock_dry_run_label(runner, tmp_path):
    config_path = _write_config(tmp_path, SAMPLE_DESCRIPTIONS)
    result = runner.invoke(main, [
        "apply-descriptions", str(config_path),
        "--workspace", "test-ws",
        "--mock",
        "--dry-run",
    ])
    assert result.exit_code == 0, result.output
    assert "DRY RUN" in result.output


def test_cli_apply_descriptions_without_mock_requires_fabric(runner, tmp_path):
    config_path = _write_config(tmp_path, SAMPLE_DESCRIPTIONS)
    result = runner.invoke(main, [
        "apply-descriptions", str(config_path),
        "--workspace", "test-ws",
    ])
    assert result.exit_code != 0
    assert "Fabric" in result.output


def test_cli_apply_descriptions_help(runner):
    result = runner.invoke(main, ["apply-descriptions", "--help"])
    assert result.exit_code == 0
    assert "config_path" in result.output.lower() or "CONFIG_PATH" in result.output


def test_writeback_result_default_field_factories_distinct():
    a = WritebackResult()
    b = WritebackResult()
    a.changes.append({"x": 1})
    a.errors.append("boom")
    assert b.changes == []
    assert b.errors == []
