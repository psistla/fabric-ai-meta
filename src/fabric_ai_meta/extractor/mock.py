"""Mock extractor that loads SemanticModelMeta from a JSON fixture file."""

import json

from fabric_ai_meta.extractor.base import BaseExtractor
from fabric_ai_meta.models.metadata import SemanticModelMeta, from_dict


class MockExtractor(BaseExtractor):
    """Loads a SemanticModelMeta from a JSON fixture file for testing."""

    def __init__(self, fixture_path: str) -> None:
        self.fixture_path = fixture_path

    def extract(self, model_name: str, workspace: str) -> SemanticModelMeta:
        """Read the JSON fixture and return a SemanticModelMeta."""
        with open(self.fixture_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return from_dict(data)
