"""Model-level enrichment: heuristic classification plus measure dependency wiring.

Lives here rather than in `classifier.py` because `dax_parser` already imports
from `classifier`, so wiring the two together there would close an import cycle.
"""

from fabric_ai_meta.analyzer.classifier import (
    classify_column_role,
    classify_measure_heuristic,
    classify_table_heuristic,
)
from fabric_ai_meta.analyzer.dax_parser import parse_measure_dependencies
from fabric_ai_meta.models.metadata import SemanticModelMeta


def classify_model_in_place(model: SemanticModelMeta) -> None:
    """Populate heuristic classifications and measure dependencies in place."""
    for table in model.tables:
        table.table_type = classify_table_heuristic(table, model.relationships)
        for col in table.columns:
            col.role = classify_column_role(col, table, model.relationships)
        for measure in table.measures:
            measure.category = classify_measure_heuristic(measure)

    all_measures = {
        m.name: m.dax_expression for t in model.tables for m in t.measures
    }
    for table in model.tables:
        for measure in table.measures:
            deps = parse_measure_dependencies(
                measure.name, measure.dax_expression, all_measures
            )
            measure.depends_on_measures = deps["depends_on_measures"]
            measure.depends_on_columns = deps["depends_on_columns"]
            measure.implicit_filters = deps["implicit_business_rules"]
