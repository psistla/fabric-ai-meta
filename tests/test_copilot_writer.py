"""Tests for the Copilot writeback module (S7-01, S7-02).

Covers the abstract CopilotWriter contract, the in-memory MockCopilotWriter,
the CopilotWritebackResult dataclass, the envelope splice helpers, and the
real-Fabric SemanticLinkCopilotWriter (network mocked).
"""

import base64
import json
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from fabric_ai_meta.auth.entra import FabricEnvironmentError
from fabric_ai_meta.cli import main as cli_main
from fabric_ai_meta.models.copilot import (
    AIDataSchema,
    AIInstructions,
    CopilotBundle,
    CopilotSettings,
    CopilotVersion,
    ExamplePrompts,
    VerifiedAnswer,
)
from fabric_ai_meta.writeback.copilot_writer import (
    CopilotWritebackResult,
    CopilotWriter,
    MockCopilotWriter,
    SemanticLinkCopilotWriter,
    _bundle_to_copilot_parts,
    splice_copilot_into_envelope,
)


def _b64(text: str) -> str:
    return base64.b64encode(text.encode("utf-8")).decode("ascii")


def _envelope(parts: list[dict]) -> dict:
    return {"definition": {"parts": parts}}


def _full_bundle() -> CopilotBundle:
    md = "# Instructions\n- Prefer DISTINCTCOUNT.\n"
    return CopilotBundle(
        ai_instructions=AIInstructions(markdown=md, raw_bytes=md.encode("utf-8")),
        verified_answers=[
            VerifiedAnswer(
                filename="q1.json",
                question="What were sales?",
                raw={"question": "What were sales?", "dax": "EVALUATE 1"},
            ),
            VerifiedAnswer(
                filename="q2.json",
                question="Top customers?",
                raw={"question": "Top customers?", "dax": "EVALUATE 2"},
            ),
        ],
        ai_data_schema=AIDataSchema(raw={"tables": [{"name": "Sales"}]}),
        example_prompts=ExamplePrompts(prompts=["A", "B"], raw=["A", "B"]),
        settings=CopilotSettings(raw={"enabled": True}),
        version=CopilotVersion(raw={"version": "1.0"}),
    )


def test_mock_copilot_writer_returns_correct_counts():
    writer = MockCopilotWriter()
    bundle = _full_bundle()
    result = writer.apply_copilot(
        bundle=bundle, model_name="TestModel", workspace="ws"
    )
    assert result.ai_instructions_updated is True
    assert result.verified_answers_written == 2
    assert result.ai_data_schema_updated is True
    assert result.example_prompts_updated is True
    assert result.settings_updated is True
    assert result.version_updated is True
    # 1 instructions + 2 verified answers + 1 schema + 1 prompts + 1 settings + 1 version
    assert result.total_changes == 7


def test_mock_copilot_writer_dry_run_always_true():
    writer = MockCopilotWriter()
    bundle = _full_bundle()
    r_default = writer.apply_copilot(bundle, "M", "ws")
    r_explicit = writer.apply_copilot(bundle, "M", "ws", dry_run=False)
    assert r_default.dry_run is True
    assert r_explicit.dry_run is True


def test_copilot_writeback_result_is_json_serializable():
    writer = MockCopilotWriter()
    bundle = _full_bundle()
    result = writer.apply_copilot(bundle, "M", "ws")
    payload = json.dumps(result.to_dict())
    parsed = json.loads(payload)
    assert parsed["total_changes"] == 7
    assert isinstance(parsed["changes"], list)


def test_changes_have_correct_structure():
    writer = MockCopilotWriter()
    bundle = _full_bundle()
    result = writer.apply_copilot(bundle, "M", "ws")
    required_keys = {"path", "operation", "primitive"}
    for change in result.changes:
        assert required_keys.issubset(change.keys())
        # Mock and SemanticLink writers share the same vocabulary.
        assert change["operation"] in {"create", "update", "delete"}
        assert change["path"].startswith("Copilot/")

    # Verified answer changes name the actual filenames.
    va_paths = {c["path"] for c in result.changes if c["primitive"] == "verified_answers"}
    assert va_paths == {
        "Copilot/VerifiedAnswers/q1.json",
        "Copilot/VerifiedAnswers/q2.json",
    }
    # AI Instructions, schema, prompts, settings, version each contribute exactly one change.
    for primitive, expected_path in [
        ("ai_instructions", "Copilot/Instructions/instructions.md"),
        ("ai_data_schema", "Copilot/schema.json"),
        ("example_prompts", "Copilot/examplePrompts.json"),
        ("copilot_settings", "Copilot/settings.json"),
        ("copilot_version", "Copilot/version.json"),
    ]:
        rows = [c for c in result.changes if c["primitive"] == primitive]
        assert len(rows) == 1
        assert rows[0]["path"] == expected_path


