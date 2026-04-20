# fabric-ai-meta

![CI](https://github.com/psistla/fabric-ai-meta/actions/workflows/ci.yml/badge.svg)
![Version](https://img.shields.io/badge/version-1.0.0-238636?style=flat-square)
![Tests](https://img.shields.io/badge/tests-284%20passing-1a7f37?style=flat-square)
![Python](https://img.shields.io/badge/python-3.10%2B-0550ae?style=flat-square)
![License](https://img.shields.io/badge/license-MIT-6e40c9?style=flat-square)

Extract, classify, and export metadata from Microsoft Fabric semantic models for AI frameworks.

**Automates Prep for AI** across 100+ models. No manual configuration.
**Exports to LangChain, OpenAI, Semantic Kernel, AutoGen.** One extraction, every framework.
**Governs at workspace scale:** naming inconsistencies, duplicate measures, readiness scores.

### Install

```bash
pip install -e ".[dev]"
```

### Quickstart

```bash
fabric-ai-meta analyze "Adventure Works" --workspace "Production" --mock --output ./output
```

Produces `ai-ready-schema.json`, `readiness-score.json`, and `measure-dependency-graph.json` in `./output/adventure-works/`.

<p align="center">
<a href="#the-problem">The Problem</a> · <a href="#who-this-helps">Who This Helps</a> · <a href="#architecture">Architecture</a> · <a href="#usage">Usage</a> · <a href="#output-files">Output Files</a> · <a href="#llm-enrichment">LLM Enrichment</a> · <a href="#library-api">Library API</a> · <a href="#development">Development</a>
</p>

---

<details>
<summary><strong>The Problem:</strong> why this exists</summary>

<br>

Microsoft Fabric has invested heavily in AI features for semantic models: Prep for AI, Copilot-generated descriptions, Data Agents, and the emerging Fabric IQ Ontology. These are powerful, but they share three limitations:

**1. They don't scale.** Prep for AI requires manual configuration (selecting tables, writing AI Instructions, defining Verified Answers), one model at a time. An enterprise with 50 semantic models faces hundreds of hours of repetitive work. There is no bulk API.

**2. They don't leave Fabric.** Building a LangChain agent or an OpenAI function-calling pipeline against Fabric data? Microsoft offers no export path. Your AI application starts blind: no table types, no measure semantics, no relationship graph.

**3. They don't govern across models.** Copilot can describe a single measure, but it can't tell you that `Total Sales` in Model A and `Sum of Sales` in Model B are the same calculation with different names.

| Gap | What fabric-ai-meta does |
|-----|--------------------------|
| Manual Prep for AI | Auto-generates `prep-for-ai-config.json`: table selections, AI Instructions, Verified Answers, description backfill |
| Manual description writeback | `apply-descriptions` writes generated table and column descriptions back through XMLA / TOM |
| No external AI export | Produces framework-native schemas for LangChain, OpenAI, Semantic Kernel, and AutoGen |
| No cross-model governance | Detects naming inconsistencies, duplicate DAX, ranks models by readiness, outputs governance report |

This is not a replacement for Microsoft's tools. It is an **automation layer on top of them** and a **bridge to the external AI ecosystem**.

</details>

<details>
<summary><strong>Who This Helps:</strong> three practitioner profiles</summary>

<br>

**Fabric Architects / Senior BI Developers.** You manage 10-100+ semantic models. You need Prep for AI configured, descriptions filled in, naming standards enforced, at scale, not one model at a time. fabric-ai-meta gives you bulk workspace scan, auto-generated Prep for AI configs, LLM-powered description backfill, and a governance report across your entire estate.

**AI/ML Engineers Building on Fabric Data.** You're building agents or RAG pipelines that query semantic models. You need structured metadata in your framework's native format. You don't have deep DAX expertise. fabric-ai-meta gives you one-command export to LangChain, OpenAI, Semantic Kernel, or AutoGen, plus an AI-ready schema with query guidance, pitfalls, and measure dependency graphs.

**Data Governance Teams.** You need visibility into documentation completeness, naming consistency, and model quality across the estate. fabric-ai-meta gives you a governance scorecard, automated naming violation detection, and AI readiness scores broken down by description coverage, naming consistency, and relationship completeness.

</details>

<details>
<summary><strong>Philosophy:</strong> five principles</summary>

<br>

1. **Extract everything.** Tables, columns, measures, DAX, relationships, hierarchies, descriptions, formatting rules, hidden-object flags.
2. **Classify automatically.** Every table gets a type (fact, dimension, bridge). Every measure gets a category (additive, semi-additive, time intelligence). Heuristics first; LLM refines.
3. **Score honestly.** AI Readiness Score (0.0-1.0) broken down by description coverage, naming consistency, relationship completeness, and business rule documentation. No vanity metrics.
4. **Export universally.** One extraction produces LangChain, OpenAI, Semantic Kernel, AutoGen, and custom pipeline outputs.
5. **Govern at scale.** Naming inconsistencies, duplicate measures, documentation gaps across an entire workspace in a single command.

</details>

---

## Architecture

`sempy.fabric` requires the Microsoft Fabric notebook runtime and does not work locally.
The tool operates in two modes detected automatically at startup:

```mermaid
flowchart TD
    A([CLI command]) --> B{Environment?}
    B -->|FABRIC_NOTEBOOK_ID set\nor notebookutils importable| C[Fabric Mode]
    B -->|Local machine| D{--mock flag?}
    D -->|Yes| E[Local/CI Mode]
    D -->|No| F[FabricEnvironmentError]

    C --> G[SemanticLinkExtractor\nAmbient credential]
    E --> H[MockExtractor\nFixture JSON files]

    G --> I[Core Engine]
    H --> I

    I --> J[Analyzer\nClassify · Score · Governance]
    J --> K[Generator\nSchemas · Exports · Reports]
```

| Mode | Where it runs | Extractor | Auth |
|------|--------------|-----------|------|
| **Fabric mode** | Fabric notebook | `SemanticLinkExtractor` | Ambient (automatic) |
| **Local/CI mode** | Any machine | `MockExtractor` + fixture JSON | None needed |

> **Every command supports `--mock`:** `analyze`, `scan`, `export`, `score`, and `governance` all work locally without a Fabric connection.

---

## Usage

<details>
<summary><strong>analyze</strong>: extract, classify, score, and export a single model</summary>

```bash
# Local dev with mock fixtures
fabric-ai-meta analyze "Adventure Works" --workspace "Production" --mock

# With LLM enrichment (generates missing descriptions)
fabric-ai-meta analyze "Adventure Works" --workspace "Production" --mock --llm-enrich

# Specify output directory
fabric-ai-meta analyze "Adventure Works" --workspace "Production" --mock --output ./output
```
</details>

<details>
<summary><strong>scan</strong>: bulk scan all models in a workspace</summary>

```bash
fabric-ai-meta scan --workspace "Production" --mock --output ./output
```

Produces per-model output directories and a `workspace-summary.json` with score ranking.
</details>

<details>
<summary><strong>export prep-for-ai</strong>: generate Prep for AI config</summary>

```bash
# Rule-based (no LLM)
fabric-ai-meta export prep-for-ai "Adventure Works" --workspace "Production" --mock

# With LLM-generated AI instructions
fabric-ai-meta export prep-for-ai "Adventure Works" --workspace "Production" --mock --llm-enrich
```

Output is a `prep-for-ai-config.json` you apply manually in Power BI Desktop or Fabric Service.
</details>

<details>
<summary><strong>apply-descriptions</strong>: write generated descriptions back to a model</summary>

```bash
# Preview the writeback locally without contacting Fabric
fabric-ai-meta apply-descriptions ./output/adventure-works/prep-for-ai-config.json \
  --workspace "Production" --mock

# Inside a Fabric notebook, dry-run against the live model (default)
fabric-ai-meta apply-descriptions ./prep-for-ai-config.json --workspace "Production"

# Commit the changes through XMLA / TOM
fabric-ai-meta apply-descriptions ./prep-for-ai-config.json --workspace "Production" --no-dry-run
```

Reads the `generated_descriptions` section of a `prep-for-ai-config.json` and applies them to table and column descriptions through the Tabular Object Model. `--mock` runs locally without any service contact; without `--mock`, the command must run inside a Fabric notebook runtime.
</details>

<details>
<summary><strong>governance</strong>: cross-model analysis and scorecard</summary>

```bash
fabric-ai-meta governance --workspace "Production" --mock --report ./governance-report.json
```

Detects naming inconsistencies, duplicate DAX expressions, and ranks models by AI readiness.
</details>

<details>
<summary><strong>score</strong>: AI readiness score for a model</summary>

```bash
fabric-ai-meta score "Adventure Works" --workspace "Production" --mock
```
</details>

<details>
<summary><strong>export</strong>: framework-specific exports</summary>

```bash
fabric-ai-meta export langchain "Adventure Works" --workspace "Production" --mock
fabric-ai-meta export openai "Adventure Works" --workspace "Production" --mock
fabric-ai-meta export semantic-kernel "Adventure Works" --workspace "Production" --mock
fabric-ai-meta export autogen "Adventure Works" --workspace "Production" --mock
```
</details>

<details>
<summary><strong>diff</strong>: compare two workspace scans</summary>

```bash
# JSON output (default)
fabric-ai-meta diff baseline.json current.json

# Human-readable text
fabric-ai-meta diff baseline.json current.json --format text

# Save to file
fabric-ai-meta diff baseline.json current.json --output delta-report.json
```

Compares two `workspace-summary.json` files and reports: models added/removed, score changes, table/measure count changes, and per-model improvement or regression status.
</details>

---

## Output Files

### Per-model (written to `{output}/{model-slug}/`)

| File | Description |
|------|-------------|
| `ai-ready-schema.json` | Full AI-ready schema: tables, measures, query guidance, scoring |
| `langchain-tool.json` | LangChain tool definition |
| `openai-function.json` | OpenAI function calling schema |
| `semantic-kernel-plugin.json` | Semantic Kernel plugin manifest |
| `autogen-tool.json` | AutoGen tool definition with full model context |
| `prep-for-ai-config.json` | Prep for AI settings with step-by-step application guide |
| `readiness-score.json` | AI readiness score and component breakdown |
| `measure-dependency-graph.json` | DAX measure dependency graph |
| `extraction-raw.json` | Raw extracted metadata |

### Workspace-level

| File | Description |
|------|-------------|
| `workspace-summary.json` | Score ranking, recommendations, model inventory across all models |
| `governance-report.json` | Cross-model naming issues, duplicate measures, governance scorecard |

---

## LLM Enrichment

Add `--llm-enrich` to any command to enable Claude-powered analysis:

```bash
export ANTHROPIC_API_KEY=sk-ant-...

fabric-ai-meta analyze "Adventure Works" --workspace "Production" --mock --llm-enrich
```

**What LLM enrichment adds:**
- Missing table/column/measure descriptions (batch-generated, cached)
- Natural-language grain detection for fact tables
- AI Instructions text for Prep for AI configs

**Cost controls** (configure in `.fabric-ai-meta.toml`):

```toml
[llm]
max_cost_per_run = 0.20   # raises CostLimitExceededError if exceeded
cache_enabled = true       # SHA-256 keyed file cache, no TTL
```

---

## Library API

All public functions are importable directly from the top-level package:

```python
from fabric_ai_meta import (
    MockExtractor,
    SemanticModelMeta,
    score_model,
    generate_ai_ready_schema,
    to_openai_function,
    to_langchain_tool_definition,
    classify_table_heuristic,
)

# Load a model from fixture
extractor = MockExtractor(fixture_path="tests/fixtures/adventure_works.json")
model = extractor.extract("Adventure Works")

# Score it
score, breakdown = score_model(model)

# Generate exports
schema = generate_ai_ready_schema(model)
openai_fn = to_openai_function(model)
```

See `fabric_ai_meta.__all__` for the full list of 27 public exports.

---

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run full test suite (284 tests, no Fabric runtime or real LLM calls required)
pytest tests/ -x -q

# Run with coverage
pytest tests/ --cov=fabric_ai_meta
```

All tests run locally. Fabric-dependent code is mocked via `MockExtractor` and fixture JSON files in `tests/fixtures/`.

### Fabric Quickstart Notebook

A ready-to-run Jupyter notebook for Microsoft Fabric is available at [`notebooks/quickstart.ipynb`](notebooks/quickstart.ipynb). It walks through authentication, model listing, analysis, export, and governance inside a Fabric notebook session.

### Output Schemas

JSON Schema files for all output formats are in [`schemas/`](schemas/):

| Schema | Validates |
|--------|-----------|
| `schemas/v1.json` | `ai-ready-schema.json` output |
| `schemas/workspace-summary/v1.json` | `workspace-summary.json` output |
| `schemas/governance-report/v1.json` | `governance-report.json` output |

---

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `ANTHROPIC_API_KEY` | For `--llm-enrich` only | Claude API key |
| `FABRIC_NOTEBOOK_ID` | Auto-set in Fabric | Signals Fabric notebook runtime |
