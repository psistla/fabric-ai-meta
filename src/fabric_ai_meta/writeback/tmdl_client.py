"""Read-only client for the Fabric REST API semantic model definition endpoints.

Research-spike companion to ``docs/research/tmdl-prep-for-ai-spike.md``. The
goal is to inspect the TMDL definition returned by ``getDefinition`` and look
for AI Instructions and Verified Answers, the two Prep for AI primitives that
have no public object-level API.

This module deliberately does not implement ``updateDefinition``: write paths
are out of scope until the spike confirms that the settings actually live in
the TMDL payload.
"""

from __future__ import annotations

import base64
import json
from typing import Any
from urllib import error as urllib_error
from urllib import request as urllib_request

FABRIC_API_BASE = "https://api.fabric.microsoft.com/v1"

# Annotation keys / property names worth searching for. The spike hypothesis is
# that Microsoft persists Prep for AI configuration as model-level annotations
# under the __PBI_ namespace (consistent with prior linguistic-schema patterns).
PREP_FOR_AI_HINTS = (
    "__PBI_AIInstructions",
    "__PBI_VerifiedAnswers",
    "AIInstructions",
    "VerifiedAnswers",
    "ai_instructions",
    "verified_answers",
)


class TMDLClient:
    """Lightweight client for ``getDefinition`` and TMDL parsing helpers."""

    def __init__(self, credential: Any, workspace_id: str):
        self.credential = credential
        self.workspace_id = workspace_id

    def get_definition(self, model_id: str) -> dict:
        """Call ``POST .../semanticModels/{id}/getDefinition`` and return the JSON body.

        Returns the raw response shape:

        ``{"definition": {"parts": [{"path": ..., "payload": <base64>, "payloadType": ...}, ...]}}``
        """
        url = (
            f"{FABRIC_API_BASE}/workspaces/{self.workspace_id}"
            f"/semanticModels/{model_id}/getDefinition"
        )
        token = _get_token(self.credential)
        req = urllib_request.Request(
            url,
            data=b"",
            method="POST",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib_request.urlopen(req) as resp:
                body = resp.read().decode("utf-8")
        except urllib_error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(
                f"getDefinition failed: HTTP {exc.code} {exc.reason}: {detail}"
            ) from exc
        return json.loads(body)

    def list_definition_files(self, model_id: str) -> list[str]:
        """Return the list of TMDL file paths inside the model definition."""
        definition = self.get_definition(model_id)
        return _extract_paths(definition)

    def find_prep_for_ai_settings(self, definition: dict) -> dict | None:
        """Search the TMDL parts for AI Instructions / Verified Answers hints.

        Returns ``{"matches": [{"path": ..., "hint": ..., "snippet": ...}, ...]}``
        when one or more candidate strings appear in any decoded TMDL file.
        Returns ``None`` when no hints are found.

        Best-effort. The decisive verification (whether the matched string
        actually represents a Prep for AI setting) belongs in the notebook
        spike, not this code.
        """
        matches: list[dict] = []
        for part in _iter_parts(definition):
            text = _decode_part_text(part)
            if text is None:
                continue
            for hint in PREP_FOR_AI_HINTS:
                if hint in text:
                    matches.append({
                        "path": part.get("path", "<unknown>"),
                        "hint": hint,
                        "snippet": _snippet_around(text, hint),
                    })
        if not matches:
            return None
        return {"matches": matches}


def _extract_paths(definition: dict) -> list[str]:
    return [
        str(part.get("path"))
        for part in _iter_parts(definition)
        if part.get("path") is not None
    ]


def _iter_parts(definition: dict):
    return ((definition or {}).get("definition") or {}).get("parts") or []


def _decode_part_text(part: dict) -> str | None:
    payload = part.get("payload")
    if payload is None:
        return None
    payload_type = part.get("payloadType", "InlineBase64")
    if payload_type != "InlineBase64":
        return None
    try:
        return base64.b64decode(payload).decode("utf-8", errors="replace")
    except Exception:
        return None


def _snippet_around(text: str, needle: str, radius: int = 120) -> str:
    idx = text.find(needle)
    if idx == -1:
        return ""
    start = max(0, idx - radius)
    end = min(len(text), idx + len(needle) + radius)
    return text[start:end]


def _get_token(credential: Any) -> str:
    """Extract a bearer token from an azure.identity-style credential."""
    if credential is None:
        raise RuntimeError(
            "TMDLClient requires an explicit credential. Inside Fabric, use "
            "notebookutils.credentials.getToken('pbi') or pass an azure.identity "
            "credential acquired with the Fabric / Power BI scope."
        )
    if isinstance(credential, str):
        return credential
    token_obj = credential.get_token("https://api.fabric.microsoft.com/.default")
    return token_obj.token
