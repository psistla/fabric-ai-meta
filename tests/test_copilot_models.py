"""Tests for fabric_ai_meta.models.copilot dataclasses."""


def test_module_exposes_all_dataclasses():
    from fabric_ai_meta.models.copilot import (
        AIDataSchema,
        AIInstructions,
        CopilotBundle,
        CopilotSettings,
        CopilotVersion,
        ExamplePrompts,
        VerifiedAnswer,
    )
    assert AIInstructions is not None
    assert VerifiedAnswer is not None
    assert AIDataSchema is not None
    assert ExamplePrompts is not None
    assert CopilotSettings is not None
    assert CopilotVersion is not None
    assert CopilotBundle is not None


def test_empty_bundle_to_dict_returns_all_none_and_empty_list():
    from fabric_ai_meta.models.copilot import CopilotBundle

    d = CopilotBundle().to_dict()
    assert d == {
        "ai_instructions": None,
        "verified_answers": [],
        "ai_data_schema": None,
        "example_prompts": None,
        "settings": None,
        "version": None,
    }


def test_full_bundle_to_dict_omits_raw_bytes_keeps_markdown():
    from fabric_ai_meta.models.copilot import (
        AIDataSchema,
        AIInstructions,
        CopilotBundle,
        CopilotSettings,
        CopilotVersion,
        ExamplePrompts,
        VerifiedAnswer,
    )

    bundle = CopilotBundle(
        ai_instructions=AIInstructions(markdown="# Hi", raw_bytes=b"# Hi"),
        verified_answers=[
            VerifiedAnswer(filename="a.json", question="Q1?", raw={"k": 1}),
            VerifiedAnswer(filename="b.json", question=None, raw={"k": 2}),
        ],
        ai_data_schema=AIDataSchema(raw={"tables": []}),
        example_prompts=ExamplePrompts(prompts=["one", "two"], raw=["one", "two"]),
        settings=CopilotSettings(raw={"enabled": True}),
        version=CopilotVersion(raw={"v": 1}),
    )
    d = bundle.to_dict()
    assert d["ai_instructions"] == {"markdown": "# Hi"}
    assert "raw_bytes" not in d["ai_instructions"]
    assert d["verified_answers"] == [
        {"filename": "a.json", "question": "Q1?", "raw": {"k": 1}},
        {"filename": "b.json", "question": None, "raw": {"k": 2}},
    ]
    assert d["ai_data_schema"] == {"raw": {"tables": []}}
    assert d["example_prompts"] == {"prompts": ["one", "two"], "raw": ["one", "two"]}
    assert d["settings"] == {"raw": {"enabled": True}}
    assert d["version"] == {"raw": {"v": 1}}


def test_to_dict_output_is_json_serializable():
    import json

    from fabric_ai_meta.models.copilot import (
        AIInstructions,
        CopilotBundle,
        VerifiedAnswer,
    )

    bundle = CopilotBundle(
        ai_instructions=AIInstructions(markdown="text", raw_bytes=b"text"),
        verified_answers=[VerifiedAnswer(filename="x.json", question="q", raw={})],
    )
    serialized = json.dumps(bundle.to_dict())  # must not raise
    assert "raw_bytes" not in serialized
    assert "markdown" in serialized
