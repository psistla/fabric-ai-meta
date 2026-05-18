"""Exporter plugin contract.

Subclass `BaseExporter` and register the class via the `fabric_ai_meta.exporters`
Python entry-point group to make a custom exporter available as
`fabric-ai-meta export <name>`. See `docs/plugin-development.md` for a walk-through.
"""

import json
import os
import re
from abc import ABC, abstractmethod
from typing import ClassVar

from fabric_ai_meta.models.metadata import SemanticModelMeta


class ExporterError(Exception):
    """Raised when an exporter cannot generate or write its payload."""


def _slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


class BaseExporter(ABC):
    """Subclass to publish a custom exporter as a Python entry point.

    Attributes:
        name: short identifier; becomes the CLI subcommand name. Must be unique
            within the registry. Plugin-supplied exporters override built-ins of
            the same name (documented behavior, not a bug).
        output_filename: default file name written under `{output_dir}/{model-slug}/`.
        description: one-line description shown in `export --help`.
    """

    name: ClassVar[str] = ""
    output_filename: ClassVar[str] = ""
    description: ClassVar[str] = ""
    # When True, the CLI calls `extractor.extract(..., with_copilot=True)` so the
    # exporter can rely on `model.copilot` being populated. Override per exporter.
    requires_copilot: ClassVar[bool] = False

    @abstractmethod
    def generate(self, model: SemanticModelMeta) -> dict:
        """Return the exporter's payload as a JSON-serializable dict."""

    def write(self, model: SemanticModelMeta, output_dir: str) -> str:
        """Serialize `generate(model)` to `{output_dir}/{model-slug}/{output_filename}`.

        Override only if the exporter needs a non-JSON output format. Returns the
        absolute path of the file written.
        """
        if not self.name:
            raise ExporterError(f"{type(self).__name__} is missing a `name` attribute")
        if not self.output_filename:
            raise ExporterError(f"{type(self).__name__} is missing an `output_filename` attribute")

        payload = self.generate(model)
        slug = _slugify(model.name) if model.name else "model"
        target_dir = os.path.join(output_dir, slug)
        os.makedirs(target_dir, exist_ok=True)
        path = os.path.join(target_dir, self.output_filename)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        return path
