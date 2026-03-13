# fabric-ai-meta — Claude Code Task List

> **How to use this file:**
> - Work through tasks in strict order — each task depends on the previous one
> - Complete **one task per Claude Code session**, then commit before starting the next
> - At the start of each session, tell Claude Code: `Read TASKS.md and SPEC.md. I am starting Task [N].`
> - Mark tasks done by changing `[ ]` to `[x]`
> - Spec reference = `SPEC.md` (place `fabric-ai-metadata-spec-v1.1.md` in your project root as `SPEC.md`)

---

## Rules for Every Session

```
1. Read TASKS.md and SPEC.md before writing any code
2. Implement only the current task — do not touch files from other tasks
3. Stop and ask if a spec detail is ambiguous — do not invent behavior
4. After finishing, list every file created or modified
5. Do not proceed to the next task
```

---

## Phase 1 — Foundation

---

### Task 01 — Project Scaffolding

**Session prompt:**
```
Read TASKS.md and SPEC.md. I am starting Task 01.
```

**Spec sections:** 8 (Project Structure), 9 (Dependencies)

**What to build:**
- `pyproject.toml` — exact content from SPEC.md Section 9, using `requires-python = ">=3.10"`
- `.fabric-ai-meta.toml.example` — exact content from SPEC.md Appendix B
- `README.md` — one-paragraph placeholder, project name and purpose only
- `LICENSE` — MIT license placeholder
- Full directory tree from SPEC.md Section 8:
  - `src/fabric_ai_meta/` with all sub-packages
  - `tests/` with `conftest.py` placeholder
  - `docs/` with three placeholder `.md` files
- Every `__init__.py` must contain:
  - Module docstring describing the module's responsibility (one sentence)
  - No imports yet

**Do not:**
- Write any logic
- Import anything between modules
- Create fixture files (that is Task 03)

**Done when:**
- `pip install -e ".[dev]"` completes without error
- `fabric-ai-meta --help` prints the click help stub (even if it says "not implemented")
- All directories from SPEC.md Section 8 exist

**Commit message:** `task-01: project scaffolding and pyproject.toml`

---

### Task 02 — Data Models

**Session prompt:**
```
Read TASKS.md and SPEC.md. I am starting Task 02.
Files from Task 01 are in place. Do not modify any file except src/fabric_ai_meta/models/metadata.py.
```

**Spec sections:** 5.1 (Internal Metadata Schema)

**What to build:**

File: `src/fabric_ai_meta/models/metadata.py`

- All enums: `TableType`, `MeasureCategory`, `ColumnRole` — exact members, exact string values from SPEC.md
- All dataclasses: `ColumnMeta`, `MeasureMeta`, `RelationshipMeta`, `HierarchyMeta`, `TableMeta`, `SemanticModelMeta`
- Add `to_dict()` method to each dataclass that returns a JSON-serializable dict (use `dataclasses.asdict()` as the base, but convert enum values to their `.value` strings)
- Add a module-level `from_dict()` factory function for `SemanticModelMeta` that can reconstruct the full object tree from a plain dict (needed by mock extractor in Task 03)

**Important correctness notes from the spec:**
- `SEMI_ADDITIVE` = balance-type measures only (inventory, account balances). Do NOT include DISTINCTCOUNT here
- `NON_ADDITIVE` = ratios, percentages, averages, DISTINCTCOUNT
- Add inline comments in the enum matching the SPEC.md comments exactly

**Do not:**
- Create any other files
- Import from other fabric_ai_meta modules

**Done when:**
- `python -c "from fabric_ai_meta.models.metadata import SemanticModelMeta; print('ok')"` succeeds
- `pytest tests/ -x -q` passes (no tests yet, just no import errors)
- `to_dict()` on a fully-populated `SemanticModelMeta` produces valid JSON via `json.dumps()`

**Commit message:** `task-02: data models and serialization`

---

### Task 03 — Mock Extractor + Test Fixtures

**Session prompt:**
```
Read TASKS.md and SPEC.md. I am starting Task 03.
Tasks 01 and 02 are complete. Only create or modify files listed in this task.
```

**Spec sections:** 5.2 (AI-Ready Export Schema — for fixture shape reference), 6.1 (Extractor — interface contract)

**What to build:**

File: `src/fabric_ai_meta/extractor/base.py`
- Abstract base class `BaseExtractor` with one abstract method:
  ```python
  def extract(self, model_name: str, workspace: str) -> SemanticModelMeta:
      ...
  ```

