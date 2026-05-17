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
| 4 | **Extraction timing**: opt-in `--with-copilot` flag on `analyze` / `scan`. Default off. Extractor reads from Fabric REST (Fabric mode) or sidecar fixture (`--mock`). | Avoids paying a Fabric REST call cost on every existing `analyze`. Default-off keeps the v1.3.x performance contract. |
| 5 | **Fixture format**: sidecar file `<model>.copilot.json` containing the **raw `getDefinition` envelope** (not a hand-shaped Copilot bundle). | Exercises the production parsing path; captures Microsoft payload-shape drift in CI; first sidecar is captured from a real model, later ones can be hand-authored. |
| 6 | **Output layout**: mirror Microsoft's `Copilot/` folder verbatim under `./output/<slug>/copilot/`. | Makes the future `apply-copilot` round-trip trivial (same paths in, same paths out); each primitive diffs cleanly; matches what the spike doc documents. |
| 7 | **Backward compat**: keep `TMDLClient.find_prep_for_ai_settings()` returning its current snippet-dict shape. No deprecation warning. | The function is 3 weeks old, the spike notebook is its only caller, and forcing a churn for a parallel API would break the notebook silently. |

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

    def to_dict(self) -> dict: ...         # JSON-serializable dict
```

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

`BaseExtractor.extract(model_name, *, with_copilot: bool = False) -> SemanticModelMeta`. Keyword-only flag, default False, keeps every existing caller untouched.

`MockExtractor.extract(name, with_copilot=False)`:

```python
if with_copilot:
    sidecar_path = self.fixture_path.with_suffix(".copilot.json")
    if sidecar_path.exists():
        envelope = json.loads(sidecar_path.read_text())
        model.copilot = CopilotReader.from_definition(envelope)
    # absence of sidecar is not an error — model.copilot stays None
```

`SemanticLinkExtractor.extract(name, with_copilot=False)`:

```python
if with_copilot:
    from ..writeback.tmdl_client import TMDLClient
    client = TMDLClient(self._fabric_credential(), self.workspace_id)
    envelope = client.get_definition(model_id)
    model.copilot = CopilotReader.from_definition(envelope)
```

### Exporter (`generator/export_copilot.py`)

```python
class CopilotExporter(BaseExporter):
    name = "copilot"
    output_filename = "copilot/"            # marker: directory output, not single file
    description = "Microsoft Copilot/ folder mirror (AI Instructions, Verified Answers, AI Data Schema, etc.)"

    def generate(self, model: SemanticModelMeta) -> dict:
        if model.copilot is None:
            raise ExporterError(
                "model.copilot is None. Re-run extract with --with-copilot."
            )
        return model.copilot.to_dict()      # used by tests and for in-memory schema validation

    def write(self, model: SemanticModelMeta, output_dir: Path) -> Path:
        """Override default JSON write — mirror Microsoft's Copilot/ layout verbatim."""
        if model.copilot is None:
            raise ExporterError("model.copilot is None. Re-run extract with --with-copilot.")

        copilot_dir = output_dir / model.slug / "copilot"
        copilot_dir.mkdir(parents=True, exist_ok=True)
        b = model.copilot

        if b.ai_instructions is not None:
            instr_dir = copilot_dir / "Instructions"
            instr_dir.mkdir(parents=True, exist_ok=True)
            (instr_dir / "instructions.md").write_bytes(b.ai_instructions.raw_bytes)
        if b.ai_data_schema is not None:
            (copilot_dir / "schema.json").write_text(json.dumps(b.ai_data_schema.raw, indent=2))
        if b.example_prompts is not None:
            (copilot_dir / "examplePrompts.json").write_text(json.dumps(b.example_prompts.raw, indent=2))
        if b.settings is not None:
            (copilot_dir / "settings.json").write_text(json.dumps(b.settings.raw, indent=2))
        if b.version is not None:
            (copilot_dir / "version.json").write_text(json.dumps(b.version.raw, indent=2))
        if b.verified_answers:
            va_dir = copilot_dir / "VerifiedAnswers"
            va_dir.mkdir(parents=True, exist_ok=True)
            for va in b.verified_answers:
                (va_dir / va.filename).write_text(json.dumps(va.raw, indent=2))
        return copilot_dir
```

The default `BaseExporter.write()` dumps `generate()` as one JSON file. Copilot output is a directory tree, so `write()` is overridden. The `output_filename = "copilot/"` trailing slash signals directory mode cosmetically; the real layout is decided by `write()`.

### CLI

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

**Implicit `with_copilot=True` for the `copilot` exporter.** The CLI handler for `export` inspects the exporter name and passes `with_copilot=True` to `extract()` when the exporter is `copilot`. Other exporters call `extract()` with the default `with_copilot=False`. This keeps the surface user-friendly — nobody runs `export copilot` and forgets the flag.

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
- `__all__` count grows from 35 to ~40 (5 new exports: `CopilotBundle`, `AIInstructions`, `VerifiedAnswer`, `AIDataSchema`, `CopilotReader`).

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

None. All five brainstorming questions answered; no architectural gaps remain.
