# Plugin Development Guide

fabric-ai-meta ships four built-in exporters (`langchain`, `openai`, `semantic-kernel`, `autogen`). Anyone can add more by publishing a Python package that registers a `BaseExporter` subclass under the `fabric_ai_meta.exporters` entry-point group. No fork required; install the plugin and it appears as `fabric-ai-meta export <name>`.

This guide walks through the contract, the entry-point registration, a complete worked example, and how plugins interact with the built-in registry.

---

## The `BaseExporter` contract

```python
from fabric_ai_meta import BaseExporter, SemanticModelMeta


class MyExporter(BaseExporter):
    name = "my-format"                  # CLI subcommand name; must be unique
    output_filename = "my-format.json"  # written under {output}/{model-slug}/
    description = "My custom format"    # shown in `export --help`

    def generate(self, model: SemanticModelMeta) -> dict:
        """Return a JSON-serializable dict produced from the model."""
        return {
            "model": model.name,
            "tables": [t.name for t in model.tables],
        }
```

That is the entire contract. `BaseExporter` provides a default `write(model, output_dir)` that serializes `generate()` as indented JSON. Override `write()` only if the exporter needs a non-JSON output (YAML, CSV, a directory tree, etc.).

What you get from `BaseExporter`:

- A consistent `SemanticModelMeta` input: every `model.tables[i]`, `model.relationships[i]`, `model.tables[i].measures[i]` is fully populated and has been classified and (optionally) LLM-enriched before your exporter runs.
- A standard output location: `BaseExporter.write()` slugifies the model name and writes under `{output_dir}/{slug}/{output_filename}`.
- CLI integration for free: once registered, `fabric-ai-meta export <name>` works with `--workspace` and `--mock` flags wired up automatically.

---

## Registering an entry point

Plugins are ordinary Python packages. Declare the entry point in your plugin's `pyproject.toml`:

```toml
[project]
name = "my-fabric-plugin"
version = "0.1.0"

[project.entry-points."fabric_ai_meta.exporters"]
my-format = "my_fabric_plugin:MyExporter"
```

The key on the left-hand side (`my-format`) is the CLI subcommand name and the registry key. The right-hand side is `module:attribute` pointing at your `BaseExporter` subclass.

When a user runs `pip install my-fabric-plugin`, the entry point is registered in their environment's metadata. fabric-ai-meta's `discover_exporters()` finds it via `importlib.metadata.entry_points(group="fabric_ai_meta.exporters")` on every CLI invocation.

---

## Worked example: a dbt source exporter

