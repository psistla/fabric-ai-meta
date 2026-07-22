"""Graph-necessity advisor.

Answers "does this model's workload justify a graph/ontology, or does a
described schema already suffice?" from already-extracted metadata. Pure:
no extraction, no Fabric calls, no required LLM calls.

Spec: planning/superpowers/specs/2026-07-22-graph-necessity-advisor-design.md
"""
from __future__ import annotations

from collections import deque

from fabric_ai_meta.models.metadata import SemanticModelMeta, TableType

# Weights sum to 1.0 (assertion below), mirroring SCORING_WEIGHTS in scorer.py.
PRESSURE_WEIGHTS: dict[str, float] = {
    "workload_hop_pressure": 0.35,
    "bridge_m2m_presence": 0.25,
    "relationship_graph_depth": 0.20,
    "multi_fact_complexity": 0.20,
}
assert abs(sum(PRESSURE_WEIGHTS.values()) - 1.0) < 1e-9, "PRESSURE_WEIGHTS must sum to 1.0"

# Final-pressure tier cutoffs (named per spec).
PRESSURE_THRESHOLDS: dict[str, float] = {"optional_at": 0.33, "warranted_at": 0.66}

_MULTI_HOP_MIN_TABLES = 3  # fact + 1 dim = 2 tables = flat; 3+ = multi-hop
_BRIDGE_CAP = 2  # relationship count at which bridge_m2m_presence saturates
_DEPTH_STAR = 2  # diameter of a plain star (offset baseline)
_DEPTH_SPAN = 3  # diameter units above a star that map to 1.0
_FACT_SPAN = 2  # extra fact tables that map multi_fact_complexity to 1.0


def _table_names(model: SemanticModelMeta) -> set[str]:
    return {t.name for t in model.tables}


def _bridge_count(model: SemanticModelMeta) -> int:
    ttype = {t.name: t.table_type for t in model.tables}
    count = 0
    for r in model.relationships:
        if not r.is_active:
            continue
        if (
            r.cardinality == "many-to-many"
            or ttype.get(r.from_table) == TableType.BRIDGE
            or ttype.get(r.to_table) == TableType.BRIDGE
        ):
            count += 1
    return count


def _bridge_m2m_presence(model: SemanticModelMeta) -> float:
    return min(1.0, _bridge_count(model) / _BRIDGE_CAP)


def _adjacency(model: SemanticModelMeta) -> dict[str, set[str]]:
    names = _table_names(model)
    adj: dict[str, set[str]] = {n: set() for n in names}
    for r in model.relationships:
        if r.is_active and r.from_table in names and r.to_table in names:
            adj[r.from_table].add(r.to_table)
            adj[r.to_table].add(r.from_table)
    return adj


def _component(start: str, adj: dict[str, set[str]]) -> set[str]:
    comp: set[str] = set()
    dq = deque([start])
    while dq:
        n = dq.popleft()
        if n in comp:
            continue
        comp.add(n)
        dq.extend(adj[n] - comp)
    return comp


def _component_diameter(comp: set[str], adj: dict[str, set[str]]) -> int:
    diameter = 0
    for src in comp:
        dist = {src: 0}
        dq = deque([src])
        while dq:
            n = dq.popleft()
            for nb in adj[n]:
                if nb not in dist:
                    dist[nb] = dist[n] + 1
                    dq.append(nb)
        diameter = max(diameter, max(dist.values()))
    return diameter


def _largest_component_diameter(model: SemanticModelMeta) -> int:
    adj = _adjacency(model)
    seen: set[str] = set()
    best = 0
    for start in adj:
        if start in seen:
            continue
        comp = _component(start, adj)
        seen |= comp
        if len(comp) <= 2:
            continue
        best = max(best, _component_diameter(comp, adj))
    return best


def _relationship_graph_depth(model: SemanticModelMeta) -> float:
    diameter = _largest_component_diameter(model)
    return round(min(max(0, diameter - _DEPTH_STAR), _DEPTH_SPAN) / _DEPTH_SPAN, 2)


def _multi_fact_complexity(model: SemanticModelMeta) -> float:
    facts = sum(1 for t in model.tables if t.table_type == TableType.FACT)
    return round(min(1.0, max(0, facts - 1) / _FACT_SPAN), 2)


def _tables_from_columns(depends_on_columns: list[str], table_names: set[str]) -> set[str]:
    out: set[str] = set()
    for ref in depends_on_columns:
        name = ref.split("[", 1)[0].strip().strip("'")
        if name in table_names:
            out.add(name)
    return out


def _measure_question_sets(model: SemanticModelMeta, table_names: set[str]) -> list[set[str]]:
    sets: list[set[str]] = []
    for t in model.tables:
        for ms in t.measures:
            tables = _tables_from_columns(ms.depends_on_columns, table_names)
            if tables:  # exclude measure-of-measure (empty) -- not a question
                sets.append(tables)
    return sets


def _question_sets(
    questions: list[str], model: SemanticModelMeta, table_names: set[str]
) -> list[set[str]]:
    lowered = [(t.name, t.name.lower(), [c.name.lower() for c in t.columns]) for t in model.tables]
    sets: list[set[str]] = []
    for q in questions:
        ql = q.lower()
        matched: set[str] = set()
        for name, name_l, cols in lowered:
            if name_l in ql or any(col and col in ql for col in cols):
                matched.add(name)
        sets.append(matched & table_names)  # every question counted, even if empty
    return sets


def _resolve_questions(model: SemanticModelMeta, questions: list[str] | None):
    """Return (table_sets, source, matched_count). source in
    {'questions','copilot','measures', None} by precedence; only non-empty
    sources are selected so 0/0 never occurs."""
    table_names = _table_names(model)
    if questions:  # non-empty list only
        sets = _question_sets(questions, model, table_names)
        return sets, "questions", sum(1 for s in sets if s)
    prompts = None
    if model.copilot is not None and model.copilot.example_prompts is not None:
        prompts = model.copilot.example_prompts.prompts
    if prompts:
        sets = _question_sets(prompts, model, table_names)
        return sets, "copilot", sum(1 for s in sets if s)
    measure_sets = _measure_question_sets(model, table_names)
    if measure_sets:
        return measure_sets, "measures", len(measure_sets)
    return [], None, 0


def _workload_hop_pressure(sets: list[set[str]]) -> float | None:
    if not sets:
        return None  # signal drops
    multi = sum(1 for s in sets if len(s) >= _MULTI_HOP_MIN_TABLES)
    return round(multi / len(sets), 2)
