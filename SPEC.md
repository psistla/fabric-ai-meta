# Technical Specification: Fabric Semantic Model → AI-Ready Metadata Generator

> **Document Type:** Product Requirements Document + Technical Design Spec
> **Version:** 1.2 (Open Question #1 Resolved)
> **Date:** March 13, 2026
> **Purpose:** Drive Claude Code implementation — this document is the single source of truth for what to build, why, and how.
> **Changelog from v1.1:** `sempy.fabric` requires Fabric notebook runtime — local execution is not supported. Two-mode architecture (Fabric runtime vs local dev/mock) is now the confirmed design. See [Correction Log](#correction-log) for full details.

---

## 1. Executive Summary

### What We're Building

A Python-based tool (CLI + library) that connects to Microsoft Fabric semantic models, extracts full metadata (tables, columns, measures, relationships, hierarchies), performs AI-driven analysis (table classification, grain detection, measure dependency mapping), and produces two categories of output:

1. **Auto-generated Prep for AI configurations** — accelerating what Microsoft expects teams to do manually
2. **Framework-agnostic AI-ready schemas** — exporting structured metadata for LangChain, Semantic Kernel, AutoGen, OpenAI function calling, and custom agent pipelines

### Runtime Environment Model (Confirmed)

> **RESOLVED — Open Question #1:** `sempy.fabric` requires the Microsoft Fabric notebook runtime. It cannot be used in a local Python environment.

This means the tool operates in two distinct modes:

| Mode | Where it runs | Extractor used | Use case |
|------|--------------|----------------|----------|
| **Fabric mode** | Inside a Fabric notebook | `SemanticLinkExtractor` | Production — real model extraction |
| **Local dev mode** | Any local machine | `MockExtractor` only | Development, testing, CI/CD |

The CLI must detect which mode it is in at startup and behave accordingly:
- **Fabric mode detected** (env var `FABRIC_NOTEBOOK_ID` present, or `notebookutils` importable): use `SemanticLinkExtractor`
- **Local mode detected**: all commands that require live extraction must fail with a clear `FabricEnvironmentError` unless `--mock` flag is passed
- **`--mock` flag**: always available on all extraction commands; bypasses the environment check and uses `MockExtractor` with fixture files

This is not a limitation to work around — it is the confirmed architecture. All CLI design, testing strategy, and documentation must reflect it.

### Why This Exists

Microsoft Fabric's native AI features (Prep for AI, Copilot descriptions, Data Agents) require manual, model-by-model configuration. Enterprises with 10–100+ semantic models cannot scale this process. Additionally, Microsoft's tools only serve the Fabric-internal ecosystem — there is no native export path for external AI frameworks.

### Critical Competitive Context

> **WARNING: Microsoft is actively building in this space.** The following native features already exist and must be treated as known constraints, not opportunities to replicate:
>
> - **Prep for AI** (GA in Power BI Desktop + Service): Manual configuration of AI Data Schemas, AI Instructions, and Verified Answers per semantic model
> - **Copilot for measure descriptions** (GA August 2025): Auto-generates natural-language measure descriptions
> - **Fabric Data Agents** (GA): Consume semantic models as data sources, honor Prep for AI configurations
> - **Fabric IQ + Ontology** (Announced Ignite 2025, preview): Semantic data layer mapping data to meaningful concepts
> - **Default Semantic Model sunset** (Completed Nov 2025): Forces explicit model creation, increasing demand for governance tooling
>
> **Our positioning:** Automation layer ON TOP of Microsoft's features, not a replacement. Bridge TO external AI frameworks. Governance ACROSS models at scale.

---

## 2. Target Users

### Primary: Fabric Architects / Senior BI Developers

- Manage 10–100+ semantic models across workspaces
- Need to prepare models for AI consumption at scale
- Responsible for governance, naming standards, documentation completeness

### Secondary: AI/ML Engineers Building on Fabric Data

- Building custom agents, copilots, or RAG pipelines against Fabric data
- Need structured metadata in their framework's native format
- Don't have deep Fabric/DAX expertise

### Tertiary: Data Governance Teams

- Need visibility into documentation completeness across the estate
- Want consistent naming, descriptions, and classification standards

---

## 3. Scope and Phasing

### Phase 1: Core Extraction + AI Schema Export (MVP — Weeks 1–3)

- Connect to Fabric semantic models via Semantic Link (Python)
- Extract tables, columns, measures (DAX), relationships, hierarchies
- AI-driven classification (fact/dim/bridge, grain detection, measure categorization)
- Export AI-ready JSON schema for external frameworks
- AI Readiness Score per model
- CLI interface

### Phase 2: Prep for AI Automation (Weeks 4–5)

- Auto-generate Prep for AI configurations (AI Data Schema selections, AI Instructions, Verified Answer suggestions)
- Auto-generate missing column/table descriptions using LLM
- Bulk operations across workspaces

### Phase 3: Governance + Cross-Model Intelligence (Weeks 6–8)

- Cross-model analysis (naming inconsistencies, duplicate measures, conflicting business logic)
- Governance scorecard across workspace estate
- Web UI dashboard
- Export governance reports

### Out of Scope (v1)

- Real-time sync / webhook-based updates
- Direct modification of semantic models (read-only tool)
- Power BI report analysis (focus is semantic model metadata only)
- Competing with Fabric IQ Ontology (different abstraction level)

---

## 4. Architecture

### 4.1 System Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                        User Interface Layer                       │
├──────────────┬──────────────────────┬────────────────────────────┤
│   CLI (P1)   │   Python API (P1)    │      Web UI (P3)           │
└──────┬───────┴──────────┬───────────┴────────────┬───────────────┘
       │                  │                        │
┌──────▼──────────────────▼────────────────────────▼───────────────┐
│                 Environment Detection (startup)                    │
│  Fabric runtime? → SemanticLinkExtractor                         │
│  Local + --mock? → MockExtractor                                 │
│  Local, no --mock? → FabricEnvironmentError (clear message)      │
└──────────────────────────────┬───────────────────────────────────┘
                               │
┌──────────────────────────────▼───────────────────────────────────┐
│                      Core Engine                                  │
├─────────────────────────────────────────────────────────────────-─┤
│  ┌─────────────┐  ┌──────────────┐  ┌──────────────────────────┐ │
│  │  Extractor   │  │  Analyzer    │  │  Generator               │ │
│  │             │  │              │  │                          │ │
│  │ • Tables    │  │ • Classify   │  │ • AI-Ready JSON Schema   │ │
│  │ • Columns   │──▶ • Grain     │──▶ • Prep for AI Config     │ │
│  │ • Measures  │  │ • DAX Deps  │  │ • LangChain Tools        │ │
│  │ • Relations │  │ • Scoring   │  │ • OpenAI Functions       │ │
│  │ • Hierarchy │  │ • Gaps      │  │ • Semantic Kernel Plugins │ │
│  └─────────────┘  └──────────────┘  └──────────────────────────┘ │
│                                                                   │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │                    LLM Integration                          │ │
│  │  • Claude API for classification, description generation,   │ │
│  │    grain inference, business rule extraction                 │ │
│  └─────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────┘
       │
┌──────▼──────────────────────────────────────────────────────────┐
│                    Data Access Layer                              │
├─────────────────────────────────────────────────────────────────-─┤
│  Primary: Semantic Link (sempy.fabric)                           │
│  ⚠️  CONFIRMED: Requires Fabric notebook runtime.               │
│      Does NOT work in local Python environments.                 │
│  ├── list_datasets() — enumerate models in workspace             │
│  ├── list_tables(dataset) — table metadata                       │
│  ├── list_measures(dataset) — measures with DAX expressions      │
│  ├── list_relationships(dataset) — relationship graph            │
│  ├── list_columns(dataset, table) — column metadata              │
│  └── evaluate_dax() — sample value retrieval via DAX queries     │
│      ⚠️  NOT evaluate_measure() — that function does not exist   │
│          in the sempy.fabric public API                          │
│                                                                   │
│  Local dev / CI/CD: MockExtractor                                │
│  └── Loads SemanticModelMeta from JSON fixture files             │
│      No Fabric connection required                               │
│      Activated by --mock flag on all extraction commands         │
│                                                                   │
│  Fallback: XMLA via TOM (.NET interop or pyadomd)               │
│  └── Full fidelity: calc groups, perspectives, translations,     │
│      object-level security, partitions                           │
│  ⚠️  pyadomd requires Windows (ADOMD.NET dependency).            │
│      On Linux/macOS, use pythonnet + Microsoft.AnalysisServices  │
│      or document as Windows-only fallback.                       │
│  ⚠️  XMLA also only usable inside Fabric/XMLA-enabled network.  │
│                                                                   │
│  Auth: Entra ID (Azure AD) — user token or service principal     │
│  ⚠️  Auth only required in Fabric mode — skipped in mock mode   │
└──────────────────────────────────────────────────────────────────┘
```

### 4.2 Key Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Primary extraction API | Semantic Link (`sempy.fabric`) | Python-native, no XMLA dependency. **Confirmed: requires Fabric notebook runtime — does not work locally.** |
| Local dev / CI/CD extraction | `MockExtractor` + JSON fixtures | Only viable extraction path outside Fabric runtime. All local development and testing uses this path. |
| Runtime detection | Env var `FABRIC_NOTEBOOK_ID` + `notebookutils` import check | Determines which extractor to use at startup; fails fast with clear error in local mode without `--mock` |
| Fallback extraction | XMLA via `pyadomd` (Windows) or TOM interop | Required for calc groups, perspectives, translations — Semantic Link doesn't expose these. **pyadomd is Windows-only. Also requires Fabric/XMLA network access — not usable locally.** |
| LLM provider | Claude API (Anthropic) | Best reasoning for DAX analysis and classification tasks; model: `claude-sonnet-4-6` |
| Output format | JSON (primary), YAML (optional) | JSON is universal; every framework can consume it |
| CLI framework | `click` | Simple, well-documented, supports nested commands |
| Package distribution | PyPI (`pip install fabric-ai-meta`) | Maximum reach for notebook users; local users use mock mode only |
| Config management | TOML (`pyproject.toml` + `.fabric-ai-meta.toml`) | Modern Python standard |

### 4.3 Authentication Architecture

```
Authentication Flow:
1. Fabric mode (notebook): Automatic — uses Fabric notebook's ambient credential
   sempy.fabric picks this up automatically; no explicit auth code needed
2. Fabric mode (service principal): Client ID + Secret / Certificate for CI/CD
   pipelines running inside Fabric (e.g., Fabric pipelines, scheduled notebooks)
3. Local mock mode: No authentication required — MockExtractor reads from fixture
   files only; no Fabric connection is made

⚠️  Interactive browser login (azure-identity InteractiveBrowserCredential) is
    NOT needed for sempy.fabric — it handles auth internally within the Fabric
    runtime. The auth/entra.py module exists for service principal config only.

Required Permissions (Fabric mode only):
- Semantic Model: Read.All (minimum)
- Workspace: Read.All (for cross-workspace scanning)
- XMLA: Read-only enabled on capacity (for fallback extraction)

Required Fabric SKU (Fabric mode only):
- Semantic Link: Any F SKU or Pro license (for basic metadata)
- XMLA endpoint: F/P SKU with XMLA read-only enabled
- Minimum viable: F2 ($262.80/month PAYG at $0.36/hr × 730 hrs)
```

---

## 5. Data Model

### 5.1 Internal Metadata Schema

This is the canonical internal representation. All extractors normalize to this format before analysis or export.

```python
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class TableType(Enum):
    FACT = "fact"
    DIMENSION = "dimension"
    BRIDGE = "bridge"
    CONFIGURATION = "configuration"
    AGGREGATE = "aggregate"
    STAGING = "staging"
    UNKNOWN = "unknown"


class MeasureCategory(Enum):
    ADDITIVE = "additive"          # SUM, COUNT — can aggregate across all dims
    SEMI_ADDITIVE = "semi_additive" # Balance-type measures (inventory, account balances)
                                   # — can be summed across most dims but NOT time
                                   # Uses LASTDATE/OPENINGBALANCEMONTH patterns
                                   # ⚠️ DISTINCTCOUNT is non-additive, NOT semi-additive
    NON_ADDITIVE = "non_additive"   # Ratios, percentages, averages, DISTINCTCOUNT
                                   # — cannot be summed across any dimension correctly
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


@dataclass
class HierarchyMeta:
    name: str
    table: str
    levels: list[str]          # Ordered column names top-to-bottom


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
```

### 5.2 AI-Ready Export Schema (JSON)

This is the output format consumed by AI agents and frameworks.

> **Note on `$schema` URL:** The `fabric-ai-meta.dev` domain is a placeholder. Publish the JSON Schema file to a real URL (e.g., GitHub Pages or PyPI docs site) before v1.0 release, or use a relative path reference during development.

```json
{
  "$schema": "https://fabric-ai-meta.dev/schema/v1.json",
  "version": "1.0",
  "model": {
    "name": "Contoso Sales",
    "workspace": "Production Analytics",
    "summary": "Enterprise sales analytics model covering order transactions, product catalog, customer demographics, and store locations. Grain: one row per order line item. Covers fiscal years 2020-2026.",
    "ai_readiness_score": 0.78,
    "extraction_timestamp": "2026-03-12T14:30:00Z"
  },
  "tables": [
    {
      "name": "Sales",
      "type": "fact",
      "grain": "One row per order line item",
      "description": "Transactional sales data at the line-item level. Each row represents a single product sold in a single transaction.",
      "row_count_estimate": 12500000,
      "columns": [
        {
          "name": "OrderID",
          "type": "int64",
          "role": "key",
          "description": "Unique identifier for each sales order"
        },
        {
          "name": "ProductKey",
          "type": "int64",
          "role": "foreign_key",
          "joins_to": "Product.ProductKey",
          "description": "Foreign key to Product dimension"
        },
        {
          "name": "Quantity",
          "type": "int64",
          "role": "measure_column",
          "description": "Number of units sold in this line item",
          "sample_values": ["1", "2", "5", "10", "25"]
        }
      ],
      "relationships_outbound": [
        {
          "to_table": "Product",
          "join": "Sales.ProductKey = Product.ProductKey",
          "cardinality": "many-to-one"
        },
        {
          "to_table": "Customer",
          "join": "Sales.CustomerKey = Customer.CustomerKey",
          "cardinality": "many-to-one"
        },
        {
          "to_table": "Calendar",
          "join": "Sales.OrderDate = Calendar.Date",
          "cardinality": "many-to-one"
        }
      ]
    }
  ],
  "measures": [
    {
      "name": "Total Revenue",
      "category": "additive",
      "description": "Sum of extended price across all line items. Excludes returns and discounts.",
      "dax": "SUMX('Sales', [Quantity] * [UnitPrice])",
      "valid_filter_dimensions": ["Product", "Customer", "Calendar", "Store"],
      "implicit_business_rules": [
        "Excludes returned orders (filtered by Sales[IsReturned] = FALSE in base table)",
        "Uses list price, not discounted price"
      ],
      "depends_on": ["Sales[Quantity]", "Sales[UnitPrice]"]
    },
    {
      "name": "Revenue YTD",
      "category": "time_intelligence",
      "description": "Year-to-date cumulative revenue based on fiscal calendar",
      "dax": "TOTALYTD([Total Revenue], 'Calendar'[Date])",
      "depends_on_measures": ["Total Revenue"],
      "requires_date_filter": true
    }
  ],
  "query_guidance": {
    "valid_filter_paths": [
      "To filter Sales by product category: Sales → Product → Product[Category]",
      "To filter Sales by region: Sales → Store → Store[Region]",
      "NEVER filter Sales directly by Customer[Segment] — use the relationship path"
    ],
    "common_pitfalls": [
      "Calendar table uses fiscal year (July-June), not calendar year",
      "Sales[Amount] is a raw column — use [Total Revenue] measure instead for correct aggregation",
      "Many-to-many between Product and Promotion requires bridge table — filter through PromotionBridge"
    ],
    "recommended_aggregations": {
      "revenue_by_product": "SUMMARIZECOLUMNS(Product[Category], \"Total Revenue\", [Total Revenue])",
      "monthly_trend": "SUMMARIZECOLUMNS('Calendar'[YearMonth], \"Total Revenue\", [Total Revenue])"
    }
  },
  "scoring": {
    "overall": 0.78,
    "breakdown": {
      "description_coverage": 0.65,
      "measure_documentation": 0.82,
      "relationship_completeness": 1.0,
      "naming_consistency": 0.70,
      "sample_values_available": 0.55,
      "business_rules_documented": 0.40
    },
    "recommendations": [
      "Add descriptions to 35% of columns that are currently undocumented",
      "Standardize naming: 'Cust_ID' should be 'CustomerID' to match convention",
      "Document implicit filter in [Net Revenue] measure — excludes international orders"
    ]
  }
}
```

---

## 6. Component Specifications

### 6.1 Extractor Module

**File:** `src/fabric_ai_meta/extractor/semantic_link.py`

**Responsibilities:**
- Authenticate to Fabric workspace
- Enumerate semantic models in workspace(s)
- Extract all metadata objects per model
- Normalize to internal `SemanticModelMeta` dataclass
- Handle pagination and rate limiting

**Key Implementation Notes:**

```python
# Semantic Link extraction pattern
# ⚠️  This code only runs inside a Fabric notebook runtime.
#     It will fail with ImportError or ConnectionError in local Python environments.
import sempy.fabric as fabric

# List all models in workspace
models = fabric.list_datasets(workspace="Production Analytics")

# For each model, extract metadata
tables = fabric.list_tables("Contoso Sales", workspace="Production Analytics")
measures = fabric.list_measures("Contoso Sales", workspace="Production Analytics")
relationships = fabric.list_relationships("Contoso Sales", workspace="Production Analytics")

# For columns — must iterate per table
for table_name in tables["Name"]:
    columns = fabric.list_columns("Contoso Sales", table_name, workspace="Production Analytics")

# For sample values — use evaluate_dax (NOT evaluate_measure — that function does not exist)
sample_query = """
    EVALUATE
    TOPN(10, DISTINCT('Product'[Category]))
"""
samples = fabric.evaluate_dax("Contoso Sales", sample_query, workspace="Production Analytics")
```

**Environment Detection (required at CLI startup):**

```python
def detect_fabric_runtime() -> bool:
    """
    Returns True if running inside a Fabric notebook runtime.
    sempy.fabric is only usable when this returns True.
    """
    import os
    import sys
    # Check 1: Fabric sets this env var in all notebook runtimes
    if os.environ.get("FABRIC_NOTEBOOK_ID"):
        return True
    # Check 2: notebookutils is injected by Fabric into the notebook kernel
    if "notebookutils" in sys.modules:
        return True
    return False


class FabricEnvironmentError(Exception):
    """
    Raised when a live extraction command is run outside Fabric notebook runtime.
    Always includes a remediation message directing the user to --mock or Fabric.
    """
    DEFAULT_MESSAGE = (
        "This command requires the Microsoft Fabric notebook runtime.\n"
        "sempy.fabric is not available in local Python environments.\n\n"
        "Options:\n"
        "  1. Run this command inside a Fabric notebook\n"
        "  2. Use --mock flag for local development with fixture data:\n"
        "     fabric-ai-meta analyze \"Model Name\" --workspace \"ws\" --mock\n"
    )
```

**XMLA Fallback** (`src/fabric_ai_meta/extractor/xmla.py`):
- Use `pyadomd` (Windows only — requires ADOMD.NET) or `pythonnet` with `Microsoft.AnalysisServices.Tabular`
- **⚠️ Platform constraint:** `pyadomd` depends on the ADOMD.NET client library which is Windows-only. On Linux or macOS environments (including CI/CD runners), this fallback will not be available without additional setup. Document this constraint clearly; treat XMLA fallback as Windows-first for v1.
- Required for: calculation groups, perspectives, translations, partition details
- Requires: F/P SKU with XMLA read-only enabled

**Error Handling:**
- `PermissionError` if user lacks Semantic Model Read access
- `ConnectionError` if XMLA endpoint not enabled (graceful fallback message)
- `TimeoutError` for large models — implement chunked extraction
- Rate limiting: exponential backoff with max 3 retries

### 6.2 Analyzer Module

**File:** `src/fabric_ai_meta/analyzer/classifier.py`

**Responsibilities:**
- Classify tables as fact/dimension/bridge/configuration
- Detect grain of fact tables
- Parse DAX measure dependency trees
- Classify measures by category (additive, semi-additive, time-intelligence, etc.)
- Detect column roles (key, foreign key, attribute, measure column)
- Identify implicit business rules in DAX expressions
- Score AI readiness

**Classification Strategy:**

Table classification uses heuristic rules first, then LLM for ambiguous cases:

```python
# Heuristic rules (no LLM needed)
def classify_table_heuristic(table: TableMeta, relationships: list[RelationshipMeta]) -> TableType:
    """
    Rule-based classification — handles ~70% of cases.

    Fact indicators:
    - Has multiple outbound many-to-one relationships
    - Contains numeric columns likely to be aggregated
    - Table name contains: fact, fct, sales, transactions, events, orders

    Dimension indicators:
    - Has inbound one-to-many relationships
    - Predominantly text/categorical columns
    - Table name contains: dim, dimension, lookup, product, customer, date, calendar

    Bridge indicators:
    - Only has foreign key columns
    - Has exactly 2 many-to-one relationships
    - No measures defined on table

    Configuration indicators:
    - Small row count (< 100 rows)
    - Contains parameter/config-like columns
    """
    pass
```

**Measure Category Classification Notes:**

When classifying measures, apply these rules before calling the LLM:

```python
# Heuristic patterns for measure categorization
TIME_INTEL_FUNCTIONS = {"TOTALYTD", "TOTALQTD", "TOTALMTD", "SAMEPERIODLASTYEAR",
                         "DATEYTD", "PREVIOUSMONTH", "PREVIOUSQUARTER", "PREVIOUSYEAR",
                         "OPENINGBALANCEMONTH", "CLOSINGBALANCEMONTH"}

SEMI_ADDITIVE_PATTERNS = {"LASTDATE", "FIRSTDATE", "OPENINGBALANCEMONTH",
                           "CLOSINGBALANCEMONTH", "OPENINGBALANCEQUARTER",
                           "CLOSINGBALANCEQUARTER"}
# ⚠️ Semi-additive = balance-type measures (inventory, account balances).
# DISTINCTCOUNT is NON-additive — cannot be summed across any dimension.
# Do NOT classify DISTINCTCOUNT as semi-additive.

NON_ADDITIVE_INDICATORS = {"DIVIDE", "AVERAGE", "AVERAGEX", "DISTINCTCOUNT",
                            "DISTINCTCOUNTNOBLANK"}
```

**DAX Dependency Parser:**

```python
def parse_measure_dependencies(measure_name: str, dax: str, all_measures: dict) -> dict:
    """
    Parse DAX expression to extract:
    1. Referenced measures (e.g., [Total Revenue] inside TOTALYTD)
    2. Referenced columns (e.g., Sales[Quantity])
    3. Filter modifications (CALCULATE filters, ALL, REMOVEFILTERS)
    4. Time intelligence functions used
    5. Implicit business rules (hardcoded filter values)

    Returns dependency graph node for this measure.
    """
    pass
```

**AI Readiness Scoring:**

```python
# Weights sum to exactly 1.0
SCORING_WEIGHTS = {
    "description_coverage": 0.25,       # % of columns + tables with descriptions
    "measure_documentation": 0.20,      # % of measures with descriptions
    "relationship_completeness": 0.15,  # All FKs have defined relationships
    "naming_consistency": 0.15,         # Follows naming convention (no abbreviations, consistent casing)
    "sample_values_available": 0.10,    # % of categorical columns with sample values extracted
    "business_rules_documented": 0.15,  # Implicit DAX filters are documented
}
# Verification: 0.25 + 0.20 + 0.15 + 0.15 + 0.10 + 0.15 = 1.00 ✓
```

### 6.3 Generator Module

**File:** `src/fabric_ai_meta/generator/`

**Sub-modules:**

#### 6.3.1 AI-Ready Schema Generator (`schema.py`)

Produces the canonical JSON schema (Section 5.2). This is the primary output format.

#### 6.3.2 Prep for AI Config Generator (`prep_for_ai.py`)

Auto-generates configurations that can be applied in Power BI Desktop or Service:

```python
@dataclass
class PrepForAIConfig:
    """Output that maps to Power BI's Prep for AI feature."""

    # AI Data Schema — which tables/columns to include
    included_tables: list[str]
    excluded_columns: dict[str, list[str]]  # table -> columns to exclude

    # AI Instructions — natural language guidance
    ai_instructions: str  # Generated prompt text for the model

    # Verified Answers — question-to-DAX mappings
    verified_answers: list[dict]  # [{"question": "...", "dax": "...", "description": "..."}]

    # Missing descriptions — generated by LLM
    generated_descriptions: dict[str, dict[str, str]]  # table -> column -> description
```

**AI Instructions generation prompt template:**

```
You are generating AI Instructions for a Power BI semantic model named "{model_name}".

Model context:
- Tables: {table_summary}
- Key measures: {measure_summary}
- Relationships: {relationship_summary}

Generate concise AI Instructions that:
1. Define which tables/columns answer which types of questions
2. Specify metric preferences (e.g., "For profitability questions, use [Contribution Margin]")
3. Define default groupings (e.g., "Analyze revenue by fiscal quarter unless specified")
4. List common abbreviations and synonyms
5. Document business rules not obvious from column names

Output format: Plain text instructions, max 2000 characters.
```

> **Open Question (Section 13, item 4):** Confirm whether a Fabric REST API exists to programmatically apply Prep for AI configurations, or whether the UI is the only application path. If manual-only, Phase 2 output is "a configuration file to apply manually" — adjust acceptance criteria PREP-01 accordingly.

#### 6.3.3 Framework Export Generators

**LangChain Tools Schema** (`export_langchain.py`):

```python
def to_langchain_tool_definition(model: SemanticModelMeta) -> dict:
    """
    Generates a LangChain-compatible tool definition that an agent
    can use to query this semantic model.

    IMPORTANT: LangChain's standard StructuredTool schema only natively supports
    name, description, and args_schema (parameters). The 'metadata' field below
    is a non-standard extension — it will NOT be automatically parsed by LangChain.

    Usage: Consumers of this export must manually inject the metadata fields
    into the tool description string or use a custom tool wrapper class.
    The metadata is included here for completeness and to enable custom
    agent implementations that do consume extended context.
    """
    return {
        "name": f"query_{sanitize(model.name)}",
        "description": (
            f"Query the {model.name} semantic model. {model.description}. "
            f"Valid filter paths and pitfalls are documented in the metadata field."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "question": {
                    "type": "string",
                    "description": "Natural language question about the data"
                },
                "tables": {
                    "type": "array",
                    "items": {"type": "string", "enum": [t.name for t in model.tables]},
                    "description": "Tables relevant to the query"
                },
                "measures": {
                    "type": "array",
                    "items": {
                        "type": "string",
                        "enum": [m.name for t in model.tables for m in t.measures]
                    },
                    "description": "Measures to evaluate"
                }
            }
        },
        # Non-standard extension — for custom agent implementations only
        "metadata": {
            "model_context": generate_context_prompt(model),
            "valid_filter_paths": extract_filter_paths(model),
            "common_pitfalls": extract_pitfalls(model)
        }
    }
```

**OpenAI Function Calling Schema** (`export_openai.py`):

```python
def to_openai_function(model: SemanticModelMeta) -> dict:
    """Generates OpenAI function calling compatible schema."""
    pass
```

**Semantic Kernel Plugin** (`export_semantic_kernel.py`):

```python
def to_semantic_kernel_plugin(model: SemanticModelMeta) -> dict:
    """Generates Semantic Kernel plugin definition with KernelFunction annotations."""
    pass
```

### 6.4 LLM Integration Module

**File:** `src/fabric_ai_meta/llm/client.py`

**Responsibilities:**
- Manage Claude API calls for classification, description generation, and analysis
- Token budget management — compress large model metadata to fit context windows
- Caching — avoid re-analyzing unchanged models
- Cost tracking per operation

**Key Design Constraints:**

```python
# Token budget management
# Claude Sonnet (claude-sonnet-4-6) actual context window: 200,000 tokens
# We use 190,000 as a conservative operational budget (leaves headroom for system prompt overhead)
MAX_CONTEXT_TOKENS = 190_000   # Conservative budget — actual window is 200K
RESERVED_FOR_RESPONSE = 8_000
MAX_MODEL_CONTEXT = MAX_CONTEXT_TOKENS - RESERVED_FOR_RESPONSE  # 182,000 tokens for input

# For large models (500+ measures), use chunked analysis:
# 1. Send table structure + relationships (always fits)
# 2. Send measures in batches of 50 for classification
# 3. Merge results

# Cost estimation (Claude Sonnet pricing — verify current rates at console.anthropic.com)
# ⚠️ Pricing changes over time. Do not hardcode rates in business logic.
# Retrieve programmatically or document as a config value.
# As of spec authoring: approximately $3/MTok input, $15/MTok output (verify before release)
# Typical model analysis: ~20K input tokens, ~5K output tokens
# Estimated cost per model: ~$0.14 (verify with current pricing)
# Enterprise estate (50 models): ~$7.00 per full scan (estimated)

ANTHROPIC_MODEL = "claude-sonnet-4-6"  # Current production model string as of March 2026
```

**Caching Strategy:**

```python
# Cache key = hash of model metadata
# Cache location = local SQLite or .fabric-ai-meta-cache/ directory
# Cache invalidation = when extraction timestamp changes
# This avoids redundant LLM calls for unchanged models
```

---

## 7. CLI Interface

### 7.1 Command Structure

```bash
# Installation
pip install fabric-ai-meta

# Authentication
fabric-ai-meta auth login              # Interactive browser login
fabric-ai-meta auth status             # Show current auth state
fabric-ai-meta auth logout

# Single model analysis
fabric-ai-meta analyze "Contoso Sales" \
    --workspace "Production Analytics" \
    --output ./output/ \
    --format json \
    --include-sample-values \
    --llm-enrich                       # Enable LLM classification + descriptions

# Bulk workspace scan
fabric-ai-meta scan \
    --workspace "Production Analytics" \
    --output ./output/ \
    --format json

# Export to specific framework
fabric-ai-meta export langchain "Contoso Sales" --workspace "Production Analytics"
fabric-ai-meta export openai "Contoso Sales" --workspace "Production Analytics"
fabric-ai-meta export semantic-kernel "Contoso Sales" --workspace "Production Analytics"
fabric-ai-meta export prep-for-ai "Contoso Sales" --workspace "Production Analytics"

# AI Readiness Score
fabric-ai-meta score "Contoso Sales" --workspace "Production Analytics"
fabric-ai-meta score --workspace "Production Analytics" --all  # Score all models

# Cross-model governance (Phase 3)
fabric-ai-meta governance \
    --workspace "Production Analytics" \
    --report ./governance-report.json
```

### 7.2 Output Structure

```
output/
├── contoso-sales/
│   ├── ai-ready-schema.json          # Primary AI-ready export
│   ├── prep-for-ai-config.json       # Auto-generated Prep for AI settings
│   ├── langchain-tool.json           # LangChain tool definition
│   ├── openai-function.json          # OpenAI function calling schema
│   ├── semantic-kernel-plugin.json   # Semantic Kernel plugin def
│   ├── readiness-score.json          # Scoring breakdown
│   ├── measure-dependency-graph.json # DAX dependency tree
│   └── extraction-raw.json           # Raw extracted metadata (for debugging)
└── workspace-summary.json            # Cross-model summary
```

---

## 8. Project Structure

```
fabric-ai-meta/
├── pyproject.toml
├── README.md
├── LICENSE
├── .fabric-ai-meta.toml.example      # Config template
│
├── src/
│   └── fabric_ai_meta/
│       ├── __init__.py
│       ├── cli.py                     # Click CLI entrypoint
│       ├── config.py                  # Configuration management
│       │
│       ├── auth/
│       │   ├── __init__.py
│       │   └── entra.py               # Azure AD / Entra ID auth
│       │
│       ├── extractor/
│       │   ├── __init__.py
│       │   ├── base.py                # Abstract extractor interface
│       │   ├── semantic_link.py       # Primary: sempy.fabric
│       │   └── xmla.py               # Fallback: XMLA/TOM (Windows-only)
│       │
│       ├── analyzer/
│       │   ├── __init__.py
│       │   ├── classifier.py          # Table/measure/column classification
│       │   ├── dax_parser.py          # DAX dependency analysis
│       │   ├── scorer.py              # AI readiness scoring
│       │   └── governance.py          # Cross-model analysis (Phase 3)
│       │
│       ├── generator/
│       │   ├── __init__.py
│       │   ├── schema.py              # AI-ready JSON schema
│       │   ├── prep_for_ai.py         # Prep for AI config generation
│       │   ├── export_langchain.py    # LangChain format
│       │   ├── export_openai.py       # OpenAI format
│       │   └── export_semantic_kernel.py  # Semantic Kernel format
│       │
│       ├── llm/
│       │   ├── __init__.py
│       │   ├── client.py              # Claude API wrapper
│       │   ├── prompts.py             # Prompt templates
│       │   └── cache.py               # Response caching
│       │
│       └── models/
│           ├── __init__.py
│           └── metadata.py            # Dataclass definitions (Section 5.1)
│
├── tests/
│   ├── conftest.py
│   ├── fixtures/                      # Sample model metadata for testing
│   │   ├── contoso_sales.json
│   │   └── adventure_works.json
│   ├── test_extractor.py
│   ├── test_analyzer.py
│   ├── test_generator.py
│   └── test_cli.py
│
└── docs/
    ├── schema-spec.md                 # AI-ready schema format specification
    ├── prep-for-ai-guide.md           # How to apply generated Prep for AI configs
    └── framework-integration.md       # How to use exports in each AI framework
```

---

## 9. Dependencies

```toml
[project]
name = "fabric-ai-meta"
version = "0.1.0"
requires-python = ">=3.10"

dependencies = [
    "click>=8.1",                      # CLI framework
    "anthropic>=0.40",                 # Claude API client
    "azure-identity>=1.15",            # Entra ID authentication
    "semantic-link-sempy>=0.8",        # Fabric Semantic Link
    "pydantic>=2.0",                   # Data validation
    "rich>=13.0",                      # CLI output formatting (includes progress bars)
    "networkx>=3.0",                   # DAX dependency graph analysis
    # Note: tqdm removed — rich.progress covers all progress bar needs
    # Adding both creates redundancy; use rich.progress throughout
]

[project.optional-dependencies]
xmla = [
    "pyadomd>=0.1",                    # XMLA connectivity — Windows-only (requires ADOMD.NET)
                                       # Not available on Linux/macOS without additional setup
]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "ruff>=0.5",
    "mypy>=1.10",
]

