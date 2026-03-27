"""Abstract base class defining the extractor interface."""

from abc import ABC, abstractmethod

from fabric_ai_meta.models.metadata import SemanticModelMeta


class BaseExtractor(ABC):
    """Base class for all semantic model extractors."""

    @abstractmethod
    def extract(self, model_name: str, workspace: str) -> SemanticModelMeta:
        """Extract metadata for a semantic model and return a SemanticModelMeta."""
        ...

    @abstractmethod
    def list_models(self, workspace: str) -> list[str]:
        """Return names of all semantic models available in the workspace."""
        ...
