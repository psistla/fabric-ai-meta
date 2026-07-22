"""Cross-model governance analysis for naming consistency and duplicate detection."""

import json
import os
import re
from datetime import datetime, timezone

from fabric_ai_meta.analyzer.graph_necessity import assess_graph_necessity
from fabric_ai_meta.models.metadata import SemanticModelMeta


def _normalize_name(name: str) -> str:
    """Lowercase, strip brackets, underscores, spaces, and hyphens."""
    return re.sub(r"[\s_\-\[\]]", "", name).lower()


def _normalize_dax(dax: str) -> str:
    """Strip all whitespace and lowercase for DAX comparison."""
    return re.sub(r"\s+", "", dax).lower()


def find_naming_inconsistencies(models: list[SemanticModelMeta]) -> list[dict]:
    """Detect same concept named differently across (or within) models.

    Normalizes names (lowercase, strip underscores/spaces/hyphens/brackets)
    and groups by normalized form. Reports entries where >=2 surface variants
    exist. Same-model variants count.

    Returns:
        List of dicts: {normalized, variants, found_in, object_type}
    """
    results = []

    for object_type, get_items in [
        ("column", lambda m: [(c.name, m.name) for t in m.tables for c in t.columns]),
        ("measure", lambda m: [(ms.name, m.name) for t in m.tables for ms in t.measures]),
    ]:
        # normalized -> {surface_variant -> set(model_names)}
        name_map: dict[str, dict[str, set]] = {}
        for model in models:
            for item_name, model_name in get_items(model):
                norm = _normalize_name(item_name)
                name_map.setdefault(norm, {}).setdefault(item_name, set()).add(model_name)

        for normalized, variants in name_map.items():
            if len(variants) <= 1:
                continue
            all_models: set = set()
            for model_set in variants.values():
                all_models |= model_set
            results.append({
                "normalized": normalized,
                "variants": sorted(variants.keys()),
                "found_in": sorted(all_models),
                "object_type": object_type,
            })

    return results


def find_duplicate_measures(models: list[SemanticModelMeta]) -> list[dict]:
    """Detect measures with identical DAX expressions across models.

    Normalizes DAX by stripping whitespace and lowercasing. Only reports
    groups found in 2+ models.

    Returns:
        List of dicts: {measure_name or variants, dax_normalized, found_in, dax_identical}
    """
    # normalized_dax -> [(measure_name, model_name)]
    dax_map: dict[str, list[tuple[str, str]]] = {}

    for model in models:
        for table in model.tables:
            for measure in table.measures:
                norm_dax = _normalize_dax(measure.dax_expression or "")
                if not norm_dax:
                    continue
                dax_map.setdefault(norm_dax, []).append((measure.name, model.name))

    result = []
    for norm_dax, entries in dax_map.items():
        unique_models = sorted({model_name for _, model_name in entries})
        if len(unique_models) <= 1:
            continue
        measure_names = sorted({name for name, _ in entries})
        entry: dict = {
            "dax_normalized": norm_dax,
            "found_in": unique_models,
            "dax_identical": True,
        }
        if len(measure_names) == 1:
            entry["measure_name"] = measure_names[0]
        else:
            entry["variants"] = measure_names
        result.append(entry)

    return result


def _has_any_copilot_artifact(signals: dict) -> bool:
    """Return True if a signals dict reports at least one non-empty primitive."""
    return any([
        signals.get("has_ai_instructions"),
        signals.get("verified_answer_count", 0) > 0,
        signals.get("ai_data_schema_table_count", 0) > 0,
        signals.get("example_prompt_count", 0) > 0,
    ])


def aggregate_copilot_signals(
    name_signal_pairs: list[tuple[str, dict]],
) -> dict:
    """Workspace-level rollup of per-model Copilot signals.

    Input is a list of ``(model_name, signals_dict)`` so callers can use this
    over either live ``CopilotBundle`` objects or already-serialized signals
    blocks in a ``workspace-summary.json``.
    """
    models_with_any = sorted(
        name for name, sig in name_signal_pairs if _has_any_copilot_artifact(sig)
    )
    missing_instructions = sorted(
        name for name, sig in name_signal_pairs
        if not sig.get("has_ai_instructions")
    )
    total_verified_answers = sum(
        sig.get("verified_answer_count", 0) for _, sig in name_signal_pairs
    )
    return {
        "models_with_copilot": len(models_with_any),
        "models_with_copilot_names": models_with_any,
        "models_without_ai_instructions": missing_instructions,
        "total_verified_answers": total_verified_answers,
    }


