"""MCP server exposing fabric-ai-meta tools to AI agents.

Tools are plain Python functions at module level so the test suite can call
them directly without going through the MCP protocol or installing the
optional ``mcp`` dependency. The MCP server itself is built lazily via
``build_server()`` so that ``import fabric_ai_meta.mcp_server`` works even
when ``mcp`` is not installed.
"""

from __future__ import annotations

import dataclasses
import json
from typing import Any

from fabric_ai_meta.analyzer.pipeline import classify_model_in_place
from fabric_ai_meta.extractor.factory import _build_extractor

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _error(message: str) -> dict:
    return {"error": message}


# ---------------------------------------------------------------------------
# Tool functions (called directly by tests; wrapped by FastMCP at run time)
# ---------------------------------------------------------------------------


def list_models(workspace: str, mock: bool = True) -> dict:
    """List semantic models available in the given workspace.

    Args:
        workspace: Workspace name.
        mock: When True, list models from local fixture files. When False,
            requires the Microsoft Fabric notebook runtime.

    Returns:
        ``{"workspace": str, "models": list[str]}`` or ``{"error": str}``.
    """
    try:
        extractor = _build_extractor(workspace=workspace, mock=mock, model_name=None)
        names = extractor.list_models(workspace)
        return {"workspace": workspace, "models": list(names)}
    except Exception as exc:
        return _error(str(exc))


def analyze_model(model_name: str, workspace: str, mock: bool = True) -> dict:
    """Extract, classify, and score a single semantic model.

    Returns score, breakdown, and high-level counts. Use ``generate_schema``
    when you also need the full table / column / measure detail.
    """
    try:
        from fabric_ai_meta.analyzer.scorer import score_model as _score
        extractor = _build_extractor(workspace=workspace, mock=mock, model_name=model_name)
        model = extractor.extract(model_name, workspace)
        classify_model_in_place(model)
        overall, breakdown = _score(model)
        return {
            "model": model_name,
            "workspace": workspace,
            "score": overall,
            "breakdown": breakdown,
            "table_count": len(model.tables),
            "measure_count": sum(len(t.measures) for t in model.tables),
        }
    except Exception as exc:
        return _error(str(exc))


def score_model(model_name: str, workspace: str, mock: bool = True) -> dict:
    """Compute the AI readiness score for a single model.

    Returns ``{"score": float in [0, 1], "breakdown": dict[str, float]}``.
    """
    try:
        from fabric_ai_meta.analyzer.scorer import score_model as _score
        extractor = _build_extractor(workspace=workspace, mock=mock, model_name=model_name)
        model = extractor.extract(model_name, workspace)
        classify_model_in_place(model)
        overall, breakdown = _score(model)
        return {
            "model": model_name,
            "score": overall,
            "breakdown": breakdown,
        }
    except Exception as exc:
        return _error(str(exc))


def generate_schema(model_name: str, workspace: str, mock: bool = True) -> dict:
    """Generate the AI-ready schema dict for a model.

    The schema is the same structure produced by
    ``fabric-ai-meta analyze`` and written to ``ai-ready-schema.json``.
    """
    try:
        from fabric_ai_meta.generator.schema import generate_ai_ready_schema
        extractor = _build_extractor(workspace=workspace, mock=mock, model_name=model_name)
        model = extractor.extract(model_name, workspace)
        classify_model_in_place(model)
        return generate_ai_ready_schema(model)
    except Exception as exc:
        return _error(str(exc))


def governance_report(workspace: str, mock: bool = True) -> dict:
    """Run the cross-model governance analysis for an entire workspace.

    Returns naming inconsistencies, duplicate measure expressions, model score
    ranking, and recommendations.
    """
    try:
        from fabric_ai_meta.analyzer.governance import generate_governance_report
        from fabric_ai_meta.analyzer.scorer import score_model as _score

        extractor = _build_extractor(workspace=workspace, mock=mock, model_name=None)
        names = extractor.list_models(workspace)
        models = []
        for name in names:
            m = extractor.extract(name, workspace)
            classify_model_in_place(m)
            overall, breakdown = _score(m)
            m.ai_readiness_score = overall
            m.scoring_breakdown = breakdown
            models.append(m)
        return generate_governance_report(models)
    except Exception as exc:
        return _error(str(exc))


def diff_summaries(baseline_json: str, current_json: str) -> dict:
    """Compare two ``workspace-summary.json`` payloads and return the delta.

    Inputs are JSON-encoded strings (not file paths) so the tool works in
    environments where the agent has the data in-memory but no shared
    filesystem with the server.
    """
    try:
        from fabric_ai_meta.analyzer.delta import compare_workspace_summaries
        baseline = json.loads(baseline_json)
        current = json.loads(current_json)
        return compare_workspace_summaries(baseline, current)
    except Exception as exc:
        return _error(str(exc))


TOOLS: tuple[Any, ...] = (
    list_models,
    analyze_model,
    score_model,
    generate_schema,
    governance_report,
    diff_summaries,
)


# ---------------------------------------------------------------------------
# Server construction
# ---------------------------------------------------------------------------


def build_server():
    """Construct and return a FastMCP server with all tools registered.

    Lazy-imports ``mcp`` so the rest of the module remains importable in
    environments that do not have the optional dependency installed.
    """
    try:
        from mcp.server.fastmcp import FastMCP  # type: ignore[import-not-found]
    except ImportError as exc:
        raise ImportError(
            "The MCP server requires the optional 'mcp' dependency. Install with: "
            "pip install 'fabric-ai-meta[mcp]'"
        ) from exc

    server = FastMCP("fabric-ai-meta")
    for tool in TOOLS:
        server.tool()(tool)
    return server


def run(transport: str = "stdio", port: int = 8000) -> None:
    """Build the server and run it on the requested transport."""
    server = build_server()
    if transport == "streamable-http":
        server.settings.port = port
        server.run(transport="streamable-http")
    else:
        server.run(transport="stdio")


# Convenience: ensure dataclasses (e.g. WritebackResult) can be JSON-encoded
# when an agent passes one in via diff_summaries-like flows in the future.
def _to_jsonable(obj: Any) -> Any:
    if dataclasses.is_dataclass(obj):
        return dataclasses.asdict(obj)
    return obj


if __name__ == "__main__":
    run()
