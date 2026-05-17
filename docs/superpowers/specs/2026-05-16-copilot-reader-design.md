# CopilotReader and `export copilot` — Design

**Status:** Approved by user, pending implementation
**Target release:** v1.4.0
**Date:** 2026-05-16
**Author:** Brainstorming session with Prasanth Sistla

---

## Problem

`fabric-ai-meta`'s tagline is "Automates Prep for AI." Today the project ships `apply-descriptions`, which writes only table and column descriptions to a semantic model through XMLA / TOM. The actual Prep for AI primitives that Microsoft Fabric exposes — **AI Instructions, AI Data Schema, Verified Answers, example prompts, Copilot settings** — still require manual UI work, one model at a time.

A prior research spike (`notebooks/tmdl-spike.ipynb` + `docs/research/tmdl-prep-for-ai-spike.md`) proved these primitives live in a `Copilot/` folder sibling to `definition/` inside a semantic model and are accessible through the Fabric REST API endpoints `getDefinition` / `updateDefinition`. The spike landed a read-only `TMDLClient.get_definition()` and a snippet-level `find_prep_for_ai_settings()`. The full read/write cycle is unbuilt.

This design covers the **read half**: structured access to all Copilot primitives, surfaced as typed Python objects plus a CLI dump. The write half (`CopilotWriter` and `apply-copilot`) is explicitly out of scope and follows in a later release.

## Goals

1. Surface every Copilot/ primitive as a Python object usable in library code.
2. Provide a CLI command that writes the Copilot/ payload to disk in Microsoft's native folder layout.
3. Provide a fixture-driven test path so contributors can exercise the parser without a live Fabric model.
4. Keep backward compatibility with the existing `TMDLClient.find_prep_for_ai_settings()` used by the spike notebook.
5. Land in one release without forcing existing callers to change.

## Non-Goals

- `updateDefinition` calls (write path).
- Long-running operation polling.
- Write-permission probing.
- Storage-mode-based refresh-latency warnings.
- Round-trip preservation of non-Copilot parts.
- Native typed schemas for every JSON primitive — Microsoft has not published a schema, and we will not invent one beyond the high-confidence fields.

All five live in the future `CopilotWriter` design.

## Decisions (locked through brainstorming)

| # | Decision | Rationale |
|---|----------|-----------|
| 1 | **Hybrid typing**: dataclasses with a `raw: dict` escape hatch on every JSON primitive. AI Instructions also keeps `raw_bytes`. | Honest about uncertainty in undocumented JSON shapes; typed access for high-confidence fields; adding inferred fields later is non-breaking. |
| 2 | **CLI placement**: new `copilot` exporter inside the existing `export` group, registered via `BaseExporter`. | Mirrors the `export prep-for-ai` pattern; reuses dynamic exporter registry; users discover it via `fabric-ai-meta export --help`. |
| 3 | **`SemanticModelMeta.copilot`**: new optional field. | Lets `CopilotExporter.generate(model)` follow the standard exporter contract without bypassing the model abstraction. |
| 4 | **Extraction timing**: opt-in `--with-copilot` flag on `analyze` / `scan`. Default off. Extractor reads from Fabric REST via `TMDLClient.get_definition` (Fabric mode) or sidecar fixture (`--mock`). | Avoids paying a Fabric REST call cost on every existing `analyze`. Default-off keeps the v1.3.x performance contract. |
| 5 | **Fixture format**: sidecar file `<model>.copilot.json` containing the **raw `getDefinition` envelope** (not a hand-shaped Copilot bundle). | Exercises the production parsing path; captures Microsoft payload-shape drift in CI; first sidecar is captured from a real model, later ones can be hand-authored. |
| 6 | **Output layout**: mirror Microsoft's `Copilot/` folder verbatim under `./output/<slug>/copilot/`. | Makes the future `apply-copilot` round-trip trivial (same paths in, same paths out); each primitive diffs cleanly; matches what the spike doc documents. |
| 7 | **Backward compat**: keep `TMDLClient.find_prep_for_ai_settings()` returning its current snippet-dict shape. No deprecation warning. | The function is 3 weeks old, the spike notebook is its only caller, and forcing a churn for a parallel API would break the notebook silently. |
| 8 | **`BaseExtractor.extract` ABI**: extend with kw-only `with_copilot: bool = False` at the ABC level. | No `fabric_ai_meta.extractors` entry-point group exists today, so no third-party `BaseExtractor` subclasses to break. Kw-only + default False keeps all in-tree callers source-compatible. Documented as an additive change. |
| 9 | **AI Instructions Markdown decode policy**: attempt strict UTF-8 first. On `UnicodeDecodeError`, fall back to `errors="replace"` and `logging.warning()` the path. `raw_bytes` is always preserved verbatim regardless of decode outcome. | Gives a strong round-trip guarantee for the common case (well-formed UTF-8) while tolerating corrupt payloads without crashing the reader. `raw_bytes` is the source of truth for any future writer. |
| 10 | **`VerifiedAnswer.filename`**: stores the **basename** only (e.g., `"answer-001.json"`), not the full part path. | The exporter writes `va_dir / va.filename` and only basenames are safe inside the `VerifiedAnswers/` directory. The reader strips the `Copilot/VerifiedAnswers/` prefix during parse. |
| 11 | **`CopilotExporter.output_filename = ""`** + fully overridden `write()`. | The default `BaseExporter.write()` enforces `output_filename` is non-empty and writes a single JSON file. CopilotExporter writes a directory tree, so it overrides `write()` entirely and never calls `super().write()`. The empty `output_filename` documents that the field is intentionally unused. |
| 12 | **`CopilotBundle.to_dict()` shape**: omits `raw_bytes`; emits `markdown` as a string field. | `to_dict()` exists for JSON serialization (e.g., schema validation, future workspace-summary inclusion). Binary `raw_bytes` is not JSON-friendly. The in-memory bundle retains both `markdown` and `raw_bytes`; serialization keeps only `markdown`. Round-trip strictness is an in-memory guarantee, not a serialization guarantee. |