def test_empty_bundle_zero_changes():
    writer = MockCopilotWriter()
    result = writer.apply_copilot(CopilotBundle(), "M", "ws")
    assert result.total_changes == 0
    assert result.ai_instructions_updated is False
    assert result.verified_answers_written == 0
    assert result.ai_data_schema_updated is False
    assert result.example_prompts_updated is False
    assert result.settings_updated is False
    assert result.version_updated is False
    assert result.changes == []
    assert result.errors == []


def test_bundle_with_only_instructions():
    writer = MockCopilotWriter()
    md = "# Only instructions"
    bundle = CopilotBundle(
        ai_instructions=AIInstructions(markdown=md, raw_bytes=md.encode("utf-8"))
    )
    result = writer.apply_copilot(bundle, "M", "ws")
    assert result.ai_instructions_updated is True
    assert result.total_changes == 1
    assert result.changes[0]["path"] == "Copilot/Instructions/instructions.md"
    assert result.changes[0]["primitive"] == "ai_instructions"
    assert result.changes[0]["operation"] == "create"


def test_copilot_writer_is_abstract():
    with pytest.raises(TypeError):
        CopilotWriter()  # type: ignore[abstract]


def test_mock_copilot_writer_is_subclass():
    assert issubclass(MockCopilotWriter, CopilotWriter)


def test_writeback_result_default_field_factories_distinct():
    a = CopilotWritebackResult()
    b = CopilotWritebackResult()
    a.changes.append({"x": 1})
    a.errors.append("boom")
    assert b.changes == []
    assert b.errors == []


# ---------------------------------------------------------------------------
# _bundle_to_copilot_parts
# ---------------------------------------------------------------------------

def test_bundle_to_parts_emits_all_primitive_paths():
    parts = _bundle_to_copilot_parts(_full_bundle())
    paths = sorted(p["path"] for p in parts)
    assert paths == sorted([
        "Copilot/Instructions/instructions.md",
        "Copilot/VerifiedAnswers/q1.json",
        "Copilot/VerifiedAnswers/q2.json",
        "Copilot/schema.json",
        "Copilot/examplePrompts.json",
        "Copilot/settings.json",
        "Copilot/version.json",
    ])
    for p in parts:
        assert p["payloadType"] == "InlineBase64"
        assert p["payload"]


def test_bundle_to_parts_instructions_uses_raw_bytes():
    md = "# Hello\n"
    bundle = CopilotBundle(
        ai_instructions=AIInstructions(markdown="ignored", raw_bytes=md.encode("utf-8"))
    )
    parts = _bundle_to_copilot_parts(bundle)
    assert len(parts) == 1
    decoded = base64.b64decode(parts[0]["payload"]).decode("utf-8")
    assert decoded == md  # raw_bytes wins over markdown for byte-perfect round-trip


def test_bundle_to_parts_empty_bundle_yields_empty_list():
    assert _bundle_to_copilot_parts(CopilotBundle()) == []


def test_bundle_to_parts_rejects_path_traversal_in_va_filename():
    """A VerifiedAnswer constructed programmatically with `../` is rejected."""
    bundle = CopilotBundle(verified_answers=[
        VerifiedAnswer(filename="../etc/passwd", question=None, raw={}),
    ])
    with pytest.raises(ValueError, match="Unsafe"):
        _bundle_to_copilot_parts(bundle)


def test_bundle_to_parts_rejects_va_filename_with_slash():
    bundle = CopilotBundle(verified_answers=[
        VerifiedAnswer(filename="subdir/answer.json", question=None, raw={}),
    ])
    with pytest.raises(ValueError, match="Unsafe"):
        _bundle_to_copilot_parts(bundle)


