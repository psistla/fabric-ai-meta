"""Extractor construction, shared by the CLI and the MCP server.

Both surfaces previously held their own copy of this logic, which is how they
could return different results for the same model. One construction path now.
"""

import os

from fabric_ai_meta.extractor.base import BaseExtractor

FIXTURES_DIR = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "tests", "fixtures")
)


def _slugify(name: str) -> str:
    import re
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def _fixture_path_for(model_name: str) -> str:
    slug = _slugify(model_name).replace("-", "_")
    candidate = os.path.join(FIXTURES_DIR, f"{slug}.json")
    if os.path.exists(candidate):
        return candidate
    default = os.path.join(FIXTURES_DIR, "adventure_works.json")
    if os.path.exists(default):
        return default
    raise FileNotFoundError(f"No fixture for model '{model_name}' (looked at {candidate})")


def _build_extractor(
    *,
    workspace: str | None,
    mock: bool = False,
    pbip: str | None = None,
    model_name: str | None = None,
) -> BaseExtractor:
    """Construct the right extractor for the requested mode.

    `model_name is None` selects multi-model (fixture_dir) mode for mock.
    """
    if mock and pbip:
        raise ValueError("--mock and --pbip are mutually exclusive")

    if pbip:
        from fabric_ai_meta.extractor.pbip import PbipExtractor
        return PbipExtractor(pbip)

    if mock:
        from fabric_ai_meta.extractor.mock import MockExtractor
        if model_name is None:
            return MockExtractor(fixture_dir=FIXTURES_DIR)
        return MockExtractor(fixture_path=_fixture_path_for(model_name))

    from fabric_ai_meta.auth.entra import (
        FabricEnvironmentError,
        detect_notebook_environment,
    )
    if not detect_notebook_environment():
        raise FabricEnvironmentError()
    from fabric_ai_meta.extractor.semantic_link import SemanticLinkExtractor
    return SemanticLinkExtractor(workspace=workspace)