## Architecture

### Module Layout

```
src/fabric_ai_meta/
├── models/
│   ├── metadata.py                          # MODIFIED: SemanticModelMeta.copilot: CopilotBundle | None = None
│   └── copilot.py                           # NEW: CopilotBundle + sub-dataclasses
├── extractor/
│   ├── base.py                              # MODIFIED: extract() gains with_copilot: bool = False (kw-only)
│   ├── mock.py                              # MODIFIED: read <fixture>.copilot.json when with_copilot=True
│   └── semantic_link.py                     # MODIFIED: call TMDLClient.get_definition + parse Copilot/ when with_copilot=True
├── generator/
│   ├── copilot_reader.py                    # NEW: CopilotReader (pure parser, no network)
│   └── export_copilot.py                    # NEW: CopilotExporter (BaseExporter subclass, overrides write())
└── cli.py                                   # MODIFIED: --with-copilot on analyze/scan; export copilot auto-registers; implicit with_copilot for export copilot

tests/
├── fixtures/
│   ├── adventure_works.copilot.json         # NEW: sanitized raw getDefinition envelope, all six primitives
│   └── enterprise_sales.copilot.json        # NEW: larger envelope with 3+ Verified Answers
├── test_copilot_reader.py                   # NEW (~12 tests)
├── test_export_copilot.py                   # NEW (~8 tests)
└── test_extractor.py                        # MODIFIED (~5 new tests for with_copilot path)
```

Unchanged: `writeback/tmdl_client.py`. Existing `find_prep_for_ai_settings()` keeps its current shape and continues to back the spike notebook.

### Data Model (`models/copilot.py`)

```python
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any


@dataclass
class AIInstructions:
    """Copilot/Instructions/instructions.md content."""
    markdown: str
    raw_bytes: bytes                       # undecoded payload, for byte-perfect round-trip later


@dataclass
class VerifiedAnswer:
    """One file under Copilot/VerifiedAnswers/."""
    filename: str                          # original filename inside VerifiedAnswers/
    question: str | None                   # best-effort extraction
    raw: dict[str, Any]                    # full parsed JSON


@dataclass
class AIDataSchema:
    """Copilot/schema.json."""
    raw: dict[str, Any]                    # entire JSON, untyped until shape verified


@dataclass
class ExamplePrompts:
    """Copilot/examplePrompts.json."""
    prompts: list[str]                     # best-effort extraction if shape is a flat list
    raw: dict[str, Any] | list[Any]


@dataclass
class CopilotSettings:
    """Copilot/settings.json."""
    raw: dict[str, Any]


@dataclass
class CopilotVersion:
    """Copilot/version.json."""
    raw: dict[str, Any]


@dataclass
class CopilotBundle:
    """All Prep for AI primitives for one semantic model.

    Every field is optional; a model may have AI Instructions but no Verified
    Answers, or vice versa. Empty fields stay None / [].
    """
    ai_instructions: AIInstructions | None = None
    verified_answers: list[VerifiedAnswer] = field(default_factory=list)
    ai_data_schema: AIDataSchema | None = None
    example_prompts: ExamplePrompts | None = None
    settings: CopilotSettings | None = None
    version: CopilotVersion | None = None

    def to_dict(self) -> dict:
        """JSON-serializable view. Omits AIInstructions.raw_bytes (not JSON-safe).
        Shape:
          {
            "ai_instructions": {"markdown": "..."} | None,
            "verified_answers": [{"filename": "...", "question": "...", "raw": {...}}, ...],
            "ai_data_schema": {"raw": {...}} | None,
            "example_prompts": {"prompts": [...], "raw": {...}} | None,
            "settings": {"raw": {...}} | None,
            "version": {"raw": {...}} | None,
          }
        """
```

