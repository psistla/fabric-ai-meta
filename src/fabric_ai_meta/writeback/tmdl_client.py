"""Client for the Fabric REST API semantic model definition endpoints.

The endpoints ``getDefinition`` and ``updateDefinition`` return the model
as a flat list of parts: TMDL files under ``definition/``, AI / Copilot
artifacts under ``Copilot/``, plus project metadata. This module focuses
on locating Prep for AI primitives, which live in the ``Copilot/`` tree:

- ``Copilot/Instructions/instructions.md``: AI Instructions (Markdown)
- ``Copilot/schema.json``: AI Data Schema
- ``Copilot/VerifiedAnswers/*``: Verified Answers
- ``Copilot/examplePrompts.json``: example prompts shown to users
- ``Copilot/settings.json`` / ``Copilot/version.json``: Copilot config / schema version

The class deliberately stops at read + locate. Writing back is out of
scope for the spike; see the research doc's "Recommendation" section
for the writer design (``CopilotWriter``) blocked on this finding.
"""

from __future__ import annotations

import base64
import json
import time
from typing import Any
from urllib import error as urllib_error
from urllib import request as urllib_request

FABRIC_API_BASE = "https://api.fabric.microsoft.com/v1"

# Path prefixes inside the model definition payload that identify Prep for AI
# primitives. Matched against the ``path`` of each part returned by
# ``getDefinition``. Verified against the Microsoft Learn reference for the
# Fabric REST SemanticModel definition envelope.
COPILOT_PATH_PREFIXES: tuple[str, ...] = (
    "Copilot/Instructions/",
    "Copilot/VerifiedAnswers/",
    "Copilot/schema.json",
    "Copilot/examplePrompts.json",
    "Copilot/settings.json",
    "Copilot/version.json",
)

PRIMITIVE_BY_PREFIX: dict[str, str] = {
    "Copilot/Instructions/": "ai_instructions",
    "Copilot/VerifiedAnswers/": "verified_answers",
    "Copilot/schema.json": "ai_data_schema",
    "Copilot/examplePrompts.json": "example_prompts",
    "Copilot/settings.json": "copilot_settings",
    "Copilot/version.json": "copilot_version",
}


class TMDLClient:
    """Client for ``getDefinition`` and helpers to locate Prep for AI parts.

    Read-only by design. Despite the name (kept for backward compatibility
    with the original spike), this client also surfaces ``Copilot/`` parts:
    ``getDefinition`` returns TMDL and Copilot files in the same envelope.
    """

    def __init__(self, credential: Any, workspace_id: str):
        self.credential = credential
        self.workspace_id = workspace_id

    def get_definition(self, model_id: str) -> dict:
        """Call ``POST .../semanticModels/{id}/getDefinition``.

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

    # Floor for poll interval in production to prevent tight loops that would
    # rate-limit the Fabric API. Tests opt out by passing 0 explicitly.
    _MIN_POLL_INTERVAL_SECONDS = 0.5

    def update_definition(
        self,
        model_id: str,
        definition: dict,
        *,
        poll_interval_seconds: float = 2.0,
        timeout_seconds: float = 300.0,
    ) -> dict:
        """Call ``POST .../semanticModels/{id}/updateDefinition`` and wait for LRO.

        ``definition`` must already be in the envelope shape ``{"definition":
        {"parts": [...]}}`` accepted by the Fabric REST API. The call is
        long-running: a 202 returns a ``Location`` header pointing at the
        operation status endpoint, which is polled until the status is
        terminal. A synchronous 200 response is treated as immediate success.

        Returns the final operation-status dict (with ``status: "Succeeded"``).

        Raises:
            RuntimeError: On HTTP error, on ``Failed`` LRO terminal status, or
                when polling exceeds ``timeout_seconds``.
        """
        url = (
            f"{FABRIC_API_BASE}/workspaces/{self.workspace_id}"
            f"/semanticModels/{model_id}/updateDefinition"
        )
        token = _get_token(self.credential)
        body = json.dumps(definition).encode("utf-8")
        req = urllib_request.Request(
            url,
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib_request.urlopen(req) as resp:
                status_code = getattr(resp, "status", None) or resp.getcode()
                location = resp.getheader("Location") if hasattr(resp, "getheader") else None
        except urllib_error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(
                f"updateDefinition failed: HTTP {exc.code} {exc.reason}: {detail}"
            ) from exc

        if status_code == 200 or not location:
            return {"status": "Succeeded"}

        # Floor poll interval in production. Tests opt out with poll_interval_seconds=0.
        effective_interval = poll_interval_seconds
        if 0 < effective_interval < self._MIN_POLL_INTERVAL_SECONDS:
            effective_interval = self._MIN_POLL_INTERVAL_SECONDS

        return self._poll_lro(
            location, token,
            poll_interval_seconds=effective_interval,
            timeout_seconds=timeout_seconds,
        )

    def _poll_lro(
        self,
        operation_url: str,
        token: str,
        *,
        poll_interval_seconds: float,
        timeout_seconds: float,
    ) -> dict:
        deadline = time.monotonic() + timeout_seconds
        while True:
            req = urllib_request.Request(
                operation_url,
                method="GET",
                headers={"Authorization": f"Bearer {token}"},
            )
            try:
                with urllib_request.urlopen(req) as resp:
                    payload = resp.read().decode("utf-8")
            except urllib_error.HTTPError as exc:
                detail = exc.read().decode("utf-8", errors="replace")
                raise RuntimeError(
                    f"LRO status poll failed: HTTP {exc.code} {exc.reason}: {detail}"
                ) from exc

            try:
                status_body = json.loads(payload) if payload else {}
            except json.JSONDecodeError:
                status_body = {}
            state = str(status_body.get("status") or "").lower()
            if state == "succeeded":
                return status_body
            if state == "failed":
                err = status_body.get("error") or {}
                raise RuntimeError(
                    f"updateDefinition LRO Failed: "
                    f"{err.get('code', 'Unknown')} {err.get('message', '')}".rstrip()
                )

            if time.monotonic() >= deadline:
                raise RuntimeError(
                    f"updateDefinition LRO timed out after {timeout_seconds:.1f}s "
                    f"(last status: {state or 'unknown'!r})"
                )
            if poll_interval_seconds > 0:
                time.sleep(poll_interval_seconds)

    def list_definition_files(self, model_id: str) -> list[str]:
        """Return the list of file paths inside the model definition."""
        definition = self.get_definition(model_id)
        return _extract_paths(definition)

    def find_prep_for_ai_settings(self, definition: dict) -> dict | None:
        """Locate AI Instructions, AI Data Schema, and Verified Answers.

        Matches each part's ``path`` against ``COPILOT_PATH_PREFIXES``. Returns
        ``{"matches": [{"path": ..., "primitive": ..., "snippet": ...}, ...]}``
        when at least one match is found; ``None`` otherwise.

        ``snippet`` is a short prefix of the decoded part contents to give the
        notebook reader a quick read on the file's shape (Markdown for
        instructions; JSON for everything else).
        """
        matches: list[dict] = []
        for part in _iter_parts(definition):
            path = str(part.get("path") or "")
            primitive = _primitive_for_path(path)
            if primitive is None:
                continue
            text = _decode_part_text(part)
            matches.append({
                "path": path,
                "primitive": primitive,
                "snippet": (text or "")[:240],
            })
        if not matches:
            return None
        return {"matches": matches}


def _primitive_for_path(path: str) -> str | None:
    for prefix, primitive in PRIMITIVE_BY_PREFIX.items():
        if path.startswith(prefix):
            return primitive
    return None


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