[project.scripts]
fabric-ai-meta = "fabric_ai_meta.cli:main"
```

> **Dependency note on pydantic:** Pydantic is listed as a core dependency for runtime data validation. If you prefer to keep the dependency surface minimal and use Python dataclasses only, move pydantic to optional-dependencies. The internal data model (Section 5.1) is defined as dataclasses and does not require pydantic at runtime.

---

## 10. Acceptance Criteria

### Phase 1 MVP

- [ ] **AUTH-01:** Successfully authenticate via interactive browser login (Entra ID)
- [ ] **AUTH-02:** Detect and use ambient notebook credential when running in Fabric
- [ ] **EXT-01:** Extract tables, columns (with types), measures (with DAX), and relationships from a semantic model via Semantic Link
- [ ] **EXT-02:** Handle models with 100+ tables and 500+ measures without timeout
- [ ] **EXT-03:** Extract sample values (top 10 distinct) for categorical columns using `evaluate_dax`
- [ ] **ANA-01:** Classify tables as fact/dimension/bridge with >85% accuracy on test models
- [ ] **ANA-02:** Detect grain of fact tables and express in natural language
- [ ] **ANA-03:** Parse DAX measure dependencies into a directed graph
- [ ] **ANA-04:** Classify measures by category (additive, semi-additive, time-intelligence, etc.)
- [ ] **ANA-05:** Calculate AI Readiness Score with breakdown
- [ ] **GEN-01:** Generate AI-ready JSON schema conforming to spec (Section 5.2)
- [ ] **GEN-02:** Generate LangChain tool definition
- [ ] **GEN-03:** Generate OpenAI function calling schema
- [ ] **GEN-04:** Generated schemas are valid JSON and parseable by target frameworks
- [ ] **CLI-01:** `fabric-ai-meta analyze` command works end-to-end
- [ ] **CLI-02:** `fabric-ai-meta score` displays formatted readiness score
- [ ] **CLI-03:** `fabric-ai-meta export` produces framework-specific outputs
- [ ] **LLM-01:** LLM calls use <$0.20 per model analysis
- [ ] **LLM-02:** LLM responses are cached to avoid redundant API calls

### Phase 2

- [ ] **PREP-01:** Auto-generate Prep for AI Data Schema configuration
- [ ] **PREP-02:** Auto-generate AI Instructions text
- [ ] **PREP-03:** Suggest Verified Answers from common measure patterns
- [ ] **DESC-01:** Generate missing column descriptions via LLM
- [ ] **BULK-01:** Scan all models in a workspace in single command

### Phase 3

- [ ] **GOV-01:** Detect naming inconsistencies across models in a workspace
- [ ] **GOV-02:** Identify duplicate measures across models
- [ ] **GOV-03:** Generate governance scorecard report
- [ ] **WEB-01:** Web UI displays model inventory with readiness scores

---

## 11. Validation Strategy

### Test with Real Models

The MVP must be validated against at minimum these scenarios:

1. **Small model:** Adventure Works sample (10 tables, 30 measures)
2. **Medium model:** Enterprise sales model (50 tables, 200 measures)
3. **Large model:** Finance model (100+ tables, 500+ measures, calculation groups)
4. **Direct Lake model:** Model backed by lakehouse with entity partitions
5. **Import model:** Traditional import-mode model

### Accuracy Benchmarks

- Table classification accuracy: >85% on manual review
- Grain detection accuracy: >80% (expressed correctly in natural language)
- Measure categorization accuracy: >90% for additive vs non-additive
- Generated descriptions: rated "useful" by a Fabric developer on >75% of outputs

### Integration Test

Feed generated AI-ready schema to a text-to-SQL agent (Claude or GPT) and measure:
- Baseline: agent queries model with no metadata context
- With schema: agent queries model with generated AI-ready schema
- Target: measurable improvement in query correctness (qualitative, not prescribing a specific %)

---

## 12. Risk Register

| Risk | Severity | Mitigation |
|------|----------|------------|
| Semantic Link API changes or deprecation | High | Abstract behind interface; XMLA fallback ready |
| Microsoft ships automated Prep for AI (makes Phase 2 redundant) | High | Monitor Fabric roadmap monthly; pivot to export-only if needed |
| sempy.fabric not usable locally — limits developer experience | High | **CONFIRMED RISK.** Mitigation: MockExtractor + fixture-driven dev workflow. All tests run locally via mock. Real extraction only tested inside Fabric notebooks. |
| Fabric IQ Ontology subsumes AI-ready schema concept | Medium | Position as complementary (Ontology = runtime, our schema = development-time) |
| LLM classification hallucinations on complex DAX | Medium | Heuristic-first approach; LLM only for ambiguous cases; confidence scoring |
| Large models exceed token limits | Medium | Chunked analysis with merge strategy (already designed) |
| XMLA access requires F64+ in practice for some features | Low | Document SKU requirements clearly; Semantic Link covers most use cases |
| Rate limiting on Semantic Link APIs in shared capacity | Low | Exponential backoff; warn user about capacity contention |
| pyadomd (XMLA fallback) unavailable on Linux/macOS | Medium | Document as Windows-only for v1; research pythonnet alternative for cross-platform v2 |

---

## 13. Open Questions (Resolve During Implementation)

1. ~~**Semantic Link outside Fabric notebooks:** Does `sempy.fabric` work reliably in a local Python environment?~~ **✅ RESOLVED (March 13, 2026):** `sempy.fabric` requires the Fabric notebook runtime. It does not work in local Python environments. Architecture updated accordingly — see Section 1.1 (Runtime Environment Model) and Section 6.1 (FabricEnvironmentError).

2. **Calculation group extraction via Semantic Link:** Confirm whether `list_measures()` returns calculation group items or only standard measures. If not, XMLA fallback is required earlier than planned.

3. **Sample value extraction costs:** Running `evaluate_dax` for TOPN queries on large models consumes CUs. Quantify the CU cost of extracting sample values for a 50-table model.

4. **Prep for AI programmatic application:** Is there an API to apply Prep for AI configurations, or is it manual-only via the UI? If manual-only, our Phase 2 output is a "configuration file to apply manually" rather than an automated pipeline. Acceptance criteria PREP-01 through PREP-03 must be scoped accordingly.

5. **Schema versioning:** How do we handle schema format evolution? Semantic versioning on the JSON schema (`v1`, `v2`) with backward compatibility guarantees?

6. **pyadomd cross-platform:** What is the recommended path for XMLA access on Linux/macOS? Evaluate `pythonnet` + `Microsoft.AnalysisServices.Tabular` as a cross-platform alternative before v1 release.

---

## 14. Implementation Order (Claude Code Directives)

When using Claude Code to build this project, follow this sequence:

```
Step 1: Project scaffolding
  → pyproject.toml, package structure, CLI skeleton with click
  → Run: creates empty module files with docstrings