**Parser strictness.** `CopilotReader._parse_*` use **duck typing**, not strict key presence checks. Each parser tries best-effort extraction of high-confidence fields (e.g., `question` from a Verified Answer) and falls back to leaving the typed field `None` while keeping the full payload in `raw`. A parser raises only on hard structural failure (e.g., the `payload` is not valid base64, or the decoded bytes are not valid JSON for a primitive that requires JSON). Hard failures are caught one level up by `CopilotReader.from_definition`, which logs a warning with the part path and continues parsing the remaining parts. This matches the "read paths are lenient" rule under Error Handling.

`SemanticModelMeta` gains exactly one new optional field:

```python
@dataclass
class SemanticModelMeta:
    ...
    copilot: CopilotBundle | None = None   # NEW, defaults None — backward compat
```

### Reader (`generator/copilot_reader.py`)

```python
class CopilotReader:
    """Pure parser. No network calls. No auth. Stateless."""

    @staticmethod
    def from_definition(definition: dict) -> CopilotBundle:
        """Parse a getDefinition response into a CopilotBundle.

        Walks the parts list, dispatches each Copilot/ part to a primitive
        parser based on path prefix (reuses COPILOT_PATH_PREFIXES from
        writeback.tmdl_client). Returns a CopilotBundle with fields
        populated where the corresponding parts exist, None / [] otherwise.
        """

    # Per-primitive parsers (private, pure):
    @staticmethod
    def _parse_ai_instructions(part: dict) -> AIInstructions: ...
    @staticmethod
    def _parse_verified_answer(part: dict) -> VerifiedAnswer: ...
    @staticmethod
    def _parse_ai_data_schema(part: dict) -> AIDataSchema: ...
    @staticmethod
    def _parse_example_prompts(part: dict) -> ExamplePrompts: ...
    @staticmethod
    def _parse_copilot_settings(part: dict) -> CopilotSettings: ...
    @staticmethod
    def _parse_copilot_version(part: dict) -> CopilotVersion: ...
```

Static + pure design enables fixture-driven testing with zero mocking. The reader takes a dict and returns a bundle. Network and auth live in `TMDLClient`. Reader lives under `generator/` (not `writeback/`) because `writeback/` is reserved for code that mutates Fabric state.

### Extractor Wiring

`BaseExtractor.extract` signature changes from:

```python
def extract(self, model_name: str, workspace: str) -> SemanticModelMeta: ...
```

to:

```python
def extract(self, model_name: str, workspace: str, *, with_copilot: bool = False) -> SemanticModelMeta: ...
```

Keyword-only `with_copilot` with default `False`. Existing in-tree callers pass two positional args and are unaffected.

#### `MockExtractor.extract(model_name, workspace=None, *, with_copilot=False)`

Two extractor modes already exist (`fixture_path` for one model, `fixture_dir` for many). Sidecar resolution must cover both:

```python
def _sidecar_path_for_fixture(fixture_file: str) -> str:
    """Return /abs/path/to/<base>.copilot.json next to the model fixture."""
    base, _ext = os.path.splitext(fixture_file)
    return base + ".copilot.json"

# fixture_path mode:
fixture_file = self.fixture_path

# fixture_dir mode (after matching the right *.json by slugified name):
fixture_file = fpath   # the matched *.json file inside fixture_dir

# Common post-load step:
model = from_dict(data)
if with_copilot:
    sidecar = _sidecar_path_for_fixture(fixture_file)
    if os.path.exists(sidecar):
        with open(sidecar, "r", encoding="utf-8") as f:
            envelope = json.load(f)
        model.copilot = CopilotReader.from_definition(envelope)
    # absence of sidecar is not an error — model.copilot stays None
return model
```

