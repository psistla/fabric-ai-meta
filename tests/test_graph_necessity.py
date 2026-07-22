"""Tests for the graph-necessity advisor."""

from fabric_ai_meta.analyzer.graph_necessity import PRESSURE_THRESHOLDS, PRESSURE_WEIGHTS


def test_pressure_weights_sum_to_one():
    assert abs(sum(PRESSURE_WEIGHTS.values()) - 1.0) < 1e-9
    assert set(PRESSURE_WEIGHTS) == {
        "workload_hop_pressure",
        "bridge_m2m_presence",
        "relationship_graph_depth",
        "multi_fact_complexity",
    }


def test_pressure_threshold_keys():
    # guards against a typo surfacing as a KeyError deep in Task 4
    assert set(PRESSURE_THRESHOLDS) == {"optional_at", "warranted_at"}
