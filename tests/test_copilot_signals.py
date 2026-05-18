"""Tests for CopilotBundle.signals() — governance signals per model."""

from fabric_ai_meta.models.copilot import (
    AIDataSchema,
    AIInstructions,
    CopilotBundle,
    CopilotSettings,
    CopilotVersion,
    ExamplePrompts,
    VerifiedAnswer,
)


def _full_bundle() -> CopilotBundle:
    md = "# Instructions\n- prefer X over Y.\n"
    return CopilotBundle(
        ai_instructions=AIInstructions(markdown=md, raw_bytes=md.encode("utf-8")),
        verified_answers=[
            VerifiedAnswer(filename="a.json", question="q", raw={}),
            VerifiedAnswer(filename="b.json", question="q", raw={}),
        ],
        ai_data_schema=AIDataSchema(raw={
            "tables": [{"name": "Sales"}, {"name": "Date"}, {"name": "Customer"}]
        }),
        example_prompts=ExamplePrompts(prompts=["p1", "p2"], raw=["p1", "p2"]),
        settings=CopilotSettings(raw={"enabled": True}),
        version=CopilotVersion(raw={"version": "1.0"}),
    )


def test_signals_full_bundle():
    sig = _full_bundle().signals()
    assert sig == {
        "has_ai_instructions": True,
        "ai_instructions_length": len("# Instructions\n- prefer X over Y.\n"),
        "verified_answer_count": 2,
        "ai_data_schema_table_count": 3,
        "example_prompt_count": 2,
        "copilot_enabled": True,
        "copilot_version": "1.0",
    }


def test_signals_empty_bundle():
    sig = CopilotBundle().signals()
    assert sig == {
        "has_ai_instructions": False,
        "ai_instructions_length": 0,
        "verified_answer_count": 0,
        "ai_data_schema_table_count": 0,
        "example_prompt_count": 0,
        "copilot_enabled": None,
        "copilot_version": None,
    }


def test_signals_partial_only_ai_instructions():
    md = "# only"
    bundle = CopilotBundle(
        ai_instructions=AIInstructions(markdown=md, raw_bytes=md.encode("utf-8"))
    )
    sig = bundle.signals()
    assert sig["has_ai_instructions"] is True
    assert sig["ai_instructions_length"] == len(md)
    assert sig["verified_answer_count"] == 0
    assert sig["copilot_enabled"] is None


def test_signals_schema_without_tables_field():
    bundle = CopilotBundle(
        ai_data_schema=AIDataSchema(raw={"other": "value"})
    )
    assert bundle.signals()["ai_data_schema_table_count"] == 0


def test_signals_settings_without_enabled_field():
    bundle = CopilotBundle(settings=CopilotSettings(raw={"other": True}))
    assert bundle.signals()["copilot_enabled"] is None


def test_signals_version_coerces_numeric_version_to_string():
    bundle = CopilotBundle(version=CopilotVersion(raw={"version": 2}))
    assert bundle.signals()["copilot_version"] == "2"


def test_signals_json_serializable():
    import json
    payload = json.dumps(_full_bundle().signals())
    assert json.loads(payload)["has_ai_instructions"] is True


def test_copilotbundle_round_trip_via_to_dict():
    """to_dict → from_dict preserves all non-raw_bytes fields."""
    original = _full_bundle()
    restored = CopilotBundle.from_dict(original.to_dict())
    assert restored is not None
    assert restored.signals() == original.signals()
    assert restored.ai_instructions.markdown == original.ai_instructions.markdown
    assert restored.ai_data_schema.raw == original.ai_data_schema.raw
    assert [va.filename for va in restored.verified_answers] == [
        va.filename for va in original.verified_answers
    ]


def test_copilotbundle_from_dict_handles_none_and_empty():
    assert CopilotBundle.from_dict(None) is None
    assert CopilotBundle.from_dict({}) is None


def test_semanticmodelmeta_round_trip_preserves_copilot():
    """SemanticModelMeta.to_dict → from_dict reconstructs `copilot` bundle."""
    from fabric_ai_meta.models.metadata import SemanticModelMeta, from_dict

    model = SemanticModelMeta(
        name="M", workspace="ws", description=None,
        tables=[], relationships=[], ai_readiness_score=None, scoring_breakdown={},
        extraction_timestamp="2026-05-17T00:00:00+00:00", extraction_method="mock",
    )
    model.copilot = _full_bundle()
    restored = from_dict(model.to_dict())
    assert restored.copilot is not None
    assert restored.copilot.signals() == model.copilot.signals()