The example below is illustrative; no real dbt plugin ships with fabric-ai-meta. It emits a `sources:` block compatible with [dbt's source schema](https://docs.getdbt.com/reference/source-properties) so a downstream dbt project can reference Fabric tables.

**Project layout:**

```
my-fabric-dbt-plugin/
├── pyproject.toml
└── my_fabric_dbt_plugin/
    └── __init__.py
```

**`my_fabric_dbt_plugin/__init__.py`:**

```python
from fabric_ai_meta import BaseExporter, SemanticModelMeta


class DbtExporter(BaseExporter):
    name = "dbt"
    output_filename = "dbt-sources.yml"
    description = "dbt sources definition for a Fabric semantic model"

    def generate(self, model: SemanticModelMeta) -> dict:
        return {
            "version": 2,
            "sources": [
                {
                    "name": _safe(model.name),
                    "description": model.description or "",
                    "tables": [
                        {
                            "name": _safe(t.name),
                            "description": t.description or t.ai_description or "",
                            "columns": [
                                {
                                    "name": _safe(c.name),
                                    "description": c.description or c.ai_description or "",
                                    "data_type": c.data_type,
                                }
                                for c in t.columns
                            ],
                        }
                        for t in model.tables
                    ],
                }
            ],
        }


def _safe(name: str) -> str:
    return name.replace(" ", "_").lower()
```

**`pyproject.toml`:**

```toml
[project]
name = "my-fabric-dbt-plugin"
version = "0.1.0"
dependencies = ["fabric-ai-meta>=1.2.0"]

[project.entry-points."fabric_ai_meta.exporters"]
dbt = "my_fabric_dbt_plugin:DbtExporter"

[build-system]
requires = ["setuptools>=68.0"]
build-backend = "setuptools.build_meta"
```

**Install and use:**

```bash
cd my-fabric-dbt-plugin
pip install -e .

# The plugin now appears in --help
fabric-ai-meta export --help

# Run it like any built-in exporter
fabric-ai-meta export dbt "Adventure Works" --mock
```

The output lands at `./output/adventure-works/dbt-sources.yml` (or wherever `output.output_dir` points in `.fabric-ai-meta.toml`).

> **Output format note.** `BaseExporter.write()` writes JSON by default. The `DbtExporter` above returns a dict that happens to be valid YAML when serialized; to actually emit YAML you would override `write()` and use `yaml.safe_dump`. The example keeps the default write path for simplicity.

---

## Local testing

You do not need to publish to PyPI to test a plugin. From the plugin's source directory:

```bash
pip install -e .
fabric-ai-meta export <plugin-name> <model-name> --mock
```

The editable install registers the entry point in your virtualenv immediately. Subsequent edits to the plugin source take effect on the next `fabric-ai-meta` invocation.

To exercise the plugin from Python:

```python
from fabric_ai_meta import discover_exporters, get_exporter, MockExtractor

# Discover all registered exporters
registry = discover_exporters()
assert "dbt" in registry

# Or look up by name
DbtExporter = get_exporter("dbt")
model = MockExtractor().extract("Adventure Works", "Production Analytics")
payload = DbtExporter().generate(model)
```

---

## Name conflict resolution

When a plugin registers an exporter with the same `name` as a built-in (or another plugin), the **plugin wins**. This is intentional, not a bug: it lets users swap a bundled exporter for a customized version without forking fabric-ai-meta.

If two installed plugins both register the same name, the resolution order is whatever `importlib.metadata.entry_points` returns. We make no ordering guarantee between plugins. Plugin authors should choose distinct, namespaced names (`acme-langchain`, not `langchain`) to avoid clobbering each other.

To check what is actually registered in a given environment:

```python
from fabric_ai_meta import discover_exporters

for name, cls in discover_exporters().items():
    print(f"{name:20s} -> {cls.__module__}.{cls.__name__}")
```

---

## Error handling

Use `ExporterError` from `fabric_ai_meta.generator.base` (re-exported as `fabric_ai_meta.ExporterError`) to signal problems your `generate()` cannot recover from. The CLI surfaces the message and exits non-zero.

```python
from fabric_ai_meta import BaseExporter, ExporterError


class StrictExporter(BaseExporter):
    name = "strict"
    output_filename = "strict.json"

    def generate(self, model):
        if not model.tables:
            raise ExporterError("Model has no tables; cannot export.")
        return {"ok": True}
```

A broken plugin (raises at import time, fails to load, returns a non-class object) is **silently skipped** during discovery so it cannot break the registry for healthy exporters. Test your plugin with `pip install -e .` before publishing.

---

## What is out of scope

- **Plugins declare their own dependencies.** The base `fabric-ai-meta` install is only `click`, `rich`, `networkx`, and `pydantic`; anything else your exporter needs (an SDK, a serializer) belongs in your plugin's own `dependencies`, not assumed present.
- **No plugin marketplace.** Discoverability is just `pip search` and the entry-point group name.
- **No plugin verification or signing.** Use trusted plugins from sources you control. fabric-ai-meta loads any entry point under `fabric_ai_meta.exporters` in the current environment.
- **No CLI hooks beyond `export`.** Plugins extend the export surface only; `analyze`, `scan`, `score`, `governance`, `apply-descriptions`, `apply-copilot`, and `serve` are not pluggable.
- **No `export prep-for-ai` plugin slot.** The Prep for AI command has a custom signature (`--llm-enrich`, no positional model variants) and stays a hand-written CLI command, not a `BaseExporter` subclass.
