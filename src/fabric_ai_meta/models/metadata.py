"""Dataclass definitions for semantic model metadata (SPEC.md Section 5.1)."""

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Optional

from fabric_ai_meta.models.copilot import CopilotBundle


class TableType(Enum):
    FACT = "fact"
    DIMENSION = "dimension"
    BRIDGE = "bridge"
    CONFIGURATION = "configuration"
    AGGREGATE = "aggregate"
    STAGING = "staging"
    UNKNOWN = "unknown"


class MeasureCategory(Enum):
    ADDITIVE = "additive"          # SUM, COUNT, can aggregate across all dims
    SEMI_ADDITIVE = "semi_additive" # Balance-type measures (inventory, account balances)
                                   #, can be summed across most dims but NOT time
                                   # Uses LASTDATE/OPENINGBALANCEMONTH patterns
                                   # ⚠️ DISTINCTCOUNT is non-additive, NOT semi-additive
    NON_ADDITIVE = "non_additive"   # Ratios, percentages, averages, DISTINCTCOUNT
                                   #, cannot be summed across any dimension correctly
    TIME_INTELLIGENCE = "time_intelligence"  # YTD, QTD, prior period
    CALCULATED = "calculated"       # Derived from other measures
    FILTER_CONTEXT = "filter_context"  # CALCULATE with explicit filters
    UNKNOWN = "unknown"


class ColumnRole(Enum):
    KEY = "key"                    # Primary key
    FOREIGN_KEY = "foreign_key"    # Joins to another table
    ATTRIBUTE = "attribute"        # Descriptive, filterable
    MEASURE_COLUMN = "measure_column"  # Numeric, aggregatable
    DATE = "date"                  # date/datetime for time intelligence
    SORT = "sort"                  # Sort-by column
    DISPLAY = "display"            # Display-only, not for analysis
    UNKNOWN = "unknown"


def _enum_to_value(obj):
    """Convert enum instances to their string values for serialization."""
    if isinstance(obj, Enum):
        return obj.value
    return obj


def _dict_factory(items):
    """Custom dict factory for dataclasses.asdict that converts enums to values."""
    return {k: _enum_to_value(v) for k, v in items}


