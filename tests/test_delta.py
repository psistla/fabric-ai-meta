"""Tests for workspace summary delta/diff comparison."""

import json

from fabric_ai_meta.analyzer.delta import compare_workspace_summaries, format_delta_text


def _make_summary(models, timestamp="2026-04-01T00:00:00Z"):
    """Build a minimal workspace-summary dict."""
    total = len(models)
    scores = [m["ai_readiness_score"] for m in models if m.get("ai_readiness_score") is not None]
    avg = sum(scores) / len(scores) if scores else None
    return {
        "$schema": "https://raw.githubusercontent.com/psistla/fabric-ai-meta/master/schemas/workspace-summary/v1.json",
        "version": "1.0",
        "workspace": "test",
        "scan_timestamp": timestamp,
        "model_count": total,
        "average_readiness_score": avg,
        "models": models,
        "score_ranking": [m["name"] for m in sorted(models, key=lambda x: x.get("ai_readiness_score") or 0, reverse=True)],
        "recommendations": [],
    }


def _make_model(name, score=0.7, tables=4, measures=5, desc_cov=0.8, copilot=None):
    entry = {
        "name": name,
        "slug": name.lower().replace(" ", "-"),
        "ai_readiness_score": score,
        "table_count": tables,
        "measure_count": measures,
        "description_coverage": desc_cov,
        "extraction_timestamp": "2026-04-01T00:00:00Z",
        "output_directory": f"{name.lower().replace(' ', '-')}/",
        "errors": [],
    }
    if copilot is not None:
        entry["copilot"] = copilot
    return entry


def _copilot_signals(
    has_ai_instructions=True, verified_answer_count=2,
    ai_data_schema_table_count=3, example_prompt_count=2,
    copilot_enabled=True, copilot_version="1.0",
    ai_instructions_length=42,
):
    return {
        "has_ai_instructions": has_ai_instructions,
        "ai_instructions_length": ai_instructions_length,
        "verified_answer_count": verified_answer_count,
        "ai_data_schema_table_count": ai_data_schema_table_count,
        "example_prompt_count": example_prompt_count,
        "copilot_enabled": copilot_enabled,
        "copilot_version": copilot_version,
    }


# ---------------------------------------------------------------------------
# Copilot signal delta tests (S7-04)
# ---------------------------------------------------------------------------

def test_delta_omits_copilot_changes_when_neither_side_has_signals():
    baseline = _make_summary([_make_model("M", score=0.6)])
    current = _make_summary([_make_model("M", score=0.6)])
    delta = compare_workspace_summaries(baseline, current)
    md = next(d for d in delta["model_deltas"] if d["name"] == "M")
    assert "copilot_changes" not in md


def test_delta_omits_copilot_changes_when_only_one_side_has_signals():
    """Toggling --with-copilot between scans must NOT report false regressions."""
    baseline = _make_summary([
        _make_model("M", score=0.6, copilot=_copilot_signals(has_ai_instructions=True))
    ])
    current = _make_summary([_make_model("M", score=0.6)])  # no copilot
    delta = compare_workspace_summaries(baseline, current)
    md = next(d for d in delta["model_deltas"] if d["name"] == "M")
    assert "copilot_changes" not in md
    assert md["status"] == "unchanged"

    # Mirror case: copilot only in current.
    baseline = _make_summary([_make_model("M", score=0.6)])
    current = _make_summary([
        _make_model("M", score=0.6, copilot=_copilot_signals(has_ai_instructions=True))
    ])
    delta = compare_workspace_summaries(baseline, current)
    md = next(d for d in delta["model_deltas"] if d["name"] == "M")
    assert "copilot_changes" not in md


def test_delta_detects_ai_instructions_removal():
    baseline = _make_summary([
        _make_model("M", score=0.7, copilot=_copilot_signals(has_ai_instructions=True))
    ])
    current = _make_summary([
        _make_model("M", score=0.7, copilot=_copilot_signals(
            has_ai_instructions=False, ai_instructions_length=0,
        ))
    ])
    delta = compare_workspace_summaries(baseline, current)
    md = next(d for d in delta["model_deltas"] if d["name"] == "M")
    assert md["copilot_changes"]["ai_instructions_removed"] is True
    # Removal of AI Instructions on an otherwise-unchanged model downgrades status.
    assert md["status"] == "degraded"


