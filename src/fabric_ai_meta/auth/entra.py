"""Azure AD / Entra ID authentication helpers."""

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


# Alias used throughout the spec and CLI startup
detect_fabric_runtime = detect_notebook_environment


class FabricEnvironmentError(Exception):
    """Raised when a live extraction command is run outside Fabric notebook runtime.

    Always includes a remediation message directing the user to --mock or Fabric.
    """

    DEFAULT_MESSAGE = (
        "This command requires the Microsoft Fabric notebook runtime.\n"
        "sempy.fabric is not available in local Python environments.\n\n"
        "Options:\n"
        "  1. Run this command inside a Fabric notebook\n"
        "  2. Use --mock flag for local development with fixture data:\n"
        '     fabric-ai-meta analyze "Model Name" --workspace "ws" --mock\n'
    )

    def __init__(self, message: str | None = None):
        super().__init__(message or self.DEFAULT_MESSAGE)


def get_credential(
    method: str = "interactive",
    tenant_id: str | None = None,
    client_id: str | None = None,
    client_secret: str | None = None,
):
    """Return an Azure credential for authenticating to Fabric services.

    Args:
        method: "interactive", "service_principal", or "notebook".
        tenant_id: Required for service_principal.
        client_id: Required for service_principal.
        client_secret: Required for service_principal.

    Returns:
        An azure.identity credential object, or None for notebook mode
        (sempy.fabric picks up the ambient Fabric credential automatically).
    """
    if method == "notebook":
        # sempy.fabric uses the Fabric ambient credential automatically;
        # no explicit credential object is needed.
        return None
    elif method == "service_principal":
        from azure.identity import ClientSecretCredential

        return ClientSecretCredential(
            tenant_id=tenant_id,
            client_id=client_id,
            client_secret=client_secret,
        )
    else:  # "interactive"
        from azure.identity import InteractiveBrowserCredential

        return InteractiveBrowserCredential()
