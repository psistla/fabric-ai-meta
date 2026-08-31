# fabric-ai-meta

![CI](https://github.com/psistla/fabric-ai-meta/actions/workflows/ci.yml/badge.svg)
[![PyPI Downloads](https://static.pepy.tech/personalized-badge/fabric-ai-meta?period=total&units=INTERNATIONAL_SYSTEM&left_color=GREY&right_color=RED&left_text=downloads)](https://pepy.tech/projects/fabric-ai-meta)
![Version](https://img.shields.io/badge/version-2.0.1-238636?style=flat-square)
![Tests](https://img.shields.io/badge/tests-686%20passing-1a7f37?style=flat-square)
![Python](https://img.shields.io/badge/python-3.10%2B-0550ae?style=flat-square)
![License](https://img.shields.io/badge/license-MIT-6e40c9?style=flat-square)

**Make any Power BI semantic model readable by AI, from your laptop.**

Point it at a `.pbip` folder and you get a classified schema, an AI readiness score, and framework-native exports for LangChain, OpenAI, Semantic Kernel, and AutoGen. No Fabric tenant, no notebook, no sign-in.

![pip install fabric-ai-meta, analyze a model, and get a scored, classified, AI-ready schema in 30 seconds](https://raw.githubusercontent.com/psistla/fabric-ai-meta/master/docs/assets/demo-core.gif)

![Install, pick a source, run a command, and feed the output to AI frameworks, writeback, or the new agent tools](https://raw.githubusercontent.com/psistla/fabric-ai-meta/master/docs/assets/developer-flow.svg)

## Who it's for

| You are | You get |
|---|---|
| A **BI developer** exploring a model | A local, classified schema and readiness score, no Fabric tenant needed |
| An **AI engineer** building on top of it | Framework-native exports, plus MCP tools an agent can query safely |
| A **governance team** watching many models | Cross-model drift, naming inconsistency, and duplicate-DAX detection at scale |
| A **Fabric architect** cleaning up a model | Auto-generated descriptions and a dry-run-first writeback path |

Full command sequence for each in the [user guide's workflow paths](https://github.com/psistla/fabric-ai-meta/blob/master/docs/user-guide.md#typical-workflow-paths).

## Try it

In Power BI Desktop: **File > Save As > .pbip**. Then:

```bash
pip install fabric-ai-meta
fabric-ai-meta analyze "Sales" --pbip ./Sales.SemanticModel
```

That reads the local TMDL, classifies every table and measure, scores the model, and writes `./output/sales/`:

```text
ai-ready-schema.json          # tables, measures, relationships, all classified
readiness-score.json          # {"score": 0.82}  <- how AI-ready this model is
langchain-tool.json           # drop straight into LangChain
openai-function.json          # and into OpenAI function calling
semantic-kernel-plugin.json   # and Semantic Kernel  (export autogen adds the fourth)
measure-dependency-graph.json
extraction-raw.json
```

It parses your DAX, so a `TOTALYTD(...)` measure comes back understood, not guessed:

```json
{ "name": "Sales YTD", "category": "time_intelligence", "requires_date_filter": true }
```

No model handy? `fabric-ai-meta analyze "Adventure Works" --mock` runs the same flow on bundled fixtures.

## Your models never leave your machine

Table names, measure logic, and business rules describe how your company works. You never have to trust this tool with any of it.

- **Local by default.** `--pbip` reads TMDL off your disk, `--mock` uses bundled fixtures. Neither touches a network or an account.
- **No telemetry.** The only outbound calls in the codebase go to the Fabric REST API and to the LLM provider you configure. Both are opt-in.
- **LLM enrichment is opt-in and capped.** Nothing is sent anywhere without `--llm-enrich`. You pick the provider (10+, including local Ollama), you supply the key, and `max_cost_per_run` stops an overspending run.
- **Writeback is dry-run by default.** `apply-descriptions` and `apply-copilot` show the diff and change nothing until you pass `--no-dry-run`.

Reaching a live workspace, to read it or to write back, is the only thing that needs Fabric, because the Fabric SDKs only exist in the notebook runtime. Everything else, analysis, scoring, and every export, runs anywhere Python does.

| Mode | Where it runs | Extractor | Auth |
|------|--------------|-----------|------|
| Fabric | Fabric notebook | `SemanticLinkExtractor` (needs `[fabric]`) | Ambient, automatic |
| Local `.pbip` | Any machine | `PbipExtractor` over local TMDL | None |
| Local / CI mock | Any machine | `MockExtractor` over fixture JSON | None |

## Commands

Every command takes `--pbip <folder>`, `--mock`, or `--workspace <name>`. Worked examples for all of them are in the [user guide](https://github.com/psistla/fabric-ai-meta/blob/master/docs/user-guide.md).

| Command | What it does |
|---------|--------------|
| `analyze` | Extract, classify, score, and export one model |
| `scan` | The same across a whole workspace or a Git Integration repo, plus `workspace-summary.json` |
| `score` | AI readiness score: description coverage, naming consistency, relationship completeness |
| `governance` | Cross-model naming inconsistencies, duplicate DAX under different names, readiness ranking |
| `export` | `langchain`, `openai`, `semantic-kernel`, `autogen`, `prep-for-ai`, `copilot`, `capability-manifest`, `agent-readiness`, or [your own plugin](https://github.com/psistla/fabric-ai-meta#custom-exporters) |
| `auth` | `login`, `status`, `logout` for local Entra sign-in (requires `[fabric]`) |
| `apply-descriptions` | Push generated descriptions to a live model through XMLA / TOM |
| `apply-copilot` | Push an edited `Copilot/` folder back through the Fabric REST API |
| `diff` | Compare two workspace scans: score changes, models added or removed, regressions |
| `serve` | MCP server exposing eight tools, so your IDE agent can answer questions about your models directly |

Add `--llm-enrich` to any extraction command to fill in missing descriptions and detect fact-table grain. It is off unless you ask, [cost-capped, and works with 10+ providers](https://github.com/psistla/fabric-ai-meta/blob/master/docs/user-guide.md#7-turn-on-llm-enrichment-fill-in-the-gaps) including a local Ollama.

Before funding a knowledge-graph project: `governance --graph-necessity` scores whether your star schema already answers real questions without one, so you're not building infrastructure the model doesn't need. Verdict tiers and the scoring signals are in the [user guide](https://github.com/psistla/fabric-ai-meta/blob/master/docs/user-guide.md#do-you-even-need-an-ontology---graph-necessity).

## Built for an agent to query safely

An agent writing DAX against your model can't see the traps an analyst would catch on sight: a semi-additive measure summed across time, a ratio averaged instead of recomputed, a column that means something different than its name suggests. Three tools close that gap.

- **`guide_query` (MCP).** Guidance to read before writing one query: the correct measure, a safe join path, and warnings for semi-additive, ratio, hardcoded-literal, or calculation-group traps.
- **`export capability-manifest`.** The same warnings for the whole model, read once instead of discovered query by query. Every measure comes back `answerable`, `answerable_with_caveats`, or `refused`.
- **`export agent-readiness`.** A ranked list of what's currently blocking clean answers, undescribed objects, ambiguous names, missing relationships, each paired with a fix.

![capability-manifest flags a semi-additive balance measure that must not be summed across time, then agent-readiness ranks what blocks clean answers](https://raw.githubusercontent.com/psistla/fabric-ai-meta/master/docs/assets/demo-agent-safety.gif)

```bash
fabric-ai-meta export agent-readiness "Contoso Sales" --mock --output ./output
```

```json
{
  "type": "ambiguous_name",
  "table": "FactSales",
  "column": "Customer_Key",
  "message": "Column name 'Customer_Key' is inconsistent (underscore, all-caps abbreviation, or too short).",
  "fix": "Rename 'Customer_Key' to a clear, consistent name."
}
```

## Why this exists

Microsoft's AI features for semantic models (Prep for AI, Copilot descriptions, Data Agents, Fabric IQ Ontology) share three limits. Prep for AI is configured by hand, one model at a time, with no bulk API. Nothing exports outside Fabric, so a LangChain or function-calling pipeline starts blind. And nothing compares models, so `Total Sales` in one and `Sum of Sales` in another stay invisibly identical.

This is not a replacement for those tools. It is an automation layer on top of them and a bridge to the AI ecosystem outside Fabric.

## Library API

```python
from fabric_ai_meta import MockExtractor, score_model, generate_ai_ready_schema, to_openai_function

model = MockExtractor().extract("Adventure Works", "Production Analytics")
score, breakdown = score_model(model)
schema = generate_ai_ready_schema(model)
openai_fn = to_openai_function(model)
```

51 public exports; see `fabric_ai_meta.__all__`.

### Custom exporters

Subclass `BaseExporter`, register it under the `fabric_ai_meta.exporters` entry point group, and it appears as `fabric-ai-meta export <name>` with the same flags as the built-ins. No fork needed. Worked dbt example: [`docs/plugin-development.md`](https://github.com/psistla/fabric-ai-meta/blob/master/docs/plugin-development.md).

## Docs

| | |
|---|---|
| [User guide](https://github.com/psistla/fabric-ai-meta/blob/master/docs/user-guide.md) | Every capability from install to writeback, with persona-mapped paths |
| [`notebooks/quickstart.ipynb`](https://github.com/psistla/fabric-ai-meta/blob/master/notebooks/quickstart.ipynb) | The same tour inside a Fabric runtime |
| [CI/CD guide](https://github.com/psistla/fabric-ai-meta/blob/master/docs/ci-cd-guide.md) | Enforce governance thresholds on every PR, with ready-to-paste workflows |
| [Plugin development](https://github.com/psistla/fabric-ai-meta/blob/master/docs/plugin-development.md) | Ship your own exporter |
| [`schemas/`](https://github.com/psistla/fabric-ai-meta/tree/master/schemas) | JSON Schema for every output file |

## Contributing

Issues and pull requests welcome. Before opening one:

```bash
pip install -e ".[dev]"
pytest tests/ -q     # 686 tests, no Fabric runtime or network needed
ruff check .
```

New exporters ship as [plugins](https://github.com/psistla/fabric-ai-meta#custom-exporters) rather than PRs here. Sample models under `src/fabric_ai_meta/fixtures/` and doc fixes are the easiest first contributions.

If this saved you time, star the repository. That is the signal I use to decide what to build next.

## License

MIT. See [LICENSE](https://github.com/psistla/fabric-ai-meta/blob/master/LICENSE).

Built by [Prasanth Sistla](https://github.com/psistla). Not affiliated with, endorsed by, or sponsored by Microsoft. "Microsoft Fabric", "Power BI", and "Copilot" are trademarks of Microsoft Corporation.