Step 2: Data models
  → Implement all dataclasses from Section 5.1
  → Add JSON serialization/deserialization

Step 3: Mock extractor
  → Create a mock extractor that loads from JSON fixtures
  → Build test fixtures based on Adventure Works sample model
  → This unblocks all downstream development without Fabric access

Step 4: Analyzer — heuristic classification
  → Table classifier (rule-based)
  → Column role detector (rule-based)
  → DAX dependency parser (regex + AST-lite)
  → AI readiness scorer

Step 5: Generator — AI-ready schema
  → JSON schema output matching Section 5.2 spec
  → Validate output against JSON Schema draft

Step 6: Generator — framework exports
  → LangChain tool definition
  → OpenAI function calling schema
  → Semantic Kernel plugin definition

Step 7: LLM integration
  → Claude API client (model: claude-sonnet-4-6) with caching
  → Prompt templates for classification, description generation, grain detection
  → Token budget management (190K operational budget, 200K actual window)

Step 8: Semantic Link extractor (Fabric notebook runtime required)
  → CONFIRMED: sempy.fabric only works inside Fabric notebook runtime
  → Implement SemanticLinkExtractor — this code runs in Fabric notebooks only
  → Implement FabricEnvironmentError and detect_fabric_runtime() in auth/entra.py
  → CLI startup must call detect_fabric_runtime() and gate extraction commands
  → --mock flag must bypass environment check on all extraction commands
  → Error handling and retry logic

