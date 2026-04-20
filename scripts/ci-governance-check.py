"""Enforce governance thresholds against a governance-report.json file.

Standalone script. Depends only on the Python standard library so CI runners
do not need ``fabric-ai-meta`` installed at gate time when the report is
produced upstream and passed in as an artifact.

Exit codes:
    0  All thresholds satisfied.
    1  At least one threshold breached, or the report file could not be read.

Usage:
    python scripts/ci-governance-check.py <report.json> \\
        [--max-naming-issues N] \\
        [--max-duplicate-measures N] \\
        [--min-score F]
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path


def load_report(path: Path) -> dict:
    if not path.is_file():
        raise FileNotFoundError(f"Report file not found: {path}")
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def compute_average_score(report: dict) -> float | None:
    """Compute the average AI readiness score across the ranked models.

    The governance report's ``score_ranking`` carries one entry per model
    with an ``ai_readiness_score`` field. Models that failed to score have
    ``None`` and are excluded from the average. Returns ``None`` when no
    model was successfully scored.
    """
    ranking = report.get("score_ranking") or []
    scores = [
        entry.get("ai_readiness_score")
        for entry in ranking
        if isinstance(entry, dict) and entry.get("ai_readiness_score") is not None
    ]
    if not scores:
        return None
    return sum(scores) / len(scores)


def evaluate(
    report: dict,
    max_naming_issues: int | None,
    max_duplicate_measures: int | None,
    min_score: float,
) -> tuple[bool, list[str]]:
    """Return (passed, messages). ``passed`` is False if any threshold breached."""
    messages: list[str] = []
    passed = True

    summary = report.get("summary") or {}
    naming_issues = int(summary.get("total_naming_issues") or 0)
    duplicate_measures = int(summary.get("total_duplicate_measures") or 0)
    model_count = int(summary.get("model_count") or 0)

    if max_naming_issues is not None and naming_issues > max_naming_issues:
        passed = False
        messages.append(
            f"FAIL: naming inconsistencies = {naming_issues} "
            f"(threshold: {max_naming_issues})"
        )
    else:
        messages.append(
            f"OK:   naming inconsistencies = {naming_issues}"
            + (f" (threshold: {max_naming_issues})" if max_naming_issues is not None else "")
        )

    if max_duplicate_measures is not None and duplicate_measures > max_duplicate_measures:
        passed = False
        messages.append(
            f"FAIL: duplicate measures = {duplicate_measures} "
            f"(threshold: {max_duplicate_measures})"
        )
    else:
        messages.append(
            f"OK:   duplicate measures = {duplicate_measures}"
            + (f" (threshold: {max_duplicate_measures})" if max_duplicate_measures is not None else "")
        )

    average_score = compute_average_score(report)
    if average_score is None:
        if min_score > 0:
            passed = False
            messages.append(
                f"FAIL: no models had a score; cannot satisfy min-score {min_score:.2f}"
            )
        else:
            messages.append("OK:   no models had a score; min-score check skipped")
    else:
        if average_score + 1e-9 < min_score:
            passed = False
            messages.append(
                f"FAIL: average score = {average_score:.3f} (threshold: {min_score:.3f})"
            )
        else:
            messages.append(
                f"OK:   average score = {average_score:.3f} (threshold: {min_score:.3f})"
            )

    messages.append(f"      models in report: {model_count}")
    return passed, messages


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Enforce governance thresholds against a fabric-ai-meta report.",
    )
    p.add_argument("report", type=Path, help="Path to governance-report.json")
    p.add_argument(
        "--max-naming-issues", type=int, default=None,
        help="Fail if total_naming_issues exceeds this value.",
    )
    p.add_argument(
        "--max-duplicate-measures", type=int, default=None,
        help="Fail if total_duplicate_measures exceeds this value.",
    )
    p.add_argument(
        "--min-score", type=float, default=0.0,
        help="Fail if average ai_readiness_score across models is below this value (0.0-1.0).",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv if argv is not None else sys.argv[1:])

    if not (0.0 <= args.min_score <= 1.0) or math.isnan(args.min_score):
        print(f"ERROR: --min-score must be between 0.0 and 1.0, got {args.min_score}",
              file=sys.stderr)
        return 1

    try:
        report = load_report(args.report)
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    except json.JSONDecodeError as exc:
        print(f"ERROR: {args.report} is not valid JSON: {exc}", file=sys.stderr)
        return 1

    passed, messages = evaluate(
        report,
        max_naming_issues=args.max_naming_issues,
        max_duplicate_measures=args.max_duplicate_measures,
        min_score=args.min_score,
    )

    print(f"\nGovernance check: {args.report}")
    for line in messages:
        print(f"  {line}")
    print()
    if passed:
        print("PASS: all thresholds satisfied.")
        return 0
    print("FAIL: one or more thresholds were breached.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
