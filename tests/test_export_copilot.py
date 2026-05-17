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