Step 9: CLI polish
  → Rich output formatting (use rich.progress for progress bars)
  → Config file support

Step 10: Prep for AI generator (Phase 2)
  → AI Data Schema configuration
  → AI Instructions generation
  → Verified Answer suggestions
  → Resolve Open Question #4 before finalizing this step

Step 11: Tests
  → Unit tests for each module
  → Integration test with mock extractor
  → CLI tests
```

---

## Appendix A: Microsoft Native Feature Reference

For developer reference — these are the features this tool complements, not replaces:

| Feature | Status | What It Does | Our Relationship |
|---------|--------|-------------|-----------------|
| Prep for AI — AI Data Schema | GA | Manual table/column selection for AI scope | We auto-generate this configuration |
| Prep for AI — AI Instructions | GA | Manual text instructions for AI context | We auto-generate this text |
| Prep for AI — Verified Answers | GA | Manual question-to-visual mappings | We suggest these from measure patterns |
| Copilot for measure descriptions | GA (Aug 2025) | Auto-generates measure descriptions | We generate descriptions for columns AND tables, not just measures |
| Fabric Data Agents | GA | Consume semantic models for NL querying | We export metadata FOR agents outside Fabric |
| Fabric IQ + Ontology | Preview (late 2025) | Semantic data layer mapping | Different abstraction level — we focus on model-level metadata |
| TMDL | GA (Aug 2024) | Human-readable model serialization | We consume TMDL as input, not compete with it |
| Semantic Link (sempy) | GA | Python API for model metadata + data | Our primary extraction layer |

## Appendix B: Configuration File Format

```toml
# .fabric-ai-meta.toml