#### `SemanticLinkExtractor.extract(model_name, workspace=None, *, with_copilot=False)`

After the existing extraction logic builds `model`, append:

```python
if with_copilot:
    model.copilot = self._extract_copilot(model_name, ws)
return model

def _extract_copilot(self, model_name: str, workspace: str) -> CopilotBundle | None:
    """Fetch and parse the Copilot/ folder for the model. Returns None on
    missing GUIDs (workspace or model not resolvable)."""
    fabric = self._fabric
    workspace_id = fabric.resolve_workspace_id(workspace)
    if workspace_id is None:
        logger.warning("Cannot resolve workspace id for %r; skipping Copilot extract.", workspace)
        return None
    model_id = fabric.resolve_item_id(model_name, type="SemanticModel", workspace=workspace)
    if model_id is None:
        logger.warning("Cannot resolve model id for %r; skipping Copilot extract.", model_name)
        return None
    token = self._fabric_bearer_token()
    from ..writeback.tmdl_client import TMDLClient
    client = TMDLClient(token, workspace_id)
    envelope = client.get_definition(model_id)
    return CopilotReader.from_definition(envelope)

def _fabric_bearer_token(self) -> str:
    """Obtain a Power BI / Fabric bearer token from the Fabric notebook runtime."""
    import notebookutils  # type: ignore[import-not-found]  # only available in Fabric
    return notebookutils.credentials.getToken("pbi")
```

**Notes on this path:**

- `fabric.resolve_workspace_id` and `fabric.resolve_item_id` are the canonical sempy.fabric helpers for name → GUID lookup. Both return `None` (or raise) when the name does not exist in the runtime. Resolution failures are non-fatal: they log a warning and leave `model.copilot = None`. Existing tabular extraction (tables / measures / relationships) is untouched.
- `TMDLClient.__init__(credential, workspace_id)` accepts a bearer token **string** directly (per its existing `_get_token` helper, which short-circuits for `isinstance(credential, str)`). No `azure.identity` token-acquisition flow needed inside Fabric.
- Outside Fabric, `--with-copilot` without `--mock` raises `FabricEnvironmentError` from the existing notebook detection at extractor construction time. `_fabric_bearer_token()` therefore only runs in environments where `notebookutils` is importable.

### Exporter (`generator/export_copilot.py`)

`BaseExporter.write()` actual signature in `src/fabric_ai_meta/generator/base.py`:

```python
def write(self, model: SemanticModelMeta, output_dir: str) -> str: ...
```

It uses module-level `_slugify(model.name)` for the per-model subdir. `SemanticModelMeta` has no `slug` attribute; that's a derived value. `CopilotExporter` must match the same signature and slug derivation:

