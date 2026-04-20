"""LangChain tool definition export format (SPEC.md Section 6.3.3)."""

import re

from fabric_ai_meta.models.metadata import SemanticModelMeta


def sanitize(name: str) -> str:
    """Replace spaces and special chars with underscores, lowercase."""
    return re.sub(r"[^a-z0-9_]", "_", name.lower()).strip("_")


def generate_context_prompt(model: SemanticModelMeta) -> str:
    """Return a natural-language context prompt summarising the model.

    Currently returns an empty string. Richer prompt synthesis is a
    planned enhancement; consumers that need a context prompt today
    should compose one from ``model.description`` and the table list.
    """
    return ""


def extract_filter_paths(model: SemanticModelMeta) -> list[str]:
    """Return the list of valid filter paths derived from the relationship graph.

    Currently returns an empty list. Path extraction is a planned
    enhancement that will walk ``model.relationships`` to surface
    every joinable column-to-column traversal.
    """
    return []


def extract_pitfalls(model: SemanticModelMeta) -> list[str]:
    """Return common query pitfalls for non-additive and time-intelligence measures.

    Currently returns an empty list. Pitfall detection is a planned
    enhancement that will inspect each measure's category and DAX
    expression to flag patterns prone to misuse.
    """
    return []


def to_langchain_tool_definition(model: SemanticModelMeta) -> dict:
    """Generate a LangChain-compatible tool definition for querying this semantic model.

    IMPORTANT: LangChain's standard StructuredTool schema only natively supports
    name, description, and args_schema (parameters). The 'metadata' field below
    is a non-standard extension; it will NOT be automatically parsed by LangChain.

    Usage: Consumers of this export must manually inject the metadata fields
    into the tool description string or use a custom tool wrapper class.
    The metadata is included here for completeness and to enable custom
    agent implementations that do consume extended context.
    """
    description_text = model.description or f"Semantic model: {model.name}"
    return {
        "name": f"query_{sanitize(model.name)}",
        "description": (
            f"Query the {model.name} semantic model. {description_text}. "
            f"Valid filter paths and pitfalls are documented in the metadata field."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "question": {
                    "type": "string",
                    "description": "Natural language question about the data",
                },
                "tables": {
                    "type": "array",
                    "items": {
                        "type": "string",
                        "enum": [t.name for t in model.tables],
                    },
                    "description": "Tables relevant to the query",
                },
                "measures": {
                    "type": "array",
                    "items": {
                        "type": "string",
                        "enum": [
                            m.name for t in model.tables for m in t.measures
                        ],
                    },
                    "description": "Measures to evaluate",
                },
            },
        },
        # Non-standard extension, for custom agent implementations only
        "metadata": {
            "model_context": generate_context_prompt(model),
            "valid_filter_paths": extract_filter_paths(model),
            "common_pitfalls": extract_pitfalls(model),
        },
    }