File: `src/fabric_ai_meta/extractor/mock.py`
- `MockExtractor(BaseExtractor)` — loads a `SemanticModelMeta` from a JSON fixture file
- Constructor takes `fixture_path: str`
- `extract()` reads the JSON file and calls `SemanticModelMeta.from_dict()`

File: `tests/fixtures/adventure_works.json`
- A realistic Adventure Works fixture with:
  - 4 tables: `FactInternetSales` (fact), `DimProduct` (dimension), `DimCustomer` (dimension), `DimDate` (dimension)
  - `FactInternetSales` has at minimum: `SalesOrderNumber` (key), `ProductKey` (foreign_key), `CustomerKey` (foreign_key), `OrderDateKey` (foreign_key), `SalesAmount` (measure_column), `OrderQuantity` (measure_column)
  - 3 measures on `FactInternetSales`: `[Internet Total Sales]` (additive), `[Internet Sales Amount YTD]` (time_intelligence), `[Internet Distinct Count Customers]` (non_additive)
  - 3 relationships (FactInternetSales → each dimension)
  - Mix of: tables with descriptions, tables without; measures with descriptions, measures without
  - `ai_readiness_score: null` (not yet scored)
  - `extraction_method: "mock"`

File: `tests/fixtures/contoso_sales.json`
- A second fixture for the Contoso Sales model referenced in SPEC.md Section 5.2
- Minimum: 3 tables, 5 measures, 2 relationships — enough to test multi-table scenarios

File: `tests/conftest.py`
- Pytest fixtures:
  ```python
  @pytest.fixture
  def adventure_works_model() -> SemanticModelMeta:
      ...  # loads from fixture file via MockExtractor

  @pytest.fixture
  def contoso_model() -> SemanticModelMeta:
      ...
  ```

File: `tests/test_extractor.py`
- Test that `MockExtractor.extract()` returns a valid `SemanticModelMeta`
- Test that table count matches fixture
- Test that `to_dict()` round-trips cleanly through `json.dumps()` → `json.loads()` → `from_dict()`

**Done when:**
- `pytest tests/test_extractor.py -v` passes all tests
- The Adventure Works fixture loads without errors and has the correct structure

**Commit message:** `task-03: mock extractor and test fixtures`

---

### Task 04 — Analyzer: Heuristic Classifier

**Session prompt:**
```
Read TASKS.md and SPEC.md. I am starting Task 04.
Tasks 01–03 are complete. Only create or modify files listed in this task.
```

**Spec sections:** 6.2 (Analyzer Module — full section)

**What to build:**

File: `src/fabric_ai_meta/analyzer/classifier.py`
- `classify_table_heuristic(table: TableMeta, relationships: list[RelationshipMeta]) -> TableType`
  - Implement all rules from SPEC.md Section 6.2 heuristic block (name patterns, relationship direction, column composition)
  - Returns `TableType.UNKNOWN` when no rule matches confidently
- `classify_column_role(column: ColumnMeta, table: TableMeta, relationships: list[RelationshipMeta]) -> ColumnRole`
  - FK detection: column name matches a relationship's `from_column`
  - Key detection: column name ends with `Key`, `ID`, `Id` and is not a FK to another table
  - Date detection: `data_type == "datetime"` or column name is `Date`, `DateKey`
  - Sort detection: column name contains `Sort` or `Order` and is not numeric
- `classify_measure_heuristic(measure: MeasureMeta) -> MeasureCategory`
  - Scan DAX for time intelligence functions → `TIME_INTELLIGENCE`
  - Scan for `DISTINCTCOUNT` → `NON_ADDITIVE`
  - Scan for `DIVIDE`, `AVERAGE`, `AVERAGEX` → `NON_ADDITIVE`
  - Scan for `LASTDATE`, `OPENINGBALANCEMONTH`, etc. → `SEMI_ADDITIVE`
  - Scan for `SUM`, `SUMX`, `COUNT`, `COUNTROWS` at top level → `ADDITIVE`
  - Reference to another measure in the expression → `CALCULATED`
  - Fallback → `UNKNOWN`

