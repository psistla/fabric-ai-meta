"""F1: query guidance.

An MCP tool an agent calls before it writes a query, so it is told the correct
measure, the safe join path, and this specific model's traps, instead of
guessing. Every output here traces to a fact already in SemanticModelMeta - a
relationship, a measure's DAX, or its parsed dependencies from
analyzer.dax_parser - never an inference. Where the metadata does not say,
this refuses (grain, calculation-group internals, synonyms) rather than
guessing; see planning/decisions/f1-narrowed-to-verified-metadata.md.
"""

from __future__ import annotations

import re

from fabric_ai_meta.models.metadata import (
    MeasureCategory,
    MeasureMeta,
    RelationshipMeta,
    SemanticModelMeta,
)

_MAX_MEASURE_WALK_DEPTH = 10

_WHOLE_BODY_LITERAL_RE = re.compile(r"^\s*[+-]?\d+(\.\d+)?\s*$")
_WHOLE_BODY_STRING_RE = re.compile(r'^\s*"([^"]|"")*"\s*$')
_CALC_GROUP_FILTER_RE = re.compile(r"'([^']+)'\[([^\]]+)\]\s*=\s*\"[^\"]*\"")


def _resolve_base_table(
    measure: MeasureMeta, measures_by_name: dict[str, MeasureMeta]
) -> str | None:
    """Walk a measure's dependency chain to the table it ultimately aggregates.

    `depends_on_columns` on the measure ITSELF is not trusted first: a
    time-intelligence measure's only literal `Table[Column]` reference is
    often its date-filter argument (`TOTALYTD([Sales], 'Date'[Date])`), which
    is not the table it aggregates. A node falls back to its own column
    references only when NONE of its measure references resolve to a real
    measure in `measures_by_name` (a dangling reference counts as
    unresolved). Resolution is evaluated independently per node, so one
    branch of a diamond-shaped dependency graph (two measures sharing a
    common base measure) cannot make a sibling branch wrongly think its own
    real dependency is unresolved. Depth- and cycle-guarded.
    """
    seen: set[str] = {measure.name}
    queue = [measure]
    depth = 0
    while queue and depth < _MAX_MEASURE_WALK_DEPTH:
        depth += 1
        next_queue: list[MeasureMeta] = []
        for m in queue:
            ref_names = [r.strip("[]") for r in m.depends_on_measures]
            resolved_any = False
            for ref_name in ref_names:
                dep = measures_by_name.get(ref_name)
                if dep is not None:
                    resolved_any = True
                    if ref_name not in seen:
                        seen.add(ref_name)
                        next_queue.append(dep)
            if resolved_any:
                continue
            if m.depends_on_columns:
                return m.depends_on_columns[0].split("[", 1)[0]
        queue = next_queue
    return None


def _build_adjacency(relationships: list[RelationshipMeta]) -> dict[str, set[str]]:
    adjacency: dict[str, set[str]] = {}
    for rel in relationships:
        if not rel.is_active:
            continue
        adjacency.setdefault(rel.from_table, set()).add(rel.to_table)
        adjacency.setdefault(rel.to_table, set()).add(rel.from_table)
    return adjacency


def _find_join_path(
    relationships: list[RelationshipMeta], base_table: str, target_table: str
) -> list[str] | None:
    """Shortest path of table names over active relationships, either
    direction (grouping a fact by a related dimension's column works
    regardless of cross-filter direction). `[base_table]` when they are the
    same table. `None` when unreachable."""
    if base_table == target_table:
        return [base_table]
    adjacency = _build_adjacency(relationships)
    frontier = [[base_table]]
    visited = {base_table}
    while frontier:
        path = frontier.pop(0)
        node = path[-1]
        for neighbor in adjacency.get(node, ()):
            if neighbor in visited:
                continue
            new_path = path + [neighbor]
            if neighbor == target_table:
                return new_path
            visited.add(neighbor)
            frontier.append(new_path)
    return None


def _report_plumbing_reason(dax: str) -> str | None:
    """A narrow, cheap heuristic (design decision 5): catches icons, swatches,
    and pure display strings. Does NOT catch a string-concatenation measure
    with FORMAT() embedded mid-expression (e.g. won-pho's
    `"Total sales: " & FORMAT([Sales], ...)`) - see Task 6's pinned
    characterization test."""
    stripped = dax.strip()
    if "data:image" in dax:
        return "returns an embedded image (data URI)"
    if _WHOLE_BODY_STRING_RE.match(stripped):
        return "returns a fixed string literal"
    if stripped.upper().startswith("FORMAT("):
        return "returns a formatted display string"
    return None


