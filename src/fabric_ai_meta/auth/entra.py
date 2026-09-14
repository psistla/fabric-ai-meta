"""Fabric notebook runtime detection and ambient-credential helpers."""

import os
import sys


def detect_notebook_environment() -> bool:
    """Return True if running inside a Fabric/Jupyter notebook runtime.

    Checks:
    - FABRIC_NOTEBOOK_ID env var (set by Fabric in all notebook kernels)
    - notebookutils in sys.modules (Fabric-injected utility module)
    - ipykernel in sys.modules (generic Jupyter notebook indicator)
    """
    if os.environ.get("FABRIC_NOTEBOOK_ID"):
        return True
    if "notebookutils" in sys.modules:
        return True
    if "ipykernel" in sys.modules:
        return True
    return False


class FabricEnvironmentError(Exception):
    """Raised when a live extraction command is run outside Fabric notebook runtime.

    Always includes a remediation message directing the user to --mock or Fabric.
    """

    DEFAULT_MESSAGE = (
        "Live workspace extraction requires the Microsoft Fabric notebook runtime.\n"
        "sempy.fabric only works inside Fabric; installing extras will not change this.\n\n"
        "To read a real model on this machine, point at a local Power BI project:\n"
        '  fabric-ai-meta analyze "Model Name" --pbip path/to/MyReport.SemanticModel\n\n'
        "Other options:\n"
        "  - Run this command inside a Fabric notebook\n"
        "  - Use bundled sample data with --mock\n"
    )

    def __init__(self, message: str | None = None):
        super().__init__(message or self.DEFAULT_MESSAGE)


def fabric_bearer_token() -> str:
    """Power BI / Fabric bearer token from the notebook runtime's ambient credential."""
    import notebookutils  # type: ignore[import-not-found]
    return notebookutils.credentials.getToken("pbi")


class MissingFabricDependencyError(ImportError):
    """Raised inside a Fabric runtime when an optional dependency is absent.

    Distinct from FabricEnvironmentError: that one means the wrong environment,
    where installing extras cannot help. This one means the right environment
    with a missing package, where it is the entire fix.
    """

    def __init__(self, distribution: str):
        super().__init__(
            f"{distribution} is required for this command but is not installed.\n"
            f"Install the Fabric extra:  pip install 'fabric-ai-meta[fabric]'"
        )
