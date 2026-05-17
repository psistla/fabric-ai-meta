"""Abstract base class defining the extractor interface."""

from abc import ABC, abstractmethod

from fabric_ai_meta.models.metadata import SemanticModelMeta


class BaseExtractor(ABC):
    """Base class for all semantic model extractors."""

    @abstractmethod
    def extract(
        self, model_name: str, workspace: str, *, with_copilot: bool = False
    ) -> SemanticModelMeta:
        """Extract metadata for a semantic model.

        Args:
            model_name: Name of the semantic model.
            workspace: Workspace name.
            with_copilot: If True, also fetch and populate `SemanticModelMeta.copilot`
                with the model's `Copilot/` folder (AI Instructions, Verified Answers,
                etc.). When False (default), `copilot` is left None.
        """
        ...

    @abstractmethod
    def list_models(self, workspace: str) -> list[str]:
        """Return names of all semantic models available in the workspace."""
        ...