File: `src/fabric_ai_meta/analyzer/scorer.py`
- `score_model(model: SemanticModelMeta) -> tuple[float, dict]`
  - Applies SCORING_WEIGHTS from SPEC.md Section 6.2 exactly
  - Returns `(overall_score, breakdown_dict)`
  - Weights must sum to 1.0 — add an assertion at module load time
  - `description_coverage`: (tables with description + columns with description) / (total tables + total columns)
  - `measure_documentation`: measures with description / total measures
  - `relationship_completeness`: FK columns that have a matching relationship / total FK columns
  - `naming_consistency`: columns/measures with no abbreviations or inconsistent casing / total (simple heuristic: penalize names containing `_`, all-caps segments, or names < 3 chars)
  - `sample_values_available`: columns with `len(sample_values) > 0` and role in (ATTRIBUTE, MEASURE_COLUMN) / total such columns
  - `business_rules_documented`: measures with `len(implicit_filters) > 0` and category in (FILTER_CONTEXT, TIME_INTELLIGENCE) / total such measures (0 = no such measures → score 1.0)

File: `tests/test_analyzer.py`
- Test table classification for each fixture table (verify FactInternetSales → FACT, DimProduct → DIMENSION)
- Test measure classification (verify `[Internet Total Sales]` → ADDITIVE, `[Internet Sales Amount YTD]` → TIME_INTELLIGENCE, `[Internet Distinct Count Customers]` → NON_ADDITIVE)
- Test scorer returns a float between 0.0 and 1.0 and breakdown keys match `SCORING_WEIGHTS`

**Do not:**
- Make any LLM calls
- Modify any file from Tasks 01–03

**Done when:**
- `pytest tests/test_analyzer.py -v` passes all tests
- Classification accuracy on Adventure Works fixture matches expected types

**Commit message:** `task-04: heuristic classifier and AI readiness scorer`

---

### Task 05 — DAX Dependency Parser

**Session prompt:**
```
Read TASKS.md and SPEC.md. I am starting Task 05.
Tasks 01–04 are complete. Only create or modify files listed in this task.
```

**Spec sections:** 6.2 (DAX Dependency Parser subsection)

**What to build:**

File: `src/fabric_ai_meta/analyzer/dax_parser.py`
- `parse_measure_dependencies(measure_name: str, dax: str, all_measures: dict[str, str]) -> dict`
  - Returns:
    ```python
    {
        "measure_name": str,
        "depends_on_measures": list[str],   # [measure] references found in DAX
        "depends_on_columns": list[str],    # Table[Column] references found in DAX
        "time_intelligence_functions": list[str],  # any TI functions used
        "filter_modifications": list[str],  # CALCULATE, ALL, REMOVEFILTERS, KEEPFILTERS
        "implicit_business_rules": list[str],  # hardcoded values in filters e.g. [Status] = "Active"
    }
    ```
  - Implement with regex patterns:
    - Measure refs: `\[([^\]]+)\]` not preceded by a table name (no `'Table'[col]` or `Table[col]` prefix)
    - Column refs: `'?(\w[\w\s]*)'?\[([^\]]+)\]` — captures `Table[Column]` and `'Table Name'[Column]`
    - TI functions: match against the `TIME_INTEL_FUNCTIONS` set from classifier.py
    - Filter modifications: match `CALCULATE`, `ALL\b`, `REMOVEFILTERS`, `KEEPFILTERS`, `ALLEXCEPT`
    - Business rules: string literals inside filter arguments — `= "..."` or `= \d+` patterns

- `build_dependency_graph(measures: list[MeasureMeta]) -> dict`
  - Calls `parse_measure_dependencies` for each measure
  - Returns a dict keyed by measure name, values are the dependency dicts
  - Detects circular dependencies — log a warning, do not raise

File: `tests/test_analyzer.py` (extend, do not replace)
- Add tests for `parse_measure_dependencies` against the Adventure Works measures
- Verify `[Internet Sales Amount YTD]` depends on `[Internet Total Sales]`
- Verify column refs are extracted correctly

**Done when:**
- All existing `test_analyzer.py` tests still pass
- New DAX parser tests pass

**Commit message:** `task-05: DAX dependency parser`

---

### Task 06 — AI-Ready JSON Schema Generator

**Session prompt:**
```
Read TASKS.md and SPEC.md. I am starting Task 06.
Tasks 01–05 are complete. Only create or modify files listed in this task.
```

**Spec sections:** 5.2 (AI-Ready Export Schema), 6.3.1 (Schema Generator)

**What to build:**

