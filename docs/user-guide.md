# End-to-End User Guide

A plain-language walk-through of every fabric-ai-meta capability, in the order a typical user adopts them. Start at step 1 if you are new; jump to a numbered step if you know what you need.

For per-command reference (every flag, every option), see the `Usage` section in the [README](../README.md). For CI/CD recipes see [`ci-cd-guide.md`](ci-cd-guide.md). For building your own exporter see [`plugin-development.md`](plugin-development.md).

---

## 1. Install

```bash
pip install fabric-ai-meta             # core
pip install 'fabric-ai-meta[llm]'      # add multi-provider LLM enrichment
pip install 'fabric-ai-meta[mcp]'      # add the MCP server
pip install 'fabric-ai-meta[xmla]'     # add description writeback (Windows)
```

Install everything at once: `pip install 'fabric-ai-meta[llm,mcp,xmla,dev]'`.

For development against the source tree:

```bash
git clone https://github.com/psistla/fabric-ai-meta.git
cd fabric-ai-meta
pip install -e ".[dev]"
```

For airgapped or restricted environments that cannot reach PyPI directly, download the wheel from the GitHub release page on a connected machine and upload it as a workspace library (Fabric environment libraries, internal artifact registry, etc.). Every release attaches both `fabric_ai_meta-X.Y.Z-py3-none-any.whl` and `fabric_ai_meta-X.Y.Z.tar.gz`.

---

## 2. Try it locally first (no Fabric required)

Two fixture models ship with the package (Adventure Works, Contoso Sales). Run any command with `--mock`:

```bash
fabric-ai-meta analyze "Adventure Works" --mock --output ./output
```

You get 7 files in `./output/adventure-works/`:

| File | What it is |
|------|------------|
| `ai-ready-schema.json` | Full structured metadata (tables, measures, query guidance, scoring) |
| `langchain-tool.json` | LangChain `StructuredTool` definition |
| `openai-function.json` | OpenAI function calling schema |
| `semantic-kernel-plugin.json` | Microsoft Semantic Kernel plugin manifest |
| `readiness-score.json` | AI readiness score with component breakdown |
| `measure-dependency-graph.json` | DAX measure dependency graph |
| `extraction-raw.json` | Raw extracted metadata |

Now you know the shape of every output before connecting to real Fabric.

---

## 3. Connect to real Fabric

Two ways:

**Inside a Fabric notebook (recommended).** Open a notebook in your Fabric workspace and run:

```python
%pip install fabric-ai-meta
!fabric-ai-meta analyze "Sales Model" --workspace "Production"
```

Ambient Entra credentials are picked up automatically. The CLI detects the notebook environment via the `FABRIC_NOTEBOOK_ID` environment variable.

**Locally with Entra auth.**

```bash
fabric-ai-meta auth login
fabric-ai-meta analyze "Sales Model" --workspace "Production"
```

Note: `sempy.fabric` requires the Fabric notebook runtime, so the local path falls back to XMLA through `pyadomd` on Windows (install with the `[xmla]` extra).

---

## 4. Configure your project (optional)

Drop a `.fabric-ai-meta.toml` in your working directory:

```toml
[extraction]
default_workspace = "Production Analytics"
include_sample_values = false

[llm]
provider = "anthropic"
model = "claude-sonnet-4-6"
api_key_env = "ANTHROPIC_API_KEY"
cache_enabled = true
max_cost_per_run = 0.20

[output]
output_dir = "./fabric-output"
```

