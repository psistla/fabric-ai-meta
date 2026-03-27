# fabric-ai-meta

A Python CLI and library that extracts metadata from Microsoft Fabric semantic models, performs AI-driven analysis, and generates AI-ready outputs — automating what Microsoft expects teams to do manually across 10–100+ models.

## What it does

**AI-ready schema exports** — structured metadata for:
- LangChain tool definitions
- OpenAI function calling schemas
- Semantic Kernel plugin manifests

**Prep for AI automation** — generates the `prep-for-ai-config.json` file you apply manually in Power BI Desktop or Fabric Service (no public API exists):
- AI Data Schema (included tables, excluded columns)
- AI Instructions (rule-based or LLM-generated)
- Verified Answers (DAX-backed Q&A pairs)
- Generated Descriptions (LLM batch backfill for undescribed columns and measures)

**Bulk workspace scan** — process every model in a workspace in one command, producing per-model outputs and a `workspace-summary.json` with readiness scores and recommendations.

## Architecture

`sempy.fabric` requires the Microsoft Fabric notebook runtime and does not work locally.

| Mode | Where | Extractor |
|------|-------|-----------|
| **Fabric mode** | Fabric notebook | `SemanticLinkExtractor` (ambient credential) |
| **Local/CI mode** | Any machine | `MockExtractor` + fixture JSON (`--mock` flag) |

## Installation

```bash
pip install -e ".[dev]"
```

## Usage

```bash
# Analyze a single model (local dev with mock fixtures)
fabric-ai-meta analyze "Adventure Works" --workspace "Production" --mock

# Export Prep for AI config (mock, no LLM)
fabric-ai-meta export prep-for-ai "Adventure Works" --workspace "Production" --mock

# Export Prep for AI config with LLM enrichment
fabric-ai-meta export prep-for-ai "Adventure Works" --workspace "Production" --mock --llm-enrich

# Bulk scan all models in a workspace
fabric-ai-meta scan --workspace "Production" --mock

# Score a model
fabric-ai-meta score "Adventure Works" --workspace "Production" --mock

# Cross-model governance report (Fabric runtime required)
fabric-ai-meta governance --workspace "Production"
```

## Output files (per model)

| File | Description |
|------|-------------|
| `ai-ready-schema.json` | Full AI-ready schema with tables, measures, and query guidance |
| `langchain-tool.json` | LangChain tool definition |
| `openai-function.json` | OpenAI function calling schema |
| `semantic-kernel-plugin.json` | Semantic Kernel plugin manifest |
| `prep-for-ai-config.json` | Prep for AI settings with application guide |
| `readiness-score.json` | AI readiness score and breakdown |
| `measure-dependency-graph.json` | DAX measure dependency graph |
| `extraction-raw.json` | Raw extracted metadata |

Bulk scan also produces `workspace-summary.json` with score ranking and recommendations across all models.

## Development

```bash
# Run full test suite
pytest tests/ -x -q

# Run with coverage
pytest tests/ --cov=fabric_ai_meta
```

All tests run locally — no Fabric runtime or real LLM calls required.

## Environment variables

| Variable | Description |
|----------|-------------|
| `ANTHROPIC_API_KEY` | Required for `--llm-enrich` |
| `FABRIC_NOTEBOOK_ID` | Set automatically in Fabric notebooks |