File: `src/fabric_ai_meta/generator/schema.py`
- `generate_ai_ready_schema(model: SemanticModelMeta) -> dict`
  - Produces the exact JSON structure from SPEC.md Section 5.2
  - Top-level keys: `$schema`, `version`, `model`, `tables`, `measures`, `query_guidance`, `scoring`
  - `$schema` value: `"https://fabric-ai-meta.dev/schema/v1.json"` (placeholder — see SPEC.md note)
  - `tables`: include only non-hidden tables; for each table include columns (non-hidden), outbound relationships
  - `measures`: flatten all measures from all tables; include non-hidden measures only
  - `query_guidance.valid_filter_paths`: generate from relationship graph (e.g., "To filter {fact} by {attribute}: {fact} → {dim} → {dim}[{col}]")
  - `query_guidance.common_pitfalls`: generate entries for each non-additive measure (warn agents not to SUM it), and for each time-intelligence measure (warn that a date filter is required)
  - `query_guidance.recommended_aggregations`: generate one SUMMARIZECOLUMNS example per fact table using its top additive measure and first dimension
  - `scoring`: pull from `model.ai_readiness_score` and `model.scoring_breakdown`; if not yet scored, call `score_model()` first

- `write_schema_to_file(model: SemanticModelMeta, output_path: str) -> str`
  - Calls `generate_ai_ready_schema()`, writes to JSON file, returns the file path

File: `tests/test_generator.py`
- Test that `generate_ai_ready_schema()` on the Adventure Works fixture produces valid JSON
- Test that top-level keys match the spec
- Test that hidden tables/columns are excluded
- Test that all measure names in output match the source model

**Done when:**
- `pytest tests/test_generator.py -v` passes
- Output JSON is parseable and matches spec structure

**Commit message:** `task-06: AI-ready JSON schema generator`

---

### Task 07 — Framework Export Generators

**Session prompt:**
```
Read TASKS.md and SPEC.md. I am starting Task 07.
Tasks 01–06 are complete. Only create or modify files listed in this task.
```

**Spec sections:** 6.3.3 (Framework Export Generators)

**What to build:**

File: `src/fabric_ai_meta/generator/export_langchain.py`
- `to_langchain_tool_definition(model: SemanticModelMeta) -> dict`
  - Implement exactly as shown in SPEC.md Section 6.3.3
  - Include the `sanitize()` helper: replace spaces and special chars with underscores, lowercase
  - Include stubs for `generate_context_prompt()`, `extract_filter_paths()`, `extract_pitfalls()` — these are implemented fully in Task 10 (LLM); for now return empty string / empty list
  - The `metadata` field is non-standard — add the docstring warning from the spec

File: `src/fabric_ai_meta/generator/export_openai.py`
- `to_openai_function(model: SemanticModelMeta) -> dict`
  - OpenAI function calling format:
    ```json
    {
      "type": "function",
      "function": {
        "name": "query_{model_name}",
        "description": "...",
        "parameters": {
          "type": "object",
          "properties": { ... },
          "required": ["question"]
        }
      }
    }
    ```
  - Parameters: `question` (string, required), `tables` (array of enum, optional), `measures` (array of enum, optional)
  - Description: combine model summary + key pitfalls inline (since OpenAI has no metadata extension)

File: `src/fabric_ai_meta/generator/export_semantic_kernel.py`
- `to_semantic_kernel_plugin(model: SemanticModelMeta) -> dict`
  - Semantic Kernel plugin manifest format:
    ```json
    {
      "schema_version": "v1",
      "name": "{model_name}",
      "description": "...",
      "functions": [
        {
          "name": "query",
          "description": "...",
          "parameters": [ ... ]
        }
      ]
    }
    ```
  - One function named `query` with parameters: `question` (string), `tables` (string, comma-separated), `measures` (string, comma-separated)

File: `tests/test_generator.py` (extend)
- Test LangChain export: valid dict, has `name`, `description`, `parameters`, `metadata`
- Test OpenAI export: valid dict, `type == "function"`, parameters has `required: ["question"]`
- Test Semantic Kernel export: valid dict, has `schema_version`, `functions` list

**Done when:**
- All generator tests pass
- All three exports produce valid JSON

**Commit message:** `task-07: framework export generators (LangChain, OpenAI, Semantic Kernel)`

---

### Task 08 — LLM Integration (Claude API Client)

**Session prompt:**
```
Read TASKS.md and SPEC.md. I am starting Task 08.
Tasks 01–07 are complete. Only create or modify files listed in this task.
```

**Spec sections:** 6.4 (LLM Integration Module), Appendix B (config: [llm] section)