[auth]
method = "interactive"  # "interactive", "service_principal", "notebook"
tenant_id = "your-tenant-id"  # Required for service_principal
client_id = "your-client-id"  # Required for service_principal

[extraction]
default_workspace = "Production Analytics"
include_sample_values = true
sample_value_count = 10
extraction_method = "semantic_link"  # "semantic_link" or "xmla"

[llm]
provider = "anthropic"
model = "claude-sonnet-4-6"           # Current model string — update as new versions release
api_key_env = "ANTHROPIC_API_KEY"    # Environment variable name
cache_enabled = true
cache_dir = ".fabric-ai-meta-cache"
max_cost_per_run = 5.00  # USD — abort if cumulative cost exceeds this

[output]
default_format = "json"
output_dir = "./output"
include_raw_extraction = false

[scoring]
weights.description_coverage = 0.25
weights.measure_documentation = 0.20
weights.relationship_completeness = 0.15
weights.naming_consistency = 0.15
weights.sample_values_available = 0.10
weights.business_rules_documented = 0.15
# Weights sum: 1.00 ✓
```

---

## Correction Log

> This section documents every hallucination and logical inconsistency found in v1.0, and the fix applied in v1.1. Use this as a review checklist.

### 🔴 Critical Corrections

**1. Wrong Claude model string (Sections 4.2, 6.4, Appendix B)**
- **v1.0:** `claude-sonnet-4-20250514`
- **v1.1:** `claude-sonnet-4-6`
- **Why:** The model string `claude-sonnet-4-20250514` is the format for an older generation. As of March 2026, the current Claude Sonnet model string is `claude-sonnet-4-6`. Using the wrong string causes immediate API errors at runtime.

**2. Wrong DAX syntax in `recommended_aggregations` (Section 5.2)**
- **v1.0:**
  ```
  "revenue_by_product": "SUMMARIZECOLUMNS(Product[Category], 'Total Revenue')"
  ```
- **v1.1:**
  ```
  "revenue_by_product": "SUMMARIZECOLUMNS(Product[Category], \"Total Revenue\", [Total Revenue])"
  ```
- **Why:** `SUMMARIZECOLUMNS` requires measure expressions as name–value pairs: `(groupBy_column, "alias", expression)`. The v1.0 version passes a table reference `'Total Revenue'` (single quotes = table in DAX) as a groupBy column, which would either error or silently produce wrong results. Both `recommended_aggregations` entries were wrong and have been corrected.

**3. Phantom API function `evaluate_measure()` in architecture diagram (Section 4.1)**
- **v1.0:** Architecture diagram listed `evaluate_measure() — sample value retrieval`
- **v1.1:** Corrected to `evaluate_dax() — sample value retrieval via DAX queries`
- **Why:** `evaluate_measure()` does not exist in the `sempy.fabric` public API. The correct function is `evaluate_dax()`, which is also what the code in Section 6.1 correctly uses. This creates a direct contradiction in v1.0.

### 🟡 Logical Inconsistencies Fixed

**4. MAX_CONTEXT_TOKENS comment misidentifies budget as "context window" (Section 6.4)**
- **v1.0:** `MAX_CONTEXT_TOKENS = 180_000  # Claude Sonnet context window`
- **v1.1:** `MAX_CONTEXT_TOKENS = 190_000  # Conservative budget — actual window is 200K`
- **Why:** Claude Sonnet's actual context window is 200,000 tokens. Labeling an operational budget as "the context window" misleads implementers into thinking the hard limit is 180K. Also updated the budget from 180K to 190K to use more of the available window while leaving proper headroom.

