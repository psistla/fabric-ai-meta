"""Mock extractor that loads SemanticModelMeta from a JSON fixture file or directory."""

import json
import os
import re

from fabric_ai_meta.extractor.base import BaseExtractor
from fabric_ai_meta.models.metadata import SemanticModelMeta, from_dict


def _slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


class MockExtractor(BaseExtractor):
    """Loads SemanticModelMeta from JSON fixture files for local testing.

    Two modes (backward compatible):
    - fixture_path: single JSON file → loads one model (Phase 1 behaviour)
    - fixture_dir:  directory of *.json files → supports list_models() + extract() by name
    If neither is provided, defaults to fixture_dir = "tests/fixtures/".
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
            # Default: look relative to the package root for tests/fixtures/
            here = os.path.dirname(os.path.abspath(__file__))
            self.fixture_path = None
            self.fixture_dir = os.path.normpath(
                os.path.join(here, "..", "..", "tests", "fixtures")
            )

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
            fpath = os.path.join(self.fixture_dir, fname)
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                names.append(data.get("name", fname[:-5]))
            except Exception:
                pass
        return sorted(names)

    def extract(self, model_name: str, workspace: str | None = None) -> SemanticModelMeta:
        """Load and return a SemanticModelMeta.

        fixture_path mode: loads that file directly (existing Phase 1 behaviour).
        fixture_dir mode:  finds the fixture whose model name matches (case-insensitive,
                           slugified). Raises FileNotFoundError if no match.
        """
        if self.fixture_path is not None:
            return self._load(self.fixture_path)

        target_slug = _slugify(model_name)
        for fname in sorted(os.listdir(self.fixture_dir)):
            if not fname.endswith(".json"):
                continue
            fpath = os.path.join(self.fixture_dir, fname)
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                candidate_name = data.get("name", fname[:-5])
                if _slugify(candidate_name) == target_slug:
                    return from_dict(data)
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
