"""LangChain tool definition export format (SPEC.md Section 6.3.3)."""

import re

from fabric_ai_meta.models.metadata import SemanticModelMeta


def sanitize(name: str) -> str:
    """Replace spaces and special chars with underscores, lowercase."""
    return re.sub(r"[^a-z0-9_]", "_", name.lower()).strip("_")


def generate_context_prompt(model: SemanticModelMeta) -> str:
    """Generate a context prompt summarising the model for an LLM agent.

    Stub — full implementation deferred to Task 10 (LLM integration).
    """
    return ""


def extract_filter_paths(model: SemanticModelMeta) -> list[str]:
    """Extract valid filter paths from the relationship graph.

    Stub — full implementation deferred to Task 10 (LLM integration).
    """
    return []


def extract_pitfalls(model: SemanticModelMeta) -> list[str]:
    """Extract common query pitfalls for non-additive / time-intelligence measures.

    Stub — full implementation deferred to Task 10 (LLM integration).
    """
    return []


def to_langchain_tool_definition(model: SemanticModelMeta) -> dict:
    """Generate a LangChain-compatible tool definition for querying this semantic model.

    IMPORTANT: LangChain's standard StructuredTool schema only natively supports
    name, description, and args_schema (parameters). The 'metadata' field below
    is a non-standard extension — it will NOT be automatically parsed by LangChain.

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
        # Non-standard extension — for custom agent implementations only
        "metadata": {
            "model_context": generate_context_prompt(model),
            "valid_filter_paths": extract_filter_paths(model),
            "common_pitfalls": extract_pitfalls(model),
        },
    }
