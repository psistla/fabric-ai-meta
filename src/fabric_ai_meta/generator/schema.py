"""AI-ready JSON schema generator (SPEC.md Sections 5.2 and 6.3.1)."""

import json

from fabric_ai_meta.analyzer.scorer import score_model
from fabric_ai_meta.models.metadata import (
    MeasureCategory,
    SemanticModelMeta,
    TableType,
)


def generate_ai_ready_schema(model: SemanticModelMeta) -> dict:
    """Produce the canonical AI-ready JSON structure from SPEC.md Section 5.2.

    Top-level keys: $schema, version, model, tables, measures,
    query_guidance, scoring.
    """
    # Ensure scoring is populated
    if model.ai_readiness_score is None:
        overall, breakdown = score_model(model)
        model.ai_readiness_score = overall
        model.scoring_breakdown = breakdown

    return {
        "$schema": "https://raw.githubusercontent.com/psistla/fabric-ai-meta/master/schemas/v1.json",
        "version": "1.0",
        "model": _build_model_section(model),
        "tables": _build_tables_section(model),
        "measures": _build_measures_section(model),
        "query_guidance": _build_query_guidance(model),
        "scoring": _build_scoring_section(model),
    }


def write_schema_to_file(model: SemanticModelMeta, output_path: str) -> str:
    """Generate the AI-ready schema and write it to a JSON file.

    Returns the output file path.
    """
    schema = generate_ai_ready_schema(model)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(schema, f, indent=2, ensure_ascii=False)
    return output_path


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _build_model_section(model: SemanticModelMeta) -> dict:
    summary = model.description or f"Semantic model: {model.name}"
    return {
        "name": model.name,
        "workspace": model.workspace,
        "summary": summary,
        "ai_readiness_score": model.ai_readiness_score,
        "extraction_timestamp": model.extraction_timestamp,
    }


def _build_tables_section(model: SemanticModelMeta) -> list[dict]:
    """Include only non-hidden tables; for each table include non-hidden columns
    and outbound relationships."""
    visible_tables = [t for t in model.tables if not t.is_hidden]
    result = []
    for table in visible_tables:
        visible_columns = [c for c in table.columns if not c.is_hidden]
        columns_out = []
        for col in visible_columns:
            col_entry: dict = {
                "name": col.name,
                "type": col.data_type,
                "role": col.role.value,
                "description": col.description or col.ai_description,
            }
            # For FK columns, add joins_to info
            for rel in model.relationships:
                if rel.from_table == table.name and rel.from_column == col.name:
                    col_entry["joins_to"] = f"{rel.to_table}.{rel.to_column}"
                    break
            if col.sample_values:
                col_entry["sample_values"] = col.sample_values
            columns_out.append(col_entry)

        # Outbound relationships for this table
        outbound = [
            {
                "to_table": r.to_table,
                "join": f"{r.from_table}.{r.from_column} = {r.to_table}.{r.to_column}",
                "cardinality": r.cardinality,
            }
            for r in model.relationships
            if r.from_table == table.name
        ]

        entry: dict = {
            "name": table.name,
            "type": table.table_type.value,
            "description": table.description or table.ai_description,
        }
        if table.grain:
            entry["grain"] = table.grain
        if table.row_count_estimate is not None:
            entry["row_count_estimate"] = table.row_count_estimate
        entry["columns"] = columns_out
        if outbound:
            entry["relationships_outbound"] = outbound
        result.append(entry)
    return result


def _build_measures_section(model: SemanticModelMeta) -> list[dict]:
    """Flatten all non-hidden measures from all tables."""
    measures_out = []
    for table in model.tables:
        for m in table.measures:
            if m.is_hidden:
                continue
            entry: dict = {
                "name": m.name,
                "category": m.category.value,
                "description": m.description or m.ai_description,
                "dax": m.dax_expression,
            }
            if m.depends_on_columns:
                entry["depends_on"] = m.depends_on_columns
            if m.depends_on_measures:
                entry["depends_on_measures"] = m.depends_on_measures
            if m.implicit_filters:
                entry["implicit_business_rules"] = m.implicit_filters
            if m.category == MeasureCategory.TIME_INTELLIGENCE:
                entry["requires_date_filter"] = True
            measures_out.append(entry)
    return measures_out


def _build_query_guidance(model: SemanticModelMeta) -> dict:
    """Generate query guidance from the relationship graph."""
    return {
        "valid_filter_paths": _generate_filter_paths(model),
        "common_pitfalls": _generate_pitfalls(model),
        "recommended_aggregations": _generate_aggregations(model),
    }


def _generate_filter_paths(model: SemanticModelMeta) -> list[str]:
    """Generate filter path guidance from relationships.

    Pattern: "To filter {fact} by {attribute}: {fact} -> {dim} -> {dim}[{col}]"
    """
    paths = []
    for rel in model.relationships:
        from_table = rel.from_table
        to_table = rel.to_table
        # Find attribute columns in the target dimension table
        dim_table = next((t for t in model.tables if t.name == to_table), None)
        if dim_table is None:
            continue
        attr_cols = [
            c for c in dim_table.columns
            if not c.is_hidden and c.name != rel.to_column
        ]
        for col in attr_cols[:2]:  # limit to 2 representative columns per dim
            paths.append(
                f"To filter {from_table} by {col.name}: "
                f"{from_table} \u2192 {to_table} \u2192 {to_table}[{col.name}]"
            )
    return paths


def _generate_pitfalls(model: SemanticModelMeta) -> list[str]:
    """Generate pitfall warnings for non-additive and time-intelligence measures."""
    pitfalls = []
    for table in model.tables:
        for m in table.measures:
            if m.is_hidden:
                continue
            if m.category == MeasureCategory.NON_ADDITIVE:
                pitfalls.append(
                    f"{m.name} is non-additive \u2014 do not SUM it across dimensions"
                )
            elif m.category == MeasureCategory.TIME_INTELLIGENCE:
                pitfalls.append(
                    f"{m.name} requires a date filter to return meaningful results"
                )
    return pitfalls


def _generate_aggregations(model: SemanticModelMeta) -> dict:
    """Generate one SUMMARIZECOLUMNS example per fact table."""
    aggs = {}
    for table in model.tables:
        if table.table_type != TableType.FACT:
            continue
        # Find top additive measure
        additive = [
            m for m in table.measures
            if m.category == MeasureCategory.ADDITIVE and not m.is_hidden
        ]
        if not additive:
            continue
        top_measure = additive[0]
        # Find first related dimension
        dim_rel = next(
            (r for r in model.relationships if r.from_table == table.name),
            None,
        )
        if dim_rel is None:
            continue
        dim_table = next(
            (t for t in model.tables if t.name == dim_rel.to_table), None
        )
        if dim_table is None:
            continue
        # Pick first visible non-key attribute column from dimension
        dim_col = next(
            (c for c in dim_table.columns
             if not c.is_hidden and c.name != dim_rel.to_column),
            None,
        )
        if dim_col is None:
            continue
        slug = top_measure.name.strip("[]").lower().replace(" ", "_")
        aggs[f"{slug}_by_{dim_col.name.lower()}"] = (
            f"SUMMARIZECOLUMNS("
            f"{dim_table.name}[{dim_col.name}], "
            f'"{top_measure.name}", {top_measure.name})'
        )
    return aggs


def _build_scoring_section(model: SemanticModelMeta) -> dict:
    return {
        "overall": model.ai_readiness_score,
        "breakdown": model.scoring_breakdown,
    }
