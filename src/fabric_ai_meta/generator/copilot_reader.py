"""Parse a Fabric REST getDefinition response into a CopilotBundle.

Pure functions: no I/O, no network, no auth. Network and auth live in
`fabric_ai_meta.writeback.tmdl_client.TMDLClient`. Reader takes a dict,
returns a bundle.

Read paths are deliberately lenient. A malformed individual part is logged
and skipped; the rest of the envelope still produces a valid CopilotBundle.
"""

from __future__ import annotations

import base64
import json
import logging
from typing import Any

from fabric_ai_meta.models.copilot import (
    AIDataSchema,
    AIInstructions,
    CopilotBundle,
    CopilotSettings,
    CopilotVersion,
    ExamplePrompts,
    VerifiedAnswer,
)
from fabric_ai_meta.writeback.tmdl_client import COPILOT_PATH_PREFIXES, PRIMITIVE_BY_PREFIX

logger = logging.getLogger(__name__)


class CopilotReader:
    """Stateless parser for the Copilot/ folder inside a getDefinition envelope."""

    @staticmethod
    def from_definition(definition: dict) -> CopilotBundle:
        """Parse a getDefinition response into a CopilotBundle.

        Walks the parts list, dispatches each Copilot/ part to a primitive
        parser based on path prefix. Returns a CopilotBundle with populated
        fields where matching parts exist, defaults (None / []) otherwise.
        """
        bundle = CopilotBundle()

        for part in _iter_parts(definition):
            path = str(part.get("path") or "")
            primitive = _primitive_for_path(path)
            if primitive is None:
                continue
            try:
                if primitive == "ai_instructions":
                    bundle.ai_instructions = CopilotReader._parse_ai_instructions(part)
                elif primitive == "verified_answers":
                    bundle.verified_answers.append(CopilotReader._parse_verified_answer(part))
                elif primitive == "ai_data_schema":
                    bundle.ai_data_schema = CopilotReader._parse_ai_data_schema(part)
                elif primitive == "example_prompts":
                    bundle.example_prompts = CopilotReader._parse_example_prompts(part)
                elif primitive == "copilot_settings":
                    bundle.settings = CopilotReader._parse_copilot_settings(part)
                elif primitive == "copilot_version":
                    bundle.version = CopilotReader._parse_copilot_version(part)
            except Exception as exc:
                logger.warning(
                    "Skipping malformed Copilot part %r: %s", path, exc
                )
                continue

        # Sort verified answers deterministically by filename.
        bundle.verified_answers.sort(key=lambda va: va.filename)
        return bundle

    @staticmethod
    def _parse_ai_instructions(part: dict) -> AIInstructions:
        raw_bytes = _decode_part_bytes(part)
        try:
            markdown = raw_bytes.decode("utf-8")
        except UnicodeDecodeError:
            logger.warning(
                "AI Instructions payload is not valid UTF-8; using replacement decode."
            )
            markdown = raw_bytes.decode("utf-8", errors="replace")
        return AIInstructions(markdown=markdown, raw_bytes=raw_bytes)

    @staticmethod
    def _parse_verified_answer(part: dict) -> VerifiedAnswer:
        raw = _decode_part_json(part)
        path = str(part.get("path") or "")
        filename = path.rsplit("/", 1)[-1] if "/" in path else path
        question = None
        if isinstance(raw, dict):
            for key in ("question", "Question", "questionText", "name", "Name"):
                if isinstance(raw.get(key), str):
                    question = raw[key]
                    break
        return VerifiedAnswer(filename=filename, question=question, raw=raw)

    @staticmethod
    def _parse_ai_data_schema(part: dict) -> AIDataSchema:
        return AIDataSchema(raw=_decode_part_json(part))

    @staticmethod
    def _parse_example_prompts(part: dict) -> ExamplePrompts:
        raw = _decode_part_json(part)
        prompts: list[str] = []
        candidates: list[Any] = []
        if isinstance(raw, list):
            candidates = raw
        elif isinstance(raw, dict):
            for key in ("prompts", "examples", "items"):
                val = raw.get(key)
                if isinstance(val, list):
                    candidates = val
                    break
        for c in candidates:
            if isinstance(c, str):
                prompts.append(c)
            elif isinstance(c, dict):
                for key in ("prompt", "text", "value"):
                    if isinstance(c.get(key), str):
                        prompts.append(c[key])
                        break
        return ExamplePrompts(prompts=prompts, raw=raw)

    @staticmethod
    def _parse_copilot_settings(part: dict) -> CopilotSettings:
        return CopilotSettings(raw=_decode_part_json(part))

    @staticmethod
    def _parse_copilot_version(part: dict) -> CopilotVersion:
        return CopilotVersion(raw=_decode_part_json(part))


def _iter_parts(definition: dict):
    return ((definition or {}).get("definition") or {}).get("parts") or []


def _primitive_for_path(path: str) -> str | None:
    for prefix in COPILOT_PATH_PREFIXES:
        if path.startswith(prefix):
            return PRIMITIVE_BY_PREFIX[prefix]
    return None


def _decode_part_bytes(part: dict) -> bytes:
    payload = part.get("payload")
    payload_type = part.get("payloadType", "InlineBase64")
    if payload is None:
        raise ValueError("Copilot part has no 'payload'.")
    if payload_type != "InlineBase64":
        raise ValueError(f"Unsupported payloadType {payload_type!r}; expected InlineBase64.")
    return base64.b64decode(payload)


def _decode_part_json(part: dict) -> Any:
    return json.loads(_decode_part_bytes(part).decode("utf-8"))