```python
import json
import os
from fabric_ai_meta.generator.base import BaseExporter, ExporterError, _slugify
from fabric_ai_meta.models.metadata import SemanticModelMeta

class CopilotExporter(BaseExporter):
    name = "copilot"
    output_filename = ""                    # intentionally unused; write() is fully overridden
    description = "Microsoft Copilot/ folder mirror (AI Instructions, Verified Answers, AI Data Schema, etc.)"

    def generate(self, model: SemanticModelMeta) -> dict:
        """JSON-serializable view of the bundle (no raw_bytes). Used by tests and
        future schema validation; not used by write()."""
        if model.copilot is None:
            raise ExporterError(
                "model.copilot is None. Re-run extract with with_copilot=True "
                "(CLI: --with-copilot, or use `fabric-ai-meta export copilot`)."
            )
        return model.copilot.to_dict()

    def write(self, model: SemanticModelMeta, output_dir: str) -> str:
        """Mirror Microsoft's Copilot/ folder layout verbatim under
        {output_dir}/{slug}/copilot/. Returns the absolute path of the copilot/
        directory, or an empty string if the bundle had no parts to write."""
        if model.copilot is None:
            raise ExporterError(
                "model.copilot is None. Re-run extract with with_copilot=True."
            )

        slug = _slugify(model.name) if model.name else "model"
        copilot_dir = os.path.join(output_dir, slug, "copilot")
        b = model.copilot

        wrote_anything = False

        if b.ai_instructions is not None:
            instr_dir = os.path.join(copilot_dir, "Instructions")
            os.makedirs(instr_dir, exist_ok=True)
            with open(os.path.join(instr_dir, "instructions.md"), "wb") as f:
                f.write(b.ai_instructions.raw_bytes)
            wrote_anything = True
        if b.ai_data_schema is not None:
            os.makedirs(copilot_dir, exist_ok=True)
            with open(os.path.join(copilot_dir, "schema.json"), "w", encoding="utf-8") as f:
                json.dump(b.ai_data_schema.raw, f, indent=2)
            wrote_anything = True
        if b.example_prompts is not None:
            os.makedirs(copilot_dir, exist_ok=True)
            with open(os.path.join(copilot_dir, "examplePrompts.json"), "w", encoding="utf-8") as f:
                json.dump(b.example_prompts.raw, f, indent=2)
            wrote_anything = True
        if b.settings is not None:
            os.makedirs(copilot_dir, exist_ok=True)
            with open(os.path.join(copilot_dir, "settings.json"), "w", encoding="utf-8") as f:
                json.dump(b.settings.raw, f, indent=2)
            wrote_anything = True
        if b.version is not None:
            os.makedirs(copilot_dir, exist_ok=True)
            with open(os.path.join(copilot_dir, "version.json"), "w", encoding="utf-8") as f:
                json.dump(b.version.raw, f, indent=2)
            wrote_anything = True
        if b.verified_answers:
            va_dir = os.path.join(copilot_dir, "VerifiedAnswers")
            os.makedirs(va_dir, exist_ok=True)
            for va in b.verified_answers:
                # va.filename is basename only (no Copilot/VerifiedAnswers/ prefix)
                with open(os.path.join(va_dir, va.filename), "w", encoding="utf-8") as f:
                    json.dump(va.raw, f, indent=2)
            wrote_anything = True

        return copilot_dir if wrote_anything else ""
```

The default `BaseExporter.write()` dumps `generate()` as one JSON file. Copilot output is a directory tree, so `write()` is fully overridden and never calls `super().write()`. `output_filename` stays empty as a documentation signal that the field is unused; the parent's emptiness check never fires because we don't enter the parent's `write()`.

Return contract: `write()` returns the absolute path of the copilot/ directory on success, or an empty string when the bundle had nothing to write (no primitives). The CLI handler treats an empty return as a notice condition.

### CLI

User-visible commands:

```bash
# Existing analyze gains opt-in flag
fabric-ai-meta analyze MODEL --workspace W --with-copilot
fabric-ai-meta analyze MODEL --workspace W --with-copilot --mock

# Existing scan gains opt-in flag
fabric-ai-meta scan --workspace W --with-copilot

# NEW: export copilot
fabric-ai-meta export copilot MODEL --workspace W                  # writes ./output/<slug>/copilot/...
fabric-ai-meta export copilot MODEL --workspace W --mock           # uses sidecar fixture
fabric-ai-meta export copilot MODEL --workspace W --output ./snapshot
```

**Concrete CLI plumbing changes** (matching actual `src/fabric_ai_meta/cli.py` shapes):

1. **`_run_analysis`** (used by `analyze`) gains `with_copilot: bool = False` parameter. The `analyze` Click command adds `@click.option("--with-copilot", is_flag=True, default=False, help="Also fetch the Copilot/ folder via Fabric REST getDefinition.")` and threads `with_copilot=with_copilot` into `_run_analysis`. Inside `_run_analysis`, the single call site `extractor.extract(model_name, workspace)` becomes `extractor.extract(model_name, workspace, with_copilot=with_copilot)`.

2. **`scan` command** gets the same `--with-copilot` flag. The inner loop's `extractor.extract(name, workspace)` becomes `extractor.extract(name, workspace, with_copilot=with_copilot)`. Empty bundles do not contribute to the workspace summary in v1.4.0 (deferred until governance signals are defined for Copilot artifacts).

3. **`_export_single(model_name, workspace, exporter, mock=False)`** gains `with_copilot: bool = False`. The body's `extractor.extract(model_name, workspace)` becomes `extractor.extract(model_name, workspace, with_copilot=with_copilot)`. The success print is unchanged; if `exporter.write(...)` returns an empty string (CopilotExporter signaling "nothing written"), the handler prints `[yellow]No Copilot/ parts in model definition. Nothing exported.[/yellow]` instead of `[green]Written:[/green] {path}`.

