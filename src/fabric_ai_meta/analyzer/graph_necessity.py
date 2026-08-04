"""Graph-necessity advisor.

Answers "does this model's workload justify a graph/ontology, or does a
described schema already suffice?" from already-extracted metadata. Pure:
no extraction, no Fabric calls, no required LLM calls.

Spec: planning/archive/specs/2026-07-22-graph-necessity-advisor.md
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


_RECOMMENDATION = {
    "GRAPH_UNNECESSARY": "Described schema suffices; defer ontology/graph adoption.",
    "GRAPH_OPTIONAL": "Mixed signal; a graph would help specific relational slices. "
                      "Revisit if multi-hop questions grow.",
    "GRAPH_WARRANTED": "Genuine multi-hop workload; an ontology/graph is warranted.",
}

_CONFIDENCE = {"questions": "strong", "copilot": "evidenced",
               "measures": "evidenced", None: "directional"}


def _evidence(present, q_sets, source, matched, model):
    # Invariant: only workload_hop_pressure can drop, so the three structural
    # signals are always in `present`. Guard them if that ever changes.
    lines = []
    if "workload_hop_pressure" in present:
        n = len(q_sets)
        k = sum(1 for s in q_sets if len(s) >= _MULTI_HOP_MIN_TABLES)
        if present["workload_hop_pressure"] >= 0.5:
            lines.append(f"{k} of {n} questions traverse >=3 tables (multi-hop)")
        else:
            lines.append(f"{n - k} of {n} questions resolve within <=2 tables (flat aggregation)")
    if present["bridge_m2m_presence"] >= 0.5:
        lines.append(
            f"{_bridge_count(model)} bridge/many-to-many relationship(s) "
            "mediate relational analysis"
        )
    else:
        lines.append("no bridge or many-to-many relationships")
    diameter = _largest_component_diameter(model)
    if present["relationship_graph_depth"] >= 0.5:
        lines.append(f"relationship graph is deep (diameter {diameter})")
    else:
        lines.append(f"relationship graph is a shallow star (diameter {diameter})")
    facts = sum(1 for t in model.tables if t.table_type == TableType.FACT)
    if present["multi_fact_complexity"] >= 0.5:
        lines.append(f"{facts} fact tables imply cross-fact / drill-across questions")
    else:
        lines.append("single fact table")
    if source == "questions" and q_sets and matched < len(q_sets) / 2:
        lines.append(
            f"note: only {matched} of {len(q_sets)} supplied questions matched model "
            "vocabulary; treat pressure as low-coverage"
        )
    return lines


def assess_graph_necessity(
    model: SemanticModelMeta, questions: list[str] | None = None
) -> dict:
    """Assess whether this model's workload justifies a graph/ontology.

    Args:
        model: The semantic model to assess (classification should have run).
        questions: Optional real questions that sharpen the workload signal.

    Returns:
        Dict with keys: name, tier, pressure, confidence, signals, evidence,
        recommendation.
    """
    q_sets, source, matched = _resolve_questions(model, questions)
    raw = {
        "workload_hop_pressure": _workload_hop_pressure(q_sets),
        "bridge_m2m_presence": _bridge_m2m_presence(model),
        "relationship_graph_depth": _relationship_graph_depth(model),
        "multi_fact_complexity": _multi_fact_complexity(model),
    }
    present = {k: v for k, v in raw.items() if v is not None}
    weight_sum = sum(PRESSURE_WEIGHTS[k] for k in present)
    pressure = round(sum(present[k] * PRESSURE_WEIGHTS[k] for k in present) / weight_sum, 2)

    tier = (
        "GRAPH_WARRANTED" if pressure >= PRESSURE_THRESHOLDS["warranted_at"]
        else "GRAPH_OPTIONAL" if pressure >= PRESSURE_THRESHOLDS["optional_at"]
        else "GRAPH_UNNECESSARY"
    )
    signals = {}
    for k in present:
        entry = {
            "score": round(present[k], 2),
            "weight": round(PRESSURE_WEIGHTS[k] / weight_sum, 2),
        }
        if k == "workload_hop_pressure":
            entry["source"] = source
        signals[k] = entry

    confidence = _CONFIDENCE[source]
    # Supplied questions only earn "strong" if they actually resolved against the
    # model's vocabulary. Fewer than half matching means the workload signal was
    # computed from mostly-empty question sets, so say so instead of overclaiming.
    if source == "questions" and matched < len(q_sets) / 2:
        confidence = "directional"

    return {
        "name": model.name,
        "tier": tier,
        "pressure": pressure,
        "confidence": confidence,
        "signals": signals,
        "evidence": _evidence(present, q_sets, source, matched, model),
        "recommendation": _RECOMMENDATION[tier],
    }