Set the matching API key environment variable (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GEMINI_API_KEY`, etc.) and you are done. Subsequent commands pick up the workspace, output directory, and LLM settings automatically.

Full provider matrix (10+ providers) is in the [README LLM Enrichment section](../README.md#llm-enrichment).

---

## 5. Bulk-scan a whole workspace

```bash
fabric-ai-meta scan --workspace "Production" --output ./output
```

Loops over every semantic model in the workspace and produces:

- A per-model output directory (the same 7 files described in step 2) for every model
- A top-level `workspace-summary.json` with score ranking and recommendations across all models

Track readiness over time:

```bash
fabric-ai-meta scan --workspace "Production" --output ./current \
  --baseline ./previous/workspace-summary.json
```

Produces a delta report: new and removed models, score regressions, table-count changes.

---

## 6. Generate AI-ready exports

One command per framework:

```bash
fabric-ai-meta export langchain "Sales Model" --workspace "Production"
fabric-ai-meta export openai "Sales Model" --workspace "Production"
fabric-ai-meta export semantic-kernel "Sales Model" --workspace "Production"
fabric-ai-meta export autogen "Sales Model" --workspace "Production"
```

Drop the output straight into agent code:

```python
import json
tool_def = json.load(open("output/sales-model/openai-function.json"))
# pass to OpenAI function-calling API
```

---

## 7. Turn on LLM enrichment (fill in the gaps)

Raw Fabric metadata is often incomplete: missing descriptions, fuzzy table types, no grain statements. Add `--llm-enrich` to any extraction command:

```bash
fabric-ai-meta analyze "Sales Model" --workspace "Production" --llm-enrich
```

The LLM does three things:

- Generates missing table, column, and measure descriptions in batches
- Classifies ambiguous tables as fact, dimension, or bridge
- Detects fact-table grain in plain English

Responses are cached by SHA-256 hash of the prompt, so re-runs are free. The `max_cost_per_run` setting in your TOML caps spend per command.

---

## 8. Automate Prep for AI

Microsoft's Prep for AI wizard requires manual configuration for every model. Skip the wizard:

```bash
fabric-ai-meta export prep-for-ai "Sales Model" --workspace "Production" --llm-enrich
```

Produces a `prep-for-ai-config.json` with:

- The list of tables to include (staging and bridge tables excluded automatically)
- LLM-generated AI Instructions text
- Verified Answers (sample question plus DAX measure)
- Hidden columns flagged for exclusion
- Description backfill for every undocumented object

Apply the file content step by step in the Fabric Prep for AI UI. The Prep for AI surface has no public API; this command automates everything up to the manual UI paste.

---

## 9. Write descriptions back to the live model

After LLM enrichment, push the generated descriptions back to your semantic model:

```bash
# Preview locally without contacting Fabric
fabric-ai-meta apply-descriptions ./output/sales-model/prep-for-ai-config.json --mock

# Dry-run against the live model (default behavior, safe)
fabric-ai-meta apply-descriptions ./prep-for-ai-config.json --workspace "Production"

# Commit the changes through XMLA / TOM
fabric-ai-meta apply-descriptions ./prep-for-ai-config.json --workspace "Production" --no-dry-run
```

Writeback uses the Tabular Object Model. Live commits must run inside a Fabric notebook runtime. The local `--mock` mode prints the writeback plan without making any service call.

---

## 10. Cross-model governance report

```bash
fabric-ai-meta governance --workspace "Production" --report ./governance-report.json
```

Produces a JSON report covering:

- Naming inconsistencies (`Total_Sales` vs `Total Sales` vs `TotalSales` flagged together)
- Duplicate DAX expressions (same calculation under different measure names)
- Description coverage percentage per model
- AI readiness score rankings across the workspace

---

## 11. Wire into CI/CD

Drop a governance check into your PR pipeline:

```yaml
- run: pip install fabric-ai-meta
- run: fabric-ai-meta governance --workspace "$WORKSPACE" --report report.json --mock
- run: python scripts/ci-governance-check.py report.json --min-score 0.7
```

The PR fails when readiness drops below the threshold. Full guide with ready-to-paste GitHub Actions and Azure DevOps workflows: [`docs/ci-cd-guide.md`](ci-cd-guide.md).

---

## 12. Expose to AI agents through MCP

Start the MCP server:

```bash
fabric-ai-meta serve                                            # stdio (default; auto-discovered by IDEs)
fabric-ai-meta serve --transport streamable-http --port 8000    # HTTP
```

The project ships a `.mcp.json` at the repository root so any MCP-aware IDE auto-discovers the server when the working directory is opened.

Six tools are exposed to agents:

- `list_models`: enumerate models in a workspace
- `analyze_model`: full per-model analysis
- `score_model`: AI readiness score
- `generate_schema`: produce the AI-ready schema
- `governance_report`: cross-model report
- `diff_summaries`: compare two scans

Now you can ask your agent: "Analyze our Sales Model and tell me which tables are missing descriptions." The agent calls the MCP tools and returns the answer.

---

## 13. Use as a Python library

Skip the CLI entirely and embed the engine in your own code:

```python
from fabric_ai_meta import (
    MockExtractor,
    score_model,
    generate_ai_ready_schema,
    to_openai_function,
)

extractor = MockExtractor(fixture_path="tests/fixtures/adventure_works.json")
model = extractor.extract("Adventure Works")

score, breakdown = score_model(model)
schema = generate_ai_ready_schema(model)
openai_fn = to_openai_function(model)
```

35 symbols are exposed at the top level (see `fabric_ai_meta.__all__`). Embed in data platforms, notebooks, governance pipelines, or backend services.

---

## 14. Ship a custom exporter

Need a dbt sources export, a Purview lineage emitter, or an internal sink? Subclass `BaseExporter` and register the class via a Python entry point:

```python
# my_plugin/__init__.py
from fabric_ai_meta import BaseExporter

class DbtExporter(BaseExporter):
    name = "dbt"
    output_filename = "dbt-sources.yml"
    description = "dbt sources from a Fabric model"

    def generate(self, model):
        return {"version": 2, "sources": [...]}
```

```toml
# pyproject.toml
[project.entry-points."fabric_ai_meta.exporters"]
dbt = "my_plugin:DbtExporter"
```

```bash
pip install -e .
fabric-ai-meta export dbt "Sales Model" --workspace "Production"
```

The CLI auto-discovers the plugin. Full contract, worked example, conflict resolution rules: [`plugin-development.md`](plugin-development.md).

---

## Typical workflow paths

Different personas need different command sequences. Pick the one that matches you:

### Solo BI developer exploring the tool

```
1. Install                           pip install fabric-ai-meta
2. Try locally                       fabric-ai-meta analyze "Adventure Works" --mock
3. Try real workspace                fabric-ai-meta analyze "Your Model" --workspace ...
4. Export to your framework          fabric-ai-meta export openai "Your Model" --workspace ...
```

### Enterprise governance team

```
1. Install                           pip install fabric-ai-meta
2. Configure TOML                    write .fabric-ai-meta.toml
3. Bulk scan                         fabric-ai-meta scan --workspace ...
4. Governance report                 fabric-ai-meta governance --workspace ... --report ...
5. Wire into CI                      see docs/ci-cd-guide.md
6. Track over time                   fabric-ai-meta scan --baseline previous-summary.json
```

### AI engineer building agents

```
1. Install + LLM extra               pip install 'fabric-ai-meta[llm,mcp]'
2. Enrich the model                  fabric-ai-meta analyze "Your Model" --workspace ... --llm-enrich
3. Export for your framework         fabric-ai-meta export langchain "Your Model" --workspace ...
4. Or expose via MCP                 fabric-ai-meta serve  (then connect from your IDE)
```

### Fabric architect cleaning a model

```
1. Install + LLM + XMLA              pip install 'fabric-ai-meta[llm,xmla]'
2. Enrich descriptions               fabric-ai-meta analyze "Sales Model" --workspace ... --llm-enrich
3. Generate Prep for AI config       fabric-ai-meta export prep-for-ai "Sales Model" --workspace ... --llm-enrich
4. Preview writeback                 fabric-ai-meta apply-descriptions ./...config.json --mock
5. Commit writeback                  fabric-ai-meta apply-descriptions ./...config.json --workspace ... --no-dry-run
                                     (must run inside a Fabric notebook)
```

## Exporting Copilot artifacts (`export copilot`)

Microsoft Fabric stores Prep for AI primitives - AI Instructions, Verified Answers, AI Data Schema, example prompts, Copilot settings - in a `Copilot/` folder inside the semantic model. fabric-ai-meta v1.4.0 reads that folder via the Fabric REST `getDefinition` endpoint and writes it to your local disk in the same layout, so you can diff, version-control, and review it outside Fabric.

### When to use this

- You need a snapshot of every Copilot artifact across one or more models.
- You want to diff what changed between two Prep for AI configurations over time.
- You are preparing for the future `apply-copilot` writeback (round-trips will use these same files).

### Four-step workflow

1. **Inspect locally with a sidecar fixture.** No Fabric needed:

   ```bash
   fabric-ai-meta export copilot "Adventure Works" --mock
   ```

2. **Inspect a live model from inside a Fabric notebook.** Auth is automatic via `notebookutils`:

   ```bash
   fabric-ai-meta export copilot "Sales Model" --workspace "Production"
   ```

3. **Review the output tree.** The exporter writes:

   ```
   ./output/sales-model/copilot/
   ├── Instructions/instructions.md
   ├── VerifiedAnswers/<one .json per answer>
   ├── schema.json
   ├── examplePrompts.json
   ├── settings.json
   └── version.json
   ```

4. **Bring Copilot data into the broader analyze pipeline.** Add `--with-copilot` to `analyze` or `scan` to populate `SemanticModelMeta.copilot` alongside everything else:

   ```bash
   fabric-ai-meta analyze "Sales Model" --workspace "Production" --with-copilot
   fabric-ai-meta scan --workspace "Production" --with-copilot
   ```

### Limits

- Models with no Copilot configuration produce an empty bundle and the exporter prints a notice (no `copilot/` directory written).
- Outside a Fabric notebook, `--with-copilot` without `--mock` raises `FabricEnvironmentError`.

## Applying Copilot artifacts back to a model (`apply-copilot`, v1.5.0)

The inverse of `export copilot`. Reads a local `Copilot/` folder and writes it to a live semantic model through the Fabric REST `updateDefinition` long-running operation. Closes the read-edit-write loop for Prep for AI.

### When to use this

- You edited `Instructions/instructions.md` locally and want to push the change without manually re-uploading through the Power BI Service UI.
- You renamed or added Verified Answers and need the model to reflect the new set.
- You are version-controlling Copilot artifacts and want CI to apply the source-of-truth folder back on every merge.

### Three-step workflow

1. **Snapshot the live folder.** Either pull from the live model or start from a sidecar:

   ```bash
   fabric-ai-meta export copilot "Sales Model" --workspace "Production"
   ```

2. **Edit the local files.** Modify `Instructions/instructions.md`, add or delete `VerifiedAnswers/*.json`, refresh `schema.json`, etc.

3. **Dry-run, then apply.** Default is dry-run; nothing is written until you pass `--no-dry-run`.

   ```bash
   # Local preview against the mock writer (no service contact)
   fabric-ai-meta apply-copilot ./output/sales-model/copilot \
     --model "Sales Model" --workspace "Production" --mock

   # Real dry-run from inside a Fabric notebook (fetches current envelope, computes diff, does not write)
   fabric-ai-meta apply-copilot ./output/sales-model/copilot \
     --model "Sales Model" --workspace "Production"

   # Commit the changes via updateDefinition
   fabric-ai-meta apply-copilot ./output/sales-model/copilot \
     --model "Sales Model" --workspace "Production" --no-dry-run
   ```

### What gets written

- All `Copilot/` parts in the new folder replace the live model's `Copilot/` subtree.
- Any `Copilot/` part on the live model that is NOT in the local folder is deleted (full-replace semantics). To preserve a primitive, round-trip it through `export copilot` first.
- Non-Copilot parts of the model definition (TMDL under `definition/`, project metadata) are preserved byte-for-byte.

### Output

The command prints `DRY RUN`, `APPLIED`, or `FAILED`, followed by a per-primitive table of planned changes (operation: `create` / `update` / `delete`). Non-zero exit on errors during a real apply, so CI can detect failed writebacks.

### Track Copilot completeness across the workspace

`scan --with-copilot` and `governance --with-copilot` now include per-model and workspace-level Copilot signals:

```bash
fabric-ai-meta scan --workspace "Production" --with-copilot
fabric-ai-meta governance --workspace "Production" --with-copilot --report ./gov.json
```

The reports surface `models_without_ai_instructions`, `verified_answer_count`, `ai_data_schema_table_count`, and similar per model, plus workspace rollups. Use these to drive a governance bar like "every production model must have AI Instructions."

### Limits

- Refresh-latency warning for DirectQuery / Direct Lake models is not yet emitted. The Fabric REST write returns success on the metadata change itself; downstream cache invalidation is out of scope.
- The mock writer reports every primitive as `create` because it has no live envelope to diff against; in real mode you will see the full `create` / `update` / `delete` vocabulary.
