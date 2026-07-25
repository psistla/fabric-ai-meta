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


def _available_sample_models() -> list[str]:
    """Display names of the bundled sample models, for error messages.

    Display names, not slugs: every other surface (`scan`, the MCP tools)
    shows "Contoso Sales", so an error listing "contoso_sales" would answer
    in a vocabulary the user never typed. MockExtractor.list_models already
    skips ``*.copilot.json`` sidecars.
    """
    if not os.path.isdir(FIXTURES_DIR):
        return []
    from fabric_ai_meta.extractor.mock import MockExtractor
    return MockExtractor(fixture_dir=FIXTURES_DIR).list_models("")


def _fixture_path_for(model_name: str) -> str:
    """Resolve a bundled sample model by name. Exact match only.

    Never substitutes a different model: a wrong answer labelled with the
    requested name is worse than no answer.
    """
    slug = _slugify(model_name).replace("-", "_")
    candidate = os.path.join(FIXTURES_DIR, f"{slug}.json")
    if os.path.exists(candidate):
        return candidate
    available = ", ".join(_available_sample_models()) or "none found"
    raise FileNotFoundError(
        f"No bundled sample model named '{model_name}'.\n"
        f"Available samples: {available}\n"
        f"To read one of your own models, use --pbip instead of --mock."
    )


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
