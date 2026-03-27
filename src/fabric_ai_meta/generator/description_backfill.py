"""LLM-driven description backfill for semantic model objects.

Enterprise model cost note: a model with 50 tables and ~300 undescribed columns
produces ~22 batches of 15 items each. Total cost is bounded by max_cost_per_run
from config; CostLimitExceededError is raised if that limit is hit mid-run.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from fabric_ai_meta.models.metadata import SemanticModelMeta

if TYPE_CHECKING:
    from fabric_ai_meta.llm.client import FabricLLMClient


@dataclass
class DescriptionBackfill:
    """Container for LLM-generated descriptions, split by object type."""

    table_descriptions: dict[str, str] = field(default_factory=dict)
    # table_name → {col_name → description}
    column_descriptions: dict[str, dict[str, str]] = field(default_factory=dict)
    # table_name → {measure_name → description}
    measure_descriptions: dict[str, dict[str, str]] = field(default_factory=dict)


def backfill_descriptions(
    model: SemanticModelMeta, llm_client: "FabricLLMClient"
) -> DescriptionBackfill:
    """Scan model for undescribed objects and generate descriptions via LLM.

    Only items where both description and ai_description are None are included.
    Sibling context is passed to give the LLM enough signal to infer purpose.
    """
    items: list[dict] = []

    for table in model.tables:
        if table.is_hidden:
            continue

        # Table itself
        if table.description is None and table.ai_description is None:
            related = [
                r.to_table if r.from_table == table.name else r.from_table
                for r in model.relationships
                if r.from_table == table.name or r.to_table == table.name
            ]
            items.append({
                "id": f"table:{table.name}",
                "type": "table",
                "name": table.name,
                "parent_table": table.name,
                "siblings": ", ".join(related[:5]) if related else "none",
            })

        # Columns
        sibling_col_names = [c.name for c in table.columns]
        for col in table.columns:
            if col.description is None and col.ai_description is None:
                siblings = [n for n in sibling_col_names if n != col.name]
                items.append({
                    "id": f"column:{table.name}:{col.name}",
                    "type": "column",
                    "name": col.name,
                    "parent_table": table.name,
                    "data_type": col.data_type,
                    "siblings": ", ".join(siblings[:8]),
                })

        # Measures
        sibling_measure_names = [m.name for m in table.measures]
        for measure in table.measures:
            if measure.description is None and measure.ai_description is None:
                siblings = [n for n in sibling_measure_names if n != measure.name]
                items.append({
                    "id": f"measure:{table.name}:{measure.name}",
                    "type": "measure",
                    "name": measure.name,
                    "parent_table": table.name,
                    "dax": (measure.dax_expression or "")[:200],
                    "siblings": ", ".join(siblings[:5]),
                })

    if not items:
        return DescriptionBackfill()

    id_to_desc = llm_client.generate_descriptions_batch(items, model.name)

    backfill = DescriptionBackfill()
    for item_id, description in id_to_desc.items():
        parts = item_id.split(":", 2)
        if not parts:
            continue
        obj_type = parts[0]
        if obj_type == "table" and len(parts) >= 2:
            backfill.table_descriptions[parts[1]] = description
        elif obj_type == "column" and len(parts) == 3:
            table_name, col_name = parts[1], parts[2]
            backfill.column_descriptions.setdefault(table_name, {})[col_name] = description
        elif obj_type == "measure" and len(parts) == 3:
            table_name, measure_name = parts[1], parts[2]
            backfill.measure_descriptions.setdefault(table_name, {})[measure_name] = description

    return backfill


def apply_backfill(model: SemanticModelMeta, backfill: DescriptionBackfill) -> None:
    """Apply generated descriptions to model objects in place (sets ai_description)."""
    for table in model.tables:
        if table.name in backfill.table_descriptions:
            table.ai_description = backfill.table_descriptions[table.name]

        col_descs = backfill.column_descriptions.get(table.name, {})
        for col in table.columns:
            if col.name in col_descs:
                col.ai_description = col_descs[col.name]

        measure_descs = backfill.measure_descriptions.get(table.name, {})
        for measure in table.measures:
            if measure.name in measure_descs:
                measure.ai_description = measure_descs[measure.name]
