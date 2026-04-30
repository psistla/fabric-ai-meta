"""Fabric AI Meta: extracts, analyzes, and exports Microsoft Fabric semantic model metadata for AI consumption."""

__version__ = "1.1.1"

# Core data model
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
from fabric_ai_meta.analyzer.delta import compare_workspace_summaries
from fabric_ai_meta.analyzer.governance import generate_governance_report
from fabric_ai_meta.analyzer.scorer import score_model

# Extractors
from fabric_ai_meta.extractor.base import BaseExtractor
from fabric_ai_meta.extractor.mock import MockExtractor
from fabric_ai_meta.generator.export_autogen import to_autogen_tool
from fabric_ai_meta.generator.export_langchain import to_langchain_tool_definition
from fabric_ai_meta.generator.export_openai import to_openai_function
from fabric_ai_meta.generator.export_semantic_kernel import to_semantic_kernel_plugin
from fabric_ai_meta.generator.prep_for_ai import generate_prep_for_ai

# Generators
from fabric_ai_meta.generator.schema import generate_ai_ready_schema
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
from fabric_ai_meta.writeback.description_writer import (
    DescriptionWriter,
    MockWriter,
    SemanticLinkWriter,
    WritebackResult,
)

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
    "compare_workspace_summaries",
    "generate_governance_report",
    "score_model",
    # Generators
    "generate_ai_ready_schema",
    "generate_prep_for_ai",
    "to_langchain_tool_definition",
    "to_openai_function",
    "to_semantic_kernel_plugin",
    "to_autogen_tool",
    # Writeback
    "DescriptionWriter",
    "MockWriter",
    "SemanticLinkWriter",
    "WritebackResult",
]
