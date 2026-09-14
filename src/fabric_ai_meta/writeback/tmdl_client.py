"""Client for the Fabric REST API semantic model definition endpoints.

The endpoints ``getDefinition`` and ``updateDefinition`` return the model
as a flat list of parts: TMDL files under ``definition/``, AI / Copilot
artifacts under ``Copilot/``, plus project metadata. Prep for AI primitives
live in the ``Copilot/`` tree:

- ``Copilot/Instructions/instructions.md``: AI Instructions (Markdown)
- ``Copilot/schema.json``: AI Data Schema
- ``Copilot/VerifiedAnswers/*``: Verified Answers
- ``Copilot/examplePrompts.json``: example prompts shown to users
- ``Copilot/settings.json`` / ``Copilot/version.json``: Copilot config / schema version
"""

from __future__ import annotations

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
PRIMITIVE_BY_PREFIX: dict[str, str] = {
    "Copilot/Instructions/": "ai_instructions",
    "Copilot/VerifiedAnswers/": "verified_answers",
    "Copilot/schema.json": "ai_data_schema",
    "Copilot/examplePrompts.json": "example_prompts",
    "Copilot/settings.json": "copilot_settings",
    "Copilot/version.json": "copilot_version",
}
COPILOT_PATH_PREFIXES: tuple[str, ...] = tuple(PRIMITIVE_BY_PREFIX)


class TMDLClient:
    """Client for ``getDefinition`` and ``updateDefinition``.

    Despite the name, the envelope carries TMDL and ``Copilot/`` parts alike.
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
