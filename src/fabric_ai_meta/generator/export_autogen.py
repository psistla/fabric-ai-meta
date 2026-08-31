"""AutoGen tool definition export format for autogen-agentchat v0.4+."""

import re
from typing import Any

from fabric_ai_meta.models.metadata import MeasureCategory, SemanticModelMeta


def _sanitize(name: str) -> str:
    """Replace spaces and special chars with underscores, lowercase."""
    return re.sub(r"[^a-z0-9_]", "_", name.lower()).strip("_")


def to_autogen_tool(model: SemanticModelMeta) -> dict:
    """Generate an AutoGen-compatible tool definition for querying this semantic model.

    Returns a dict structured for use with ``autogen-agentchat`` v0.4+ tool
    registration.  The schema describes the model's tables, columns, measures,
    relationships, and query pitfalls so an AutoGen agent can reason about the
    data without additional context injection.
    """
    description_text = model.description or f"Semantic model: {model.name}"

    # Build table schemas
    tables: list[dict[str, Any]] = []
    for table in model.tables:
        if table.is_hidden:
            continue
        columns = [
            {
                "name": col.name,
                "data_type": col.data_type,
                "role": col.role.value,
                "description": col.ai_description or col.description or "",
            }
            for col in table.columns
            if not col.is_hidden
        ]
        measures = [
            {
                "name": m.name,
                "dax_expression": m.dax_expression,
                "category": m.category.value,
                "description": m.ai_description or m.description or "",
            }
            for m in table.measures
            if not m.is_hidden
        ]
        tables.append({
            "name": table.name,
            "type": table.table_type.value,
            "grain": table.grain or "",
            "description": table.ai_description or table.description or "",
            "columns": columns,
            "measures": measures,
        })

    # Build relationships
    relationships = [
        {
            "from": f"{r.from_table}[{r.from_column}]",
            "to": f"{r.to_table}[{r.to_column}]",
            "cardinality": r.cardinality,
            "cross_filter": r.cross_filter_direction,
            "is_active": r.is_active,
        }
        for r in model.relationships
    ]

    # Collect pitfalls
    pitfalls = []
    for table in model.tables:
        for m in table.measures:
            if m.is_hidden:
                continue
            if m.category == MeasureCategory.NON_ADDITIVE:
                pitfalls.append(f"{m.name} is non-additive, do not SUM it")
            elif m.category == MeasureCategory.SEMI_ADDITIVE:
                pitfalls.append(f"{m.name} is semi-additive, cannot be summed across time")
            elif m.category == MeasureCategory.TIME_INTELLIGENCE:
                pitfalls.append(f"{m.name} requires a date filter")

    return {
        "type": "function",
        "function": {
            "name": f"query_{_sanitize(model.name)}",
            "description": f"Query the {model.name} semantic model. {description_text}.",
            "parameters": {
                "type": "object",
                "properties": {
                    "question": {
                        "type": "string",
                        "description": "Natural language question about the data",
                    },
                    "tables": {
                        "type": "array",
                        "items": {"type": "string", "enum": [t["name"] for t in tables]},
                        "description": "Tables relevant to the query",
                    },
                    "measures": {
                        "type": "array",
                        "items": {
                            "type": "string",
                            "enum": [
                                m["name"]
                                for t in tables
                                for m in t["measures"]
                            ],
                        },
                        "description": "Measures to evaluate",
                    },
                },
                "required": ["question"],
            },
        },
        "model_context": {
            "tables": tables,
            "relationships": relationships,
            "pitfalls": pitfalls,
        },
    }