**What to build:**

File: `src/fabric_ai_meta/llm/prompts.py`
- `TABLE_CLASSIFICATION_PROMPT` — template string for classifying an ambiguous table
  - Inputs: table name, column list (name + type), relationship summary, possible types
  - Output instruction: return JSON `{"table_type": "fact|dimension|bridge|configuration|aggregate|staging", "confidence": 0.0-1.0, "reasoning": "..."}`
- `GRAIN_DETECTION_PROMPT` — template for detecting fact table grain
  - Inputs: table name, columns, row count estimate, sample values
  - Output instruction: return JSON `{"grain": "natural language grain statement", "confidence": 0.0-1.0}`
- `DESCRIPTION_GENERATION_PROMPT` — template for generating missing descriptions
  - Inputs: object type (table/column/measure), object name, parent table name, data type or DAX, existing sibling descriptions for context
  - Output instruction: return JSON `{"description": "concise business description, max 150 chars"}`
- `AI_INSTRUCTIONS_PROMPT` — exact template from SPEC.md Section 6.3.2

File: `src/fabric_ai_meta/llm/cache.py`
- `LLMCache` class
  - Constructor: `def __init__(self, cache_dir: str = ".fabric-ai-meta-cache")`
  - `get(key: str) -> str | None` — returns cached response or None
  - `set(key, response: str) -> None` — stores response
  - `make_key(prompt: str) -> str` — SHA-256 hash of the prompt string
  - Backend: JSON files in `cache_dir/`, one file per key (filename = key)
  - No TTL for v1 — cache is valid until manually cleared

File: `src/fabric_ai_meta/llm/client.py`
- `FabricLLMClient` class
  - Constructor:
    ```python
    def __init__(self, api_key: str | None = None, cache_enabled: bool = True,
                 cache_dir: str = ".fabric-ai-meta-cache",
                 max_cost_usd: float | None = None):
    ```
    - `api_key` defaults to `os.environ["ANTHROPIC_API_KEY"]`
    - Creates `anthropic.Anthropic(api_key=api_key)` client
    - Creates `LLMCache` if `cache_enabled`
  - `call(prompt: str, max_tokens: int = 1000, system: str | None = None) -> str`
    - Checks cache first — returns cached response if hit
    - Makes API call: model `claude-sonnet-4-6`, passes prompt as user message
    - Stores response in cache
    - Tracks cumulative token usage; raises `CostLimitExceededError` if `max_cost_usd` is set and exceeded
    - Token counting: use `response.usage.input_tokens` and `response.usage.output_tokens` from the Anthropic response object
  - `classify_table(table: TableMeta, relationships: list[RelationshipMeta]) -> tuple[TableType, float]`
    - Formats `TABLE_CLASSIFICATION_PROMPT`, calls `self.call()`, parses JSON response
    - Returns `(TableType, confidence_float)`
  - `detect_grain(table: TableMeta) -> tuple[str, float]`
    - Formats `GRAIN_DETECTION_PROMPT`, calls `self.call()`, parses JSON response
  - `generate_description(obj_type: str, name: str, context: dict) -> str`
    - Formats `DESCRIPTION_GENERATION_PROMPT`, calls `self.call()`, parses JSON response

- `CostLimitExceededError(Exception)` — raised when cumulative cost exceeds `max_cost_usd`

File: `tests/test_llm.py`
- Test cache: set + get round trip works
- Test cache: cache miss returns None
- Test `make_key`: same prompt always produces same key, different prompts produce different keys
- DO NOT make real API calls in tests — mock `anthropic.Anthropic` using `unittest.mock.patch`

**Done when:**
- `pytest tests/test_llm.py -v` passes (with mocked API)
- `FabricLLMClient` can be instantiated (will fail gracefully if no API key set)

**Commit message:** `task-08: LLM client, prompt templates, and caching`

---

### Task 09 — Semantic Link Extractor

> **Pre-condition:** Resolve SPEC.md Open Question #1 before this task. If `sempy.fabric` only works inside Fabric notebook runtime, add that constraint to the session prompt.

**Session prompt:**
```
Read TASKS.md and SPEC.md. I am starting Task 09.
Tasks 01–08 are complete. Only create or modify files listed in this task.
[If sempy only works in notebooks, add:] Note: sempy.fabric only functions inside a Fabric notebook runtime. The CLI must detect the environment and raise a clear FabricEnvironmentError when run locally.
```