def test_splice_drops_existing_parts_with_empty_path():
    """A part with empty/None path in `getDefinition` output is filtered out."""
    existing = _envelope([
        {"path": "definition/model.tmdl", "payload": _b64("m"),
         "payloadType": "InlineBase64"},
        {"path": "", "payload": _b64("junk"), "payloadType": "InlineBase64"},
        {"path": None, "payload": _b64("junk"), "payloadType": "InlineBase64"},
    ])
    new_env, _changes = splice_copilot_into_envelope(existing, CopilotBundle())
    paths = [p["path"] for p in new_env["definition"]["parts"]]
    assert paths == ["definition/model.tmdl"]


# ---------------------------------------------------------------------------
# splice_copilot_into_envelope
# ---------------------------------------------------------------------------

def test_splice_preserves_non_copilot_parts():
    existing = _envelope([
        {"path": "definition/model.tmdl", "payload": _b64("model"),
         "payloadType": "InlineBase64"},
        {"path": "definition/tables/Sales.tmdl", "payload": _b64("sales"),
         "payloadType": "InlineBase64"},
    ])
    new_env, changes = splice_copilot_into_envelope(existing, _full_bundle())
    tmdl_paths = [p["path"] for p in new_env["definition"]["parts"]
                  if p["path"].startswith("definition/")]
    assert tmdl_paths == ["definition/model.tmdl", "definition/tables/Sales.tmdl"]


def test_splice_replaces_old_copilot_parts():
    existing = _envelope([
        {"path": "definition/model.tmdl", "payload": _b64("m"),
         "payloadType": "InlineBase64"},
        {"path": "Copilot/Instructions/instructions.md", "payload": _b64("OLD"),
         "payloadType": "InlineBase64"},
        {"path": "Copilot/VerifiedAnswers/stale.json", "payload": _b64('{"q":"x"}'),
         "payloadType": "InlineBase64"},
    ])
    new_env, changes = splice_copilot_into_envelope(existing, _full_bundle())
    copilot_paths = sorted(p["path"] for p in new_env["definition"]["parts"]
                           if p["path"].startswith("Copilot/"))
    # The stale VerifiedAnswer must be gone; only the bundle's primitives remain.
    assert "Copilot/VerifiedAnswers/stale.json" not in copilot_paths
    assert "Copilot/Instructions/instructions.md" in copilot_paths
    instr_part = next(p for p in new_env["definition"]["parts"]
                      if p["path"] == "Copilot/Instructions/instructions.md")
    assert base64.b64decode(instr_part["payload"]).decode("utf-8").startswith("# Instructions")


def test_splice_with_empty_bundle_removes_all_existing_copilot():
    existing = _envelope([
        {"path": "definition/model.tmdl", "payload": _b64("m"),
         "payloadType": "InlineBase64"},
        {"path": "Copilot/Instructions/instructions.md", "payload": _b64("X"),
         "payloadType": "InlineBase64"},
        {"path": "Copilot/settings.json", "payload": _b64("{}"),
         "payloadType": "InlineBase64"},
    ])
    new_env, changes = splice_copilot_into_envelope(existing, CopilotBundle())
    remaining = [p["path"] for p in new_env["definition"]["parts"]]
    assert remaining == ["definition/model.tmdl"]
    # Two deletes recorded (one per old Copilot path).
    delete_ops = [c for c in changes if c["operation"] == "delete"]
    assert {c["path"] for c in delete_ops} == {
        "Copilot/Instructions/instructions.md",
        "Copilot/settings.json",
    }


def test_splice_diff_categorizes_create_update_delete():
    existing = _envelope([
        {"path": "Copilot/Instructions/instructions.md", "payload": _b64("OLD"),
         "payloadType": "InlineBase64"},
        {"path": "Copilot/VerifiedAnswers/keep.json", "payload": _b64("{}"),
         "payloadType": "InlineBase64"},
        {"path": "Copilot/VerifiedAnswers/drop.json", "payload": _b64("{}"),
         "payloadType": "InlineBase64"},
    ])
    bundle = CopilotBundle(
        ai_instructions=AIInstructions(markdown="NEW", raw_bytes=b"NEW"),
        verified_answers=[
            VerifiedAnswer(filename="keep.json", question="q", raw={"q": "q"}),
            VerifiedAnswer(filename="brand-new.json", question="n", raw={"q": "n"}),
        ],
    )
    _new_env, changes = splice_copilot_into_envelope(existing, bundle)
    by_path = {c["path"]: c["operation"] for c in changes}
    assert by_path["Copilot/Instructions/instructions.md"] == "update"
    assert by_path["Copilot/VerifiedAnswers/keep.json"] == "update"
    assert by_path["Copilot/VerifiedAnswers/brand-new.json"] == "create"
    assert by_path["Copilot/VerifiedAnswers/drop.json"] == "delete"


