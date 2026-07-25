"""Description writeback to Fabric semantic models via XMLA / TOM.

Closes the loop between generated descriptions (Prep for AI) and the live
model. The MockWriter records what would be written without contacting any
service; the SemanticLinkWriter uses sempy_labs to apply changes through
the Tabular Object Model when running inside a Fabric notebook.
"""

from __future__ import annotations

import dataclasses
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from fabric_ai_meta.auth.entra import (
    FabricEnvironmentError,
    MissingFabricDependencyError,
    detect_notebook_environment,
)

TABLE_KEY = "__table__"


@dataclass
class WritebackResult:
    """Outcome of an apply_descriptions call."""

    tables_updated: int = 0
    columns_updated: int = 0
    measures_updated: int = 0
    total_changes: int = 0
    changes: list[dict] = field(default_factory=list)
    dry_run: bool = True
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)


class DescriptionWriter(ABC):
    """Abstract writer that applies generated descriptions to a model."""

    @abstractmethod
    def apply_descriptions(
        self,
        model_name: str,
        workspace: str,
        descriptions: dict[str, dict[str, str]],
        dry_run: bool = True,
    ) -> WritebackResult:
        """Apply descriptions to a semantic model.

        Args:
            model_name: Name of the semantic model.
            workspace: Workspace name.
            descriptions: ``{table_name: {"__table__": desc, "col_name": desc, ...}}``
                as produced by :class:`PrepForAIConfig.generated_descriptions`.
            dry_run: When True, return what would change without writing.
        """


def _planned_changes(
    descriptions: dict[str, dict[str, str]],
) -> tuple[list[dict], int, int]:
    """Walk the descriptions dict and return (changes, table_count, column_count)."""
    changes: list[dict] = []
    tables = 0
    columns = 0
    for table_name, entries in descriptions.items():
        if not isinstance(entries, dict):
            continue
        for object_name, new_desc in entries.items():
            if object_name == TABLE_KEY:
                changes.append({
                    "type": "table",
                    "table": table_name,
                    "object": table_name,
                    "old_description": None,
                    "new_description": new_desc,
                })
                tables += 1
            else:
                changes.append({
                    "type": "column",
                    "table": table_name,
                    "object": object_name,
                    "old_description": None,
                    "new_description": new_desc,
                })
                columns += 1
    return changes, tables, columns


class MockWriter(DescriptionWriter):
    """Local writer that records planned changes without touching any service.

    Always reports ``dry_run=True`` regardless of the ``dry_run`` argument,
    since no live target exists to write against.
    """

    def apply_descriptions(
        self,
        model_name: str,
        workspace: str,
        descriptions: dict[str, dict[str, str]],
        dry_run: bool = True,
    ) -> WritebackResult:
        changes, tables, columns = _planned_changes(descriptions)
        return WritebackResult(
            tables_updated=tables,
            columns_updated=columns,
            measures_updated=0,
            total_changes=len(changes),
            changes=changes,
            dry_run=True,
            errors=[],
        )


class SemanticLinkWriter(DescriptionWriter):
    """Fabric-runtime writer that applies descriptions through TOM.

    Uses ``sempy_labs.connect_semantic_model(readonly=False)`` to mutate
    table, column, and measure ``Description`` properties, then calls
    ``SaveChanges()`` when not in dry-run mode.
    """

    def apply_descriptions(
        self,
        model_name: str,
        workspace: str,
        descriptions: dict[str, dict[str, str]],
        dry_run: bool = True,
    ) -> WritebackResult:
        if not detect_notebook_environment():
            raise FabricEnvironmentError()

        try:
            import sempy_labs as labs  # type: ignore[import-not-found]
        except ImportError as exc:
            raise MissingFabricDependencyError("semantic-link-labs") from exc

        changes: list[dict] = []
        tables_updated = 0
        columns_updated = 0
        errors: list[str] = []

        with labs.connect_semantic_model(
            dataset=model_name, workspace=workspace, readonly=dry_run
        ) as tom:
            for table_name, entries in descriptions.items():
                if not isinstance(entries, dict):
                    continue
                try:
                    tom_table = tom.model.Tables[table_name]
                except Exception as exc:
                    errors.append(f"table '{table_name}' not found: {exc}")
                    continue

                for object_name, new_desc in entries.items():
                    if object_name == TABLE_KEY:
                        old = getattr(tom_table, "Description", None) or None
                        if not dry_run:
                            tom_table.Description = new_desc
                        changes.append({
                            "type": "table",
                            "table": table_name,
                            "object": table_name,
                            "old_description": old,
                            "new_description": new_desc,
                        })
                        tables_updated += 1
                        continue

                    try:
                        tom_col = tom_table.Columns[object_name]
                    except Exception as exc:
                        errors.append(
                            f"column '{table_name}.{object_name}' not found: {exc}"
                        )
                        continue
                    old = getattr(tom_col, "Description", None) or None
                    if not dry_run:
                        tom_col.Description = new_desc
                    changes.append({
                        "type": "column",
                        "table": table_name,
                        "object": object_name,
                        "old_description": old,
                        "new_description": new_desc,
                    })
                    columns_updated += 1

            if not dry_run:
                tom.model.SaveChanges()

        return WritebackResult(
            tables_updated=tables_updated,
            columns_updated=columns_updated,
            measures_updated=0,
            total_changes=len(changes),
            changes=changes,
            dry_run=dry_run,
            errors=errors,
        )
