"""Tests for CopilotExporter."""

import json
import os
from pathlib import Path

import pytest


def _build_model_with_full_bundle():
    """Helper: SemanticModelMeta carrying a fully populated CopilotBundle."""
    from fabric_ai_meta.models.copilot import (
        AIDataSchema,
        AIInstructions,
        CopilotBundle,
        CopilotSettings,
        CopilotVersion,
        ExamplePrompts,
        VerifiedAnswer,
    )
    from fabric_ai_meta.models.metadata import SemanticModelMeta

    return SemanticModelMeta(
        name="Adventure Works",
        workspace="W",
        description=None,
        tables=[],
        relationships=[],
        ai_readiness_score=None,
        scoring_breakdown={},
        extraction_timestamp="2026-01-01T00:00:00Z",
        extraction_method="mock",
        copilot=CopilotBundle(
            ai_instructions=AIInstructions(markdown="# Hi", raw_bytes=b"# Hi"),
            verified_answers=[
                VerifiedAnswer(filename="q1.json", question="Q1?", raw={"question": "Q1?"}),
                VerifiedAnswer(filename="q2.json", question="Q2?", raw={"question": "Q2?"}),
            ],
            ai_data_schema=AIDataSchema(raw={"tables": []}),
            example_prompts=ExamplePrompts(prompts=["p1"], raw=["p1"]),
            settings=CopilotSettings(raw={"enabled": True}),
            version=CopilotVersion(raw={"v": 1}),
        ),
    )


def test_generate_returns_to_dict_when_copilot_present():
    from fabric_ai_meta.generator.export_copilot import CopilotExporter

    model = _build_model_with_full_bundle()
    payload = CopilotExporter().generate(model)
    assert payload == model.copilot.to_dict()


def test_generate_raises_exporter_error_when_copilot_is_none():
    from fabric_ai_meta.generator.base import ExporterError
    from fabric_ai_meta.generator.export_copilot import CopilotExporter
    from fabric_ai_meta.models.metadata import SemanticModelMeta

    model = SemanticModelMeta(
        name="X", workspace="W", description=None, tables=[], relationships=[],
        ai_readiness_score=None, scoring_breakdown={},
        extraction_timestamp="2026-01-01T00:00:00Z", extraction_method="mock",
    )
    with pytest.raises(ExporterError, match="with_copilot"):
        CopilotExporter().generate(model)


def test_write_full_bundle_creates_correct_directory_tree(tmp_path):
    from fabric_ai_meta.generator.export_copilot import CopilotExporter

    model = _build_model_with_full_bundle()
    result = CopilotExporter().write(model, str(tmp_path))
    assert result.endswith(os.path.join("adventure-works", "copilot"))

    base = Path(tmp_path) / "adventure-works" / "copilot"
    assert (base / "Instructions" / "instructions.md").exists()
    assert (base / "schema.json").exists()
    assert (base / "examplePrompts.json").exists()
    assert (base / "settings.json").exists()
    assert (base / "version.json").exists()
    assert (base / "VerifiedAnswers" / "q1.json").exists()
    assert (base / "VerifiedAnswers" / "q2.json").exists()


def test_write_instructions_md_is_byte_perfect(tmp_path):
    """raw_bytes is written verbatim, not re-encoded through markdown."""
    from fabric_ai_meta.generator.export_copilot import CopilotExporter
    from fabric_ai_meta.models.copilot import AIInstructions, CopilotBundle
    from fabric_ai_meta.models.metadata import SemanticModelMeta

    raw = b"original bytes including CRLF\r\nand tab\there"
    model = SemanticModelMeta(
        name="m", workspace="w", description=None, tables=[], relationships=[],
        ai_readiness_score=None, scoring_breakdown={},
        extraction_timestamp="2026-01-01T00:00:00Z", extraction_method="mock",
        copilot=CopilotBundle(ai_instructions=AIInstructions(markdown=raw.decode(), raw_bytes=raw)),
    )
    CopilotExporter().write(model, str(tmp_path))
    written = (Path(tmp_path) / "m" / "copilot" / "Instructions" / "instructions.md").read_bytes()
    assert written == raw


def test_write_verified_answers_use_basename_filenames(tmp_path):
    from fabric_ai_meta.generator.export_copilot import CopilotExporter

    model = _build_model_with_full_bundle()
    CopilotExporter().write(model, str(tmp_path))
    va_dir = Path(tmp_path) / "adventure-works" / "copilot" / "VerifiedAnswers"
    files = sorted(p.name for p in va_dir.iterdir())
    assert files == ["q1.json", "q2.json"]


def test_write_empty_bundle_returns_empty_string_and_writes_nothing(tmp_path):
    """A CopilotBundle with no primitives is a legitimate state."""
    from fabric_ai_meta.generator.export_copilot import CopilotExporter
    from fabric_ai_meta.models.copilot import CopilotBundle
    from fabric_ai_meta.models.metadata import SemanticModelMeta

    model = SemanticModelMeta(
        name="m", workspace="w", description=None, tables=[], relationships=[],
        ai_readiness_score=None, scoring_breakdown={},
        extraction_timestamp="2026-01-01T00:00:00Z", extraction_method="mock",
        copilot=CopilotBundle(),
    )
    result = CopilotExporter().write(model, str(tmp_path))
    assert result == ""
    assert not (Path(tmp_path) / "m" / "copilot").exists()