# ---------------------------------------------------------------------------
# SemanticLinkCopilotWriter
# ---------------------------------------------------------------------------

def test_semanticlink_copilot_writer_raises_outside_fabric():
    with patch("fabric_ai_meta.writeback.copilot_writer.detect_notebook_environment",
               return_value=False):
        with pytest.raises(FabricEnvironmentError):
            SemanticLinkCopilotWriter()


def _fake_fabric_module(workspace_id="ws-id-1", model_id="model-id-1"):
    fabric = MagicMock()
    fabric.resolve_workspace_id.return_value = workspace_id
    fabric.resolve_item_id.return_value = model_id
    return fabric


def _patch_notebook_env_and_sempy(fabric_mock, token="fake-token"):
    """Helper to patch all the Fabric-runtime hooks at once."""
    notebookutils = MagicMock()
    notebookutils.credentials.getToken.return_value = token
    return [
        patch("fabric_ai_meta.writeback.copilot_writer.detect_notebook_environment",
              return_value=True),
        patch.dict("sys.modules", {
            "sempy.fabric": fabric_mock,
            "notebookutils": notebookutils,
        }),
    ]


def test_semanticlink_writer_dry_run_does_not_call_update():
    fabric_mock = _fake_fabric_module()
    existing_env = _envelope([
        {"path": "definition/model.tmdl", "payload": _b64("m"),
         "payloadType": "InlineBase64"},
        {"path": "Copilot/settings.json", "payload": _b64("{}"),
         "payloadType": "InlineBase64"},
    ])
    bundle = _full_bundle()
    with (
        patch("fabric_ai_meta.writeback.copilot_writer.detect_notebook_environment",
              return_value=True),
        patch("fabric_ai_meta.writeback.copilot_writer._load_sempy_fabric",
              return_value=fabric_mock),
        patch("fabric_ai_meta.writeback.copilot_writer._fabric_bearer_token",
              return_value="tok"),
        patch("fabric_ai_meta.writeback.copilot_writer.TMDLClient") as TMDLMock,
    ):
        client_instance = TMDLMock.return_value
        client_instance.get_definition.return_value = existing_env
        writer = SemanticLinkCopilotWriter()
        result = writer.apply_copilot(bundle, "TestModel", "ws", dry_run=True)
    assert result.dry_run is True
    assert result.total_changes > 0
    client_instance.update_definition.assert_not_called()


def test_semanticlink_writer_apply_calls_update_definition():
    fabric_mock = _fake_fabric_module()
    existing_env = _envelope([
        {"path": "definition/model.tmdl", "payload": _b64("m"),
         "payloadType": "InlineBase64"},
    ])
    bundle = _full_bundle()
    with (
        patch("fabric_ai_meta.writeback.copilot_writer.detect_notebook_environment",
              return_value=True),
        patch("fabric_ai_meta.writeback.copilot_writer._load_sempy_fabric",
              return_value=fabric_mock),
        patch("fabric_ai_meta.writeback.copilot_writer._fabric_bearer_token",
              return_value="tok"),
        patch("fabric_ai_meta.writeback.copilot_writer.TMDLClient") as TMDLMock,
    ):
        client_instance = TMDLMock.return_value
        client_instance.get_definition.return_value = existing_env
        client_instance.update_definition.return_value = {"status": "Succeeded"}
        writer = SemanticLinkCopilotWriter()
        result = writer.apply_copilot(bundle, "TestModel", "ws", dry_run=False)
    assert result.dry_run is False
    assert result.errors == []
    client_instance.update_definition.assert_called_once()
    posted_envelope = client_instance.update_definition.call_args[0][1]
    # Posted envelope must contain the new Copilot parts.
    paths = [p["path"] for p in posted_envelope["definition"]["parts"]]
    assert "Copilot/Instructions/instructions.md" in paths
    assert "definition/model.tmdl" in paths  # non-Copilot preserved


