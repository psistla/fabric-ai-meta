"""Parse a Fabric REST getDefinition response into a CopilotBundle.

Two entry points:
- ``CopilotReader.from_definition(envelope)`` — pure, no I/O.
- ``CopilotReader.from_directory(path)`` — load from an on-disk ``copilot/``
  folder (the inverse of ``CopilotExporter.write``).

Network and auth live in ``fabric_ai_meta.writeback.tmdl_client.TMDLClient``.

Read paths are deliberately lenient. A malformed individual part is logged
and skipped; the rest of the envelope still produces a valid CopilotBundle.
"""

from __future__ import annotations

import base64
import json
import logging
import os
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
    def from_directory(copilot_dir: str) -> CopilotBundle:
        """Load a CopilotBundle from an on-disk ``copilot/`` directory.

        Expects the layout produced by ``CopilotExporter.write``:

        - ``Instructions/instructions.md`` — bytes
        - ``VerifiedAnswers/*.json`` — JSON files
        - ``schema.json`` — JSON (AI Data Schema)
        - ``examplePrompts.json`` — JSON
        - ``settings.json`` — JSON
        - ``version.json`` — JSON

        Each file is optional. Missing files leave the corresponding bundle
        field as ``None`` / ``[]``. Malformed JSON in any single file is
        logged and skipped.
        """
        bundle = CopilotBundle()

        instr_path = os.path.join(copilot_dir, "Instructions", "instructions.md")
        if os.path.isfile(instr_path):
            with open(instr_path, "rb") as f:
                raw_bytes = f.read()
            try:
                markdown = raw_bytes.decode("utf-8")
            except UnicodeDecodeError:
                markdown = raw_bytes.decode("utf-8", errors="replace")
            bundle.ai_instructions = AIInstructions(markdown=markdown, raw_bytes=raw_bytes)

        schema_path = os.path.join(copilot_dir, "schema.json")
        if os.path.isfile(schema_path):
            raw = _read_json_or_none(schema_path)
            if raw is not None:
                bundle.ai_data_schema = AIDataSchema(raw=raw)

        prompts_path = os.path.join(copilot_dir, "examplePrompts.json")
        if os.path.isfile(prompts_path):
            raw = _read_json_or_none(prompts_path)
            if raw is not None:
                bundle.example_prompts = ExamplePrompts(
                    prompts=_extract_prompt_strings(raw), raw=raw
                )

        settings_path = os.path.join(copilot_dir, "settings.json")
        if os.path.isfile(settings_path):
            raw = _read_json_or_none(settings_path)
            if raw is not None:
                bundle.settings = CopilotSettings(raw=raw)

        version_path = os.path.join(copilot_dir, "version.json")
        if os.path.isfile(version_path):
            raw = _read_json_or_none(version_path)
            if raw is not None:
                bundle.version = CopilotVersion(raw=raw)

        va_dir = os.path.join(copilot_dir, "VerifiedAnswers")
        if os.path.isdir(va_dir):
            for fname in sorted(os.listdir(va_dir)):
                if not fname.endswith(".json"):
                    continue
                raw = _read_json_or_none(os.path.join(va_dir, fname))
                if raw is None:
                    continue
                question = _extract_question(raw)
                bundle.verified_answers.append(
                    VerifiedAnswer(filename=fname, question=question, raw=raw)
                )

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
        return VerifiedAnswer(
            filename=filename, question=_extract_question(raw), raw=raw
        )

    @staticmethod
    def _parse_ai_data_schema(part: dict) -> AIDataSchema:
        return AIDataSchema(raw=_decode_part_json(part))

    @staticmethod
    def _parse_example_prompts(part: dict) -> ExamplePrompts:
        raw = _decode_part_json(part)
        return ExamplePrompts(prompts=_extract_prompt_strings(raw), raw=raw)

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


def _read_json_or_none(path: str) -> Any:
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Skipping malformed JSON file %r: %s", path, exc)
        return None


def _extract_question(raw: Any) -> str | None:
    if not isinstance(raw, dict):
        return None
    for key in ("question", "Question", "questionText", "name", "Name"):
        if isinstance(raw.get(key), str):
            return raw[key]
    return None


def _extract_prompt_strings(raw: Any) -> list[str]:
    """Extract a flat list of prompt strings from the loosely-typed JSON."""
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
    return prompts