@dataclass
class ColumnMeta:
    name: str
    data_type: str               # string, int64, double, datetime, boolean, decimal
    description: Optional[str]   # Existing description from model
    ai_description: Optional[str]  # LLM-generated description
    role: ColumnRole
    is_hidden: bool
    display_folder: Optional[str]
    format_string: Optional[str]
    sort_by_column: Optional[str]
    sample_values: list[str] = field(default_factory=list)  # Up to 10 distinct values
    is_nullable: bool = True
    synonyms: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Return a JSON-serializable dict."""
        return asdict(self, dict_factory=_dict_factory)


@dataclass
class MeasureMeta:
    name: str
    dax_expression: str
    description: Optional[str]
    ai_description: Optional[str]
    category: MeasureCategory
    display_folder: Optional[str]
    format_string: Optional[str]
    depends_on_measures: list[str] = field(default_factory=list)
    depends_on_columns: list[str] = field(default_factory=list)  # table[column] format
    implicit_filters: list[str] = field(default_factory=list)    # Business rules embedded in DAX
    is_hidden: bool = False

    def to_dict(self) -> dict:
        """Return a JSON-serializable dict."""
        return asdict(self, dict_factory=_dict_factory)


@dataclass
class RelationshipMeta:
    from_table: str
    from_column: str
    to_table: str
    to_column: str
    cardinality: str           # one-to-many, many-to-one, one-to-one, many-to-many
    cross_filter_direction: str  # single, both
    is_active: bool
    security_filtering: Optional[str] = None

    def to_dict(self) -> dict:
        """Return a JSON-serializable dict."""
        return asdict(self, dict_factory=_dict_factory)


@dataclass
class HierarchyMeta:
    name: str
    table: str
    levels: list[str]          # Ordered column names top-to-bottom

    def to_dict(self) -> dict:
        """Return a JSON-serializable dict."""
        return asdict(self, dict_factory=_dict_factory)


@dataclass
class TableMeta:
    name: str
    description: Optional[str]
    ai_description: Optional[str]
    table_type: TableType
    grain: Optional[str]       # Natural language: "one row per order line item per day"
    columns: list[ColumnMeta] = field(default_factory=list)
    measures: list[MeasureMeta] = field(default_factory=list)
    hierarchies: list[HierarchyMeta] = field(default_factory=list)
    row_count_estimate: Optional[int] = None
    is_hidden: bool = False
    source_partition_type: Optional[str] = None  # DirectLake, Import, DirectQuery

    def to_dict(self) -> dict:
        """Return a JSON-serializable dict."""
        return asdict(self, dict_factory=_dict_factory)


@dataclass
class SemanticModelMeta:
    name: str
    workspace: str
    description: Optional[str]
    tables: list[TableMeta] = field(default_factory=list)
    relationships: list[RelationshipMeta] = field(default_factory=list)
    ai_readiness_score: Optional[float] = None  # 0.0 to 1.0
    scoring_breakdown: dict = field(default_factory=dict)
    extraction_timestamp: Optional[str] = None
    extraction_method: Optional[str] = None  # "semantic_link" or "xmla"
    copilot: Optional[CopilotBundle] = None

    def to_dict(self) -> dict:
        """Return a JSON-serializable dict."""
        d = asdict(self, dict_factory=_dict_factory)
        d["copilot"] = self.copilot.to_dict() if self.copilot is not None else None
        return d


def from_dict(data: dict) -> SemanticModelMeta:
    """Reconstruct a full SemanticModelMeta object tree from a plain dict."""
    tables = []
    for t in data.get("tables", []):
        columns = [
            ColumnMeta(
                name=c["name"],
                data_type=c["data_type"],
                description=c.get("description"),
                ai_description=c.get("ai_description"),
                role=ColumnRole(c["role"]),
                is_hidden=c["is_hidden"],
                display_folder=c.get("display_folder"),
                format_string=c.get("format_string"),
                sort_by_column=c.get("sort_by_column"),
                sample_values=c.get("sample_values", []),
                is_nullable=c.get("is_nullable", True),
                synonyms=c.get("synonyms", []),
            )
            for c in t.get("columns", [])
        ]
        measures = [
            MeasureMeta(
                name=m["name"],
                dax_expression=m["dax_expression"],
                description=m.get("description"),
                ai_description=m.get("ai_description"),
                category=MeasureCategory(m["category"]),
                display_folder=m.get("display_folder"),
                format_string=m.get("format_string"),
                depends_on_measures=m.get("depends_on_measures", []),
                depends_on_columns=m.get("depends_on_columns", []),
                implicit_filters=m.get("implicit_filters", []),
                is_hidden=m.get("is_hidden", False),
            )
            for m in t.get("measures", [])
        ]
        hierarchies = [
            HierarchyMeta(
                name=h["name"],
                table=h["table"],
                levels=h["levels"],
            )
            for h in t.get("hierarchies", [])
        ]
        tables.append(TableMeta(
            name=t["name"],
            description=t.get("description"),
            ai_description=t.get("ai_description"),
            table_type=TableType(t["table_type"]),
            grain=t.get("grain"),
            columns=columns,
            measures=measures,
            hierarchies=hierarchies,
            row_count_estimate=t.get("row_count_estimate"),
            is_hidden=t.get("is_hidden", False),
            source_partition_type=t.get("source_partition_type"),
        ))

    relationships = [
        RelationshipMeta(
            from_table=r["from_table"],
            from_column=r["from_column"],
            to_table=r["to_table"],
            to_column=r["to_column"],
            cardinality=r["cardinality"],
            cross_filter_direction=r["cross_filter_direction"],
            is_active=r["is_active"],
            security_filtering=r.get("security_filtering"),
        )
        for r in data.get("relationships", [])
    ]

    return SemanticModelMeta(
        name=data["name"],
        workspace=data["workspace"],
        description=data.get("description"),
        tables=tables,
        relationships=relationships,
        ai_readiness_score=data.get("ai_readiness_score"),
        scoring_breakdown=data.get("scoring_breakdown", {}),
        extraction_timestamp=data.get("extraction_timestamp"),
        extraction_method=data.get("extraction_method"),
    )
