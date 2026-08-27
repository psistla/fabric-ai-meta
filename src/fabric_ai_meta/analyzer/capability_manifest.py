"""Capability manifest: what this model can and cannot answer.

A whole-model artifact - one manifest per model, generated once, unlike
guide_query which answers a single query on demand. Every measure is
classified using the exact same rules guide_query uses to decide whether to
warn or exclude, so an agent that already trusts guide_query's contract can
trust this one without learning new semantics:

- refused: report-plumbing only (same boundary as guide_query's `excluded`)
- answerable_with_caveats: 1+ warnings from _warnings_for_measure (semi-
  additive, ratio, hardcoded literal, implicit business rule, opaque
  calculation group)
- answerable: neither

Reuses analyzer.query_guidance._report_plumbing_reason and
_warnings_for_measure directly rather than re-implementing trap detection -
this manifest can never disagree with guide_query about the same measure.
It inherits every heuristic gap that module has, including the documented,
deliberately-unfixed report-plumbing gap (a FORMAT() call embedded inside a
string concatenation is not detected - see query_guidance's own docstring).
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone

from fabric_ai_meta.analyzer.query_guidance import (
    _report_plumbing_reason,
    _warnings_for_measure,
)
from fabric_ai_meta.models.metadata import MeasureMeta, SemanticModelMeta

_SCHEMA_URL = (
    "https://raw.githubusercontent.com/psistla/fabric-ai-meta/master/"
    "schemas/capability-manifest/v1.json"
)


def _classify_measure(model: SemanticModelMeta, measure: MeasureMeta) -> dict:
    reason = _report_plumbing_reason(measure.dax_expression)
    if reason:
        return {
            "status": "refused",
            "warnings": [],
            "refused_reason": {"reason": "report_plumbing", "detail": reason},
        }
    warnings = _warnings_for_measure(model, measure)
    status = "answerable_with_caveats" if warnings else "answerable"
    return {"status": status, "warnings": warnings, "refused_reason": None}


def generate_capability_manifest(model: SemanticModelMeta) -> dict:
    """Classify every measure in `model` as answerable, answerable-with-
    caveats, or refused, using the same rules guide_query applies
    per-query. Returns the full manifest dict, ready to serialize."""
    measures: list[dict] = []
    counts = {"answerable": 0, "answerable_with_caveats": 0, "refused": 0}

    for table in model.tables:
        for measure in table.measures:
            classification = _classify_measure(model, measure)
            counts[classification["status"]] += 1
            measures.append({"table": table.name, "name": measure.name, **classification})

    return {
        "$schema": _SCHEMA_URL,
        "version": "1.0",
        "model": model.name,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": {"total_measures": len(measures), **counts},
        "measures": measures,
    }


def write_capability_manifest(model: SemanticModelMeta, output_path: str) -> str:
    """Generate the capability manifest and write it to a JSON file.

    Returns the output file path.
    """
    manifest = generate_capability_manifest(model)
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
    return output_path
