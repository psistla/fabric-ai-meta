"""Mock extractor that loads SemanticModelMeta from a JSON fixture file or directory."""

import json
import os
import re

from fabric_ai_meta.extractor.base import BaseExtractor
from fabric_ai_meta.generator.copilot_reader import CopilotReader
from fabric_ai_meta.models.metadata import SemanticModelMeta, from_dict


def _slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


class MockExtractor(BaseExtractor):
    """Loads SemanticModelMeta from JSON fixture files for local testing.

    Two modes (backward compatible):
    - fixture_path: single JSON file → loads one model
    - fixture_dir:  directory of *.json files → supports list_models() + extract() by name
    If neither is provided, defaults to the bundled sample models.
    """

    def __init__(
        self,
        fixture_path: str | None = None,
        fixture_dir: str | None = None,
    ) -> None:
        if fixture_path is not None:
            self.fixture_path = fixture_path
            self.fixture_dir = None
        elif fixture_dir is not None:
            self.fixture_path = None
            self.fixture_dir = fixture_dir
        else:
            from fabric_ai_meta.extractor.factory import FIXTURES_DIR
            self.fixture_path = None
            self.fixture_dir = FIXTURES_DIR

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def list_models(self, workspace: str) -> list[str]:
        """Return model names available in this extractor.

        fixture_path mode: returns a single-item list with that model's name.
        fixture_dir mode:  scans for *.json files and returns sorted model names.
        """
        if self.fixture_path is not None:
            with open(self.fixture_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return [data.get("name", os.path.basename(self.fixture_path)[:-5])]

        names = []
        for fname in sorted(os.listdir(self.fixture_dir)):
            if not fname.endswith(".json"):
                continue
            # Skip sidecar fixtures (e.g. *.copilot.json) which are not model files.
            if fname.endswith(".copilot.json"):
                continue
            fpath = os.path.join(self.fixture_dir, fname)
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                names.append(data.get("name", fname[:-5]))
            except Exception:
                pass
        return sorted(names)

    def extract(
        self,
        model_name: str,
        workspace: str | None = None,
        *,
        with_copilot: bool = False,
    ) -> SemanticModelMeta:
        """Load and return a SemanticModelMeta.

        fixture_path mode: loads that file directly (existing single-model behaviour).
        fixture_dir mode:  finds the fixture whose model name matches (case-insensitive,
                           slugified). Raises FileNotFoundError if no match.

        When ``with_copilot=True``, looks for a ``<base>.copilot.json`` sidecar
        next to the fixture and attaches the parsed ``CopilotBundle`` to
        ``model.copilot``. Sidecar absence is silent (copilot stays None).
        """
        if self.fixture_path is not None:
            model = self._load(self.fixture_path)
            if with_copilot:
                self._attach_copilot(model, self.fixture_path)
            return model

        target_slug = _slugify(model_name)
        for fname in sorted(os.listdir(self.fixture_dir)):
            if not fname.endswith(".json"):
                continue
            # Skip sidecar fixtures (e.g. *.copilot.json) which are not model files.
            if fname.endswith(".copilot.json"):
                continue
            fpath = os.path.join(self.fixture_dir, fname)
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                candidate_name = data.get("name", fname[:-5])
                if _slugify(candidate_name) == target_slug:
                    model = from_dict(data)
                    if with_copilot:
                        self._attach_copilot(model, fpath)
                    return model
            except Exception:
                pass

        raise FileNotFoundError(
            f"No fixture found for model '{model_name}' in '{self.fixture_dir}'"
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _load(path: str) -> SemanticModelMeta:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return from_dict(data)

    @staticmethod
    def _attach_copilot(model: SemanticModelMeta, fixture_file: str) -> None:
        """Load ``<base>.copilot.json`` (if present) and attach to ``model.copilot``.

        Silent when the sidecar does not exist (copilot stays None). A
        malformed sidecar logs a warning and leaves ``copilot=None`` rather
        than crashing the entire extraction.
        """
        import logging
        base, _ = os.path.splitext(fixture_file)
        sidecar = base + ".copilot.json"
        if not os.path.exists(sidecar):
            return
        try:
            with open(sidecar, "r", encoding="utf-8") as f:
                envelope = json.load(f)
            model.copilot = CopilotReader.from_definition(envelope)
        except (OSError, json.JSONDecodeError) as exc:
            logging.getLogger(__name__).warning(
                "Skipping malformed Copilot sidecar %r: %s", sidecar, exc
            )
