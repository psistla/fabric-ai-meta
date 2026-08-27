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


def _resolve_base_table(
    measure: MeasureMeta, measures_by_name: dict[str, MeasureMeta]
) -> str | None:
    """Walk a measure's dependency chain to the table it ultimately aggregates.

    `depends_on_columns` on the measure ITSELF is not trusted first: a
    time-intelligence measure's only literal `Table[Column]` reference is
    often its date-filter argument (`TOTALYTD([Sales], 'Date'[Date])`), which
    is not the table it aggregates. Measure references are followed first;
    only a measure with no further measure references falls back to its own
    column references. Depth- and cycle-guarded.
    """
    seen: set[str] = set()
    queue = [measure]
    depth = 0
    while queue and depth < _MAX_MEASURE_WALK_DEPTH:
        depth += 1
        next_queue: list[MeasureMeta] = []
        for m in queue:
            unseen_refs = [
                r.strip("[]") for r in m.depends_on_measures if r.strip("[]") not in seen
            ]
            if unseen_refs:
                for ref_name in unseen_refs:
                    seen.add(ref_name)
                    dep = measures_by_name.get(ref_name)
                    if dep is not None:
                        next_queue.append(dep)
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
