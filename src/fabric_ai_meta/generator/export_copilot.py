"""Mirror Microsoft's Copilot/ folder layout under {output_dir}/{model-slug}/copilot/.

Exporter for the Prep for AI primitives (AI Instructions, Verified Answers,
AI Data Schema, example prompts, settings, version). Read-only; companion to
the future CopilotWriter that does the inverse via updateDefinition.
"""

from __future__ import annotations

import json
import os
from typing import ClassVar

from fabric_ai_meta.generator.base import BaseExporter, ExporterError, _slugify
from fabric_ai_meta.models.metadata import SemanticModelMeta


class CopilotExporter(BaseExporter):
    name: ClassVar[str] = "copilot"
    # write() is fully overridden; output is a directory tree, not a single file.
    output_filename: ClassVar[str] = ""
    description: ClassVar[str] = (
        "Microsoft Copilot/ folder mirror (AI Instructions, Verified Answers, "
        "AI Data Schema, example prompts, settings, version)."
    )

    def generate(self, model: SemanticModelMeta) -> dict:
        """JSON-serializable view of the bundle. Used by tests and future schema validation."""
        if model.copilot is None:
            raise ExporterError(
                "model.copilot is None. Re-run extract with with_copilot=True "
                "(CLI: --with-copilot, or use `fabric-ai-meta export copilot`)."
            )
        return model.copilot.to_dict()

    def write(self, model: SemanticModelMeta, output_dir: str) -> str:
        """Write the Copilot/ folder layout under {output_dir}/{slug}/copilot/.

        Returns the absolute path of the copilot/ directory on success, or an
        empty string if the bundle had nothing to write (no primitives present).
        """
        if model.copilot is None:
            raise ExporterError(
                "model.copilot is None. Re-run extract with with_copilot=True."
            )

        slug = _slugify(model.name) if model.name else "model"
        copilot_dir = os.path.join(output_dir, slug, "copilot")
        b = model.copilot
        wrote = False

        if b.ai_instructions is not None:
            instr_dir = os.path.join(copilot_dir, "Instructions")
            os.makedirs(instr_dir, exist_ok=True)
            with open(os.path.join(instr_dir, "instructions.md"), "wb") as f:
                f.write(b.ai_instructions.raw_bytes)
            wrote = True

        if b.ai_data_schema is not None:
            os.makedirs(copilot_dir, exist_ok=True)
            with open(os.path.join(copilot_dir, "schema.json"), "w", encoding="utf-8") as f:
                json.dump(b.ai_data_schema.raw, f, indent=2)
            wrote = True

        if b.example_prompts is not None:
            os.makedirs(copilot_dir, exist_ok=True)
            with open(os.path.join(copilot_dir, "examplePrompts.json"), "w", encoding="utf-8") as f:
                json.dump(b.example_prompts.raw, f, indent=2)
            wrote = True

        if b.settings is not None:
            os.makedirs(copilot_dir, exist_ok=True)
            with open(os.path.join(copilot_dir, "settings.json"), "w", encoding="utf-8") as f:
                json.dump(b.settings.raw, f, indent=2)
            wrote = True

        if b.version is not None:
            os.makedirs(copilot_dir, exist_ok=True)
            with open(os.path.join(copilot_dir, "version.json"), "w", encoding="utf-8") as f:
                json.dump(b.version.raw, f, indent=2)
            wrote = True

        if b.verified_answers:
            va_dir = os.path.join(copilot_dir, "VerifiedAnswers")
            os.makedirs(va_dir, exist_ok=True)
            for va in b.verified_answers:
                with open(os.path.join(va_dir, va.filename), "w", encoding="utf-8") as f:
                    json.dump(va.raw, f, indent=2)
            wrote = True

        return copilot_dir if wrote else ""
