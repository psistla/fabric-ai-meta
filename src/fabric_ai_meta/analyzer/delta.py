"""Compare two workspace summaries and produce a delta report."""


def _compute_copilot_changes(
    baseline_signals: dict | None,
    current_signals: dict | None,
) -> dict | None:
    """Diff Copilot signal blocks between two snapshots.

    Returns ``None`` unless BOTH sides have Copilot signals - asymmetric input
    (one scan was run with ``--with-copilot`` and the other without) cannot
    be meaningfully diffed without producing false regression alerts.
    """
    if not isinstance(baseline_signals, dict) or not isinstance(current_signals, dict):
        return None

    def _delta(key: str, default: int = 0) -> int:
        return current_signals.get(key, default) - baseline_signals.get(key, default)

    b_has_instr = bool(baseline_signals.get("has_ai_instructions"))
    c_has_instr = bool(current_signals.get("has_ai_instructions"))
    return {
        "ai_instructions_added": (not b_has_instr) and c_has_instr,
        "ai_instructions_removed": b_has_instr and (not c_has_instr),
        "verified_answer_count_change": _delta("verified_answer_count"),
        "ai_data_schema_table_count_change": _delta("ai_data_schema_table_count"),
        "example_prompt_count_change": _delta("example_prompt_count"),
    }


def compare_workspace_summaries(baseline: dict, current: dict) -> dict:
    """Compare two workspace-summary.json dicts and return a delta report.

    Args:
        baseline: The earlier workspace summary (from a previous scan).
        current: The later workspace summary (from the current scan).

    Returns:
        Dict with keys: summary, model_deltas.
    """
    baseline_models = {m["name"]: m for m in baseline.get("models", [])}
    current_models = {m["name"]: m for m in current.get("models", [])}

    baseline_names = set(baseline_models.keys())
    current_names = set(current_models.keys())

    models_added = sorted(current_names - baseline_names)
    models_removed = sorted(baseline_names - current_names)

    baseline_avg = baseline.get("average_readiness_score")
    current_avg = current.get("average_readiness_score")
    if baseline_avg is not None and current_avg is not None:
        avg_change = current_avg - baseline_avg
    else:
        avg_change = None

    model_deltas = []

    for name in models_added:
        m = current_models[name]
        model_deltas.append({
            "name": name,
            "status": "new",
            "score_before": None,
            "score_after": m.get("ai_readiness_score"),
            "score_change": None,
            "table_count_change": None,
            "measure_count_change": None,
            "description_coverage_change": None,
        })

    for name in models_removed:
        m = baseline_models[name]
        model_deltas.append({
            "name": name,
            "status": "removed",
            "score_before": m.get("ai_readiness_score"),
            "score_after": None,
            "score_change": None,
            "table_count_change": None,
            "measure_count_change": None,
            "description_coverage_change": None,
        })

    for name in sorted(baseline_names & current_names):
        b = baseline_models[name]
        c = current_models[name]

        b_score = b.get("ai_readiness_score")
        c_score = c.get("ai_readiness_score")
        if b_score is not None and c_score is not None:
            score_change = c_score - b_score
        else:
            score_change = None

        table_change = c.get("table_count", 0) - b.get("table_count", 0)
        measure_change = c.get("measure_count", 0) - b.get("measure_count", 0)

        b_desc = b.get("description_coverage")
        c_desc = c.get("description_coverage")
        if b_desc is not None and c_desc is not None:
            desc_change = c_desc - b_desc
        else:
            desc_change = None

        copilot_changes = _compute_copilot_changes(b.get("copilot"), c.get("copilot"))

        if score_change is not None and abs(score_change) > 1e-9:
            status = "improved" if score_change > 0 else "degraded"
        elif table_change != 0 or measure_change != 0:
            status = "improved" if (table_change > 0 or measure_change > 0) else "degraded"
        else:
            status = "unchanged"

        # A Copilot regression downgrades an otherwise-unchanged model.
        if (
            copilot_changes is not None
            and copilot_changes.get("ai_instructions_removed")
            and status == "unchanged"
        ):
            status = "degraded"

        delta_entry = {
            "name": name,
            "status": status,
            "score_before": b_score,
            "score_after": c_score,
            "score_change": round(score_change, 6) if score_change is not None else None,
            "table_count_change": table_change,
            "measure_count_change": measure_change,
            "description_coverage_change": round(desc_change, 6) if desc_change is not None else None,
        }
        if copilot_changes is not None:
            delta_entry["copilot_changes"] = copilot_changes
        model_deltas.append(delta_entry)

    return {
        "summary": {
            "baseline_timestamp": baseline.get("scan_timestamp"),
            "current_timestamp": current.get("scan_timestamp"),
            "model_count_change": current.get("model_count", 0) - baseline.get("model_count", 0),
            "average_score_change": round(avg_change, 6) if avg_change is not None else None,
            "models_added": models_added,
            "models_removed": models_removed,
        },
        "model_deltas": model_deltas,
    }