4. **`_register_exporter_commands()`** — the shared template that turns every discovered `BaseExporter` into a Click command — is extended to set `with_copilot=True` only when `ep_name == "copilot"`:

   ```python
   def _make_cmd(exporter_cls=exporter_cls, ep_name=ep_name):
       @click.command(name=ep_name, help=exporter_cls.description or f"Export {ep_name} format.")
       @click.argument("model_name")
       @click.option("--workspace", "-w", default=None)
       @click.option("--mock", is_flag=True, default=False,
                     help="Use MockExtractor with fixture data.")
       def _cmd(model_name, workspace, mock):
           _export_single(
               model_name, workspace, exporter_cls(),
               mock=mock,
               with_copilot=(ep_name == "copilot"),
           )
       return _cmd
   ```

   This is the "implicit `with_copilot=True` for `copilot`" behavior. Other built-in exporters (`langchain`, `openai`, `semantic-kernel`, `autogen`) keep their existing behavior unchanged (`with_copilot=False`). Plugin exporters likewise stay at `False` — if a future plugin wants Copilot data, the user can run `analyze --with-copilot` first to populate the bundle, then export. (Plugin-driven implicit copilot is out of scope.)

**`export prep-for-ai`** at cli.py L515 is **not** modified in v1.4.0. Its current behavior is preserved. A later release may add an option to fold Copilot artifacts into the Prep for AI config bundle once we know what that integration should look like.

**`apply-descriptions`** at cli.py — also unmodified in v1.4.0. Copilot writeback is the separate future `apply-copilot` work.

### Output Tree

```
./output/adventure-works/
├── ai-ready-schema.json                   # existing
├── ...                                    # other existing exports
└── copilot/                               # NEW (only with --with-copilot or export copilot)
    ├── Instructions/
    │   └── instructions.md
    ├── VerifiedAnswers/
    │   ├── answer-001.json
    │   └── answer-002.json
    ├── schema.json
    ├── examplePrompts.json
    ├── settings.json
    └── version.json
```

## Error Handling

| Failure mode | Behavior |
|--------------|----------|
| `--with-copilot --mock` but no sidecar file | `model.copilot = None`. No error. (Absence ≠ failure.) |
| `--with-copilot` outside Fabric, no `--mock` | `FabricEnvironmentError` from existing detection. |
| `getDefinition` HTTP error (auth, 404, 403) | `TMDLClient` raises `RuntimeError` with HTTP code + body. Propagates. Not caught. |
| Sidecar JSON malformed | `json.JSONDecodeError`. Not caught. Loud failure. |
| Sidecar exists but has no `Copilot/` parts | `model.copilot = CopilotBundle()` (all None / empty). Distinguishes "empty Copilot" from "never tried." |
| Per-primitive parse failure inside an envelope | Skip the bad part, `logging.warning()` the path, parse the rest. Don't fail the whole bundle. |
| `export copilot` called with empty bundle | Writes nothing, prints notice "No Copilot/ parts in model definition. Nothing exported." Exit 0. |

Read paths are **lenient**: a partial bundle is more useful than a hard fail. Write paths (future `CopilotWriter`) will be strict.

## Testing

Approximately 25 new tests across three files plus two fixtures.

**`tests/test_copilot_reader.py`** (~12 tests):

- Empty envelope → `CopilotBundle()` with all None / [].
- Envelope with only AI Instructions → only `ai_instructions` populated.
- Envelope with all six primitives → all fields populated.
- Multiple VerifiedAnswers → list ordered by filename.
- Malformed VerifiedAnswer JSON inside envelope → skipped, warning logged, rest parsed.
- AI Instructions Markdown round-trips: `raw_bytes` decode equals `markdown`.
- Non-Copilot parts (TMDL, `.platform`) ignored.
- `payloadType != "InlineBase64"` parts skipped.
- Each primitive parser tested individually with a minimal fixture.
- `CopilotBundle.to_dict()` produces JSON-serializable output.

**`tests/test_export_copilot.py`** (~8 tests):

