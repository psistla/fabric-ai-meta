"""Tests for CopilotReader.from_definition() parser.

Uses hand-built envelopes; no network, no fixture files. The richer
fixture-driven tests land in Chunk 4 of the v1.4.0 plan.
"""

import base64
import json


def _b64(payload) -> str:
    """Encode dict/str/bytes -> base64 string in the shape getDefinition returns."""
    if isinstance(payload, dict) or isinstance(payload, list):
        payload = json.dumps(payload).encode("utf-8")
    elif isinstance(payload, str):
        payload = payload.encode("utf-8")
    return base64.b64encode(payload).decode("ascii")


def _envelope(parts: list[dict]) -> dict:
    return {"definition": {"parts": parts}}


def test_empty_envelope_returns_empty_bundle():
    from fabric_ai_meta.generator.copilot_reader import CopilotReader
    from fabric_ai_meta.models.copilot import CopilotBundle

    bundle = CopilotReader.from_definition(_envelope([]))
    assert isinstance(bundle, CopilotBundle)
    assert bundle.ai_instructions is None
    assert bundle.verified_answers == []
    assert bundle.ai_data_schema is None
    assert bundle.example_prompts is None
    assert bundle.settings is None
    assert bundle.version is None


def test_envelope_with_only_tmdl_parts_returns_empty_bundle():
    """Non-Copilot parts must be ignored."""
    from fabric_ai_meta.generator.copilot_reader import CopilotReader

    bundle = CopilotReader.from_definition(_envelope([
        {"path": "definition/model.tmdl", "payload": _b64("model"), "payloadType": "InlineBase64"},
        {"path": ".platform", "payload": _b64('{}'), "payloadType": "InlineBase64"},
    ]))
    assert bundle.ai_instructions is None
    assert bundle.verified_answers == []


def test_ai_instructions_extracted_with_markdown_and_raw_bytes():
    from fabric_ai_meta.generator.copilot_reader import CopilotReader

    bundle = CopilotReader.from_definition(_envelope([
        {
            "path": "Copilot/Instructions/instructions.md",
            "payload": _b64("# AI Instructions\n\nAlways prefer DISTINCT()."),
            "payloadType": "InlineBase64",
        },
    ]))
    assert bundle.ai_instructions is not None
    assert bundle.ai_instructions.markdown.startswith("# AI Instructions")
    assert bundle.ai_instructions.raw_bytes == b"# AI Instructions\n\nAlways prefer DISTINCT()."


def test_ai_instructions_raw_bytes_round_trips_exact_input():
    from fabric_ai_meta.generator.copilot_reader import CopilotReader

    original = b"line one\nline two\nUTF-8 \xe2\x9c\x93"
    bundle = CopilotReader.from_definition(_envelope([
        {
            "path": "Copilot/Instructions/instructions.md",
            "payload": base64.b64encode(original).decode("ascii"),
            "payloadType": "InlineBase64",
        },
    ]))
    assert bundle.ai_instructions is not None
    assert bundle.ai_instructions.raw_bytes == original


def test_ai_instructions_invalid_utf8_falls_back_to_replacement(caplog):
    import logging

    from fabric_ai_meta.generator.copilot_reader import CopilotReader

    bad = b"\xff\xfe not valid utf8"
    with caplog.at_level(logging.WARNING, logger="fabric_ai_meta.generator.copilot_reader"):
        bundle = CopilotReader.from_definition(_envelope([
            {
                "path": "Copilot/Instructions/instructions.md",
                "payload": base64.b64encode(bad).decode("ascii"),
                "payloadType": "InlineBase64",
            },
        ]))
    assert bundle.ai_instructions is not None
    assert bundle.ai_instructions.raw_bytes == bad
    assert isinstance(bundle.ai_instructions.markdown, str)
    assert any("not valid UTF-8" in r.message for r in caplog.records)


def test_verified_answers_strip_path_prefix_and_keep_basename():
    from fabric_ai_meta.generator.copilot_reader import CopilotReader

    bundle = CopilotReader.from_definition(_envelope([
        {
            "path": "Copilot/VerifiedAnswers/answer-zeta.json",
            "payload": _b64({"question": "What is total sales?", "dax": "..."}),
            "payloadType": "InlineBase64",
        },
        {
            "path": "Copilot/VerifiedAnswers/answer-alpha.json",
            "payload": _b64({"question": "What is margin?"}),
            "payloadType": "InlineBase64",
        },
    ]))
    assert [va.filename for va in bundle.verified_answers] == [
        "answer-alpha.json",
        "answer-zeta.json",
    ]
    assert bundle.verified_answers[0].question == "What is margin?"
    assert bundle.verified_answers[1].question == "What is total sales?"
    assert bundle.verified_answers[1].raw["dax"] == "..."


def test_verified_answer_without_recognizable_question_key_keeps_none():
    from fabric_ai_meta.generator.copilot_reader import CopilotReader

    bundle = CopilotReader.from_definition(_envelope([
        {
            "path": "Copilot/VerifiedAnswers/unknown.json",
            "payload": _b64({"foo": "bar"}),
            "payloadType": "InlineBase64",
        },
    ]))
    assert len(bundle.verified_answers) == 1
    assert bundle.verified_answers[0].question is None
    assert bundle.verified_answers[0].raw == {"foo": "bar"}