def find_copilot_completeness(models: list[SemanticModelMeta]) -> dict | None:
    """Aggregate Copilot signals across models that carry a CopilotBundle.

    Returns ``None`` when no model has ``.copilot`` populated (the user did
    not run extraction with ``with_copilot=True``). Otherwise returns a dict
    with per-model signals plus workspace-level rollup counters.
    """
    with_copilot = [m for m in models if m.copilot is not None]
    if not with_copilot:
        return None

    pairs = [(m.name, m.copilot.signals()) for m in with_copilot]
    per_model = [{"name": name, **sig} for name, sig in pairs]
    rollup = aggregate_copilot_signals(pairs)
    return {**rollup, "per_model_signals": per_model}


def generate_governance_report(
    models: list[SemanticModelMeta],
    *,
    graph_necessity: bool = False,
    questions: list[str] | None = None,
) -> dict:
    """Generate a cross-model governance scorecard report.

    Args:
        models: Models to analyze.
        graph_necessity: Add a per-model graph_necessity assessment.
        questions: Optional real questions that sharpen that assessment.

    Returns:
        Dict with keys: summary, score_ranking, naming_inconsistencies,
        duplicate_measures, recommendations, copilot_completeness (optional),
        graph_necessity (optional).
    """
    scored = [
        (m.name, m.ai_readiness_score)
        for m in models
        if m.ai_readiness_score is not None
    ]
    avg_score = sum(s for _, s in scored) / len(scored) if scored else None
    lowest = min(scored, key=lambda x: x[1]) if scored else None
    highest = max(scored, key=lambda x: x[1]) if scored else None

    naming_issues = find_naming_inconsistencies(models)
    duplicate_measures = find_duplicate_measures(models)

    score_ranking = sorted(
        [
            {
                "name": m.name,
                "ai_readiness_score": m.ai_readiness_score,
                "table_count": len(m.tables),
                "measure_count": sum(len(t.measures) for t in m.tables),
            }
            for m in models
        ],
        key=lambda x: x["ai_readiness_score"] if x["ai_readiness_score"] is not None else -1.0,
        reverse=True,
    )

    recommendations = []
    for issue in naming_issues:
        recommendations.append(
            f"Standardize '{issue['normalized']}', found as "
            f"{issue['variants']} across {issue['found_in']}"
        )
    for dup in duplicate_measures:
        name = dup.get("measure_name") or dup.get("variants")
        n = len(dup["found_in"])
        recommendations.append(
            f"Consider consolidating '{name}', identical DAX in {n} models"
        )
    if lowest:
        recommendations.append(
            f"Lowest scoring: '{lowest[0]}' ({lowest[1]:.2f}), run with --llm-enrich"
        )
    for m in models:
        breakdown = m.scoring_breakdown or {}
        desc_coverage = breakdown.get("description_coverage", None)
        if desc_coverage is not None and desc_coverage < 0.5:
            recommendations.append(
                f"'{m.name}' has low description coverage ({desc_coverage:.0%}), "
                "run with --llm-enrich to generate missing descriptions"
            )

    copilot_completeness = find_copilot_completeness(models)
    if copilot_completeness is not None:
        for name in copilot_completeness["models_without_ai_instructions"]:
            recommendations.append(
                f"'{name}' has no AI Instructions; add Copilot/Instructions/instructions.md "
                "to guide Copilot answer behavior"
            )

    necessity = None
    if graph_necessity:
        necessity = [assess_graph_necessity(m, questions=questions) for m in models]
        for entry in necessity:
            if entry["tier"] == "GRAPH_WARRANTED":
                recommendations.append(
                    f"'{entry['name']}' shows genuine multi-hop workload "
                    f"(pressure {entry['pressure']:.2f}): a graph/ontology is warranted"
                )

    report = {
        "summary": {
            "model_count": len(models),
            "average_readiness_score": avg_score,
            "lowest_scoring_model": {"name": lowest[0], "score": lowest[1]} if lowest else None,
            "highest_scoring_model": {"name": highest[0], "score": highest[1]} if highest else None,
            "total_naming_issues": len(naming_issues),
            "total_duplicate_measures": len(duplicate_measures),
        },
        "score_ranking": score_ranking,
        "naming_inconsistencies": naming_issues,
        "duplicate_measures": duplicate_measures,
        "recommendations": recommendations,
    }
    if copilot_completeness is not None:
        report["copilot_completeness"] = copilot_completeness
    if necessity is not None:
        report["graph_necessity"] = necessity
    return report


def write_governance_report(report: dict, workspace: str, output_path: str) -> str:
    """Wrap report with schema metadata and write to disk.

    Args:
        report: Output of generate_governance_report()
        workspace: Workspace name (recorded in output)
        output_path: File path to write (including filename)

    Returns:
        The file path written.
    """
    output = {
        "$schema": "https://raw.githubusercontent.com/psistla/fabric-ai-meta/master/schemas/governance-report/v1.json",
        "version": "1.0",
        "workspace": workspace,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        **report,
    }
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2)
    return output_path
