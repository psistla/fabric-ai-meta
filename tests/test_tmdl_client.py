"""Tests for the TMDL research client (Task S6-02)."""

import base64
import json
from unittest.mock import MagicMock, patch

import pytest

from fabric_ai_meta.writeback.tmdl_client import (
    PREP_FOR_AI_HINTS,
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
        {"path": "model.tmdl", "payload": _b64("model"), "payloadType": "InlineBase64"},
        {"path": "tables/Sales.tmdl", "payload": _b64("table"), "payloadType": "InlineBase64"},
        {"path": "relationships.tmdl", "payload": _b64("rel"), "payloadType": "InlineBase64"},
    ])
    client = TMDLClient(_fake_credential(), workspace_id="ws-id")
    with patch.object(client, "get_definition", return_value=definition):
        paths = client.list_definition_files("model-id")
    assert paths == ["model.tmdl", "tables/Sales.tmdl", "relationships.tmdl"]


def test_list_definition_files_empty_when_no_parts():
    client = TMDLClient(_fake_credential(), workspace_id="ws-id")
    with patch.object(client, "get_definition", return_value={"definition": {"parts": []}}):
        assert client.list_definition_files("model-id") == []


# ---------------------------------------------------------------------------
# find_prep_for_ai_settings
# ---------------------------------------------------------------------------

def test_find_prep_for_ai_settings_returns_none_when_absent():
    definition = _mock_definition([
        {"path": "model.tmdl", "payload": _b64("model Sales\n  defaultMode: import\n"),
         "payloadType": "InlineBase64"},
    ])
    client = TMDLClient(_fake_credential(), workspace_id="ws")
    assert client.find_prep_for_ai_settings(definition) is None


def test_find_prep_for_ai_settings_finds_ai_instructions():
    tmdl_with_hint = (
        "model Sales\n"
        "  defaultMode: import\n"
        '  annotation __PBI_AIInstructions = "Use [Total Sales] for revenue questions."\n'
    )
    definition = _mock_definition([
        {"path": "model.tmdl", "payload": _b64(tmdl_with_hint), "payloadType": "InlineBase64"},
    ])
    client = TMDLClient(_fake_credential(), workspace_id="ws")
    result = client.find_prep_for_ai_settings(definition)
    assert result is not None
    assert len(result["matches"]) >= 1
    match = result["matches"][0]
    assert match["path"] == "model.tmdl"
    assert match["hint"] == "__PBI_AIInstructions"
    assert "Total Sales" in match["snippet"]


def test_find_prep_for_ai_settings_finds_verified_answers():
    tmdl = "model Sales\n  annotation __PBI_VerifiedAnswers = '[{...}]'\n"
    definition = _mock_definition([
        {"path": "model.tmdl", "payload": _b64(tmdl), "payloadType": "InlineBase64"},
    ])
    client = TMDLClient(_fake_credential(), workspace_id="ws")
    result = client.find_prep_for_ai_settings(definition)
    assert result is not None
    hints_found = {m["hint"] for m in result["matches"]}
    assert "__PBI_VerifiedAnswers" in hints_found


def test_find_prep_for_ai_settings_handles_unknown_payload_type():
    definition = _mock_definition([
        {"path": "extras.bin", "payload": "not-base64", "payloadType": "Binary"},
    ])
    client = TMDLClient(_fake_credential(), workspace_id="ws")
    assert client.find_prep_for_ai_settings(definition) is None


def test_find_prep_for_ai_settings_returns_all_matches_across_files():
    parts = [
        {"path": "model.tmdl",
         "payload": _b64("annotation __PBI_AIInstructions = 'a'"),
         "payloadType": "InlineBase64"},
        {"path": "tables/Sales.tmdl",
         "payload": _b64("annotation VerifiedAnswers = 'b'"),
         "payloadType": "InlineBase64"},
    ]
    client = TMDLClient(_fake_credential(), workspace_id="ws")
    result = client.find_prep_for_ai_settings(_mock_definition(parts))
    assert result is not None
    paths = [m["path"] for m in result["matches"]]
    assert "model.tmdl" in paths
    assert "tables/Sales.tmdl" in paths


# ---------------------------------------------------------------------------
# get_definition (HTTP path mocked)
# ---------------------------------------------------------------------------

def test_get_definition_calls_correct_url_and_parses_json():
    expected = _mock_definition([
        {"path": "model.tmdl", "payload": _b64("model X"), "payloadType": "InlineBase64"},
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
# Helpers
# ---------------------------------------------------------------------------

def test_decode_part_text_returns_none_for_missing_payload():
    assert _decode_part_text({"path": "x"}) is None


def test_decode_part_text_decodes_base64():
    part = {"payload": _b64("hello"), "payloadType": "InlineBase64"}
    assert _decode_part_text(part) == "hello"


def test_prep_for_ai_hints_include_pbi_namespace():
    assert "__PBI_AIInstructions" in PREP_FOR_AI_HINTS
    assert "__PBI_VerifiedAnswers" in PREP_FOR_AI_HINTS
