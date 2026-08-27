"""Agent-readiness score: per-model critic report of concrete, ranked findings.

Reuses scorer.py's existing weighted categories and per-object predicates rather
than re-deriving them - three of the four detectors below reimplement a single
one-line predicate scorer.score_model() already evaluates internally and
discards after aggregating into a ratio. Not a scorer.py refactor: scorer.py
ships and is tested, and three duplicated one-liners across two small modules
is cheaper than a shared-internals change to a public API.

unreliable_type is the one genuinely new detector: a column with no extracted
data_type is a real, verified extractor gap (see extractor/pbip.py's
_parse_column), not a scorer category. Its weight is a placeholder, not
derived from SCORING_WEIGHTS - see the constant below.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fabric_ai_meta.analyzer.scorer import SCORING_WEIGHTS, _is_name_consistent, score_model
from fabric_ai_meta.models.metadata import ColumnRole, SemanticModelMeta

_SCHEMA_URL = (
    "https://raw.githubusercontent.com/psistla/fabric-ai-meta/master/"
    "schemas/agent-readiness/v1.json"
)

_FINDING_TYPES = ("undescribed", "ambiguous_name", "missing_relationship", "unreliable_type")

_UNDESCRIBED_STRUCTURAL_WEIGHT = SCORING_WEIGHTS["description_coverage"]
_UNDESCRIBED_MEASURE_WEIGHT = SCORING_WEIGHTS["measure_documentation"]
_AMBIGUOUS_NAME_WEIGHT = SCORING_WEIGHTS["naming_consistency"]
_MISSING_RELATIONSHIP_WEIGHT = SCORING_WEIGHTS["relationship_completeness"]
# Not derived from SCORING_WEIGHTS - unreliable_type isn't one of scorer's six
# categories. Deliberately below every SCORING_WEIGHTS value (floor is 0.10)
# so it always ranks last: a caveat about extraction, not a model defect.
# Placeholder pending real-world calibration.
_UNRELIABLE_TYPE_WEIGHT = 0.05


def _finding(type_, weight, table, message, fix, *, column=None, measure=None):
    return {
        "type": type_,
        "weight": weight,
        "table": table,
        "column": column,
        "measure": measure,
        "message": message,
        "fix": fix,
    }


def _find_undescribed(model: SemanticModelMeta) -> list[dict]:
    findings = []
    for table in model.tables:
        if not table.description:
            findings.append(_finding(
                "undescribed", _UNDESCRIBED_STRUCTURAL_WEIGHT, table.name,
                f"Table '{table.name}' has no description.",
                f"Add a description to table '{table.name}'.",
            ))
        for column in table.columns:
            if not column.description:
                findings.append(_finding(
                    "undescribed", _UNDESCRIBED_STRUCTURAL_WEIGHT, table.name,
                    f"Column '{table.name}[{column.name}]' has no description.",
                    f"Add a description to column '{table.name}[{column.name}]'.",
                    column=column.name,
                ))
        for measure in table.measures:
            if not measure.description:
                findings.append(_finding(
                    "undescribed", _UNDESCRIBED_MEASURE_WEIGHT, table.name,
                    f"Measure '{measure.name}' has no description.",
                    f"Add a description to measure '{measure.name}'.",
                    measure=measure.name,
                ))
    return findings


def _find_ambiguous_names(model: SemanticModelMeta) -> list[dict]:
    findings = []
    for table in model.tables:
        for column in table.columns:
            if not _is_name_consistent(column.name):
                findings.append(_finding(
                    "ambiguous_name", _AMBIGUOUS_NAME_WEIGHT, table.name,
                    f"Column name '{column.name}' is inconsistent "
                    "(underscore, all-caps abbreviation, or too short).",
                    f"Rename '{column.name}' to a clear, consistent name.",
                    column=column.name,
                ))
        for measure in table.measures:
            if not _is_name_consistent(measure.name):
                findings.append(_finding(
                    "ambiguous_name", _AMBIGUOUS_NAME_WEIGHT, table.name,
                    f"Measure name '{measure.name}' is inconsistent "
                    "(underscore, all-caps abbreviation, or too short).",
                    f"Rename '{measure.name}' to a clear, consistent name.",
                    measure=measure.name,
                ))
    return findings


def _find_missing_relationships(model: SemanticModelMeta) -> list[dict]:
    rel_set = {(r.from_table, r.from_column) for r in model.relationships}
    findings = []
    for table in model.tables:
        for column in table.columns:
            if column.role == ColumnRole.FOREIGN_KEY and (table.name, column.name) not in rel_set:
                findings.append(_finding(
                    "missing_relationship", _MISSING_RELATIONSHIP_WEIGHT, table.name,
                    f"Foreign key '{column.name}' on '{table.name}' has no defined relationship.",
                    f"Add a relationship from {table.name}.{column.name} to its "
                    "dimension table's key column.",
                    column=column.name,
                ))
    return findings


def _find_unreliable_types(model: SemanticModelMeta) -> list[dict]:
    findings = []
    for table in model.tables:
        for column in table.columns:
            if column.data_type == "":
                findings.append(_finding(
                    "unreliable_type", _UNRELIABLE_TYPE_WEIGHT, table.name,
                    f"Column '{table.name}[{column.name}]' has no extracted data type.",
                    "Known --pbip extraction limitation for calculated columns; "
                    "verify manually or re-extract via --mock/live Fabric.",
                    column=column.name,
                ))
    return findings


def assess_agent_readiness(model: SemanticModelMeta) -> dict:
    """Run all four detectors against `model`, rank the findings by how much
    they affect the model's existing AI-readiness score, and return the full
    report dict, ready to serialize."""
    findings: list[dict] = []
    findings.extend(_find_undescribed(model))
    findings.extend(_find_ambiguous_names(model))
    findings.extend(_find_missing_relationships(model))
    findings.extend(_find_unreliable_types(model))
    findings.sort(key=lambda f: f["weight"], reverse=True)

    overall, breakdown = score_model(model)

    counts = dict.fromkeys(_FINDING_TYPES, 0)
    for finding in findings:
        counts[finding["type"]] += 1

    return {
        "$schema": _SCHEMA_URL,
        "version": "1.0",
        "model": model.name,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "score": overall,
        "breakdown": breakdown,
        "summary": {"total_findings": len(findings), **counts},
        "findings": findings,
    }
