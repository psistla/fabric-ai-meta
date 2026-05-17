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
