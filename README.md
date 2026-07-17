# fabric-ai-meta

![CI](https://github.com/psistla/fabric-ai-meta/actions/workflows/ci.yml/badge.svg)
[![PyPI Downloads](https://static.pepy.tech/personalized-badge/fabric-ai-meta?period=total&units=INTERNATIONAL_SYSTEM&left_color=GREY&right_color=RED&left_text=downloads)](https://pepy.tech/projects/fabric-ai-meta)
![Version](https://img.shields.io/badge/version-1.6.0-238636?style=flat-square)
![Tests](https://img.shields.io/badge/tests-539%20passing-1a7f37?style=flat-square)
![Python](https://img.shields.io/badge/python-3.10%2B-0550ae?style=flat-square)
![License](https://img.shields.io/badge/license-MIT-6e40c9?style=flat-square)

Extract, classify, and export metadata from Microsoft Fabric semantic models for AI frameworks.

**Turn any Power BI model into AI-ready metadata from your laptop.** No Fabric tenant, no notebook, no sign-in: point it at a local `.pbip` folder and go.

**Automates Prep for AI** across 100+ models. No manual configuration.
**Exports to LangChain, OpenAI, Semantic Kernel, AutoGen.** One extraction, every framework.
**Governs at workspace scale:** naming inconsistencies, duplicate measures, readiness scores.
**Speaks MCP:** six tools for any MCP-aware AI agent or IDE.

### Install

```bash
pip install fabric-ai-meta
```

Optional extras: `[llm]` for multi-provider LLM enrichment, `[mcp]` for the MCP server, `[xmla]` for description writeback. Combine: `pip install 'fabric-ai-meta[llm,mcp,xmla]'`. For development, clone and `pip install -e ".[dev]"`. Every release also attaches a wheel and a source distribution to its GitHub release page for airgapped installs.

### Quickstart

Point it at a model you already have. In Power BI Desktop: **File > Save As > .pbip** (5 seconds, no sign-in), then:

```bash
pip install fabric-ai-meta
fabric-ai-meta analyze "Sales" --pbip ./Sales.SemanticModel
```

One command reads the local TMDL, classifies every table and measure, scores the model, and writes `./output/sales/`:

```text
ai-ready-schema.json        # tables, measures, relationships, all classified
readiness-score.json        # {"score": 0.82}  <- how AI-ready this model is
langchain-tool.json         # drop straight into LangChain (+ OpenAI, Semantic Kernel, AutoGen)
measure-dependency-graph.json
```

It reads your DAX, so a `TOTALYTD(...)` measure comes back understood, not guessed:

```json
{ "name": "Sales YTD", "category": "time_intelligence", "requires_date_filter": true }
```

No model handy? `fabric-ai-meta analyze "Adventure Works" --mock` runs the whole flow on bundled fixtures.

> **New to the tool?** The [end-to-end user guide](https://github.com/psistla/fabric-ai-meta/blob/master/docs/user-guide.md) walks every capability from install to writeback in plain language with persona-mapped workflow paths. The [`notebooks/quickstart.ipynb`](https://github.com/psistla/fabric-ai-meta/blob/master/notebooks/quickstart.ipynb) notebook gives the same tour inside a Fabric runtime.

<p align="center">
<a href="#typical-workflows">Typical Workflows</a> · <a href="#the-problem">The Problem</a> · <a href="#who-this-helps">Who This Helps</a> · <a href="#architecture">Architecture</a> · <a href="#usage">Usage</a> · <a href="#output-files">Output Files</a> · <a href="#llm-enrichment">LLM Enrichment</a> · <a href="#library-api">Library API</a> · <a href="#plugins">Plugins</a> · <a href="#development">Development</a>
</p>

---

## Typical Workflows

Different goals need different command sequences. Pick the one that matches you, or read the full [user guide](https://github.com/psistla/fabric-ai-meta/blob/master/docs/user-guide.md) for the long version.

<p align="center">
<img src="https://raw.githubusercontent.com/psistla/fabric-ai-meta/master/docs/assets/developer-flow.svg" alt="Developer flow: install, pick a source (local .pbip, Fabric notebook, or mock), run a command, get JSON outputs, feed to AI frameworks / writeback / MCP" width="720">
</p>

<details>
<summary><strong>Local model on your laptop (no Fabric)</strong></summary>

```bash
pip install fabric-ai-meta
# In Power BI Desktop: File > Save As > .pbip
fabric-ai-meta analyze "Your Model" --pbip ./YourModel.SemanticModel   # one model
fabric-ai-meta score --all --pbip ./git-integration-repo               # a whole repo of them
fabric-ai-meta governance --pbip ./git-integration-repo --output ./gov # cross-model report
fabric-ai-meta export langchain "Your Model" --pbip ./YourModel.SemanticModel
```
</details>

<details>
<summary><strong>Solo BI developer exploring the tool</strong></summary>

```bash
pip install fabric-ai-meta
fabric-ai-meta analyze "Adventure Works" --mock                    # try with bundled fixture
fabric-ai-meta analyze "Your Model" --workspace "Production"       # then point at real workspace
fabric-ai-meta export openai "Your Model" --workspace "Production" # export to your AI framework
```
</details>

<details>
<summary><strong>Enterprise governance team</strong></summary>

```bash
pip install fabric-ai-meta
# Write a .fabric-ai-meta.toml with [extraction] default_workspace and thresholds
fabric-ai-meta scan --workspace "Production" --output ./snapshot
fabric-ai-meta governance --workspace "Production" --report ./governance-report.json
# Wire scripts/ci-governance-check.py into PR pipeline (see docs/ci-cd-guide.md)
# Track over time by re-running scan with --baseline ./previous/workspace-summary.json
```
</details>

<details>
<summary><strong>AI engineer building agents on Fabric data</strong></summary>

```bash
pip install 'fabric-ai-meta[llm,mcp]'
export ANTHROPIC_API_KEY=sk-ant-...   # or any other supported provider
fabric-ai-meta analyze "Your Model" --workspace "Production" --llm-enrich
fabric-ai-meta export langchain "Your Model" --workspace "Production"
# Or expose live tools to your IDE via MCP:
fabric-ai-meta serve
```
</details>

<details>
<summary><strong>Fabric architect cleaning a semantic model</strong></summary>

```bash
pip install 'fabric-ai-meta[llm,xmla]'
fabric-ai-meta analyze "Sales Model" --workspace "Production" --llm-enrich
fabric-ai-meta export prep-for-ai "Sales Model" --workspace "Production" --llm-enrich
fabric-ai-meta export copilot "Sales Model" --workspace "Production"                            # snapshot the live Copilot/ folder to disk
fabric-ai-meta apply-descriptions ./output/sales-model/prep-for-ai-config.json --mock           # preview
fabric-ai-meta apply-descriptions ./output/sales-model/prep-for-ai-config.json --no-dry-run     # commit (in a Fabric notebook)
```
</details>

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
| No agent-callable surface | `fabric-ai-meta serve` exposes six tools through MCP for any MCP-aware AI agent or IDE |
| No external AI export | Produces framework-native schemas for LangChain, OpenAI, Semantic Kernel, and AutoGen |
| No way to add custom exporters | Third parties ship exporters as installable Python plugins via the `fabric_ai_meta.exporters` entry point group |
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

`sempy.fabric` requires the Microsoft Fabric notebook runtime, so **live workspace** extraction only runs inside Fabric. Everything else runs on any machine: read a real local model from a `.pbip` / TMDL folder with `--pbip`, or bundled fixtures with `--mock`. The mode is detected automatically at startup:

```text
                          CLI command
                               |
                               v
                      +----------------+
                      |  Environment?  |
                      +-------+--------+
                              |
       +----------------------+---------------------------+
       |                                                  |
  Fabric runtime                                     Local machine
  (FABRIC_NOTEBOOK_ID set                                 |
   or notebookutils importable)                           v
       |                                          +----------------+
       v                                          | --pbip / --mock|
  +-------------------+                           +-------+--------+
  | Fabric Mode       |                                   |
  | SemanticLink-     |         +---------------------+---+-----------------+
  | Extractor         |         |                     |                     |
  | (ambient creds)   |         v                     v                     v
  +---------+---------+  +--------------+     +--------------+     +--------------------+
            |            | Local .pbip  |     | Local/CI     |     | Neither flag:      |
            |            | PbipExtractor|     | MockExtractor|     | FabricEnvironment- |
            |            | (TMDL folder)|     | (fixture JSON)|    | Error              |
            |            +------+-------+     +------+-------+     +--------------------+
            |                   |                    |
            +---------+---------+--------------------+
                      |
                      v
                +-----------+
                | Core      |
                | Engine    |
                +-----+-----+
                      |
                      v
            +--------------------+
            | Analyzer           |
            | Classify · Score · |
            | Governance         |
            +---------+----------+
                      |
                      v
            +--------------------+
            | Generator          |
            | Schemas · Exports ·|
            | Reports            |
            +--------------------+
```

This ASCII diagram renders identically on GitHub and PyPI; the equivalent table is below for screen readers and narrow viewports.

| Mode | Where it runs | Extractor | Auth |
|------|--------------|-----------|------|
| **Fabric mode** | Fabric notebook | `SemanticLinkExtractor` | Ambient (automatic) |
| **Local `.pbip` mode** | Any machine | `PbipExtractor` + local TMDL | None needed |
| **Local/CI mock mode** | Any machine | `MockExtractor` + fixture JSON | None needed |

> **Runs locally two ways, no Fabric connection needed:** `--pbip <folder>` reads a real local model and `--mock` runs on bundled fixtures. Both work on `analyze`, `scan`, `score`, `governance`, and `export`.

---

## Usage

<details>
<summary><strong>analyze</strong>: extract, classify, score, and export a single model</summary>

```bash
# Local model from disk, no Fabric (--pbip is exclusive with --mock and --workspace)
fabric-ai-meta analyze "Your Model" --pbip ./YourModel.SemanticModel

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

# Or scan a local directory of *.SemanticModel folders (a Git Integration repo)
fabric-ai-meta scan --pbip ./git-integration-repo --output ./output
```

Produces per-model output directories and a `workspace-summary.json` with score ranking.

**Next steps:** run [`governance`](#usage) for a cross-model report, or [`diff`](#usage) against a previous summary to track readiness over time.
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

**Next step:** run [`apply-descriptions`](#usage) to push the generated description backfill straight to the live model through XMLA / TOM instead of pasting each one in the UI.
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

**Prerequisite:** the input file is produced by [`export prep-for-ai --llm-enrich`](#usage). Without `--llm-enrich`, the config will not contain a `generated_descriptions` section to apply.
</details>

<details>
<summary><strong>governance</strong>: cross-model analysis and scorecard</summary>

```bash
fabric-ai-meta governance --workspace "Production" --mock --report ./governance-report.json
```

Detects naming inconsistencies, duplicate DAX expressions, and ranks models by AI readiness.

**Next step:** wire the report into CI/CD using [`scripts/ci-governance-check.py`](https://github.com/psistla/fabric-ai-meta/blob/master/scripts/ci-governance-check.py) and the [CI/CD guide](https://github.com/psistla/fabric-ai-meta/blob/master/docs/ci-cd-guide.md).
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

**Add your own format:** subclass `BaseExporter` and register a Python entry point under `fabric_ai_meta.exporters`. Your exporter then appears as `fabric-ai-meta export <name>` with the same flags. See the [plugin development guide](https://github.com/psistla/fabric-ai-meta/blob/master/docs/plugin-development.md) for a worked dbt example.

**Tip:** run with `--llm-enrich` on the upstream [`analyze`](#usage) step first to fill in missing descriptions before exporting.
</details>

<details>
<summary><strong>export copilot</strong>: dump the Microsoft Copilot/ folder as files on disk</summary>

```bash
# Local dev with sidecar fixture
fabric-ai-meta export copilot "Adventure Works" --workspace "Production" --mock

# Live model (inside a Fabric notebook)
fabric-ai-meta export copilot "Adventure Works" --workspace "Production"
```

Mirrors Microsoft's `Copilot/` folder layout under `{output}/{model-slug}/copilot/`: `Instructions/instructions.md`, `VerifiedAnswers/*.json`, `schema.json`, `examplePrompts.json`, `settings.json`, `version.json`. Pair with the `apply-copilot` command (v1.5.0) to write a modified folder back to a live model via the Fabric REST `updateDefinition` LRO.

**No `--with-copilot` needed:** this command implicitly enables Copilot extraction. Use `analyze --with-copilot` or `scan --with-copilot` to populate `model.copilot` alongside the other extractor outputs.
</details>

<details>
<summary><strong>apply-copilot</strong>: write a Copilot/ folder back to a live semantic model (v1.5.0)</summary>

```bash
# Preview the writeback locally with the mock writer
fabric-ai-meta apply-copilot ./output/adventure-works/copilot \
  --model "Adventure Works" --workspace "Production" --mock

# Inside a Fabric notebook, dry-run the diff against the live model (default)
fabric-ai-meta apply-copilot ./output/adventure-works/copilot \
  --model "Adventure Works" --workspace "Production"

# Commit the changes through Fabric REST updateDefinition (long-running operation)
fabric-ai-meta apply-copilot ./output/adventure-works/copilot \
  --model "Adventure Works" --workspace "Production" --no-dry-run
```

Reads a Copilot/ folder produced by `export copilot`, splices the new artifacts into the model's full TMDL definition envelope (preserving all non-Copilot parts byte-for-byte), and posts the result through `updateDefinition`. Long-running operation polling is built in. Existing Copilot parts not present in the new folder are removed (replace semantics).

**Round-trip workflow:**

```text
export copilot → edit local Copilot/ folder → apply-copilot → live model
```

Pair with `scan --with-copilot` and `governance --with-copilot` to track Copilot completeness across the workspace.
</details>

<details>
<summary><strong>serve</strong>: start the MCP server for AI agents</summary>

```bash
# Install the optional MCP extra
pip install 'fabric-ai-meta[mcp]'

# Start over stdio (default; what most MCP-aware AI agents and IDEs use)
fabric-ai-meta serve

# Start over streamable HTTP on a specific port
fabric-ai-meta serve --transport streamable-http --port 8000
```

Exposes six tools to AI agents: `list_models`, `analyze_model`, `score_model`, `generate_schema`, `governance_report`, `diff_summaries`. A ready-to-use [`.mcp.json`](https://github.com/psistla/fabric-ai-meta/blob/master/.mcp.json) lives at the project root, so any IDE that auto-discovers project-scoped MCP servers picks it up when the working directory is opened.

**Connect from a desktop MCP client:** add the contents of `.mcp.json` to your client's `mcpServers` configuration. Common locations include `%APPDATA%/<client>/<client>_config.json` on Windows and `~/Library/Application Support/<client>/<client>_config.json` on macOS.

**What this unlocks:** ask your IDE agent "Which tables in our Sales Model are missing descriptions?" and get a real answer. The agent calls `analyze_model` and `governance_report` over MCP and returns the analysis without you running the CLI by hand.
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

Add `--llm-enrich` to any command to enable LLM-powered analysis:

```bash
export ANTHROPIC_API_KEY=sk-ant-...      # default provider; swap for another below

fabric-ai-meta analyze "Adventure Works" --workspace "Production" --mock --llm-enrich
```

**Multi-provider support (via LiteLLM).** Install the optional extra and pick any of 10+ providers in `.fabric-ai-meta.toml`:

```bash
pip install 'fabric-ai-meta[llm]'
```

| Provider | `provider` | `model` example | API key env var |
|----------|-----------|-----------------|-----------------|
| Anthropic | `anthropic` | `claude-sonnet-4-6` | `ANTHROPIC_API_KEY` |
| OpenAI | `openai` | `gpt-4o` | `OPENAI_API_KEY` |
| Google Gemini | `google` | `gemini-2.5-pro` | `GEMINI_API_KEY` |
| xAI Grok | `xai` | `grok-4` | `XAI_API_KEY` |
| Mistral | `mistral` | `mistral-large-latest` | `MISTRAL_API_KEY` |
| Cohere | `cohere` | `command-r-plus` | `COHERE_API_KEY` |
| AWS Bedrock | `bedrock` | `anthropic.claude-sonnet-4-v1:0` | `AWS_*` (SDK default chain) |
| Azure OpenAI | `azure` | `<deployment-name>` | `AZURE_OPENAI_API_KEY` |
| Google Vertex AI | `vertex` | `gemini-2.5-pro` | `GOOGLE_APPLICATION_CREDENTIALS` |
| OpenAI-compatible | `openai-compatible` | `<any>` (set `base_url`) | `OPENAI_COMPATIBLE_API_KEY` |

The `openai-compatible` provider routes through any OpenAI-API-compatible host: Groq, Together, Fireworks, Ollama, LM Studio, vLLM, or a custom endpoint. Set `base_url` in config.

<details>
<summary>Example: OpenAI</summary>

```toml
[llm]
provider = "openai"
model = "gpt-4o"
api_key_env = "OPENAI_API_KEY"
```
</details>

<details>
<summary>Example: Azure OpenAI</summary>

```toml
[llm]
provider = "azure"
model = "gpt-4o-deployment"
api_key_env = "AZURE_OPENAI_API_KEY"
azure_endpoint = "https://my-resource.openai.azure.com"
azure_api_version = "2024-02-15-preview"
```
</details>

<details>
<summary>Example: Local Ollama (openai-compatible)</summary>

```toml
[llm]
provider = "openai-compatible"
model = "llama3.1"
base_url = "http://localhost:11434"
api_key_env = "OPENAI_COMPATIBLE_API_KEY"  # any non-empty value works
```
</details>

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

See `fabric_ai_meta.__all__` for the full list of 40 public exports.

---

## Plugins

Custom exporters install as ordinary Python packages and appear as `fabric-ai-meta export <name>` with the same `--workspace` and `--mock` flags as built-ins. No fork of fabric-ai-meta is required.

```python
from fabric_ai_meta import BaseExporter, SemanticModelMeta


class DbtExporter(BaseExporter):
    name = "dbt"
    output_filename = "dbt-sources.yml"
    description = "dbt sources definition"

    def generate(self, model: SemanticModelMeta) -> dict:
        return {"version": 2, "sources": [...]}
```

Register the class via the `fabric_ai_meta.exporters` entry-point group in the plugin's `pyproject.toml`:

```toml
[project.entry-points."fabric_ai_meta.exporters"]
dbt = "my_fabric_dbt_plugin:DbtExporter"
```

Full walk-through with a worked dbt example, local testing, and name-conflict rules: [`docs/plugin-development.md`](https://github.com/psistla/fabric-ai-meta/blob/master/docs/plugin-development.md).

---

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run full test suite (504 tests, no Fabric runtime or real LLM calls required)
pytest tests/ -x -q

# Run with coverage
pytest tests/ --cov=fabric_ai_meta
```

All tests run locally. Fabric-dependent code is mocked via `MockExtractor` and fixture JSON files in `tests/fixtures/`.

### Fabric Notebooks

| Notebook | Purpose |
|----------|---------|
| [`notebooks/quickstart.ipynb`](https://github.com/psistla/fabric-ai-meta/blob/master/notebooks/quickstart.ipynb) | End-to-end walkthrough: authentication, model listing, analysis, export, governance |
| [`notebooks/tmdl-spike.ipynb`](https://github.com/psistla/fabric-ai-meta/blob/master/notebooks/tmdl-spike.ipynb) | Read-only Copilot/ folder inspection: shows the raw `getDefinition` envelope the new `CopilotReader` API parses. |

### CI/CD Integration

Wire `fabric-ai-meta` into GitHub Actions or Azure DevOps to enforce governance thresholds on every PR and track readiness trends on a schedule. The guide in [`docs/ci-cd-guide.md`](https://github.com/psistla/fabric-ai-meta/blob/master/docs/ci-cd-guide.md) includes ready-to-paste workflow files and the standalone [`scripts/ci-governance-check.py`](https://github.com/psistla/fabric-ai-meta/blob/master/scripts/ci-governance-check.py) threshold script.

### Output Schemas

JSON Schema files for all output formats are in [`schemas/`](https://github.com/psistla/fabric-ai-meta/tree/master/schemas):

| Schema | Validates |
|--------|-----------|
| `schemas/v1.json` | `ai-ready-schema.json` output |
| `schemas/workspace-summary/v1.json` | `workspace-summary.json` output |
| `schemas/governance-report/v1.json` | `governance-report.json` output |
| `schemas/prep-for-ai/v1.json` | `prep-for-ai-config.json` output |

---

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `ANTHROPIC_API_KEY` | For `--llm-enrich` with default `anthropic` provider | LLM API key |
| `OPENAI_API_KEY` / `GEMINI_API_KEY` / `XAI_API_KEY` / `MISTRAL_API_KEY` / `COHERE_API_KEY` / `AZURE_OPENAI_API_KEY` / `OPENAI_COMPATIBLE_API_KEY` | For the matching provider in `[llm]` config | See provider matrix above |
| `AWS_*` (Bedrock), `GOOGLE_APPLICATION_CREDENTIALS` (Vertex) | When using Bedrock or Vertex | Standard SDK credential chains |
| `FABRIC_NOTEBOOK_ID` | Auto-set in Fabric | Signals Fabric notebook runtime |
