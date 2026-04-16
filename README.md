# fabric-ai-meta

![Version](https://img.shields.io/badge/version-1.0.0-238636?style=flat-square)
![Tests](https://img.shields.io/badge/tests-222%20passing-1a7f37?style=flat-square)
![Python](https://img.shields.io/badge/python-3.10%2B-0550ae?style=flat-square)
![License](https://img.shields.io/badge/license-MIT-6e40c9?style=flat-square)

Extract metadata from Microsoft Fabric semantic models and generate AI-ready outputs — automating what Microsoft expects teams to do manually across 10-100+ models.

<p align="center">
<a href="#-philosophy">Philosophy</a> · <a href="#-the-problem">The Problem</a> · <a href="#-who-this-helps">Who This Helps</a> · <a href="#-architecture">Architecture</a> · <a href="#-installation">Installation</a> · <a href="#-usage">Usage</a> · <a href="#-output-files">Output Files</a> · <a href="#-llm-enrichment">LLM Enrichment</a> · <a href="#-library-api">Library API</a> · <a href="#-development">Development</a>
</p>

---

## Philosophy

Semantic models are the most valuable metadata layer in any Microsoft Fabric deployment. They encode business logic in DAX, define relationships between entities, classify data into facts and dimensions, and carry institutional knowledge in descriptions, naming conventions, and folder structures. Yet this rich metadata is locked inside the Fabric ecosystem with no native path out.

**fabric-ai-meta treats semantic models as first-class metadata assets.** The philosophy is simple:

1. **Extract everything** — tables, columns, measures, DAX expressions, relationships, hierarchies, descriptions, formatting rules, and hidden-object flags. Nothing is too small to capture.
2. **Classify automatically** — every table gets a type (fact, dimension, bridge, configuration). Every measure gets a category (additive, semi-additive, time intelligence). Every column gets a role (key, foreign key, attribute, date). Heuristics run first; LLM enrichment refines where ambiguity remains.
3. **Score honestly** — an AI Readiness Score (0.0 to 1.0) tells you exactly how prepared a model is for AI consumption, broken down by description coverage, naming consistency, relationship completeness, and business rule documentation. No vanity metrics.
4. **Export universally** — the same model metadata flows to LangChain, OpenAI, Semantic Kernel, AutoGen, or your custom pipeline. One extraction, every framework.
5. **Govern at scale** — naming inconsistencies, duplicate measures, and documentation gaps across an entire workspace of models, surfaced in a single command.

This is not a replacement for Microsoft's tools. It is an **automation layer on top of them** and a **bridge to the external AI ecosystem** that Microsoft does not serve.

---

## The Problem

Microsoft Fabric has invested heavily in AI features for semantic models: Prep for AI, Copilot-generated descriptions, Data Agents, and the emerging Fabric IQ Ontology. These are powerful capabilities, but they share three critical limitations:

**1. They don't scale.** Prep for AI requires manual configuration — selecting tables, writing AI Instructions, defining Verified Answers — one model at a time. An enterprise with 50 semantic models across 10 workspaces faces hundreds of hours of repetitive configuration work. There is no bulk API.

**2. They don't leave Fabric.** If you're building a LangChain agent, an OpenAI function-calling pipeline, or a custom RAG system against Fabric data, Microsoft offers no export path. The metadata stays in Fabric, and your AI application starts blind — no table types, no measure semantics, no relationship graph, no query pitfalls.

**3. They don't govern across models.** Copilot can generate a description for a single measure, but it can't tell you that `Total Sales` in Model A and `Sum of Sales` in Model B are the same calculation with different names. Cross-model governance — naming standards, duplicate detection, documentation completeness — remains entirely manual.

**fabric-ai-meta closes all three gaps:**

| Gap | What fabric-ai-meta does |
|-----|--------------------------|
| Manual Prep for AI | Auto-generates `prep-for-ai-config.json` — table selections, AI Instructions, Verified Answers, description backfill — in seconds |
| No external AI export | Produces framework-native schemas for LangChain, OpenAI, Semantic Kernel, and AutoGen from a single extraction |
| No cross-model governance | Scans an entire workspace, detects naming inconsistencies and duplicate DAX, ranks models by AI readiness, and outputs a governance report |

---

## Who This Helps

### Fabric Architects and Senior BI Developers

You manage 10-100+ semantic models across workspaces. You know every model needs Prep for AI configured, descriptions filled in, and naming standards enforced — but doing it manually is unrealistic at scale.

**fabric-ai-meta gives you:**
- Bulk workspace scan with per-model AI readiness scores
- Auto-generated Prep for AI configs you apply in the UI (since no API exists)
- LLM-powered description backfill for undocumented tables, columns, and measures
- A governance report that catches naming inconsistencies and duplicate measures across your entire estate

### AI/ML Engineers Building on Fabric Data

You're building agents, copilots, or RAG pipelines that query Fabric semantic models. You need structured metadata — table types, measure semantics, relationship graphs, query pitfalls — in your framework's native format. You don't have deep DAX expertise, and you shouldn't need it.

**fabric-ai-meta gives you:**
- One-command export to LangChain tool definitions, OpenAI function schemas, Semantic Kernel plugin manifests, or AutoGen tool definitions
- An AI-ready JSON schema that includes query guidance, common pitfalls, valid filter paths, and recommended aggregation patterns
- Measure dependency graphs so your agent understands which calculations derive from which

### Data Governance Teams

You need visibility into documentation completeness, naming consistency, and model quality across the Fabric estate. Today, this requires opening each model individually in Power BI Desktop.

**fabric-ai-meta gives you:**
- A governance scorecard across all models in a workspace
- Automated detection of naming pattern violations and duplicate business logic
- AI readiness scores broken down by description coverage, naming consistency, relationship completeness, and business rule documentation

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

> **Every command supports `--mock`** — `analyze`, `scan`, `export`, `score`, and `governance` all work locally without a Fabric connection.

---

## Installation

```bash
pip install -e ".[dev]"
```

Verify the install:

```bash
fabric-ai-meta --help
```

---

## Usage

<details>
<summary><strong>analyze</strong> — extract, classify, score, and export a single model</summary>

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
<summary><strong>scan</strong> — bulk scan all models in a workspace</summary>

```bash
fabric-ai-meta scan --workspace "Production" --mock --output ./output
```

Produces per-model output directories and a `workspace-summary.json` with score ranking.
</details>

<details>
<summary><strong>export prep-for-ai</strong> — generate Prep for AI config</summary>

```bash
# Rule-based (no LLM)
fabric-ai-meta export prep-for-ai "Adventure Works" --workspace "Production" --mock

# With LLM-generated AI instructions
fabric-ai-meta export prep-for-ai "Adventure Works" --workspace "Production" --mock --llm-enrich
```

Output is a `prep-for-ai-config.json` you apply manually in Power BI Desktop or Fabric Service.
No public API exists for programmatic application.
</details>

<details>
<summary><strong>governance</strong> — cross-model analysis and scorecard</summary>

```bash
fabric-ai-meta governance --workspace "Production" --mock --report ./governance-report.json
```

Detects naming inconsistencies, duplicate DAX expressions, and ranks models by AI readiness.
</details>

<details>
<summary><strong>score</strong> — AI readiness score for a model</summary>

```bash
fabric-ai-meta score "Adventure Works" --workspace "Production" --mock
```
</details>

<details>
<summary><strong>export</strong> — framework-specific exports</summary>

```bash
fabric-ai-meta export langchain "Adventure Works" --workspace "Production" --mock
fabric-ai-meta export openai "Adventure Works" --workspace "Production" --mock
fabric-ai-meta export semantic-kernel "Adventure Works" --workspace "Production" --mock
fabric-ai-meta export autogen "Adventure Works" --workspace "Production" --mock
```
</details>

---

## Output Files

### Per-model (written to `{output}/{model-slug}/`)

| File | Description |
|------|-------------|
| `ai-ready-schema.json` | Full AI-ready schema — tables, measures, query guidance, scoring |
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

**Cost controls** — configure in `.fabric-ai-meta.toml`:

```toml
[llm]
max_cost_per_run = 0.20   # raises CostLimitExceededError if exceeded
cache_enabled = true       # SHA-256 keyed file cache — no TTL
```

---

## Library API

Use `fabric-ai-meta` as a Python library — all public functions are importable from the top-level package:

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
model = extractor.extract()

# Score it
score, breakdown = score_model(model)

# Generate exports
schema = generate_ai_ready_schema(model)
openai_fn = to_openai_function(model)
```

See `fabric_ai_meta.__all__` for the full list of 26 public exports.

---

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run full test suite (222 tests, no Fabric runtime or real LLM calls required)
pytest tests/ -x -q

# Run with coverage
pytest tests/ --cov=fabric_ai_meta
```

All tests run locally. Fabric-dependent code is mocked via `MockExtractor` and fixture JSON files in `tests/fixtures/`.

---

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `ANTHROPIC_API_KEY` | For `--llm-enrich` only | Claude API key |
| `FABRIC_NOTEBOOK_ID` | Auto-set in Fabric | Signals Fabric notebook runtime |
