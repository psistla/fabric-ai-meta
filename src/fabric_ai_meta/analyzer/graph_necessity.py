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
