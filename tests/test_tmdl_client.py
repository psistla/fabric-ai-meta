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


# ---------------------------------------------------------------------------
# update_definition (HTTP path + LRO polling mocked)
# ---------------------------------------------------------------------------

def _http_response(body: bytes = b"", status: int = 200, headers: dict | None = None):
    """Build a context-manager response object compatible with urlopen."""
    resp = MagicMock()
    resp.read.return_value = body
    resp.status = status
    resp.getcode.return_value = status
    resp.headers = headers or {}
    resp.getheader = lambda name, default=None: (headers or {}).get(name, default)
    resp.__enter__ = lambda self: self
    resp.__exit__ = lambda self, *a: None
    return resp


def test_update_definition_polls_lro_until_succeeded():
    op_url = "https://api.fabric.microsoft.com/v1/operations/op-123"
    responses = [
        # POST updateDefinition → 202 with Location
        _http_response(status=202, headers={"Location": op_url, "Retry-After": "0"}),
        # GET op-status → Running
        _http_response(body=json.dumps({"status": "Running"}).encode("utf-8")),
        # GET op-status → Succeeded
        _http_response(body=json.dumps({"status": "Succeeded"}).encode("utf-8")),
    ]
    new_def = {"definition": {"parts": [
        {"path": "definition/model.tmdl", "payload": _b64("model"),
         "payloadType": "InlineBase64"},
    ]}}
    with patch("fabric_ai_meta.writeback.tmdl_client.urllib_request.urlopen",
               side_effect=responses) as mock_urlopen:
        client = TMDLClient(_fake_credential(), workspace_id="ws-1")
        status = client.update_definition("model-1", new_def, poll_interval_seconds=0)
    assert status["status"] == "Succeeded"
    # POST + 2 polls = 3 calls
    assert mock_urlopen.call_count == 3
    post_req = mock_urlopen.call_args_list[0][0][0]
    assert post_req.method == "POST"
    assert "semanticModels/model-1/updateDefinition" in post_req.full_url


def test_update_definition_raises_on_failed_lro():
    op_url = "https://api.fabric.microsoft.com/v1/operations/op-fail"
    responses = [
        _http_response(status=202, headers={"Location": op_url}),
        _http_response(body=json.dumps({
            "status": "Failed",
            "error": {"code": "InvalidPayload", "message": "bad parts"},
        }).encode("utf-8")),
    ]
    with patch("fabric_ai_meta.writeback.tmdl_client.urllib_request.urlopen",
               side_effect=responses):
        client = TMDLClient(_fake_credential(), workspace_id="ws")
        with pytest.raises(RuntimeError, match="Failed"):
            client.update_definition("m", {"definition": {"parts": []}},
                                     poll_interval_seconds=0)


def test_update_definition_synchronous_200_no_polling():
    """A 200 response means the LRO completed synchronously; no polling needed."""
    responses = [_http_response(status=200, body=b"")]
    with patch("fabric_ai_meta.writeback.tmdl_client.urllib_request.urlopen",
               side_effect=responses) as mock_urlopen:
        client = TMDLClient(_fake_credential(), workspace_id="ws")
        status = client.update_definition("m", {"definition": {"parts": []}},
                                          poll_interval_seconds=0)
    assert status["status"] == "Succeeded"
    assert mock_urlopen.call_count == 1


def test_update_definition_raises_on_http_error():
    from urllib.error import HTTPError

    err = HTTPError(
        url="http://x", code=403, msg="Forbidden", hdrs=None,
        fp=MagicMock(read=lambda: b'{"error":"no write permission"}'),
    )
    with patch("fabric_ai_meta.writeback.tmdl_client.urllib_request.urlopen",
               side_effect=err):
        client = TMDLClient(_fake_credential(), workspace_id="ws")
        with pytest.raises(RuntimeError, match="updateDefinition failed"):
            client.update_definition("m", {"definition": {"parts": []}},
                                     poll_interval_seconds=0)


def test_update_definition_raises_on_lro_timeout():
    op_url = "https://api.fabric.microsoft.com/v1/operations/op-stuck"
    # First the 202, then unlimited "Running" responses.
    post_resp = _http_response(status=202, headers={"Location": op_url})
    running_resp = _http_response(body=json.dumps({"status": "Running"}).encode("utf-8"))

    def side_effect(*args, **kwargs):
        # First call returns POST response, all subsequent return Running.
        if not getattr(side_effect, "called_post", False):
            side_effect.called_post = True
            return post_resp
        return running_resp

    with patch("fabric_ai_meta.writeback.tmdl_client.urllib_request.urlopen",
               side_effect=side_effect):
        client = TMDLClient(_fake_credential(), workspace_id="ws")
        with pytest.raises(RuntimeError, match="timed out"):
            client.update_definition(
                "m",
                {"definition": {"parts": []}},
                poll_interval_seconds=0,
                timeout_seconds=0.001,
            )
