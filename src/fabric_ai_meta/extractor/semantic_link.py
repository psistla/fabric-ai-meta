"""Primary extractor using sempy.fabric Semantic Link API.

⚠️  This module only functions inside a Microsoft Fabric notebook runtime.
    sempy.fabric API calls will fail in local Python environments.
    Instantiating SemanticLinkExtractor outside Fabric raises FabricEnvironmentError.
"""

import logging
import time
from datetime import datetime, timezone
from typing import Optional

from fabric_ai_meta.auth.entra import FabricEnvironmentError, detect_notebook_environment
from fabric_ai_meta.extractor.base import BaseExtractor
from fabric_ai_meta.models.metadata import (
    ColumnMeta,
    ColumnRole,
    MeasureCategory,
    MeasureMeta,
    RelationshipMeta,
    SemanticModelMeta,
    TableMeta,
    TableType,
)

logger = logging.getLogger(__name__)

_MAX_RETRIES = 3
_RETRY_BASE_SECONDS = 1


class SemanticLinkExtractor(BaseExtractor):
    """Extract semantic model metadata via the sempy.fabric Semantic Link API.

    ⚠️  Requires Microsoft Fabric notebook runtime.
    Raises FabricEnvironmentError on instantiation if not running in Fabric.
    """

    def __init__(self, workspace: str, credential=None):
        """Initialize the extractor.

        Args:
            workspace: Default Fabric workspace name.
            credential: Optional azure.identity credential (unused by sempy in
                notebook mode: Fabric ambient credential is used automatically).

        Raises:
            FabricEnvironmentError: If not running inside a Fabric notebook runtime.
        """
        if not detect_notebook_environment():
            raise FabricEnvironmentError()
        self.workspace = workspace
        self.credential = credential
        # Deferred import, avoids ImportError at module load time in local envs.
        import sempy.fabric as fabric  # noqa: PLC0415

        self._fabric = fabric

    def extract(
        self,
        model_name: str,
        workspace: str | None = None,
        *,
        with_copilot: bool = False,
    ) -> SemanticModelMeta:
        """Extract full metadata for a semantic model.

        Args:
            model_name: Name of the Power BI / Fabric semantic model.
            workspace: Workspace to use; defaults to self.workspace.
            with_copilot: If True, also fetch the model's ``Copilot/`` folder via
                the Fabric REST ``getDefinition`` endpoint and attach it to
                ``model.copilot``. Resolution failures are logged and skipped
                rather than raised.

        Returns:
            A fully populated SemanticModelMeta object.

        Raises:
            RuntimeError: If extraction fails after all retries.
        """
        ws = workspace or self.workspace
        fabric = self._fabric

        tables_df = self._with_retry(
            fabric.list_tables, model_name, workspace=ws,
            _context=f"list_tables({model_name!r})"
        )
        measures_df = self._with_retry(
            fabric.list_measures, model_name, workspace=ws,
            _context=f"list_measures({model_name!r})"
        )
        rels_df = self._with_retry(
            fabric.list_relationships, model_name, workspace=ws,
            _context=f"list_relationships({model_name!r})"
        )

        # Group measures by table name for O(1) lookup
        measures_by_table: dict[str, list] = {}
        for _, mrow in measures_df.iterrows():
            t_name = str(
                mrow.get("Table Name", mrow.get("table_name", mrow.get("Name", "")))
            )
            measures_by_table.setdefault(t_name, []).append(mrow)

        table_metas: list[TableMeta] = []
        for _, trow in tables_df.iterrows():
            t_name = str(trow.get("Name", trow.get("name", "")))
            is_hidden = bool(trow.get("Hidden", trow.get("is_hidden", False)))

            try:
                cols_df = self._with_retry(
                    fabric.list_columns, model_name, t_name, workspace=ws,
                    _context=f"list_columns({model_name!r}, {t_name!r})"
                )
                columns = [
                    self._parse_column(crow, model_name, t_name, ws)
                    for _, crow in cols_df.iterrows()
                ]
            except Exception as exc:
                logger.warning(
                    "Could not extract columns for table '%s': %s", t_name, exc
                )
                columns = []

            measures = [
                self._parse_measure(mrow)
                for mrow in measures_by_table.get(t_name, [])
            ]

            table_metas.append(
                TableMeta(
                    name=t_name,
                    description=_coalesce(trow, "Description", "description"),
                    ai_description=None,
                    table_type=TableType.UNKNOWN,
                    grain=None,
                    columns=columns,
                    measures=measures,
                    hierarchies=[],
                    row_count_estimate=None,
                    is_hidden=is_hidden,
                    source_partition_type=_coalesce(trow, "Mode", "mode"),
                )
            )

        relationships = [
            self._parse_relationship(rrow) for _, rrow in rels_df.iterrows()
        ]

        model = SemanticModelMeta(
            name=model_name,
            workspace=ws,
            description=None,
            tables=table_metas,
            relationships=relationships,
            ai_readiness_score=None,
            scoring_breakdown={},
            extraction_timestamp=datetime.now(timezone.utc).isoformat(),
            extraction_method="semantic_link",
        )

        if with_copilot:
            model.copilot = self._extract_copilot(model_name, ws)

        return model

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _extract_copilot(self, model_name: str, workspace: str):
        """Fetch and parse the Copilot/ folder. Returns CopilotBundle or None.

        Resolution failures (workspace or model not found by sempy) log a
        warning and return None - never raise.
        """
        from fabric_ai_meta.generator.copilot_reader import CopilotReader
        from fabric_ai_meta.writeback.tmdl_client import TMDLClient

        fabric = self._fabric
        try:
            workspace_id = fabric.resolve_workspace_id(workspace)
        except Exception as exc:
            logger.warning(
                "Cannot resolve workspace id for %r: %s. Skipping Copilot extract.",
                workspace, exc,
            )
            return None
        if not workspace_id:
            logger.warning(
                "Workspace %r not found by sempy. Skipping Copilot extract.", workspace
            )
            return None

        try:
            model_id = fabric.resolve_item_id(
                model_name, type="SemanticModel", workspace=workspace
            )
        except Exception as exc:
            logger.warning(
                "Cannot resolve model id for %r: %s. Skipping Copilot extract.",
                model_name, exc,
            )
            return None
        if not model_id:
            logger.warning(
                "Model %r not found in workspace %r. Skipping Copilot extract.",
                model_name, workspace,
            )
            return None

        token = self._fabric_bearer_token()
        client = TMDLClient(token, workspace_id)
        envelope = client.get_definition(model_id)
        return CopilotReader.from_definition(envelope)

    def _fabric_bearer_token(self) -> str:
        """Obtain a Power BI / Fabric bearer token from the Fabric notebook runtime."""
        import notebookutils  # type: ignore[import-not-found]
        return notebookutils.credentials.getToken("pbi")

    def _parse_column(
        self, row, model_name: str, table_name: str, workspace: str
    ) -> ColumnMeta:
        """Normalize a sempy columns DataFrame row to ColumnMeta."""
        col_name = str(
            row.get("Column Name", row.get("column_name", row.get("Name", "")))
        )
        data_type = str(
            row.get("Data Type", row.get("data_type", "string"))
        ).lower()
        is_hidden = bool(row.get("Hidden", row.get("is_hidden", False)))

        sample_values = self._extract_sample_values(model_name, table_name, col_name)

        return ColumnMeta(
            name=col_name,
            data_type=data_type,
            description=_coalesce(row, "Description", "description"),
            ai_description=None,
            role=ColumnRole.UNKNOWN,
            is_hidden=is_hidden,
            display_folder=_coalesce(row, "Display Folder", "display_folder"),
            format_string=_coalesce(row, "Format String", "format_string"),
            sort_by_column=_coalesce(row, "Sort By Column", "sort_by_column"),
            sample_values=sample_values,
            is_nullable=True,
            synonyms=[],
        )

    def _parse_measure(self, row) -> MeasureMeta:
        """Normalize a sempy measures DataFrame row to MeasureMeta."""
        return MeasureMeta(
            name=str(
                row.get("Measure Name", row.get("measure_name", row.get("Name", "")))
            ),
            dax_expression=str(
                row.get(
                    "Measure Expression",
                    row.get("expression", row.get("dax_expression", "")),
                )
            ),
            description=_coalesce(row, "Description", "description"),
            ai_description=None,
            category=MeasureCategory.UNKNOWN,
            display_folder=_coalesce(row, "Display Folder", "display_folder"),
            format_string=_coalesce(row, "Format String", "format_string"),
            is_hidden=bool(row.get("Hidden", row.get("is_hidden", False))),
        )

    def _parse_relationship(self, row) -> RelationshipMeta:
        """Normalize a sempy relationships DataFrame row to RelationshipMeta."""
        return RelationshipMeta(
            from_table=str(row.get("From Table", row.get("from_table", ""))),
            from_column=str(row.get("From Column", row.get("from_column", ""))),
            to_table=str(row.get("To Table", row.get("to_table", ""))),
            to_column=str(row.get("To Column", row.get("to_column", ""))),
            cardinality=str(
                row.get("Multiplicity", row.get("cardinality", "one-to-many"))
            ).lower(),
            cross_filter_direction=str(
                row.get(
                    "Cross Filtering Behavior",
                    row.get("cross_filter_direction", "single"),
                )
            ).lower(),
            is_active=bool(row.get("Active", row.get("is_active", True))),
        )

    def list_models(self, workspace: str) -> list[str]:
        """Return the names of all semantic models in the given workspace.

        Args:
            workspace: Fabric workspace name.

        Returns:
            List of dataset (semantic model) names.
        """
        fabric = self._fabric
        datasets_df = self._with_retry(
            fabric.list_datasets,
            workspace=workspace,
            _context=f"list_datasets(workspace={workspace!r})",
        )
        for col in ("Dataset Name", "dataset_name", "Name", "name"):
            if col in datasets_df.columns:
                return [str(v) for v in datasets_df[col].dropna().tolist()]
        return []

    def _extract_sample_values(
        self, model_name: str, table: str, column: str
    ) -> list[str]:
        """Return up to 10 distinct sample values for a column.

        Returns an empty list on any error, sample values are best-effort only.
        Uses evaluate_dax with a TOPN(10, DISTINCT(...)) pattern per SPEC.md 6.1.
        """
        try:
            query = f"EVALUATE\nTOPN(10, DISTINCT('{table}'[{column}]))"
            df = self._fabric.evaluate_dax(model_name, query, workspace=self.workspace)
            return [str(v) for v in df.iloc[:, 0].dropna().tolist()]
        except Exception as exc:
            logger.debug(
                "Sample value extraction skipped for '%s'[%s]: %s",
                table,
                column,
                exc,
            )
            return []

    def _with_retry(self, fn, *args, _context: str = "", **kwargs):
        """Call fn(*args, **kwargs) with exponential backoff on transient errors.

        Retries on PermissionError, ConnectionError, TimeoutError.
        Max 3 attempts; initial delay 1 s, factor 2×.

        Raises:
            RuntimeError: After all retries are exhausted.
        """
        delay = _RETRY_BASE_SECONDS
        last_exc: Exception | None = None
        for attempt in range(_MAX_RETRIES):
            try:
                return fn(*args, **kwargs)
            except (PermissionError, ConnectionError, TimeoutError) as exc:
                last_exc = exc
                if attempt < _MAX_RETRIES - 1:
                    logger.warning(
                        "Attempt %d/%d failed for %s: %s, retrying in %ds…",
                        attempt + 1,
                        _MAX_RETRIES,
                        _context or fn.__name__,
                        exc,
                        delay,
                    )
                    time.sleep(delay)
                    delay *= 2
        raise RuntimeError(
            f"Extraction failed after {_MAX_RETRIES} attempts"
            f"{f' ({_context})' if _context else ''}: {last_exc}"
        ) from last_exc


# ------------------------------------------------------------------
# Module-level helper
# ------------------------------------------------------------------

def _coalesce(row, *keys) -> Optional[str]:
    """Return the first non-None, non-empty string value from row for the given keys."""
    for key in keys:
        val = row.get(key)
        if val is not None and str(val).strip():
            return str(val)
    return None
