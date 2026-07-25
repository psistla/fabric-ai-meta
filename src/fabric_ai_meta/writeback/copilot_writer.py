"""Copilot artifact writeback to Fabric semantic models.

Closes the loop between a parsed `CopilotBundle` (the read half shipped in
v1.4.0) and a live model's `Copilot/` folder. The `MockCopilotWriter` records
planned changes without touching any service; the `SemanticLinkCopilotWriter`
fetches the live model definition, splices in the new Copilot parts, and
posts the result through the Fabric REST `updateDefinition` long-running
operation.

Write semantics: the bundle is the new source of truth for the entire
`Copilot/` subtree. Existing Copilot parts not present in the bundle are
deleted. Non-Copilot parts (TMDL, project metadata) are preserved byte-for-byte.
"""

from __future__ import annotations

import base64
import dataclasses
import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from fabric_ai_meta.auth.entra import (
    FabricEnvironmentError,
    detect_notebook_environment,
)
from fabric_ai_meta.models.copilot import CopilotBundle
from fabric_ai_meta.writeback.tmdl_client import TMDLClient

logger = logging.getLogger(__name__)


@dataclass
class CopilotWritebackResult:
    """Outcome of an apply_copilot call.

    ``succeeded`` is True iff the write was actually applied without errors;
    dry-run and mock callers also report ``succeeded=True``. A failed live
    write reports ``dry_run=False, succeeded=False, errors=[...]``.
    """

    ai_instructions_updated: bool = False
    verified_answers_written: int = 0
    ai_data_schema_updated: bool = False
    example_prompts_updated: bool = False
    settings_updated: bool = False
    version_updated: bool = False
    total_changes: int = 0
    changes: list[dict] = field(default_factory=list)
    dry_run: bool = True
    succeeded: bool = True
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)


class CopilotWriter(ABC):
    """Abstract writer that applies a CopilotBundle to a semantic model."""

    @abstractmethod
    def apply_copilot(
        self,
        bundle: CopilotBundle,
        model_name: str,
        workspace: str,
        dry_run: bool = True,
    ) -> CopilotWritebackResult:
        """Apply a CopilotBundle to a semantic model.

        Args:
            bundle: Source of truth for the new Copilot/ folder contents.
            model_name: Name of the semantic model.
            workspace: Workspace name or id.
            dry_run: When True, return what would change without writing.
        """


# ---------------------------------------------------------------------------
# Bundle → parts and envelope splice helpers (pure functions)
# ---------------------------------------------------------------------------