def test_malformed_verified_answer_is_skipped_warning_logged(caplog):
    import logging

    from fabric_ai_meta.generator.copilot_reader import CopilotReader

    with caplog.at_level(logging.WARNING, logger="fabric_ai_meta.generator.copilot_reader"):
        bundle = CopilotReader.from_definition(_envelope([
            {
                "path": "Copilot/VerifiedAnswers/good.json",
                "payload": _b64({"question": "valid"}),
                "payloadType": "InlineBase64",
            },
            {
                "path": "Copilot/VerifiedAnswers/bad.json",
                "payload": "not-base64-not-json!!!",
                "payloadType": "InlineBase64",
            },
        ]))
    assert [va.filename for va in bundle.verified_answers] == ["good.json"]
    assert any("Copilot/VerifiedAnswers/bad.json" in r.message for r in caplog.records)


def test_ai_data_schema_keeps_raw_dict():
    from fabric_ai_meta.generator.copilot_reader import CopilotReader

    schema = {"tables": [{"name": "Sales", "columns": ["amount"]}]}
    bundle = CopilotReader.from_definition(_envelope([
        {"path": "Copilot/schema.json", "payload": _b64(schema), "payloadType": "InlineBase64"},
    ]))
    assert bundle.ai_data_schema is not None
    assert bundle.ai_data_schema.raw == schema


def test_example_prompts_flat_list_shape():
    from fabric_ai_meta.generator.copilot_reader import CopilotReader

    bundle = CopilotReader.from_definition(_envelope([
        {
            "path": "Copilot/examplePrompts.json",
            "payload": _b64(["What is total sales?", "Top 5 customers?"]),
            "payloadType": "InlineBase64",
        },
    ]))
    assert bundle.example_prompts is not None
    assert bundle.example_prompts.prompts == ["What is total sales?", "Top 5 customers?"]


def test_example_prompts_object_with_prompts_key_shape():
    from fabric_ai_meta.generator.copilot_reader import CopilotReader

    bundle = CopilotReader.from_definition(_envelope([
        {
            "path": "Copilot/examplePrompts.json",
            "payload": _b64({"prompts": [{"prompt": "Show sales by region"}]}),
            "payloadType": "InlineBase64",
        },
    ]))
    assert bundle.example_prompts is not None
    assert bundle.example_prompts.prompts == ["Show sales by region"]


def test_settings_and_version_keep_raw_dict():
    from fabric_ai_meta.generator.copilot_reader import CopilotReader

    bundle = CopilotReader.from_definition(_envelope([
        {"path": "Copilot/settings.json", "payload": _b64({"enabled": True}), "payloadType": "InlineBase64"},
        {"path": "Copilot/version.json", "payload": _b64({"version": "1.0"}), "payloadType": "InlineBase64"},
    ]))
    assert bundle.settings is not None and bundle.settings.raw == {"enabled": True}
    assert bundle.version is not None and bundle.version.raw == {"version": "1.0"}


def test_non_inline_base64_payload_type_skipped(caplog):
    import logging

    from fabric_ai_meta.generator.copilot_reader import CopilotReader

    with caplog.at_level(logging.WARNING, logger="fabric_ai_meta.generator.copilot_reader"):
        bundle = CopilotReader.from_definition(_envelope([
            {
                "path": "Copilot/Instructions/instructions.md",
                "payload": "ignored",
                "payloadType": "RemoteFile",
            },
        ]))
    assert bundle.ai_instructions is None
    assert any("Unsupported payloadType" in r.message or "payloadType" in r.message for r in caplog.records)


def test_full_envelope_with_all_six_primitives_populates_every_field():
    from fabric_ai_meta.generator.copilot_reader import CopilotReader

    bundle = CopilotReader.from_definition(_envelope([
        {"path": "definition/model.tmdl", "payload": _b64("ignored"), "payloadType": "InlineBase64"},
        {"path": "Copilot/Instructions/instructions.md",
         "payload": _b64("# Instructions"), "payloadType": "InlineBase64"},
        {"path": "Copilot/schema.json",
         "payload": _b64({"tables": []}), "payloadType": "InlineBase64"},
        {"path": "Copilot/examplePrompts.json",
         "payload": _b64(["one", "two"]), "payloadType": "InlineBase64"},
        {"path": "Copilot/settings.json",
         "payload": _b64({"enabled": True}), "payloadType": "InlineBase64"},
        {"path": "Copilot/version.json",
         "payload": _b64({"version": "1"}), "payloadType": "InlineBase64"},
        {"path": "Copilot/VerifiedAnswers/q1.json",
         "payload": _b64({"question": "Q1?"}), "payloadType": "InlineBase64"},
        {"path": "Copilot/VerifiedAnswers/q2.json",
         "payload": _b64({"question": "Q2?"}), "payloadType": "InlineBase64"},
    ]))
    assert bundle.ai_instructions is not None
    assert bundle.ai_data_schema is not None
    assert bundle.example_prompts is not None
    assert bundle.settings is not None
    assert bundle.version is not None
    assert [va.filename for va in bundle.verified_answers] == ["q1.json", "q2.json"]
