"""Dataclasses representing Microsoft Fabric Copilot / Prep for AI primitives.

Every JSON-shaped primitive keeps a `raw: dict` escape hatch alongside any
typed fields the parser is confident about. Adding inferred fields later is
not a breaking change since consumers that read `raw` directly are unaffected.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class AIInstructions:
    """Copilot/Instructions/instructions.md content.

    `markdown` is a best-effort UTF-8 decode of `raw_bytes`. Use `raw_bytes`
    for byte-perfect round-trips back to the model.
    """

    markdown: str
    raw_bytes: bytes


@dataclass
class VerifiedAnswer:
    """One file under Copilot/VerifiedAnswers/.

    `filename` is the basename (e.g. `"answer-001.json"`), not the full
    `Copilot/VerifiedAnswers/...` part path. `question` is a best-effort
    extraction; `raw` is always the full parsed JSON.
    """

    filename: str
    question: str | None
    raw: dict[str, Any]


@dataclass
class AIDataSchema:
    """Copilot/schema.json - the AI Data Schema (tables/columns Copilot sees)."""

    raw: dict[str, Any]


@dataclass
class ExamplePrompts:
    """Copilot/examplePrompts.json - suggested prompts shown to users."""

    prompts: list[str]
    raw: dict[str, Any] | list[Any]


@dataclass
class CopilotSettings:
    """Copilot/settings.json - Copilot toggles and behavior flags."""

    raw: dict[str, Any]


@dataclass
class CopilotVersion:
    """Copilot/version.json - schema version of the Copilot folder."""

    raw: dict[str, Any]


@dataclass
class CopilotBundle:
    """All Prep for AI primitives for one semantic model.

    Every field is optional. A model may have AI Instructions and no Verified
    Answers, or vice versa. Empty fields stay `None` / `[]`.
    """

    ai_instructions: AIInstructions | None = None
    verified_answers: list[VerifiedAnswer] = field(default_factory=list)
    ai_data_schema: AIDataSchema | None = None
    example_prompts: ExamplePrompts | None = None
    settings: CopilotSettings | None = None
    version: CopilotVersion | None = None

    def signals(self) -> dict:
        """Governance signals derived from the bundle contents.

        Stable, JSON-safe scalars suitable for embedding in workspace-summary
        and governance reports. ``copilot_enabled`` and ``copilot_version``
        are best-effort reads from the loosely-typed ``settings.json`` /
        ``version.json`` payloads; they remain ``None`` when the underlying
        primitive is absent or the expected field is missing.
        """
        ai_data_schema_table_count = 0
        if self.ai_data_schema is not None:
            raw = self.ai_data_schema.raw
            tables = raw.get("tables") if isinstance(raw, dict) else None
            if isinstance(tables, list):
                ai_data_schema_table_count = len(tables)

        copilot_enabled: bool | None = None
        if self.settings is not None and isinstance(self.settings.raw, dict):
            val = self.settings.raw.get("enabled")
            if isinstance(val, bool):
                copilot_enabled = val

        copilot_version: str | None = None
        if self.version is not None and isinstance(self.version.raw, dict):
            val = self.version.raw.get("version")
            if isinstance(val, (str, int, float)):
                copilot_version = str(val)

        return {
            "has_ai_instructions": self.ai_instructions is not None,
            "ai_instructions_length": (
                len(self.ai_instructions.markdown)
                if self.ai_instructions is not None
                else 0
            ),
            "verified_answer_count": len(self.verified_answers),
            "ai_data_schema_table_count": ai_data_schema_table_count,
            "example_prompt_count": (
                len(self.example_prompts.prompts)
                if self.example_prompts is not None
                else 0
            ),
            "copilot_enabled": copilot_enabled,
            "copilot_version": copilot_version,
        }

    def to_dict(self) -> dict:
        """JSON-serializable view. Omits `AIInstructions.raw_bytes` (not JSON-safe)."""
        return {
            "ai_instructions": (
                {"markdown": self.ai_instructions.markdown}
                if self.ai_instructions is not None
                else None
            ),
            "verified_answers": [
                {"filename": va.filename, "question": va.question, "raw": va.raw}
                for va in self.verified_answers
            ],
            "ai_data_schema": (
                {"raw": self.ai_data_schema.raw}
                if self.ai_data_schema is not None
                else None
            ),
            "example_prompts": (
                {"prompts": self.example_prompts.prompts, "raw": self.example_prompts.raw}
                if self.example_prompts is not None
                else None
            ),
            "settings": (
                {"raw": self.settings.raw} if self.settings is not None else None
            ),
            "version": (
                {"raw": self.version.raw} if self.version is not None else None
            ),
        }

    @classmethod
    def from_dict(cls, data: dict | None) -> "CopilotBundle | None":
        """Inverse of `to_dict`. Returns `None` for `None`/empty input.

        `AIInstructions.raw_bytes` is recovered by UTF-8 encoding the
        round-tripped `markdown` string. This is only byte-identical when the
        original instructions were valid UTF-8, which they always are when
        produced by `CopilotReader.from_definition`; non-UTF-8 inputs survive
        as the UTF-8 encoding of the replacement-character decoded string.
        For byte-perfect round-trips, persist the envelope or use the on-disk
        layout via `CopilotExporter` + `CopilotReader.from_directory`.
        """
        if not data:
            return None
        bundle = cls()
        ai = data.get("ai_instructions")
        if isinstance(ai, dict) and "markdown" in ai:
            md = ai["markdown"]
            bundle.ai_instructions = AIInstructions(
                markdown=md, raw_bytes=md.encode("utf-8")
            )
        for va in data.get("verified_answers") or []:
            if not isinstance(va, dict):
                continue
            bundle.verified_answers.append(VerifiedAnswer(
                filename=va.get("filename", ""),
                question=va.get("question"),
                raw=va.get("raw") or {},
            ))
        schema = data.get("ai_data_schema")
        if isinstance(schema, dict) and "raw" in schema:
            bundle.ai_data_schema = AIDataSchema(raw=schema["raw"])
        prompts = data.get("example_prompts")
        if isinstance(prompts, dict) and "raw" in prompts:
            bundle.example_prompts = ExamplePrompts(
                prompts=list(prompts.get("prompts") or []),
                raw=prompts["raw"],
            )
        settings = data.get("settings")
        if isinstance(settings, dict) and "raw" in settings:
            bundle.settings = CopilotSettings(raw=settings["raw"])
        version = data.get("version")
        if isinstance(version, dict) and "raw" in version:
            bundle.version = CopilotVersion(raw=version["raw"])
        return bundle