def test_semanticlink_writer_lro_failure_populates_errors():
    fabric_mock = _fake_fabric_module()
    existing_env = _envelope([
        {"path": "definition/model.tmdl", "payload": _b64("m"),
         "payloadType": "InlineBase64"},
    ])
    with (
        patch("fabric_ai_meta.writeback.copilot_writer.detect_notebook_environment",
              return_value=True),
        patch("fabric_ai_meta.writeback.copilot_writer._load_sempy_fabric",
              return_value=fabric_mock),
        patch("fabric_ai_meta.writeback.copilot_writer._fabric_bearer_token",
              return_value="tok"),
        patch("fabric_ai_meta.writeback.copilot_writer.TMDLClient") as TMDLMock,
    ):
        client_instance = TMDLMock.return_value
        client_instance.get_definition.return_value = existing_env
        client_instance.update_definition.side_effect = RuntimeError(
            "updateDefinition LRO Failed: InvalidPayload bad parts"
        )
        writer = SemanticLinkCopilotWriter()
        result = writer.apply_copilot(_full_bundle(), "M", "ws", dry_run=False)
    assert result.dry_run is False
    assert result.succeeded is False
    assert any("InvalidPayload" in e for e in result.errors)


def test_semanticlink_writer_succeeded_true_on_clean_apply():
    fabric_mock = _fake_fabric_module()
    existing_env = _envelope([])
    with (
        patch("fabric_ai_meta.writeback.copilot_writer.detect_notebook_environment",
              return_value=True),
        patch("fabric_ai_meta.writeback.copilot_writer._load_sempy_fabric",
              return_value=fabric_mock),
        patch("fabric_ai_meta.writeback.copilot_writer._fabric_bearer_token",
              return_value="tok"),
        patch("fabric_ai_meta.writeback.copilot_writer.TMDLClient") as TMDLMock,
    ):
        client_instance = TMDLMock.return_value
        client_instance.get_definition.return_value = existing_env
        client_instance.update_definition.return_value = {"status": "Succeeded"}
        writer = SemanticLinkCopilotWriter()
        result = writer.apply_copilot(_full_bundle(), "M", "ws", dry_run=False)
    assert result.succeeded is True
    assert result.errors == []


def test_mock_copilot_writer_always_succeeded():
    writer = MockCopilotWriter()
    result = writer.apply_copilot(_full_bundle(), "M", "ws")
    assert result.succeeded is True
    assert result.errors == []


def test_copilot_reader_from_directory_loads_full_bundle(tmp_path):
    """Round-trip: write a full bundle via the exporter, then load it back."""
    from fabric_ai_meta.generator.copilot_reader import CopilotReader
    from fabric_ai_meta.generator.export_copilot import CopilotExporter
    from fabric_ai_meta.models.metadata import SemanticModelMeta

    model = SemanticModelMeta(
        name="Test Model", workspace="ws", description=None,
        tables=[], relationships=[], ai_readiness_score=None, scoring_breakdown={},
        extraction_timestamp="2026-05-17T00:00:00+00:00", extraction_method="mock",
    )
    model.copilot = _full_bundle()
    exporter = CopilotExporter()
    copilot_dir = exporter.write(model, str(tmp_path))
    assert copilot_dir, "exporter produced no output"

    loaded = CopilotReader.from_directory(copilot_dir)
    assert loaded.ai_instructions is not None
    assert loaded.ai_instructions.markdown.startswith("# Instructions")
    assert loaded.ai_data_schema is not None
    assert loaded.example_prompts is not None
    assert loaded.example_prompts.prompts == ["A", "B"]
    assert loaded.settings is not None
    assert loaded.version is not None
    assert {va.filename for va in loaded.verified_answers} == {"q1.json", "q2.json"}


def test_copilot_reader_from_directory_partial_bundle(tmp_path):
    """Only AI Instructions present; other fields stay None / empty."""
    from fabric_ai_meta.generator.copilot_reader import CopilotReader

    instr_dir = tmp_path / "Instructions"
    instr_dir.mkdir()
    (instr_dir / "instructions.md").write_bytes(b"# Only this\n")
    loaded = CopilotReader.from_directory(str(tmp_path))
    assert loaded.ai_instructions is not None
    assert loaded.ai_instructions.markdown == "# Only this\n"
    assert loaded.ai_data_schema is None
    assert loaded.verified_answers == []