def _calc_group_reference(model: SemanticModelMeta, dax: str) -> str | None:
    """Name of a table referenced in an equality filter whose own TMDL has no
    partition block - the structural signature of a calculation-group item
    selector (design decision 6). Returns the table name, or None."""
    tables_by_name = {t.name: t for t in model.tables}
    for table_name, _column_name in _CALC_GROUP_FILTER_RE.findall(dax):
        table = tables_by_name.get(table_name)
        if table is not None and table.source_partition_type is None:
            return table_name
    return None


def _warnings_for_measure(model: SemanticModelMeta, measure: MeasureMeta) -> list[dict]:
    warnings: list[dict] = []
    if measure.category == MeasureCategory.SEMI_ADDITIVE:
        warnings.append({
            "type": "semi_additive",
            "message": f"[{measure.name}] is a balance-type measure; do not sum it across "
                       "time. Recompute at the grain you need instead.",
        })
    if measure.category == MeasureCategory.NON_ADDITIVE and "DIVIDE" in measure.dax_expression.upper():
        warnings.append({
            "type": "ratio",
            "message": f"[{measure.name}] is a ratio of two other measures; do not average "
                       "it across groups. Recompute DIVIDE(sum of numerator, sum of "
                       "denominator) at the grain you need.",
        })
    literal = _WHOLE_BODY_LITERAL_RE.match(measure.dax_expression.strip())
    if literal:
        warnings.append({
            "type": "hardcoded_literal",
            "message": f"[{measure.name}] is a hardcoded constant "
                       f"({literal.group(0).strip()}), not derived from data. Confirm this "
                       "is the intended value.",
        })
    for rule in measure.implicit_filters:
        warnings.append({
            "type": "implicit_business_rule",
            "message": f"[{measure.name}] hardcodes a filter ({rule}) inside its DAX.",
        })
    calc_group_table = _calc_group_reference(model, measure.dax_expression)
    if calc_group_table:
        warnings.append({
            "type": "opaque_calculation_group",
            "message": f"[{measure.name}] applies a calculation-group item from "
                       f"'{calc_group_table}'. Calculation groups are not extracted "
                       "(constraint 5); the underlying arithmetic is unknown.",
        })
    return warnings


def _find_measure(model: SemanticModelMeta, name: str):
    """Lookup a measure by name, case-insensitive, with bracket stripping."""
    target = name.strip().lstrip("[").rstrip("]").lower()
    for table in model.tables:
        for measure in table.measures:
            if measure.name.lower() == target:
                return table, measure
    return None


def _all_measures_by_name(model: SemanticModelMeta) -> dict[str, MeasureMeta]:
    """Flat dict of {measure_name: MeasureMeta} for all measures in model."""
    return {m.name: m for t in model.tables for m in t.measures}


def guide_query(
    model: SemanticModelMeta,
    *,
    measure: str | None = None,
    column: str | None = None,
    dimensions: list[str] | None = None,
) -> dict:
    """Guidance to read before writing a query against `model`.

    Pass exactly one of `measure` (a measure name) or `column` (a raw column
    the caller was about to aggregate directly). `dimensions` is an optional
    list of column names to group or filter by. See module docstring and
    planning/decisions/f1-narrowed-to-verified-metadata.md for what this
    does and refuses to answer.
    """
    result: dict = {
        "measure": None, "redirect": None, "excluded": None,
        "warnings": [], "dimensions": {}, "refusal": None,
    }
    if (measure is None) == (column is None):
        result["refusal"] = "Pass exactly one of `measure` or `column`."
        return result

    resolved_measure: MeasureMeta | None = None
    home_table = None

    if measure is not None:
        found = _find_measure(model, measure)
        if found is None:
            result["refusal"] = f"No measure named {measure!r} in this model."
            return result
        home_table, resolved_measure = found

    if resolved_measure is not None:
        reason = _report_plumbing_reason(resolved_measure.dax_expression)
        result["measure"] = {
            "table": home_table.name,
            "name": resolved_measure.name,
            "dax": resolved_measure.dax_expression,
            "category": resolved_measure.category.name,
        }
        if reason:
            result["excluded"] = {"reason": "report_plumbing", "detail": reason}
        else:
            result["warnings"].extend(_warnings_for_measure(model, resolved_measure))

    return result