**Spec sections:** 6.1 (Extractor Module — full section), 4.3 (Authentication)

**What to build:**

File: `src/fabric_ai_meta/auth/entra.py`
- `get_credential(method: str = "interactive", tenant_id: str | None = None, client_id: str | None = None, client_secret: str | None = None)`
  - `"interactive"` → `azure.identity.InteractiveBrowserCredential()`
  - `"service_principal"` → `azure.identity.ClientSecretCredential(tenant_id, client_id, client_secret)`
  - `"notebook"` → returns `None` (sempy uses ambient credential automatically)
- `detect_notebook_environment() -> bool`
  - Returns True if running inside a Fabric/Jupyter notebook (check for `FABRIC_NOTEBOOK_ID` env var or `ipykernel` in sys.modules)

File: `src/fabric_ai_meta/extractor/semantic_link.py`
- `SemanticLinkExtractor(BaseExtractor)`
  - Constructor: `def __init__(self, workspace: str, credential=None)`
  - `extract(self, model_name: str, workspace: str | None = None) -> SemanticModelMeta`
    - Calls `fabric.list_tables()`, `fabric.list_measures()`, `fabric.list_relationships()`
    - Iterates tables to call `fabric.list_columns()` per table
    - Calls `_extract_sample_values()` for categorical columns
    - Normalizes all results to internal dataclasses
    - Sets `extraction_method = "semantic_link"` and `extraction_timestamp` (ISO 8601 UTC)
  - `_extract_sample_values(self, model_name: str, table: str, column: str) -> list[str]`
    - Uses `evaluate_dax()` with `TOPN(10, DISTINCT('table'[column]))` pattern from SPEC.md Section 6.1
    - Returns empty list on any error (never raise — sample values are best-effort)
  - Error handling per SPEC.md Section 6.1:
    - Wrap in try/except for `PermissionError`, `ConnectionError`, `TimeoutError`
    - Exponential backoff: max 3 retries, starting at 1s, factor 2x
    - On persistent failure: raise with a clear message including which model/table failed

File: `src/fabric_ai_meta/config.py`
- `Config` dataclass mirroring all sections from SPEC.md Appendix B
- `load_config(path: str = ".fabric-ai-meta.toml") -> Config`
  - Reads TOML file; falls back to defaults if file not found
  - Use `tomllib` (Python 3.11+ stdlib) or `tomli` as a backport for 3.10

**Done when:**
- Module imports without error: `from fabric_ai_meta.extractor.semantic_link import SemanticLinkExtractor`
- Auth module imports without error: `from fabric_ai_meta.auth.entra import get_credential`
- Config loads from example file: `load_config(".fabric-ai-meta.toml.example")`
- (Live Fabric test is manual — document in README how to test against a real workspace)

**Commit message:** `task-09: Semantic Link extractor and auth`

---

### Task 10 — CLI Implementation

**Session prompt:**
```
Read TASKS.md and SPEC.md. I am starting Task 10.
Tasks 01–09 are complete. Only create or modify files listed in this task.
```

**Spec sections:** 7.1 (CLI Command Structure), 7.2 (Output Structure)

**What to build:**

File: `src/fabric_ai_meta/cli.py` (replace the stub from Task 01)

Implement all commands from SPEC.md Section 7.1 using `click`:

```
fabric-ai-meta
├── auth
│   ├── login
│   ├── status
│   └── logout
├── analyze     [model_name] --workspace --output --format --include-sample-values --llm-enrich
├── scan        --workspace --output --format
├── export
│   ├── langchain   [model_name] --workspace
│   ├── openai      [model_name] --workspace
│   ├── semantic-kernel [model_name] --workspace
│   └── prep-for-ai [model_name] --workspace
├── score
│   [model_name] --workspace
│   --all --workspace
└── governance  --workspace --report
```

For each command:
- Load config from `.fabric-ai-meta.toml` (use `load_config()`)
- Print `rich` panel with command name and parameters at start
- Show `rich.progress` spinner during extraction and analysis
- Write output files to the structure from SPEC.md Section 7.2
- Print a `rich` table summary at the end showing what was written

**`analyze` command full flow:**
1. Load config
2. Create `SemanticLinkExtractor` (or `MockExtractor` if `--mock` flag set)
3. Call `extractor.extract(model_name, workspace)`
4. Run heuristic classification on all tables and measures (update the model in place)
5. Run scorer → update `model.ai_readiness_score` and `model.scoring_breakdown`
6. If `--llm-enrich`: call `FabricLLMClient` for ambiguous tables (confidence < 0.7) and grain detection
7. Generate all outputs to `{output}/{model-slug}/`
8. Print summary table