**5. `MeasureCategory.SEMI_ADDITIVE` incorrectly included `DISTINCTCOUNT` (Section 5.1)**
- **v1.0 comment:** `"DISTINCTCOUNT, balances — limited aggregation"`
- **v1.1:** Separated semi-additive (balance-type measures) from non-additive (DISTINCTCOUNT, ratios, averages) with explicit notes in both enum comments and heuristic classification code.
- **Why:** DISTINCTCOUNT is non-additive — it cannot be meaningfully summed across any dimension. Semi-additive applies to balance-type measures (inventory, account balances) that can be summed across some dimensions but not time. Conflating these leads to incorrect measure categorization.

**6. `pydantic` listed as core dependency but commented as optional (Section 9)**
- **v1.0:** Pydantic in `dependencies` array with comment "(optional, can use dataclasses)"
- **v1.1:** Listed as core with clarifying note; guidance added on how to make it optional if desired.
- **Why:** A package cannot simultaneously be in the required `dependencies` and be "optional." Pick one. Spec now treats it as core with an explicit opt-out path documented.

**7. `tqdm` dependency is redundant given `rich` (Section 9)**
- **v1.0:** Both `tqdm>=4.65` and `rich>=13.0` listed as dependencies
- **v1.1:** `tqdm` removed; `rich.progress` used throughout for progress bars
- **Why:** `rich` includes a fully-featured progress bar system (`rich.progress`). Including both `tqdm` and `rich` duplicates functionality and adds unnecessary dependency weight.

