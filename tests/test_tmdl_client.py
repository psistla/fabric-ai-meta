"""Tests for the TMDL / Copilot research client.

Prep for AI primitives (AI Instructions, AI Data Schema, Verified Answers)
live in a ``Copilot/`` folder sibling to ``definition/`` inside the semantic
model, returned by ``getDefinition`` as separate parts. These tests assert
that the client locates them via path prefix matching rather than by
scanning TMDL files for annotation strings.
"""

import base64
import json
from unittest.mock import MagicMock, patch

import pytest

from fabric_ai_meta.writeback.tmdl_client import (
    COPILOT_PATH_PREFIXES,
    PRIMITIVE_BY_PREFIX,
    TMDLClient,
    _decode_part_text,
)


def _b64(text: str) -> str:
    return base64.b64encode(text.encode("utf-8")).decode("ascii")


def _mock_definition(parts: list[dict]) -> dict:
    return {"definition": {"parts": parts}}


def _fake_credential(token: str = "fake-token") -> MagicMock:
    cred = MagicMock()
    cred.get_token.return_value = MagicMock(token=token)
    return cred


# ---------------------------------------------------------------------------
# list_definition_files
# ---------------------------------------------------------------------------

def test_list_definition_files_returns_paths():
    definition = _mock_definition([
        {"path": "definition/model.tmdl", "payload": _b64("model"),
         "payloadType": "InlineBase64"},
        {"path": "definition/tables/Sales.tmdl", "payload": _b64("table"),
         "payloadType": "InlineBase64"},
        {"path": "Copilot/Instructions/instructions.md",
         "payload": _b64("# instructions"), "payloadType": "InlineBase64"},
    ])
    client = TMDLClient(_fake_credential(), workspace_id="ws-id")
    with patch.object(client, "get_definition", return_value=definition):
        paths = client.list_definition_files("model-id")
    assert paths == [
        "definition/model.tmdl",
        "definition/tables/Sales.tmdl",
        "Copilot/Instructions/instructions.md",
    ]


def test_list_definition_files_empty_when_no_parts():
    client = TMDLClient(_fake_credential(), workspace_id="ws-id")
    with patch.object(client, "get_definition", return_value={"definition": {"parts": []}}):
        assert client.list_definition_files("model-id") == []


# ---------------------------------------------------------------------------
# find_prep_for_ai_settings
# ---------------------------------------------------------------------------

def test_find_prep_for_ai_settings_returns_none_when_no_copilot_parts():
    definition = _mock_definition([
        {"path": "definition/model.tmdl",
         "payload": _b64("model Sales\n  defaultMode: import\n"),
         "payloadType": "InlineBase64"},
    ])
    client = TMDLClient(_fake_credential(), workspace_id="ws")
    assert client.find_prep_for_ai_settings(definition) is None


def test_find_prep_for_ai_settings_finds_ai_instructions():
    instructions_md = (
        "# AI Instructions\n\n"
        "Use [Total Sales] for revenue questions. Filter by DimDate for time analysis."
    )
    definition = _mock_definition([
        {"path": "definition/model.tmdl",
         "payload": _b64("model Sales"), "payloadType": "InlineBase64"},
        {"path": "Copilot/Instructions/instructions.md",
         "payload": _b64(instructions_md), "payloadType": "InlineBase64"},
    ])
    client = TMDLClient(_fake_credential(), workspace_id="ws")
    result = client.find_prep_for_ai_settings(definition)
    assert result is not None
    primitives = {m["primitive"] for m in result["matches"]}
    assert "ai_instructions" in primitives
    instructions_match = next(m for m in result["matches"]
                              if m["primitive"] == "ai_instructions")
    assert instructions_match["path"] == "Copilot/Instructions/instructions.md"
    assert "Total Sales" in instructions_match["snippet"]


def test_find_prep_for_ai_settings_finds_verified_answers():
    answer_json = json.dumps({
        "question": "What is Total Sales for last quarter?",
        "dax": "CALCULATE([Total Sales], DATEADD(...))",
    })
    definition = _mock_definition([
        {"path": "Copilot/VerifiedAnswers/answer-1.json",
         "payload": _b64(answer_json), "payloadType": "InlineBase64"},
        {"path": "Copilot/VerifiedAnswers/answer-2.json",
         "payload": _b64(answer_json), "payloadType": "InlineBase64"},
    ])
    client = TMDLClient(_fake_credential(), workspace_id="ws")
    result = client.find_prep_for_ai_settings(definition)
    assert result is not None
    primitives = [m["primitive"] for m in result["matches"]]
    assert primitives == ["verified_answers", "verified_answers"]


def test_find_prep_for_ai_settings_finds_ai_data_schema():
    schema_json = json.dumps({"includedTables": ["Sales", "Customer"]})
    definition = _mock_definition([
        {"path": "Copilot/schema.json",
         "payload": _b64(schema_json), "payloadType": "InlineBase64"},
    ])
    client = TMDLClient(_fake_credential(), workspace_id="ws")
    result = client.find_prep_for_ai_settings(definition)
    assert result is not None
    assert result["matches"][0]["primitive"] == "ai_data_schema"