**`score` command:**
- If single model: run extraction + scoring, print `rich.table` breakdown
- If `--all`: scan workspace, run scoring on each model, print sorted ranking

File: `tests/test_cli.py`
- Use `click.testing.CliRunner` for all tests
- Test `fabric-ai-meta --help` exits 0
- Test `fabric-ai-meta analyze --help` exits 0
- Test `fabric-ai-meta analyze "Adventure Works" --workspace "test" --mock` runs end-to-end using `MockExtractor` (add a `--mock` flag to the analyze command for testing)

**Done when:**
- `fabric-ai-meta --help` shows all top-level commands
- `pytest tests/test_cli.py -v` passes
- `fabric-ai-meta analyze "Adventure Works" --workspace "test" --mock` produces output files

**Commit message:** `task-10: CLI implementation`

---

## Phase 2 — Prep for AI Automation

---

### Task 11 — Prep for AI Generator

> **Pre-condition:** Resolve SPEC.md Open Question #4 before this task. If no programmatic API exists to apply Prep for AI configs, adjust the output to be a "manual application guide" rather than an automated pipeline.

**Session prompt:**
```
Read TASKS.md and SPEC.md. I am starting Task 11.
Tasks 01–10 are complete. Only create or modify files listed in this task.
```

**Spec sections:** 6.3.2 (Prep for AI Config Generator)

**What to build:**

File: `src/fabric_ai_meta/generator/prep_for_ai.py`
- `PrepForAIConfig` dataclass — exact fields from SPEC.md Section 6.3.2
- `generate_prep_for_ai(model: SemanticModelMeta, llm_client: FabricLLMClient) -> PrepForAIConfig`
  - `included_tables`: all non-hidden, non-staging tables
  - `excluded_columns`: hidden columns, sort-by columns, internal keys with no business meaning
  - `ai_instructions`: call `llm_client.call()` with `AI_INSTRUCTIONS_PROMPT` from prompts.py (max 2000 chars output)
  - `verified_answers`: for each time_intelligence measure, generate `{"question": "What is {measure_name} for {current period}?", "dax": "{measure DAX}", "description": "..."}`
  - `generated_descriptions`: for each table/column with no description, call `llm_client.generate_description()`

File: `tests/test_generator.py` (extend)
- Test `generate_prep_for_ai` with mocked `FabricLLMClient`
- Test that hidden columns appear in `excluded_columns`
- Test that `ai_instructions` is populated (mocked LLM returns a string)

**Done when:**
- `pytest tests/test_generator.py -v` passes
- `fabric-ai-meta export prep-for-ai` produces a valid JSON file

**Commit message:** `task-11: Prep for AI generator`

---

### Task 12 — Bulk Workspace Scan

**Session prompt:**
```
Read TASKS.md and SPEC.md. I am starting Task 12.
Tasks 01–11 are complete. Only create or modify files listed in this task.
```

**Spec sections:** 7.1 (`scan` command), 10 (BULK-01 acceptance criteria)

**What to build:**

Extend `SemanticLinkExtractor`:
- `list_models(self, workspace: str) -> list[str]`
  - Calls `fabric.list_datasets(workspace=workspace)` and returns model names

Extend `cli.py` — `scan` command:
- Calls `extractor.list_models()` to get all model names
- Runs `analyze` flow for each model
- Writes per-model output to `{output}/{model-slug}/`
- Writes `{output}/workspace-summary.json` with all model names, scores, and timestamps
- Shows `rich.progress` bar with per-model status

File: `tests/test_extractor.py` (extend)
- Test `list_models` with mocked `fabric.list_datasets`

**Done when:**
- `fabric-ai-meta scan --workspace "Production Analytics"` runs end-to-end
- `workspace-summary.json` is produced
- BULK-01 acceptance criterion is met

**Commit message:** `task-12: bulk workspace scan`

---

## Phase 3 — Governance

---

### Task 13 — Cross-Model Governance Analysis

**Session prompt:**
```
Read TASKS.md and SPEC.md. I am starting Task 13.
Tasks 01–12 are complete. Only create or modify files listed in this task.
```

**Spec sections:** 3 (Phase 3 scope), 10 (GOV-01 through GOV-03 acceptance criteria)

