"""AI readiness scoring engine for semantic models (SPEC.md Section 6.2)."""

import re

from fabric_ai_meta.models.metadata import ColumnRole, MeasureCategory, SemanticModelMeta

# Weights must sum to 1.0 — verified by assertion below.
SCORING_WEIGHTS = {
    "description_coverage": 0.25,       # % of columns + tables with descriptions
    "measure_documentation": 0.20,      # % of measures with descriptions
    "relationship_completeness": 0.15,  # All FKs have defined relationships
    "naming_consistency": 0.15,         # Follows naming convention (no abbreviations, consistent casing)
    "sample_values_available": 0.10,    # % of categorical columns with sample values extracted
    "business_rules_documented": 0.15,  # Implicit DAX filters are documented
}
# Verification: 0.25 + 0.20 + 0.15 + 0.15 + 0.10 + 0.15 = 1.00 ✓
assert abs(sum(SCORING_WEIGHTS.values()) - 1.0) < 1e-9, (
    f"SCORING_WEIGHTS must sum to 1.0, got {sum(SCORING_WEIGHTS.values())}"
)

_SAMPLE_VALUE_ROLES = {ColumnRole.ATTRIBUTE, ColumnRole.MEASURE_COLUMN}
_BUSINESS_RULE_CATEGORIES = {MeasureCategory.FILTER_CONTEXT, MeasureCategory.TIME_INTELLIGENCE}


def _is_name_consistent(name: str) -> bool:
    """
    Return True if the name follows consistent naming conventions.

    A name is penalized (returns False) if it:
    - Contains underscores (snake_case in a PascalCase model)
    - Has all-caps segments (abbreviations like ID, YTD, QTD)
    - Is shorter than 3 characters
    """
    # Strip surrounding brackets common in measure names
    clean = name.strip("[]")
    if len(clean) < 3:
        return False
    if "_" in clean:
        return False
    # Penalize all-caps segments of 2+ characters (e.g., ID, YTD, QTD)
    if re.search(r'[A-Z]{2,}', clean):
        return False
    return True


def score_model(model: SemanticModelMeta) -> tuple[float, dict]:
    """
    Compute AI readiness score for a semantic model.

    Returns:
        (overall_score, breakdown_dict) where overall_score is 0.0–1.0
        and breakdown_dict has one float per SCORING_WEIGHTS key.
    """
    all_tables = model.tables
    all_columns = [col for t in all_tables for col in t.columns]
    all_measures = [m for t in all_tables for m in t.measures]

    # --- description_coverage ---
    # (tables with description + columns with description) / (total tables + total columns)
    total_describable = len(all_tables) + len(all_columns)
    if total_describable == 0:
        desc_coverage = 1.0
    else:
        described = sum(1 for t in all_tables if t.description) + \
                    sum(1 for c in all_columns if c.description)
        desc_coverage = described / total_describable

    # --- measure_documentation ---
    # measures with description / total measures
    if not all_measures:
        measure_doc = 1.0
    else:
        measure_doc = sum(1 for m in all_measures if m.description) / len(all_measures)

    # --- relationship_completeness ---
    # FK columns that have a matching relationship / total FK columns
    fk_cols = [
        (t.name, c.name)
        for t in all_tables
        for c in t.columns
        if c.role == ColumnRole.FOREIGN_KEY
    ]
    if not fk_cols:
        rel_completeness = 1.0
    else:
        rel_set = {(r.from_table, r.from_column) for r in model.relationships}
        matched = sum(1 for tc in fk_cols if tc in rel_set)
        rel_completeness = matched / len(fk_cols)

    # --- naming_consistency ---
    # columns/measures without abbreviations or inconsistent casing / total
    nameable = [c.name for c in all_columns] + [m.name for m in all_measures]
    if not nameable:
        naming_consistency = 1.0
    else:
        consistent = sum(1 for n in nameable if _is_name_consistent(n))
        naming_consistency = consistent / len(nameable)

    # --- sample_values_available ---
    # columns with len(sample_values) > 0 and role in (ATTRIBUTE, MEASURE_COLUMN) / total such columns
    sample_eligible = [c for c in all_columns if c.role in _SAMPLE_VALUE_ROLES]
    if not sample_eligible:
        sample_available = 1.0
    else:
        with_samples = sum(1 for c in sample_eligible if len(c.sample_values) > 0)
        sample_available = with_samples / len(sample_eligible)

    # --- business_rules_documented ---
    # measures with len(implicit_filters) > 0 and category in (FILTER_CONTEXT, TIME_INTELLIGENCE)
    # / total such measures. 0 such measures → score 1.0
    rule_eligible = [m for m in all_measures if m.category in _BUSINESS_RULE_CATEGORIES]
    if not rule_eligible:
        rules_documented = 1.0
    else:
        documented = sum(1 for m in rule_eligible if len(m.implicit_filters) > 0)
        rules_documented = documented / len(rule_eligible)

    breakdown = {
        "description_coverage": round(desc_coverage, 4),
        "measure_documentation": round(measure_doc, 4),
        "relationship_completeness": round(rel_completeness, 4),
        "naming_consistency": round(naming_consistency, 4),
        "sample_values_available": round(sample_available, 4),
        "business_rules_documented": round(rules_documented, 4),
    }

    overall = sum(SCORING_WEIGHTS[k] * breakdown[k] for k in SCORING_WEIGHTS)
    return round(overall, 4), breakdown
