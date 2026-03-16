"""OpenAI function calling schema export format (SPEC.md Section 6.3.3)."""

import re

from fabric_ai_meta.models.metadata import (
    MeasureCategory,
    SemanticModelMeta,
)


def _sanitize(name: str) -> str:
    """Replace spaces and special chars with underscores, lowercase."""
    return re.sub(r"[^a-z0-9_]", "_", name.lower()).strip("_")


def to_openai_function(model: SemanticModelMeta) -> dict:
    """Generate an OpenAI function calling compatible schema.

    Parameters: question (string, required), tables (array of enum, optional),
    measures (array of enum, optional).

    Description combines model summary and key pitfalls inline since OpenAI
    has no metadata extension field.
    """
    description_text = model.description or f"Semantic model: {model.name}"

    # Collect pitfall warnings to embed in the description
    pitfalls: list[str] = []
    for table in model.tables:
        for m in table.measures:
            if m.is_hidden:
                continue
            if m.category == MeasureCategory.NON_ADDITIVE:
                pitfalls.append(f"{m.name} is non-additive — do not SUM it")
            elif m.category == MeasureCategory.TIME_INTELLIGENCE:
                pitfalls.append(f"{m.name} requires a date filter")

    description = f"Query the {model.name} semantic model. {description_text}."
    if pitfalls:
        description += " Pitfalls: " + "; ".join(pitfalls) + "."

    table_names = [t.name for t in model.tables]
    measure_names = [m.name for t in model.tables for m in t.measures if not m.is_hidden]

    return {
        "type": "function",
        "function": {
            "name": f"query_{_sanitize(model.name)}",
            "description": description,
            "parameters": {
                "type": "object",
                "properties": {
                    "question": {
                        "type": "string",
                        "description": "Natural language question about the data",
                    },
                    "tables": {
                        "type": "array",
                        "items": {"type": "string", "enum": table_names},
                        "description": "Tables relevant to the query",
                    },
                    "measures": {
                        "type": "array",
                        "items": {"type": "string", "enum": measure_names},
                        "description": "Measures to evaluate",
                    },
                },
                "required": ["question"],
            },
        },
    }