- Empty bundle → no files written, exit 0 with notice.
- Full bundle → correct directory tree on disk.
- VerifiedAnswers preserve original filenames.
- `instructions.md` written as raw bytes (not re-encoded).
- `generate()` raises `ExporterError` when `model.copilot is None`.
- CLI: `export copilot Adventure --mock` populates `model.copilot` implicitly.
- CLI: `export copilot` for model without sidecar fixture → exit 0 with notice.
- Exporter registers as `copilot` in `discover_exporters()`.

**`tests/test_extractor.py` additions** (~5 tests):

- `MockExtractor.extract(..., with_copilot=True)` with sidecar → bundle populated.
- `MockExtractor.extract(..., with_copilot=True)` no sidecar → `copilot=None`.
- `MockExtractor.extract(..., with_copilot=False)` ignores sidecar.
- `SemanticLinkExtractor.extract(..., with_copilot=True)` calls `TMDLClient.get_definition` (mocked) and parses.
- Existing `extract()` callers (`with_copilot` defaulted False) unchanged — backward compat regression.

**Fixtures:**

- `tests/fixtures/adventure_works.copilot.json`: hand-authored raw envelope with all six primitives, modest size, no real data. Doubles as the canonical "what `getDefinition` returns" reference.
- `tests/fixtures/enterprise_sales.copilot.json`: similar, larger, includes 3+ Verified Answers.

## Documentation Changes

- **README**: Update Notebooks table caption for `tmdl-spike.ipynb` (mention CopilotReader is now shipped on top of the spike findings). Add `export copilot` row to the per-command `<details>` index under Usage. Add `--with-copilot` to relevant command snippets.
- **CHANGELOG**: `[1.4.0]` entry describing `CopilotBundle`, `CopilotReader`, `export copilot`, and `--with-copilot`.
- **CLAUDE.md**: Add v1.4.0 bullet to Current State. Bump test count. Update Module Map for new files.
- **docs/user-guide.md**: New section "Exporting Copilot artifacts" with the four-step workflow (extract → bundle → export → inspect). Cross-link from the Fabric Architect persona path.

## Versioning

- Minor bump per project convention: **v1.3.5 → v1.4.0**. Reason: new public CLI command + new public Python API (`CopilotBundle`, `CopilotReader`, `CopilotExporter`, `SemanticModelMeta.copilot` field) = minor, not patch.
- `__all__` count grows from 35 to 40 (5 new top-level exports: `CopilotBundle`, `AIInstructions`, `VerifiedAnswer`, `AIDataSchema`, `CopilotReader`). The narrower dataclasses `ExamplePrompts`, `CopilotSettings`, `CopilotVersion` are intentionally **not** re-exported at the package top level — they are reachable through `CopilotBundle` fields and `from fabric_ai_meta.models.copilot import ...` but kept out of the public top-level surface to avoid name-pollution for what are essentially shape-only wrappers around `raw: dict`. Promotable in a future release if real consumers emerge.

## Out of Scope (Tracked for Future Work)

- `CopilotWriter`: writes back to `Copilot/` via `updateDefinition`.
- `apply-copilot` CLI: read → mutate → write workflow.
- LRO polling for 202 responses from `updateDefinition`.
- Write-permission probe before mutating.
- Refresh-latency warnings for DirectQuery / Direct Lake models.
- Round-trip preservation of non-Copilot parts (TMDL + project metadata).
- Typed schema discovery for AI Data Schema and Verified Answers once Microsoft publishes one.
- LLM enrichment for Copilot primitives (e.g., generate AI Instructions Markdown via `--llm-enrich`).

These are blocked on this design landing first.

## Open Questions

1. **sempy.fabric helper names.** The spec assumes `fabric.resolve_workspace_id(workspace)` and `fabric.resolve_item_id(model_name, type="SemanticModel", workspace=...)` are the right helpers. These names follow the sempy.fabric convention but are not yet verified against the version pinned in `pyproject.toml` (`semantic-link-sempy>=0.8`). If the API differs in 0.8, `_extract_copilot` substitutes the actual helper. This is verifiable in the writing-plans phase against the installed `sempy.fabric` package; not a blocker for design approval.

2. **What `scan --with-copilot` adds to `workspace-summary.json`.** v1.4.0 ships `--with-copilot` on `scan` but does **not** add new fields to the workspace summary. Each model's `copilot` is populated in-memory and discarded once the per-model export folder is written. A future release may add Copilot signals (e.g., `has_ai_instructions`, `verified_answer_count`) to `workspace-summary.json` once governance use cases are defined. Surfacing here so it's an explicit deferral, not an oversight.
