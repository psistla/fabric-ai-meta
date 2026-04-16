"""Fabric AI Meta — extracts, analyzes, and exports Microsoft Fabric semantic model metadata for AI consumption."""

__version__ = "1.0.0"

# Core data model
from fabric_ai_meta.models.metadata import (
    ColumnMeta,
    ColumnRole,
    HierarchyMeta,
    MeasureCategory,
    MeasureMeta,
    RelationshipMeta,
    SemanticModelMeta,
    TableMeta,
    TableType,
    from_dict,
)

# Extractors
from fabric_ai_meta.extractor.base import BaseExtractor
from fabric_ai_meta.extractor.mock import MockExtractor

# Analysis
from fabric_ai_meta.analyzer.classifier import (
    classify_column_role,
    classify_measure_heuristic,
    classify_table_heuristic,
)
from fabric_ai_meta.analyzer.dax_parser import (
    build_dependency_graph,
    parse_measure_dependencies,
)
from fabric_ai_meta.analyzer.governance import generate_governance_report
from fabric_ai_meta.analyzer.scorer import score_model

# Generators
from fabric_ai_meta.generator.schema import generate_ai_ready_schema
from fabric_ai_meta.generator.prep_for_ai import generate_prep_for_ai
from fabric_ai_meta.generator.export_langchain import to_langchain_tool_definition
from fabric_ai_meta.generator.export_openai import to_openai_function
from fabric_ai_meta.generator.export_semantic_kernel import to_semantic_kernel_plugin

__all__ = [
    # Version
    "__version__",
    # Data model
    "ColumnMeta",
    "ColumnRole",
    "HierarchyMeta",
    "MeasureCategory",
    "MeasureMeta",
    "RelationshipMeta",
    "SemanticModelMeta",
    "TableMeta",
    "TableType",
    "from_dict",
    # Extractors
    "BaseExtractor",
    "MockExtractor",
    # Analysis
    "classify_column_role",
    "classify_measure_heuristic",
    "classify_table_heuristic",
    "build_dependency_graph",
    "parse_measure_dependencies",
    "generate_governance_report",
    "score_model",
    # Generators
    "generate_ai_ready_schema",
    "generate_prep_for_ai",
    "to_langchain_tool_definition",
    "to_openai_function",
    "to_semantic_kernel_plugin",
]