def test_copilot_reader_from_directory_empty_dir(tmp_path):
    from fabric_ai_meta.generator.copilot_reader import CopilotReader
    loaded = CopilotReader.from_directory(str(tmp_path))
    assert loaded == CopilotBundle()


def test_copilot_reader_from_directory_extracts_verified_answer_question(tmp_path):
    from fabric_ai_meta.generator.copilot_reader import CopilotReader

    va_dir = tmp_path / "VerifiedAnswers"
    va_dir.mkdir()
    (va_dir / "a.json").write_text(
        json.dumps({"question": "How many?", "dax": "X"}), encoding="utf-8"
    )
    loaded = CopilotReader.from_directory(str(tmp_path))
    assert len(loaded.verified_answers) == 1
    assert loaded.verified_answers[0].filename == "a.json"
    assert loaded.verified_answers[0].question == "How many?"


@pytest.fixture
def runner():
    return CliRunner()


def _write_copilot_dir(tmp_path):
    """Lay out a copilot/ directory matching the exporter output shape."""
    copilot = tmp_path / "copilot"
    (copilot / "Instructions").mkdir(parents=True)
    (copilot / "Instructions" / "instructions.md").write_bytes(b"# Hi\n")
    (copilot / "schema.json").write_text(json.dumps({"tables": []}), encoding="utf-8")
    (copilot / "examplePrompts.json").write_text(json.dumps(["a"]), encoding="utf-8")
    (copilot / "settings.json").write_text(json.dumps({"enabled": True}), encoding="utf-8")
    (copilot / "version.json").write_text(json.dumps({"version": "1"}), encoding="utf-8")
    (copilot / "VerifiedAnswers").mkdir()
    (copilot / "VerifiedAnswers" / "a.json").write_text(
        json.dumps({"question": "q?", "dax": "1"}), encoding="utf-8"
    )
    return copilot


def test_cli_apply_copilot_mock_exits_zero(runner, tmp_path):
    copilot = _write_copilot_dir(tmp_path)
    result = runner.invoke(cli_main, [
        "apply-copilot", str(copilot),
        "--model", "TestModel", "--workspace", "ws",
        "--mock",
    ])
    assert result.exit_code == 0, result.output
    assert "ai_instructions=True" in result.output
    assert "verified_answers=1" in result.output


def test_cli_apply_copilot_mock_dry_run_label(runner, tmp_path):
    copilot = _write_copilot_dir(tmp_path)
    result = runner.invoke(cli_main, [
        "apply-copilot", str(copilot),
        "--model", "TestModel", "--workspace", "ws",
        "--mock", "--dry-run",
    ])
    assert result.exit_code == 0, result.output
    assert "DRY RUN" in result.output


def test_cli_apply_copilot_without_mock_requires_fabric(runner, tmp_path):
    copilot = _write_copilot_dir(tmp_path)
    result = runner.invoke(cli_main, [
        "apply-copilot", str(copilot),
        "--model", "TestModel", "--workspace", "ws",
    ])
    assert result.exit_code != 0
    assert "Fabric" in result.output


def test_cli_apply_copilot_help(runner):
    result = runner.invoke(cli_main, ["apply-copilot", "--help"])
    assert result.exit_code == 0
    assert "COPILOT_DIR" in result.output or "copilot_dir" in result.output


def test_cli_apply_copilot_missing_dir(runner):
    result = runner.invoke(cli_main, [
        "apply-copilot", "nonexistent-dir",
        "--model", "M", "--workspace", "ws", "--mock",
    ])
    assert result.exit_code != 0


def test_semanticlink_writer_resolution_failure_raises():
    """Unresolvable workspace or model id must raise, not silently apply."""
    fabric_mock = MagicMock()
    fabric_mock.resolve_workspace_id.return_value = None
    with (
        patch("fabric_ai_meta.writeback.copilot_writer.detect_notebook_environment",
              return_value=True),
        patch("fabric_ai_meta.writeback.copilot_writer._load_sempy_fabric",
              return_value=fabric_mock),
    ):
        writer = SemanticLinkCopilotWriter()
        with pytest.raises(RuntimeError, match="workspace"):
            writer.apply_copilot(_full_bundle(), "M", "ws-missing", dry_run=False)