**What to build:**

File: `src/fabric_ai_meta/analyzer/governance.py`
- `find_naming_inconsistencies(models: list[SemanticModelMeta]) -> list[dict]`
  - Detect same concept named differently across models (e.g., `CustomerID` vs `Cust_ID` vs `customer_id`)
  - Heuristic: normalize names (lowercase, remove underscores/spaces) and group by normalized form
  - Return: `[{"normalized": "customerid", "variants": ["CustomerID", "Cust_ID"], "found_in": ["Model A", "Model B"]}]`
- `find_duplicate_measures(models: list[SemanticModelMeta]) -> list[dict]`
  - Detect measures with identical (or near-identical) DAX expressions across models
  - Exact match: same DAX string (normalized — strip whitespace)
  - Return: `[{"measure_name": "Total Revenue", "found_in": ["Model A", "Model B"], "dax_identical": True}]`
- `generate_governance_report(models: list[SemanticModelMeta]) -> dict`
  - Returns a dict with:
    - `summary`: model count, average readiness score, lowest-scoring model
    - `naming_issues`: output of `find_naming_inconsistencies`
    - `duplicate_measures`: output of `find_duplicate_measures`
    - `score_ranking`: models sorted by `ai_readiness_score` descending

File: `tests/test_analyzer.py` (extend)
- Test `find_naming_inconsistencies` with two fixtures that have a known naming divergence
- Test `find_duplicate_measures` with a synthetic duplicate

**Done when:**
- `fabric-ai-meta governance --workspace "..."` produces a governance report JSON
- GOV-01, GOV-02, GOV-03 acceptance criteria are met

**Commit message:** `task-13: cross-model governance analysis`

---

### Task 14 — Full Test Suite

**Session prompt:**
```
Read TASKS.md and SPEC.md. I am starting Task 14.
Tasks 01–13 are complete. Only modify test files and conftest.py.
```

**Spec sections:** 10 (Acceptance Criteria — all phases), 11 (Validation Strategy)

**What to build:**
- Review every acceptance criterion in SPEC.md Section 10 — write a test for each uncovered criterion
- `tests/test_integration.py` — end-to-end test using MockExtractor:
  1. Extract Adventure Works fixture
  2. Run heuristic classification
  3. Run scoring
  4. Generate AI-ready schema
  5. Generate all three framework exports
  6. Assert output files exist and are valid JSON
- Ensure `pytest tests/ -v` passes with 0 failures
- Ensure `pytest tests/ --tb=short -q` shows coverage of all critical paths

**Done when:**
- `pytest tests/ -v` — all tests pass, 0 failures
- Every Phase 1 acceptance criterion (AUTH-01 through LLM-02) has at least one test covering it (AUTH tests may be skipped/mocked)

**Commit message:** `task-14: full test suite`

---

## Completion Checklist

After all tasks are complete, verify:

- [ ] `pip install -e ".[dev]"` completes cleanly
- [ ] `fabric-ai-meta --help` shows all commands
- [ ] `pytest tests/ -q` — 0 failures
- [ ] `fabric-ai-meta analyze "Model" --workspace "ws" --mock` produces all output files
- [ ] Scoring weights in `scorer.py` sum to exactly 1.0 (assertion fires at import time)
- [ ] Model string `claude-sonnet-4-6` appears nowhere else — search codebase for any stale `claude-sonnet-4-20250514` references
- [ ] `pyadomd` is in `[project.optional-dependencies.xmla]` only — not in core dependencies
- [ ] `.fabric-ai-meta.toml.example` is present and loads without error
- [ ] `SPEC.md Open Questions` (Section 13) are all resolved or have documented decisions

---

## Quick Reference — Task Dependencies

```
01 Scaffolding
└── 02 Data Models
    └── 03 Mock Extractor + Fixtures
        ├── 04 Heuristic Classifier
        │   └── 05 DAX Parser
        │       └── 06 Schema Generator
        │           └── 07 Framework Exporters
        │               └── 08 LLM Client
        │                   ├── 09 Semantic Link Extractor
        │                   │   └── 10 CLI
        │                   │       ├── 11 Prep for AI Generator
        │                   │       │   └── 12 Bulk Scan
        │                   │       │       └── 13 Governance
        │                   │       │           └── 14 Full Tests
        │                   │       └── (feeds into 12, 13)
        │                   └── (feeds into 11)
        └── (used by all downstream tasks as test foundation)
```
