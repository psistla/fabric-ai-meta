# fabric-ai-meta — Claude Code Reference

> **What this file is:** Context document for Claude Code sessions. Read this at the start of every session before reading the task file.
> **Last updated:** Sprint 3 complete (April 4, 2026) — v1.0.0 released
> **Spec:** `fabric-ai-metadata-spec-v1.2.md` (the canonical source of truth for all design decisions)

---

## Project Summary

**fabric-ai-meta** is a Python CLI + library that extracts metadata from Microsoft Fabric semantic models and produces AI-ready outputs. It automates what Microsoft expects teams to do manually across 10–100+ models.

Two output categories:
1. **AI-ready schemas** — structured metadata for LangChain, OpenAI function calling, Semantic Kernel, AutoGen
2. **Prep for AI configs** — auto-generated settings users apply manually in the Fabric UI (no API exists)

Repository: `C:\claude-projects\fabric-ai-meta` (Windows)

---

## Architecture — Two-Mode Design

`sempy.fabric` requires the Microsoft Fabric notebook runtime. It does **not** work locally. This is confirmed, not an open question.

| Mode | Where | Extractor | Auth |
|------|-------|-----------|------|
| **Fabric mode** | Fabric notebook | `SemanticLinkExtractor` | Ambient credential (automatic) |
| **Local/CI mode** | Any machine | `MockExtractor` + fixture JSON | None needed |

**Detection at startup:**
- Env var `FABRIC_NOTEBOOK_ID` present OR `notebookutils` importable → Fabric mode
- Otherwise → local mode; extraction commands require `--mock` or raise `FabricEnvironmentError`

**Every extraction command supports `--mock`.** This includes `analyze`, `scan`, `export`, `score`, and `governance`.

---

## Current State

### Phase 1 MVP — COMPLETE (Tasks 01–10)
### Sprint 2 (Phase 2) — COMPLETE (Tasks S2-01 to S2-03)
### Sprint 3 (Phase 3) — COMPLETE (Tasks S3-01 to S3-02) — v1.0.0 tagged

All acceptance criteria met: AUTH-01 through LLM-02, PREP-01 through BULK-01, GOV-01 through GOV-03.

---

## Module Map

```
src/fabric_ai_meta/
├── __init__.py
├── cli.py                          # Click CLI — analyze, score, export, auth, governance, scan
├── config.py                       # Config dataclass + load_config() from TOML
│
├── auth/
│   └── entra.py                    # get_credential(), detect_notebook_environment()
│
├── extractor/
│   ├── base.py                     # BaseExtractor ABC — extract() + list_models() abstract methods
│   ├── mock.py                     # MockExtractor(fixture_path|fixture_dir) — single or multi-model
│   └── semantic_link.py            # SemanticLinkExtractor — Fabric-runtime-only
│
├── analyzer/
│   ├── classifier.py               # classify_table_heuristic(), classify_measure_heuristic(), classify_column_role()
│   ├── dax_parser.py               # parse_measure_dependencies(), build_dependency_graph()
│   ├── scorer.py                   # score_model() → (float, dict); weights sum to 1.0
│   └── governance.py               # generate_governance_report(), find_naming_inconsistencies(),
│                                   # find_duplicate_measures(), write_governance_report()
│
├── generator/
│   ├── schema.py                   # generate_ai_ready_schema(), write_schema_to_file()
│   ├── prep_for_ai.py              # PrepForAIConfig, generate_prep_for_ai()
│   ├── description_backfill.py     # DescriptionBackfill, backfill_descriptions(), apply_backfill()
│   ├── export_langchain.py         # to_langchain_tool_definition()
│   ├── export_openai.py            # to_openai_function()
│   └── export_semantic_kernel.py   # to_semantic_kernel_plugin()
│
├── llm/
│   ├── client.py                   # FabricLLMClient — call(), classify_table(), detect_grain(),
│   │                               # generate_description(), generate_descriptions_batch()
│   ├── prompts.py                  # TABLE_CLASSIFICATION_PROMPT, GRAIN_DETECTION_PROMPT,
│   │                               # DESCRIPTION_GENERATION_PROMPT, AI_INSTRUCTIONS_PROMPT,
│   │                               # BATCH_DESCRIPTION_PROMPT
│   └── cache.py                    # LLMCache — file-based SHA-256 keyed cache
│
└── models/
    └── metadata.py                 # All enums + dataclasses: SemanticModelMeta, TableMeta, etc.

tests/
├── conftest.py                     # adventure_works_model, contoso_model fixtures
├── fixtures/
│   ├── adventure_works.json        # 4 tables, 4 measures, 3 relationships
│   └── contoso_sales.json          # 3 tables, 5 measures, 2 relationships
├── test_extractor.py
├── test_analyzer.py
├── test_generator.py
├── test_llm.py
├── test_cli.py
├── test_prep_for_ai.py
├── test_governance.py              # GOV-01, GOV-02, GOV-03 coverage
└── test_integration.py             # Full pipeline + all acceptance criteria
```

