"""Fabric AI Meta: extracts, analyzes, and exports Microsoft Fabric semantic model metadata for AI consumption."""

__version__ = "2.0.0"

# Core data model
# Analysis
from fabric_ai_meta.analyzer.agent_readiness import (
    assess_agent_readiness,
    write_agent_readiness_report,
)
from fabric_ai_meta.analyzer.capability_manifest import generate_capability_manifest
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
from fabric_ai_meta.analyzer.graph_necessity import assess_graph_necessity
from fabric_ai_meta.analyzer.query_guidance import guide_query
from fabric_ai_meta.analyzer.scorer import score_model

# Extractors
from fabric_ai_meta.extractor.base import BaseExtractor
from fabric_ai_meta.extractor.mock import MockExtractor
from fabric_ai_meta.extractor.pbip import PbipExtractor
from fabric_ai_meta.generator.base import BaseExporter, ExporterError
from fabric_ai_meta.generator.copilot_reader import CopilotReader
from fabric_ai_meta.generator.export_autogen import to_autogen_tool
from fabric_ai_meta.generator.export_langchain import to_langchain_tool_definition
from fabric_ai_meta.generator.export_openai import to_openai_function
from fabric_ai_meta.generator.export_semantic_kernel import to_semantic_kernel_plugin
from fabric_ai_meta.generator.prep_for_ai import generate_prep_for_ai
from fabric_ai_meta.generator.registry import discover_exporters, get_exporter

# Generators
from fabric_ai_meta.generator.schema import generate_ai_ready_schema
from fabric_ai_meta.models.copilot import (
    AIDataSchema,
    AIInstructions,
    CopilotBundle,
    VerifiedAnswer,
)
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
from fabric_ai_meta.writeback.copilot_writer import (
    CopilotWritebackResult,
    CopilotWriter,
    MockCopilotWriter,
    SemanticLinkCopilotWriter,
    splice_copilot_into_envelope,
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
    # Copilot (Prep for AI) - v1.4.0
    "AIDataSchema",
    "AIInstructions",
    "CopilotBundle",
    "VerifiedAnswer",
    "CopilotReader",
    # Extractors
    "BaseExtractor",
    "MockExtractor",
    "PbipExtractor",
    # Analysis
    "classify_column_role",
    "classify_measure_heuristic",
    "classify_table_heuristic",
    "build_dependency_graph",
    "parse_measure_dependencies",
    "compare_workspace_summaries",
    "assess_agent_readiness",
    "write_agent_readiness_report",
    "generate_capability_manifest",
    "generate_governance_report",
    "assess_graph_necessity",
    "guide_query",
    "score_model",
    # Generators
    "generate_ai_ready_schema",
    "generate_prep_for_ai",
    "to_langchain_tool_definition",
    "to_openai_function",
    "to_semantic_kernel_plugin",
    "to_autogen_tool",
    # Exporter plugin contract
    "BaseExporter",
    "ExporterError",
    "discover_exporters",
    "get_exporter",
    # Writeback (descriptions)
    "DescriptionWriter",
    "MockWriter",
    "SemanticLinkWriter",
    "WritebackResult",
    # Writeback (Copilot) - v1.5.0
    "CopilotWriter",
    "MockCopilotWriter",
    "SemanticLinkCopilotWriter",
    "CopilotWritebackResult",
    "splice_copilot_into_envelope",
]
