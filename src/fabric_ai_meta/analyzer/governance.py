"""Cross-model governance analysis for naming consistency and duplicate detection."""

import re

from fabric_ai_meta.models.metadata import SemanticModelMeta


def _normalize_name(name: str) -> str:
    """Lowercase, strip brackets, underscores, spaces, and hyphens."""
    return re.sub(r"[\s_\-\[\]]", "", name).lower()


def find_naming_inconsistencies(models: list[SemanticModelMeta]) -> list[dict]:
    """Detect same concept named differently across models.

    Heuristic: normalize names (lowercase, remove underscores/spaces/brackets)
    and group by normalized form. Report entries where the same normalized name
    has multiple surface variants appearing across different models.

    Returns:
        List of dicts: {normalized, variants, found_in}
    """
    # normalized -> {surface_variant -> set(model_names)}
    name_map: dict[str, dict[str, set]] = {}

    for model in models:
        for table in model.tables:
            for col in table.columns:
                norm = _normalize_name(col.name)
                name_map.setdefault(norm, {}).setdefault(col.name, set()).add(model.name)
            for measure in table.measures:
                norm = _normalize_name(measure.name)
                name_map.setdefault(norm, {}).setdefault(measure.name, set()).add(model.name)

    result = []
    for normalized, variants in name_map.items():
        if len(variants) <= 1:
            continue
        # Collect all model names across all variants
        all_models: set = set()
        for model_set in variants.values():
            all_models |= model_set
        # Only report if the inconsistency spans more than one model
        if len(all_models) > 1:
            result.append({
                "normalized": normalized,
                "variants": sorted(variants.keys()),
                "found_in": sorted(all_models),
            })

    return result


def find_duplicate_measures(models: list[SemanticModelMeta]) -> list[dict]:
    """Detect measures with identical DAX expressions across models.

    Exact match: same DAX string after stripping all whitespace.

    Returns:
        List of dicts: {measure_name, found_in, dax_identical}
    """
    # normalized_dax -> [(measure_name, model_name)]
    dax_map: dict[str, list[tuple[str, str]]] = {}

    for model in models:
        for table in model.tables:
            for measure in table.measures:
                normalized_dax = re.sub(r"\s+", "", measure.dax_expression or "")
                if not normalized_dax:
                    continue
                dax_map.setdefault(normalized_dax, []).append((measure.name, model.name))

    result = []
    for _dax, entries in dax_map.items():
        unique_models = list({model_name for _, model_name in entries})
        if len(unique_models) <= 1:
            continue
        measure_names = list({name for name, _ in entries})
        result.append({
            "measure_name": measure_names[0] if len(measure_names) == 1 else measure_names,
            "found_in": sorted(unique_models),
            "dax_identical": True,
        })

    return result


def generate_governance_report(models: list[SemanticModelMeta]) -> dict:
    """Generate a cross-model governance scorecard report.

    Returns:
        Dict with keys: summary, naming_issues, duplicate_measures, score_ranking
    """
    scored = [(m.name, m.ai_readiness_score) for m in models if m.ai_readiness_score is not None]
    avg_score = sum(s for _, s in scored) / len(scored) if scored else None
    lowest_model = min(scored, key=lambda x: x[1])[0] if scored else None

    score_ranking = sorted(
        [{"model": m.name, "ai_readiness_score": m.ai_readiness_score} for m in models],
        key=lambda x: x["ai_readiness_score"] if x["ai_readiness_score"] is not None else -1.0,
        reverse=True,
    )

    return {
        "summary": {
            "model_count": len(models),
            "average_readiness_score": avg_score,
            "lowest_scoring_model": lowest_model,
        },
        "naming_issues": find_naming_inconsistencies(models),
        "duplicate_measures": find_duplicate_measures(models),
        "score_ranking": score_ranking,
    }