def _b64_encode(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def _json_part(path: str, raw: Any) -> dict:
    return {
        "path": path,
        "payload": _b64_encode(json.dumps(raw).encode("utf-8")),
        "payloadType": "InlineBase64",
    }


def _safe_va_filename(filename: str) -> str:
    """Reject filenames that could escape the VerifiedAnswers/ subtree.

    Path-traversal segments (``..``), absolute paths, and embedded separators
    are all rejected. ``os.listdir`` returns safe basenames in normal use, but
    a programmatic ``VerifiedAnswer(filename=...)`` constructor can bypass
    that guarantee, so the writer must validate.
    """
    import os
    if not filename or filename != os.path.basename(filename):
        raise ValueError(
            f"Unsafe verified-answer filename {filename!r}: must be a basename "
            "with no directory separators or '..' segments."
        )
    if ".." in filename or "/" in filename or "\\" in filename:
        raise ValueError(f"Unsafe verified-answer filename {filename!r}.")
    return filename


def _bundle_to_copilot_parts(bundle: CopilotBundle) -> list[dict]:
    """Serialize a CopilotBundle into Fabric ``definition.parts`` entries.

    The output is in the Inline base64 wire format accepted by
    ``updateDefinition``. AI Instructions uses ``raw_bytes`` (byte-perfect)
    rather than re-encoding ``markdown``, to preserve any non-UTF-8-clean
    content from the original model.

    Raises:
        ValueError: when a ``VerifiedAnswer.filename`` is not a safe basename.
    """
    parts: list[dict] = []

    if bundle.ai_instructions is not None:
        parts.append({
            "path": "Copilot/Instructions/instructions.md",
            "payload": _b64_encode(bundle.ai_instructions.raw_bytes),
            "payloadType": "InlineBase64",
        })

    for va in bundle.verified_answers:
        safe_name = _safe_va_filename(va.filename)
        parts.append(_json_part(
            f"Copilot/VerifiedAnswers/{safe_name}", va.raw
        ))

    if bundle.ai_data_schema is not None:
        parts.append(_json_part("Copilot/schema.json", bundle.ai_data_schema.raw))

    if bundle.example_prompts is not None:
        parts.append(_json_part(
            "Copilot/examplePrompts.json", bundle.example_prompts.raw
        ))

    if bundle.settings is not None:
        parts.append(_json_part("Copilot/settings.json", bundle.settings.raw))

    if bundle.version is not None:
        parts.append(_json_part("Copilot/version.json", bundle.version.raw))

    return parts


def _primitive_for_path(path: str) -> str:
    from fabric_ai_meta.writeback.tmdl_client import (
        COPILOT_PATH_PREFIXES,
        PRIMITIVE_BY_PREFIX,
    )
    for prefix in COPILOT_PATH_PREFIXES:
        if path.startswith(prefix):
            return PRIMITIVE_BY_PREFIX[prefix]
    return "unknown"


def splice_copilot_into_envelope(
    existing_envelope: dict,
    bundle: CopilotBundle,
) -> tuple[dict, list[dict]]:
    """Return a new envelope with the Copilot/ subtree replaced by ``bundle``.

    All non-Copilot parts (TMDL under ``definition/``, project metadata) are
    preserved unchanged. The returned ``changes`` list categorizes each
    affected Copilot path as ``create``, ``update``, or ``delete``.
    """
    existing_parts = ((existing_envelope or {}).get("definition") or {}).get("parts") or []
    new_copilot_parts = _bundle_to_copilot_parts(bundle)

    # Drop parts with no usable `path`; they cannot be matched, replaced, or
    # round-tripped, and the upstream API would reject them anyway.
    existing_parts = [
        p for p in existing_parts if str(p.get("path") or "")
    ]

    existing_by_path = {
        str(p["path"]): p for p in existing_parts
        if str(p["path"]).startswith("Copilot/")
    }
    new_by_path = {str(p.get("path") or ""): p for p in new_copilot_parts}

    changes: list[dict] = []
    for path in new_by_path:
        op = "update" if path in existing_by_path else "create"
        changes.append({
            "path": path,
            "operation": op,
            "primitive": _primitive_for_path(path),
        })

    for path in existing_by_path:
        if path not in new_by_path:
            changes.append({
                "path": path,
                "operation": "delete",
                "primitive": _primitive_for_path(path),
            })

    spliced_parts = [
        p for p in existing_parts
        if not str(p["path"]).startswith("Copilot/")
    ] + new_copilot_parts

    new_envelope = {"definition": {"parts": spliced_parts}}
    return new_envelope, changes


# ---------------------------------------------------------------------------
# Writers
# ---------------------------------------------------------------------------

def _counts_from_bundle(bundle: CopilotBundle) -> dict:
    return {
        "ai_instructions_updated": bundle.ai_instructions is not None,
        "verified_answers_written": len(bundle.verified_answers),
        "ai_data_schema_updated": bundle.ai_data_schema is not None,
        "example_prompts_updated": bundle.example_prompts is not None,
        "settings_updated": bundle.settings is not None,
        "version_updated": bundle.version is not None,
    }


class MockCopilotWriter(CopilotWriter):
    """Local writer that records planned changes without touching any service.

    Always reports ``dry_run=True`` regardless of the ``dry_run`` argument,
    since no live target exists to write against. Uses the bundle directly
    (no diff against an existing envelope), so every primitive present in
    the bundle is reported as a ``write`` op.
    """

    def apply_copilot(
        self,
        bundle: CopilotBundle,
        model_name: str,
        workspace: str,
        dry_run: bool = True,
    ) -> CopilotWritebackResult:
        # Mock has no live envelope to diff against, so every primitive in the
        # bundle is reported as `create`. Matches the create/update/delete
        # vocabulary used by `SemanticLinkCopilotWriter`.
        changes = [
            {
                "path": p["path"],
                "operation": "create",
                "primitive": _primitive_for_path(p["path"]),
            }
            for p in _bundle_to_copilot_parts(bundle)
        ]
        return CopilotWritebackResult(
            **_counts_from_bundle(bundle),
            total_changes=len(changes),
            changes=changes,
            dry_run=True,
            succeeded=True,
            errors=[],
        )


def _load_sempy_fabric():
    """Lazy import sempy.fabric (only available in Fabric notebook runtime)."""
    try:
        import sempy.fabric as fabric  # noqa: PLC0415
    except ImportError as exc:
        from fabric_ai_meta.auth.entra import MissingFabricDependencyError
        raise MissingFabricDependencyError("semantic-link-sempy") from exc
    return fabric


def _fabric_bearer_token() -> str:
    """Obtain a Power BI / Fabric bearer token from the Fabric notebook runtime."""
    import notebookutils  # type: ignore[import-not-found]  # noqa: PLC0415
    return notebookutils.credentials.getToken("pbi")


class SemanticLinkCopilotWriter(CopilotWriter):
    """Fabric-runtime writer that applies a CopilotBundle through the REST API.

    Pipeline:
      1. Resolve workspace and model ids via ``sempy.fabric`` helpers.
      2. Call ``getDefinition`` to fetch the current envelope.
      3. Splice the bundle's Copilot parts in, preserving non-Copilot parts.
      4. In dry-run mode, stop and report the diff.
      5. Otherwise, POST ``updateDefinition`` and poll the LRO to completion.
    """

    def __init__(self) -> None:
        if not detect_notebook_environment():
            raise FabricEnvironmentError()

    def apply_copilot(
        self,
        bundle: CopilotBundle,
        model_name: str,
        workspace: str,
        dry_run: bool = True,
    ) -> CopilotWritebackResult:
        fabric = _load_sempy_fabric()

        workspace_id = fabric.resolve_workspace_id(workspace)
        if not workspace_id:
            raise RuntimeError(
                f"Could not resolve workspace id for {workspace!r}; "
                "verify the workspace name and that the caller has access."
            )

        model_id = fabric.resolve_item_id(
            model_name, type="SemanticModel", workspace=workspace
        )
        if not model_id:
            raise RuntimeError(
                f"Could not resolve model id for {model_name!r} in workspace "
                f"{workspace!r}; verify the model name."
            )

        token = _fabric_bearer_token()
        client = TMDLClient(token, workspace_id)
        existing_envelope = client.get_definition(model_id)
        new_envelope, changes = splice_copilot_into_envelope(
            existing_envelope, bundle
        )

        counts = _counts_from_bundle(bundle)
        errors: list[str] = []
        succeeded = True

        if not dry_run:
            try:
                client.update_definition(model_id, new_envelope)
            except Exception as exc:
                errors.append(str(exc))
                succeeded = False
                logger.warning("updateDefinition failed for %r: %s", model_name, exc)

        return CopilotWritebackResult(
            **counts,
            total_changes=len(changes),
            changes=changes,
            dry_run=dry_run,
            succeeded=succeeded,
            errors=errors,
        )
