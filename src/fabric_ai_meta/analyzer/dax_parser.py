"""DAX dependency parser (SPEC.md Section 6.2)."""

import logging
import re

from fabric_ai_meta.analyzer.classifier import TIME_INTEL_FUNCTIONS
from fabric_ai_meta.models.metadata import MeasureMeta

logger = logging.getLogger(__name__)

# [Name] not preceded by a table name (no 'Table'[col] or Table[col] prefix)
_MEASURE_REF_RE = re.compile(r"(?<!['\w])\[([^\]]+)\]")

# 'Table Name'[Column] — quoted table name
_QUOTED_COL_RE = re.compile(r"'([^']+)'\[([^\]]+)\]")

# TableName[Column] — unquoted single-word table name
_UNQUOTED_COL_RE = re.compile(r"(\w+)\[([^\]]+)\]")

# Filter modification functions
_FILTER_MOD_RE = re.compile(
    r"\b(ALLEXCEPT|CALCULATE|ALL|REMOVEFILTERS|KEEPFILTERS)\b", re.IGNORECASE
)

# Implicit business rules: = "string" or = number
_BIZ_RULE_STR_RE = re.compile(r'=\s*"([^"]+)"')
_BIZ_RULE_NUM_RE = re.compile(r"=\s*(\d+(?:\.\d+)?)")


def parse_measure_dependencies(
    measure_name: str, dax: str, all_measures: dict[str, str]
) -> dict:
    """Parse a DAX expression for dependencies and structural patterns.

    Returns:
        {
            "measure_name": str,
            "depends_on_measures": list[str],      # [Measure] refs not preceded by table
            "depends_on_columns": list[str],        # Table[Column] refs
            "time_intelligence_functions": list[str],
            "filter_modifications": list[str],
            "implicit_business_rules": list[str],
        }
    """
    dax_upper = dax.upper()

    # --- Column refs (quoted and unquoted) ---
    column_refs: set[str] = set()
    for m in _QUOTED_COL_RE.finditer(dax):
        column_refs.add(f"{m.group(1)}[{m.group(2)}]")
    for m in _UNQUOTED_COL_RE.finditer(dax):
        column_refs.add(f"{m.group(1)}[{m.group(2)}]")

    # --- Measure refs: [Name] not preceded by quote or word char ---
    # Negative lookbehind (?<!['\w]) prevents matching the [Col] part of Table[Col]
    # and 'Table'[Col]. We also filter out any name that matches a column part name.
    col_part_names = {ref.split("[")[1].rstrip("]") for ref in column_refs}
    raw_refs = _MEASURE_REF_RE.findall(dax)
    measure_ref_names = [ref for ref in raw_refs if ref not in col_part_names]
    depends_on_measures = sorted({f"[{ref}]" for ref in measure_ref_names})

    # --- Time intelligence functions ---
    functions_used = set(re.findall(r"\b([A-Z]+)\s*\(", dax_upper))
    ti_functions = sorted(functions_used & TIME_INTEL_FUNCTIONS)

    # --- Filter modification functions ---
    filter_mods = sorted({m.group(1).upper() for m in _FILTER_MOD_RE.finditer(dax_upper)})

    # --- Implicit business rules: hardcoded filter values ---
    business_rules: list[str] = []
    for m in _BIZ_RULE_STR_RE.finditer(dax):
        business_rules.append(f'= "{m.group(1)}"')
    for m in _BIZ_RULE_NUM_RE.finditer(dax):
        business_rules.append(f"= {m.group(1)}")

    return {
        "measure_name": measure_name,
        "depends_on_measures": depends_on_measures,
        "depends_on_columns": sorted(column_refs),
        "time_intelligence_functions": ti_functions,
        "filter_modifications": filter_mods,
        "implicit_business_rules": business_rules,
    }


def build_dependency_graph(measures: list[MeasureMeta]) -> dict:
    """Build a full dependency graph for a list of measures.

    Returns a dict keyed by measure name; values are the dependency dicts from
    parse_measure_dependencies. Logs a warning for any circular dependencies but
    does not raise.
    """
    all_measures = {m.name: m.dax_expression for m in measures}
    graph = {
        m.name: parse_measure_dependencies(m.name, m.dax_expression, all_measures)
        for m in measures
    }
    _detect_cycles(graph)
    return graph


def _detect_cycles(graph: dict) -> None:
    """DFS-based cycle detection; logs a warning per cycle edge found."""
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {node: WHITE for node in graph}

    def dfs(node: str, path: list[str]) -> None:
        color[node] = GRAY
        for dep in graph[node].get("depends_on_measures", []):
            if dep not in color:
                continue
            if color[dep] == GRAY:
                logger.warning(
                    "Circular dependency detected: %s -> %s (path: %s)",
                    node,
                    dep,
                    " -> ".join(path + [dep]),
                )
                continue
            if color[dep] == WHITE:
                dfs(dep, path + [node])
        color[node] = BLACK

    for node in list(color):
        if color[node] == WHITE:
            dfs(node, [node])