def test_delta_detects_ai_instructions_added():
    baseline = _make_summary([
        _make_model("M", score=0.7, copilot=_copilot_signals(
            has_ai_instructions=False, ai_instructions_length=0,
        ))
    ])
    current = _make_summary([
        _make_model("M", score=0.7, copilot=_copilot_signals(has_ai_instructions=True))
    ])
    delta = compare_workspace_summaries(baseline, current)
    md = next(d for d in delta["model_deltas"] if d["name"] == "M")
    assert md["copilot_changes"]["ai_instructions_added"] is True
    assert md["copilot_changes"]["ai_instructions_removed"] is False


def test_delta_detects_verified_answer_count_change():
    baseline = _make_summary([
        _make_model("M", copilot=_copilot_signals(verified_answer_count=5))
    ])
    current = _make_summary([
        _make_model("M", copilot=_copilot_signals(verified_answer_count=3))
    ])
    delta = compare_workspace_summaries(baseline, current)
    md = next(d for d in delta["model_deltas"] if d["name"] == "M")
    assert md["copilot_changes"]["verified_answer_count_change"] == -2


def test_delta_format_text_mentions_copilot_regression():
    baseline = _make_summary([
        _make_model("M", copilot=_copilot_signals(has_ai_instructions=True))
    ])
    current = _make_summary([
        _make_model("M", copilot=_copilot_signals(
            has_ai_instructions=False, ai_instructions_length=0,
        ))
    ])
    delta = compare_workspace_summaries(baseline, current)
    text = format_delta_text(delta)
    assert "AI Instructions removed" in text


# ---------------------------------------------------------------------------
# compare_workspace_summaries, core logic
# ---------------------------------------------------------------------------