**8. `pyadomd` Windows-only constraint undocumented (Sections 4.1, 4.2, 9, 12)**
- **v1.0:** `pyadomd` listed as XMLA fallback with no platform constraint mentioned
- **v1.1:** All references to `pyadomd` now include a Windows-only warning; risk register updated; Open Question #6 added; project structure comment updated.
- **Why:** `pyadomd` requires ADOMD.NET, a Windows-only .NET component. On Linux/macOS CI/CD runners (common in enterprise) the XMLA fallback silently fails to install. This is a build-breaking omission.

**9. LangChain `metadata` field is non-standard (Section 6.3.3)**
- **v1.0:** Function returned a `metadata` key with no explanation of LangChain compatibility
- **v1.1:** Added explicit docstring warning that `metadata` is a non-standard extension not parsed by LangChain's native tool runner, with guidance on how consumers should use it.
- **Why:** If an implementer passes this export directly to LangChain's tool runner expecting the metadata to be auto-used, it will be silently ignored. The extension is valid for custom implementations but must be documented as such.

### 🟢 Clarifications Added

**10. `$schema` URL placeholder noted (Section 5.2)**
- Added note that `fabric-ai-meta.dev` is a placeholder and must be published before v1.0 release.

**11. Pricing comment marked as verify-before-release (Section 6.4)**
- Added explicit note that pricing figures should be verified at release time and should not be hardcoded into business logic.

