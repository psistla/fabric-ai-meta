"""Semantic Kernel plugin manifest export format (SPEC.md Section 6.3.3)."""

from fabric_ai_meta.models.metadata import SemanticModelMeta


def to_semantic_kernel_plugin(model: SemanticModelMeta) -> dict:
    """Generate a Semantic Kernel plugin definition.

    Returns a plugin manifest with a single ``query`` function that accepts
    question, tables (comma-separated string), and measures (comma-separated
    string) parameters.
    """
    description_text = model.description or f"Semantic model: {model.name}"

    table_names = [t.name for t in model.tables]
    measure_names = [m.name for t in model.tables for m in t.measures if not m.is_hidden]

    return {
        "schema_version": "v1",
        "name": model.name,
        "description": f"Query the {model.name} semantic model. {description_text}.",
        "functions": [
            {
                "name": "query",
                "description": (
                    f"Query the {model.name} semantic model with a natural "
                    f"language question."
                ),
                "parameters": [
                    {
                        "name": "question",
                        "type": "string",
                        "description": "Natural language question about the data",
                        "required": True,
                    },
                    {
                        "name": "tables",
                        "type": "string",
                        "description": (
                            "Comma-separated list of tables relevant to the query. "
                            f"Available: {', '.join(table_names)}"
                        ),
                        "required": False,
                    },
                    {
                        "name": "measures",
                        "type": "string",
                        "description": (
                            "Comma-separated list of measures to evaluate. "
                            f"Available: {', '.join(measure_names)}"
                        ),
                        "required": False,
                    },
                ],
            }
        ],
    }