class TestCompareWorkspaceSummaries:
    def test_identical_summaries_no_changes(self):
        """Two identical summaries should show zero changes."""
        models = [_make_model("Model A"), _make_model("Model B")]
        baseline = _make_summary(models)
        current = _make_summary(models)
        delta = compare_workspace_summaries(baseline, current)

        assert delta["summary"]["model_count_change"] == 0
        assert delta["summary"]["average_score_change"] == 0.0
        assert delta["summary"]["models_added"] == []
        assert delta["summary"]["models_removed"] == []
        for md in delta["model_deltas"]:
            assert md["status"] == "unchanged"
            assert md["score_change"] == 0.0
            assert md["table_count_change"] == 0
            assert md["measure_count_change"] == 0

    def test_model_added(self):
        """Adding a model shows in models_added and model_deltas."""
        baseline = _make_summary([_make_model("Model A")])
        current = _make_summary([_make_model("Model A"), _make_model("Model B", score=0.8)])
        delta = compare_workspace_summaries(baseline, current)

        assert delta["summary"]["model_count_change"] == 1
        assert "Model B" in delta["summary"]["models_added"]
        new_deltas = [d for d in delta["model_deltas"] if d["status"] == "new"]
        assert len(new_deltas) == 1
        assert new_deltas[0]["name"] == "Model B"
        assert new_deltas[0]["score_after"] == 0.8
        assert new_deltas[0]["score_before"] is None

    def test_model_removed(self):
        """Removing a model shows in models_removed and model_deltas."""
        baseline = _make_summary([_make_model("Model A"), _make_model("Model B")])
        current = _make_summary([_make_model("Model A")])
        delta = compare_workspace_summaries(baseline, current)

        assert delta["summary"]["model_count_change"] == -1
        assert "Model B" in delta["summary"]["models_removed"]
        removed = [d for d in delta["model_deltas"] if d["status"] == "removed"]
        assert len(removed) == 1
        assert removed[0]["name"] == "Model B"
        assert removed[0]["score_before"] == 0.7
        assert removed[0]["score_after"] is None

    def test_score_improvement(self):
        """Improving a model's score shows status=improved with positive change."""
        baseline = _make_summary([_make_model("Model A", score=0.6)])
        current = _make_summary([_make_model("Model A", score=0.8)])
        delta = compare_workspace_summaries(baseline, current)

        md = delta["model_deltas"][0]
        assert md["status"] == "improved"
        assert md["score_change"] > 0
        assert md["score_before"] == 0.6
        assert md["score_after"] == 0.8

    def test_score_regression(self):
        """A model's score dropping shows status=degraded with negative change."""
        baseline = _make_summary([_make_model("Model A", score=0.8)])
        current = _make_summary([_make_model("Model A", score=0.6)])
        delta = compare_workspace_summaries(baseline, current)

        md = delta["model_deltas"][0]
        assert md["status"] == "degraded"
        assert md["score_change"] < 0

    def test_mixed_changes(self):
        """Add + remove + change in one comparison."""
        baseline = _make_summary([
            _make_model("Keep", score=0.7),
            _make_model("Remove", score=0.5),
        ])
        current = _make_summary([
            _make_model("Keep", score=0.9),
            _make_model("New", score=0.6),
        ])
        delta = compare_workspace_summaries(baseline, current)

        assert delta["summary"]["model_count_change"] == 0
        assert "New" in delta["summary"]["models_added"]
        assert "Remove" in delta["summary"]["models_removed"]

        statuses = {d["name"]: d["status"] for d in delta["model_deltas"]}
        assert statuses["Keep"] == "improved"
        assert statuses["New"] == "new"
        assert statuses["Remove"] == "removed"

    def test_table_count_change_detected(self):
        """Changing table count without score change still detects change."""
        baseline = _make_summary([_make_model("Model A", score=0.7, tables=4)])
        current = _make_summary([_make_model("Model A", score=0.7, tables=6)])
        delta = compare_workspace_summaries(baseline, current)

        md = delta["model_deltas"][0]
        assert md["table_count_change"] == 2
        assert md["status"] == "improved"

    def test_description_coverage_change(self):
        """Description coverage change is tracked."""
        baseline = _make_summary([_make_model("Model A", desc_cov=0.5)])
        current = _make_summary([_make_model("Model A", desc_cov=0.9)])
        delta = compare_workspace_summaries(baseline, current)

        md = delta["model_deltas"][0]
        assert md["description_coverage_change"] is not None
        assert md["description_coverage_change"] > 0

    def test_average_score_change(self):
        """Average score change is computed correctly."""
        baseline = _make_summary([_make_model("A", score=0.6), _make_model("B", score=0.8)])
        current = _make_summary([_make_model("A", score=0.7), _make_model("B", score=0.9)])
        delta = compare_workspace_summaries(baseline, current)

        assert delta["summary"]["average_score_change"] is not None
        assert delta["summary"]["average_score_change"] > 0

    def test_delta_is_json_serializable(self):
        """Delta report must be JSON-serializable."""
        baseline = _make_summary([_make_model("A")])
        current = _make_summary([_make_model("A"), _make_model("B")])
        delta = compare_workspace_summaries(baseline, current)

        raw = json.dumps(delta)
        parsed = json.loads(raw)
        assert "summary" in parsed
        assert "model_deltas" in parsed

    def test_summary_has_required_keys(self):
        """Summary section has all required keys."""
        delta = compare_workspace_summaries(
            _make_summary([_make_model("A")]),
            _make_summary([_make_model("A")]),
        )
        for key in ("baseline_timestamp", "current_timestamp", "model_count_change",
                     "average_score_change", "models_added", "models_removed"):
            assert key in delta["summary"], f"Missing key: {key}"

    def test_model_delta_has_required_keys(self):
        """Each model delta entry has all required keys."""
        delta = compare_workspace_summaries(
            _make_summary([_make_model("A")]),
            _make_summary([_make_model("A")]),
        )
        for md in delta["model_deltas"]:
            for key in ("name", "status", "score_before", "score_after", "score_change",
                         "table_count_change", "measure_count_change", "description_coverage_change"):
                assert key in md, f"Missing key: {key}"


# ---------------------------------------------------------------------------
# format_delta_text
# ---------------------------------------------------------------------------


class TestFormatDeltaText:
    def test_text_output_contains_header(self):
        delta = compare_workspace_summaries(
            _make_summary([_make_model("A")]),
            _make_summary([_make_model("A")]),
        )
        text = format_delta_text(delta)
        assert "Workspace Delta Report" in text

    def test_text_output_shows_added_model(self):
        delta = compare_workspace_summaries(
            _make_summary([]),
            _make_summary([_make_model("New Model")]),
        )
        text = format_delta_text(delta)
        assert "New Model" in text
        assert "new" in text

    def test_text_output_shows_removed_model(self):
        delta = compare_workspace_summaries(
            _make_summary([_make_model("Old Model")]),
            _make_summary([]),
        )
        text = format_delta_text(delta)
        assert "Old Model" in text
        assert "removed" in text

    def test_text_output_shows_improved(self):
        delta = compare_workspace_summaries(
            _make_summary([_make_model("A", score=0.5)]),
            _make_summary([_make_model("A", score=0.9)]),
        )
        text = format_delta_text(delta)
        assert "improved" in text

    def test_text_output_shows_unchanged(self):
        models = [_make_model("A")]
        delta = compare_workspace_summaries(_make_summary(models), _make_summary(models))
        text = format_delta_text(delta)
        assert "unchanged" in text