**12. Open Question #6 added (Section 13)**
- Added explicit question about cross-platform XMLA access path, tracking the `pyadomd` Windows-only issue.

---

## v1.2 Changes (March 13, 2026)

### 🔴 Architecture Change — sempy.fabric Runtime Constraint (Confirmed)

**Open Question #1 resolved by live testing.**

- **Finding:** `sempy.fabric` requires the Microsoft Fabric notebook runtime. It does not work in local Python environments. Import succeeds but API calls fail without the Fabric ambient credential and runtime context.
- **Impact:** Every section that assumed local CLI execution with live Fabric data was incorrect.

**Changes applied across the spec:**

| Section | Change |
|---------|--------|
| Section 1.1 | New "Runtime Environment Model" table documenting Fabric mode vs Local dev mode as the confirmed two-mode architecture |
| Section 4.1 | Architecture diagram updated — Environment Detection layer added; MockExtractor added to Data Access Layer; sempy marked as Fabric-runtime-only |
| Section 4.2 | Design decisions table — sempy entry corrected; MockExtractor added as a first-class design decision for local dev/CI/CD |
| Section 4.3 | Auth section rewritten — interactive browser login removed (sempy handles auth internally); auth module scoped to service principal only |
| Section 6.1 | `FabricEnvironmentError` class and `detect_fabric_runtime()` function fully specified with implementation code |
| Section 12 | Risk register — new confirmed High severity row for local execution limitation |
| Section 13 | Open Question #1 struck through and marked ✅ RESOLVED with date |
| Section 14 | Step 8 rewritten — "requires Fabric notebook runtime" is the confirmed constraint, not an open question |