---

## Key Constraints

1. **Model string:** `claude-sonnet-4-6` — no other string is valid
2. **pyadomd is Windows-only** — XMLA fallback requires ADOMD.NET; in optional deps only
3. **Scoring weights must sum to 1.0** — enforced by assertion at module import time
4. **Prep for AI has no public API** — output is `prep-for-ai-config.json` for manual UI application
5. **Calculation groups not extracted** — `list_measures()` returns standard measures only; out of scope for v1
6. **Sample values are opt-in** — `--include-sample-values` flag; never default due to CU cost
7. **LLM calls are cached** — SHA-256 hash of prompt → file-based cache; no TTL in v1
8. **`max_cost_per_run`** in config caps LLM spend; raises `CostLimitExceededError` when exceeded
9. **WEB-01 deferred** — Web UI dashboard is out of scope for v1; targeted for v1.1

---

## Data Model Quick Reference

Core enums (from `models/metadata.py`):
- `TableType`: FACT, DIMENSION, BRIDGE, CONFIGURATION, AGGREGATE, STAGING, UNKNOWN
- `MeasureCategory`: ADDITIVE, SEMI_ADDITIVE, NON_ADDITIVE, TIME_INTELLIGENCE, CALCULATED, FILTER_CONTEXT, UNKNOWN
- `ColumnRole`: KEY, FOREIGN_KEY, ATTRIBUTE, MEASURE_COLUMN, DATE, SORT, DISPLAY, UNKNOWN

Key dataclasses: `SemanticModelMeta` → `TableMeta` → `ColumnMeta` / `MeasureMeta` / `HierarchyMeta`; `RelationshipMeta` at model level.

Serialization: `to_dict()` on every dataclass; module-level `from_dict()` for `SemanticModelMeta`.

---

## CLI Command Tree

```
fabric-ai-meta
├── auth login | status | logout
├── analyze  [model] --workspace --output --format --include-sample-values --llm-enrich --mock
├── scan     --workspace --output --format --mock --llm-enrich
├── export   langchain|openai|semantic-kernel [model] --workspace --mock
│            prep-for-ai [model] --workspace --output --mock --llm-enrich
├── score    [model] --workspace --all --mock
└── governance --workspace --report --output --mock
```

---

## Output Schemas

| File | Schema URL |
|------|-----------|
| `ai-ready-schema.json` | `fabric-ai-meta.dev/schema/v1.json` |
| `prep-for-ai-config.json` | `fabric-ai-meta.dev/schema/prep-for-ai/v1.json` |
| `workspace-summary.json` | `fabric-ai-meta.dev/schema/workspace-summary/v1.json` |
| `governance-report.json` | `fabric-ai-meta.dev/schema/governance-report/v1.json` |

---

## Testing Patterns

- All tests run locally via `pytest tests/ -x -q`
- All Fabric-dependent code is mocked — no real `sempy.fabric` calls in tests
- LLM client is always mocked in tests — `unittest.mock.patch` on `anthropic.Anthropic`
- Fixtures loaded via `MockExtractor` or conftest.py `@pytest.fixture`
- CLI tests use `click.testing.CliRunner`
- Run full suite before every commit: `pytest tests/ -x -q`
- 210 tests, 0 failures as of v1.0.0

---

## Naming Conventions

- File names: `snake_case.py`
- Classes: `PascalCase` (e.g., `SemanticModelMeta`, `FabricLLMClient`)
- Functions: `snake_case` (e.g., `classify_table_heuristic`, `generate_ai_ready_schema`)
- CLI commands: `kebab-case` (e.g., `prep-for-ai`, `semantic-kernel`)
- Output file slugs: `kebab-case` from model name (e.g., `contoso-sales/`)
- JSON keys: `snake_case` in all output schemas

---

## Git Workflow

- Branch per sprint: `sprint-3/phase-3-governance`
- One commit per task with prescribed message
- Run full test suite before committing
- Push to remote after each task is committed
- Tags: `sprint-3-complete`, `v1.0.0`