def test_find_prep_for_ai_settings_finds_all_copilot_primitives_at_once():
    parts = [
        {"path": "Copilot/Instructions/instructions.md",
         "payload": _b64("# instructions"), "payloadType": "InlineBase64"},
        {"path": "Copilot/schema.json",
         "payload": _b64("{}"), "payloadType": "InlineBase64"},
        {"path": "Copilot/VerifiedAnswers/a.json",
         "payload": _b64("{}"), "payloadType": "InlineBase64"},
        {"path": "Copilot/examplePrompts.json",
         "payload": _b64("[]"), "payloadType": "InlineBase64"},
        {"path": "Copilot/settings.json",
         "payload": _b64("{}"), "payloadType": "InlineBase64"},
        {"path": "Copilot/version.json",
         "payload": _b64("{\"version\":1}"), "payloadType": "InlineBase64"},
    ]
    client = TMDLClient(_fake_credential(), workspace_id="ws")
    result = client.find_prep_for_ai_settings(_mock_definition(parts))
    assert result is not None
    primitives = {m["primitive"] for m in result["matches"]}
    assert primitives == {
        "ai_instructions",
        "ai_data_schema",
        "verified_answers",
        "example_prompts",
        "copilot_settings",
        "copilot_version",
    }


def test_find_prep_for_ai_settings_ignores_tmdl_annotations_with_old_hint_strings():
    """An ``__PBI_AIInstructions`` annotation inside a TMDL file is NOT a match.

    The original spike hypothesis was that AI Instructions might surface as
    TMDL annotations. That hypothesis was falsified: matching is now path-
    based and rooted at ``Copilot/``. A red-herring annotation in TMDL must
    not produce a match.
    """
    tmdl_with_red_herring = (
        "model Sales\n"
        "  annotation __PBI_AIInstructions = 'this should not match'\n"
    )
    definition = _mock_definition([
        {"path": "definition/model.tmdl",
         "payload": _b64(tmdl_with_red_herring),
         "payloadType": "InlineBase64"},
    ])
    client = TMDLClient(_fake_credential(), workspace_id="ws")
    assert client.find_prep_for_ai_settings(definition) is None


# ---------------------------------------------------------------------------
# get_definition (HTTP path mocked)
# ---------------------------------------------------------------------------

def test_get_definition_calls_correct_url_and_parses_json():
    expected = _mock_definition([
        {"path": "definition/model.tmdl", "payload": _b64("model X"),
         "payloadType": "InlineBase64"},
    ])
    fake_response = MagicMock()
    fake_response.read.return_value = json.dumps(expected).encode("utf-8")
    fake_response.__enter__ = lambda self: self
    fake_response.__exit__ = lambda self, *a: None

    with patch("fabric_ai_meta.writeback.tmdl_client.urllib_request.urlopen",
               return_value=fake_response) as mock_urlopen:
        client = TMDLClient(_fake_credential(token="abc"), workspace_id="ws-1")
        result = client.get_definition("model-1")

    assert result == expected
    request_arg = mock_urlopen.call_args[0][0]
    assert "workspaces/ws-1/semanticModels/model-1/getDefinition" in request_arg.full_url
    assert request_arg.headers["Authorization"] == "Bearer abc"


def test_get_definition_raises_on_http_error():
    from urllib.error import HTTPError

    err = HTTPError(
        url="http://x", code=403, msg="Forbidden", hdrs=None,
        fp=MagicMock(read=lambda: b'{"error":"insufficient permissions"}'),
    )
    with patch("fabric_ai_meta.writeback.tmdl_client.urllib_request.urlopen",
               side_effect=err):
        client = TMDLClient(_fake_credential(), workspace_id="ws")
        with pytest.raises(RuntimeError, match="getDefinition failed"):
            client.get_definition("m")


def test_get_definition_requires_credential():
    client = TMDLClient(credential=None, workspace_id="ws")
    with pytest.raises(RuntimeError, match="requires an explicit credential"):
        client.get_definition("m")


def test_get_definition_accepts_string_token():
    expected = _mock_definition([])
    fake_response = MagicMock()
    fake_response.read.return_value = json.dumps(expected).encode("utf-8")
    fake_response.__enter__ = lambda self: self
    fake_response.__exit__ = lambda self, *a: None

    with patch("fabric_ai_meta.writeback.tmdl_client.urllib_request.urlopen",
               return_value=fake_response) as mock_urlopen:
        client = TMDLClient(credential="raw-token-xyz", workspace_id="ws")
        client.get_definition("m")

    request_arg = mock_urlopen.call_args[0][0]
    assert request_arg.headers["Authorization"] == "Bearer raw-token-xyz"


# ---------------------------------------------------------------------------
# Helpers and constants
# ---------------------------------------------------------------------------

def test_decode_part_text_returns_none_for_missing_payload():
    assert _decode_part_text({"path": "x"}) is None


def test_decode_part_text_decodes_base64():
    part = {"payload": _b64("hello"), "payloadType": "InlineBase64"}
    assert _decode_part_text(part) == "hello"


def test_copilot_prefixes_cover_documented_primitives():
    """COPILOT_PATH_PREFIXES must cover the documented Prep for AI primitives."""
    must_include = {
        "Copilot/Instructions/",
        "Copilot/VerifiedAnswers/",
        "Copilot/schema.json",
    }
    assert must_include.issubset(set(COPILOT_PATH_PREFIXES))


def test_primitive_by_prefix_keys_match_path_prefixes():
    assert set(PRIMITIVE_BY_PREFIX.keys()) == set(COPILOT_PATH_PREFIXES)