def format_delta_text(delta: dict) -> str:
    """Format a delta report as human-readable text.

    Args:
        delta: Output of compare_workspace_summaries().

    Returns:
        Formatted text string.
    """
    lines = []
    s = delta["summary"]

    lines.append("=== Workspace Delta Report ===")
    lines.append(f"Baseline: {s['baseline_timestamp'] or 'unknown'}")
    lines.append(f"Current:  {s['current_timestamp'] or 'unknown'}")
    lines.append("")

    count_change = s["model_count_change"]
    sign = "+" if count_change > 0 else ""
    lines.append(f"Model count change: {sign}{count_change}")

    avg_change = s["average_score_change"]
    if avg_change is not None:
        sign = "+" if avg_change > 0 else ""
        lines.append(f"Average score change: {sign}{avg_change:.4f}")

    if s["models_added"]:
        lines.append(f"\nModels added: {', '.join(s['models_added'])}")
    if s["models_removed"]:
        lines.append(f"\nModels removed: {', '.join(s['models_removed'])}")

    lines.append("")
    lines.append("--- Per-Model Changes ---")

    for md in delta["model_deltas"]:
        status = md["status"]
        name = md["name"]

        if status == "new":
            score_str = f"{md['score_after']:.4f}" if md["score_after"] is not None else "N/A"
            lines.append(f"  + {name} (new, score: {score_str})")
        elif status == "removed":
            score_str = f"{md['score_before']:.4f}" if md["score_before"] is not None else "N/A"
            lines.append(f"  - {name} (removed, was: {score_str})")
        elif status == "improved":
            sc = md["score_change"]
            sc_str = f"+{sc:.4f}" if sc is not None else ""
            lines.append(f"  ^ {name} (improved{', score: ' + sc_str if sc_str else ''})")
        elif status == "degraded":
            sc = md["score_change"]
            sc_str = f"{sc:.4f}" if sc is not None else ""
            lines.append(f"  v {name} (degraded{', score: ' + sc_str if sc_str else ''})")
        else:
            lines.append(f"  = {name} (unchanged)")

        cop = md.get("copilot_changes")
        if isinstance(cop, dict):
            notes: list[str] = []
            if cop.get("ai_instructions_removed"):
                notes.append("AI Instructions removed")
            if cop.get("ai_instructions_added"):
                notes.append("AI Instructions added")
            for key, label in (
                ("verified_answer_count_change", "verified answers"),
                ("ai_data_schema_table_count_change", "schema tables"),
                ("example_prompt_count_change", "example prompts"),
            ):
                change = cop.get(key, 0)
                if change:
                    sign = "+" if change > 0 else ""
                    notes.append(f"{label} {sign}{change}")
            if notes:
                lines.append(f"      copilot: {'; '.join(notes)}")

    return "\n".join(lines)
