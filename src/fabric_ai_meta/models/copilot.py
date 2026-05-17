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
