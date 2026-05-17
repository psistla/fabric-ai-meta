# CopilotReader v1.4.0 Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the read half of Microsoft Fabric Prep for AI writeback — typed Python objects (`CopilotBundle`, `AIInstructions`, `VerifiedAnswer`, `AIDataSchema`, etc.), an `inspect`/export CLI (`fabric-ai-meta export copilot`), and a `--with-copilot` flag on `analyze`/`scan` — without modifying any existing user-visible behavior when the new flag is off.

**Architecture:** Pure parser `CopilotReader.from_definition(envelope) -> CopilotBundle` lives under `generator/`. New optional `SemanticModelMeta.copilot` field populated on demand by extractors when the caller passes `with_copilot=True`. New `CopilotExporter` (registered in `BUILTIN_EXPORTERS`) writes the bundle to disk mirroring Microsoft's `Copilot/` folder layout. CLI wires the flag through `_run_analysis`, `scan`, `_export_single`, and `_register_exporter_commands` (which sets `with_copilot=True` automatically for the `copilot` exporter only). No writes to Fabric in this release.

**Tech Stack:** Python 3.10+ (project min), `dataclasses`, `click` (CLI), `pytest`, `unittest.mock`, `sempy.fabric` (Fabric mode only), `notebookutils` (Fabric runtime only). All Fabric paths mocked in tests.

**Spec:** [docs/superpowers/specs/2026-05-16-copilot-reader-design.md](../specs/2026-05-16-copilot-reader-design.md)

**Branch:** Work on `master`. Commit per task. Push after each chunk completes.

**Before starting:** Run `pytest tests/ -x -q` to confirm green baseline (expected: 399 passed, 1 skipped as of v1.3.5). If anything fails before any code is changed, stop and fix the environment.

---

## Chunk 1: Copilot data model

**Goal:** New module `models/copilot.py` with all Copilot dataclasses and `to_dict()` serialization. No integration with anything else yet. Self-contained, fully unit-tested.

**Files:**
- Create: `src/fabric_ai_meta/models/copilot.py`
- Create: `tests/test_copilot_models.py`

### Task 1.1: Create the empty module skeleton

- [ ] **Step 1: Write the failing import test**

Create `tests/test_copilot_models.py`:

```python
"""Tests for fabric_ai_meta.models.copilot dataclasses."""

import pytest


def test_module_exposes_all_dataclasses():
    from fabric_ai_meta.models.copilot import (
        AIDataSchema,
        AIInstructions,
        CopilotBundle,
        CopilotSettings,
        CopilotVersion,
        ExamplePrompts,
        VerifiedAnswer,
    )
    assert AIInstructions is not None
    assert VerifiedAnswer is not None
    assert AIDataSchema is not None
    assert ExamplePrompts is not None
    assert CopilotSettings is not None
    assert CopilotVersion is not None
    assert CopilotBundle is not None
```

- [ ] **Step 2: Run the test and confirm it fails**

```
pytest tests/test_copilot_models.py::test_module_exposes_all_dataclasses -v
```

Expected: `ModuleNotFoundError: No module named 'fabric_ai_meta.models.copilot'`.

- [ ] **Step 3: Create the module with all dataclass stubs**

Create `src/fabric_ai_meta/models/copilot.py`:

```python
"""Dataclasses representing Microsoft Fabric Copilot / Prep for AI primitives.

Every JSON-shaped primitive keeps a `raw: dict` escape hatch alongside any
typed fields the parser is confident about. Adding inferred fields later is
not a breaking change — consumers that read `raw` directly are unaffected.

See docs/research/tmdl-prep-for-ai-spike.md for the on-disk layout these
mirror, and the v1.4.0 design at
docs/superpowers/specs/2026-05-16-copilot-reader-design.md.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class AIInstructions:
    """Copilot/Instructions/instructions.md content.

    `markdown` is a best-effort UTF-8 decode of `raw_bytes`. Use `raw_bytes`
    for byte-perfect round-trips back to the model.
    """

    markdown: str
    raw_bytes: bytes


@dataclass
class VerifiedAnswer:
    """One file under Copilot/VerifiedAnswers/.

    `filename` is the basename (e.g. `"answer-001.json"`), not the full
    `Copilot/VerifiedAnswers/...` part path. `question` is a best-effort
    extraction; `raw` is always the full parsed JSON.
    """

    filename: str
    question: str | None
    raw: dict[str, Any]


@dataclass
class AIDataSchema:
    """Copilot/schema.json — the AI Data Schema (tables/columns Copilot sees)."""

    raw: dict[str, Any]


@dataclass
class ExamplePrompts:
    """Copilot/examplePrompts.json — suggested prompts shown to users."""

    prompts: list[str]
    raw: dict[str, Any] | list[Any]


@dataclass
class CopilotSettings:
    """Copilot/settings.json — Copilot toggles and behavior flags."""

    raw: dict[str, Any]


@dataclass
class CopilotVersion:
    """Copilot/version.json — schema version of the Copilot folder."""

    raw: dict[str, Any]


@dataclass
class CopilotBundle:
    """All Prep for AI primitives for one semantic model.

    Every field is optional. A model may have AI Instructions and no
    Verified Answers, or vice versa. Empty fields stay `None` / `[]`.
    """

    ai_instructions: AIInstructions | None = None
    verified_answers: list[VerifiedAnswer] = field(default_factory=list)
    ai_data_schema: AIDataSchema | None = None
    example_prompts: ExamplePrompts | None = None
    settings: CopilotSettings | None = None
    version: CopilotVersion | None = None

    def to_dict(self) -> dict:
        """JSON-serializable view. Omits `AIInstructions.raw_bytes` (not JSON-safe)."""
        return {
            "ai_instructions": (
                {"markdown": self.ai_instructions.markdown}
                if self.ai_instructions is not None
                else None
            ),
            "verified_answers": [
                {"filename": va.filename, "question": va.question, "raw": va.raw}
                for va in self.verified_answers
            ],
            "ai_data_schema": (
                {"raw": self.ai_data_schema.raw}
                if self.ai_data_schema is not None
                else None
            ),
            "example_prompts": (
                {"prompts": self.example_prompts.prompts, "raw": self.example_prompts.raw}
                if self.example_prompts is not None
                else None
            ),
            "settings": (
                {"raw": self.settings.raw} if self.settings is not None else None
            ),
            "version": (
                {"raw": self.version.raw} if self.version is not None else None
            ),
        }
```

- [ ] **Step 4: Run the test and confirm it passes**

```
pytest tests/test_copilot_models.py::test_module_exposes_all_dataclasses -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/fabric_ai_meta/models/copilot.py tests/test_copilot_models.py
git commit -m "feat(models): add CopilotBundle dataclasses for Prep for AI primitives"
```

### Task 1.2: `CopilotBundle.to_dict()` shape

- [ ] **Step 1: Add the shape test**

Append to `tests/test_copilot_models.py`:

```python
def test_empty_bundle_to_dict_returns_all_none_and_empty_list():
    from fabric_ai_meta.models.copilot import CopilotBundle

    d = CopilotBundle().to_dict()
    assert d == {
        "ai_instructions": None,
        "verified_answers": [],
        "ai_data_schema": None,
        "example_prompts": None,
        "settings": None,
        "version": None,
    }


def test_full_bundle_to_dict_omits_raw_bytes_keeps_markdown():
    from fabric_ai_meta.models.copilot import (
        AIDataSchema,
        AIInstructions,
        CopilotBundle,
        CopilotSettings,
        CopilotVersion,
        ExamplePrompts,
        VerifiedAnswer,
    )

    bundle = CopilotBundle(
        ai_instructions=AIInstructions(markdown="# Hi", raw_bytes=b"# Hi"),
        verified_answers=[
            VerifiedAnswer(filename="a.json", question="Q1?", raw={"k": 1}),
            VerifiedAnswer(filename="b.json", question=None, raw={"k": 2}),
        ],
        ai_data_schema=AIDataSchema(raw={"tables": []}),
        example_prompts=ExamplePrompts(prompts=["one", "two"], raw=["one", "two"]),
        settings=CopilotSettings(raw={"enabled": True}),
        version=CopilotVersion(raw={"v": 1}),
    )
    d = bundle.to_dict()
    assert d["ai_instructions"] == {"markdown": "# Hi"}
    assert "raw_bytes" not in d["ai_instructions"]
    assert d["verified_answers"] == [
        {"filename": "a.json", "question": "Q1?", "raw": {"k": 1}},
        {"filename": "b.json", "question": None, "raw": {"k": 2}},
    ]
    assert d["ai_data_schema"] == {"raw": {"tables": []}}
    assert d["example_prompts"] == {"prompts": ["one", "two"], "raw": ["one", "two"]}
    assert d["settings"] == {"raw": {"enabled": True}}
    assert d["version"] == {"raw": {"v": 1}}


def test_to_dict_output_is_json_serializable():
    import json

    from fabric_ai_meta.models.copilot import (
        AIInstructions,
        CopilotBundle,
        VerifiedAnswer,
    )

    bundle = CopilotBundle(
        ai_instructions=AIInstructions(markdown="text", raw_bytes=b"text"),
        verified_answers=[VerifiedAnswer(filename="x.json", question="q", raw={})],
    )
    serialized = json.dumps(bundle.to_dict())  # must not raise
    assert "raw_bytes" not in serialized
    assert "markdown" in serialized
```

- [ ] **Step 2: Run all tests**

```
pytest tests/test_copilot_models.py -v
```

Expected: all PASS (module already implements the shape per Task 1.1 Step 3).

- [ ] **Step 3: Commit**

```bash
git add tests/test_copilot_models.py
git commit -m "test(models): cover CopilotBundle.to_dict shape and JSON safety"
```

---

## Chunk 2: SemanticModelMeta gains optional `copilot` field

**Goal:** Add `copilot: CopilotBundle | None = None` to `SemanticModelMeta` without breaking any existing call site, fixture, `to_dict()`, or `from_dict()` behavior.

**Files:**
- Modify: `src/fabric_ai_meta/models/metadata.py`
- Modify: `tests/test_extractor.py` (one new regression test)
- Test: `tests/test_copilot_models.py` (extend with integration test)

### Task 2.1: Backward-compat regression test FIRST

- [ ] **Step 1: Write the failing test that pins existing behavior**

Append to `tests/test_extractor.py`:

```python
def test_semanticmodelmeta_copilot_defaults_to_none_and_is_optional():
    """v1.4.0 adds an optional copilot field; existing constructors must not break."""
    from fabric_ai_meta.models.metadata import SemanticModelMeta

    model = SemanticModelMeta(
        name="X",
        workspace="W",
        description=None,
        tables=[],
        relationships=[],
        ai_readiness_score=None,
        scoring_breakdown={},
        extraction_timestamp="2026-01-01T00:00:00Z",
        extraction_method="mock",
    )
    assert model.copilot is None
    # Round-trip must still work; copilot omitted from input dict
    d = model.to_dict()
    assert "copilot" in d
    assert d["copilot"] is None
```

- [ ] **Step 2: Run it and confirm failure**

```
pytest tests/test_extractor.py::test_semanticmodelmeta_copilot_defaults_to_none_and_is_optional -v
```

Expected: FAIL — `SemanticModelMeta.__init__()` does not accept (and doesn't define) `copilot`. The current `to_dict()` won't include a `copilot` key.

- [ ] **Step 3: Modify `SemanticModelMeta`**

Open `src/fabric_ai_meta/models/metadata.py`. Find the `SemanticModelMeta` dataclass definition (around L141). Read the surrounding code first.

Three changes inside `metadata.py`:

(1) At the top of the file, in the imports section, add:

```python
from fabric_ai_meta.models.copilot import CopilotBundle
```

> **Note for the engineer:** This is a same-package import — `metadata.py` and `copilot.py` are siblings in `models/`. No new dependency, no circular risk (copilot.py only imports `dataclasses` and `typing`).

(2) Add the new field to `SemanticModelMeta`. The dataclass must keep its existing field order; add `copilot` **at the end** so existing positional-arg constructors keep working. Locate the last field of `SemanticModelMeta` (it's `extraction_method`). Add right after it:

```python
    copilot: CopilotBundle | None = None
```

(3) Extend `SemanticModelMeta.to_dict()` (it lives just below the dataclass, around L152). Find the existing return-dict and add the `copilot` key. Example shape (merge into the existing return dict, do not rewrite the whole method):

```python
    def to_dict(self) -> dict:
        return {
            # ... existing keys unchanged ...
            "copilot": self.copilot.to_dict() if self.copilot is not None else None,
        }
```

- [ ] **Step 4: Run the regression test**

```
pytest tests/test_extractor.py::test_semanticmodelmeta_copilot_defaults_to_none_and_is_optional -v
```

Expected: PASS.

- [ ] **Step 5: Run the full suite to catch any other breakage**

```
pytest tests/ -x -q
```

Expected: 400 passed, 1 skipped (one more than before this chunk).

- [ ] **Step 6: Commit**

```bash
git add src/fabric_ai_meta/models/metadata.py tests/test_extractor.py
git commit -m "feat(models): add optional SemanticModelMeta.copilot field (default None)"
```

### Task 2.2: `from_dict()` round-trip with copilot

- [ ] **Step 1: Add the round-trip test**

Append to `tests/test_copilot_models.py`:

```python
def test_semanticmodelmeta_from_dict_round_trip_omits_copilot():
    """from_dict on a dict without a copilot key should leave copilot = None."""
    from fabric_ai_meta.models.metadata import from_dict

    raw = {
        "name": "X",
        "workspace": "W",
        "description": None,
        "tables": [],
        "relationships": [],
        "ai_readiness_score": None,
        "scoring_breakdown": {},
        "extraction_timestamp": "2026-01-01T00:00:00Z",
        "extraction_method": "mock",
    }
    model = from_dict(raw)
    assert model.copilot is None
```

- [ ] **Step 2: Run it**

```
pytest tests/test_copilot_models.py::test_semanticmodelmeta_from_dict_round_trip_omits_copilot -v
```

Expected: PASS (`from_dict` does not pass `copilot`, dataclass default of `None` kicks in).

> **If this test fails** with `TypeError`, `from_dict` is constructing `SemanticModelMeta` by passing every key as a kwarg (including unexpected ones). In that case, read `from_dict` (around metadata.py:157) and adjust either `from_dict` to ignore unknown keys, or accept the test failure as a signal to patch `from_dict`. Do not delete the test.

- [ ] **Step 3: Run full suite**

```
pytest tests/ -x -q
```

Expected: 401 passed, 1 skipped.

- [ ] **Step 4: Commit**

```bash
git add tests/test_copilot_models.py
git commit -m "test(models): SemanticModelMeta.from_dict round-trips with copilot=None default"
```

---

## Chunk 3: `CopilotReader` — pure parser

**Goal:** Implement `generator/copilot_reader.py`. Static methods, no I/O, no network. Tests use hand-built envelopes (no fixture files yet — those land in Chunk 4).

**Files:**
- Create: `src/fabric_ai_meta/generator/copilot_reader.py`
- Create: `tests/test_copilot_reader.py`

### Task 3.1: Smallest possible parser — empty envelope

- [ ] **Step 1: Write the failing test**

Create `tests/test_copilot_reader.py`:

```python
"""Tests for CopilotReader.from_definition() parser.

Uses hand-built envelopes; no network, no fixture files. The richer
fixture-driven tests land in Chunk 4 of the v1.4.0 plan.
"""

import base64
import json


def _b64(payload) -> str:
    """Encode dict/str/bytes -> base64 string in the shape getDefinition returns."""
    if isinstance(payload, dict) or isinstance(payload, list):
        payload = json.dumps(payload).encode("utf-8")
    elif isinstance(payload, str):
        payload = payload.encode("utf-8")
    return base64.b64encode(payload).decode("ascii")


def _envelope(parts: list[dict]) -> dict:
    return {"definition": {"parts": parts}}


def test_empty_envelope_returns_empty_bundle():
    from fabric_ai_meta.generator.copilot_reader import CopilotReader
    from fabric_ai_meta.models.copilot import CopilotBundle

    bundle = CopilotReader.from_definition(_envelope([]))
    assert isinstance(bundle, CopilotBundle)
    assert bundle.ai_instructions is None
    assert bundle.verified_answers == []
    assert bundle.ai_data_schema is None
    assert bundle.example_prompts is None
    assert bundle.settings is None
    assert bundle.version is None


def test_envelope_with_only_tmdl_parts_returns_empty_bundle():
    """Non-Copilot parts must be ignored."""
    from fabric_ai_meta.generator.copilot_reader import CopilotReader

    bundle = CopilotReader.from_definition(_envelope([
        {"path": "definition/model.tmdl", "payload": _b64("model"), "payloadType": "InlineBase64"},
        {"path": ".platform", "payload": _b64('{}'), "payloadType": "InlineBase64"},
    ]))
    assert bundle.ai_instructions is None
    assert bundle.verified_answers == []
```

- [ ] **Step 2: Run it and confirm failure**

```
pytest tests/test_copilot_reader.py -v
```

Expected: `ModuleNotFoundError: No module named 'fabric_ai_meta.generator.copilot_reader'`.

- [ ] **Step 3: Create the parser with minimum behavior**

Create `src/fabric_ai_meta/generator/copilot_reader.py`:

```python
"""Parse a Fabric REST getDefinition response into a CopilotBundle.

Pure functions: no I/O, no network, no auth. Network and auth live in
`fabric_ai_meta.writeback.tmdl_client.TMDLClient`. Reader takes a dict,
returns a bundle.

Read paths are deliberately lenient. A malformed individual part is logged
and skipped; the rest of the envelope still produces a valid CopilotBundle.
"""

from __future__ import annotations

import base64
import json
import logging
from typing import Any

from fabric_ai_meta.models.copilot import (
    AIDataSchema,
    AIInstructions,
    CopilotBundle,
    CopilotSettings,
    CopilotVersion,
    ExamplePrompts,
    VerifiedAnswer,
)
from fabric_ai_meta.writeback.tmdl_client import COPILOT_PATH_PREFIXES, PRIMITIVE_BY_PREFIX

logger = logging.getLogger(__name__)


class CopilotReader:
    """Stateless parser for the Copilot/ folder inside a getDefinition envelope."""

    @staticmethod
    def from_definition(definition: dict) -> CopilotBundle:
        """Parse a getDefinition response into a CopilotBundle.

        Walks the parts list, dispatches each Copilot/ part to a primitive
        parser based on path prefix. Returns a CopilotBundle with populated
        fields where matching parts exist, defaults (None / []) otherwise.
        """
        bundle = CopilotBundle()

        for part in _iter_parts(definition):
            path = str(part.get("path") or "")
            primitive = _primitive_for_path(path)
            if primitive is None:
                continue
            try:
                if primitive == "ai_instructions":
                    bundle.ai_instructions = CopilotReader._parse_ai_instructions(part)
                elif primitive == "verified_answers":
                    bundle.verified_answers.append(CopilotReader._parse_verified_answer(part))
                elif primitive == "ai_data_schema":
                    bundle.ai_data_schema = CopilotReader._parse_ai_data_schema(part)
                elif primitive == "example_prompts":
                    bundle.example_prompts = CopilotReader._parse_example_prompts(part)
                elif primitive == "copilot_settings":
                    bundle.settings = CopilotReader._parse_copilot_settings(part)
                elif primitive == "copilot_version":
                    bundle.version = CopilotReader._parse_copilot_version(part)
            except Exception as exc:
                logger.warning(
                    "Skipping malformed Copilot part %r: %s", path, exc
                )
                continue

        # Sort verified answers deterministically by filename so callers and
        # tests do not depend on input order.
        bundle.verified_answers.sort(key=lambda va: va.filename)
        return bundle

    # ------------------------------------------------------------------
    # Per-primitive parsers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_ai_instructions(part: dict) -> AIInstructions:
        raw_bytes = _decode_part_bytes(part)
        try:
            markdown = raw_bytes.decode("utf-8")
        except UnicodeDecodeError:
            logger.warning(
                "AI Instructions payload is not valid UTF-8; using replacement decode."
            )
            markdown = raw_bytes.decode("utf-8", errors="replace")
        return AIInstructions(markdown=markdown, raw_bytes=raw_bytes)

    @staticmethod
    def _parse_verified_answer(part: dict) -> VerifiedAnswer:
        raw = _decode_part_json(part)
        path = str(part.get("path") or "")
        # Strip the Copilot/VerifiedAnswers/ prefix; store basename only.
        filename = path.rsplit("/", 1)[-1] if "/" in path else path
        question = None
        if isinstance(raw, dict):
            # Best-effort: Microsoft has not published a schema. Try common keys.
            for key in ("question", "Question", "questionText", "name", "Name"):
                if isinstance(raw.get(key), str):
                    question = raw[key]
                    break
        return VerifiedAnswer(filename=filename, question=question, raw=raw)

    @staticmethod
    def _parse_ai_data_schema(part: dict) -> AIDataSchema:
        return AIDataSchema(raw=_decode_part_json(part))

    @staticmethod
    def _parse_example_prompts(part: dict) -> ExamplePrompts:
        raw = _decode_part_json(part)
        prompts: list[str] = []
        # Best-effort: shape may be a list of strings, list of {"prompt": "..."},
        # or {"prompts": [...]}. Tolerate all three.
        candidates: list = []
        if isinstance(raw, list):
            candidates = raw
        elif isinstance(raw, dict):
            for key in ("prompts", "examples", "items"):
                val = raw.get(key)
                if isinstance(val, list):
                    candidates = val
                    break
        for c in candidates:
            if isinstance(c, str):
                prompts.append(c)
            elif isinstance(c, dict):
                for key in ("prompt", "text", "value"):
                    if isinstance(c.get(key), str):
                        prompts.append(c[key])
                        break
        return ExamplePrompts(prompts=prompts, raw=raw)

    @staticmethod
    def _parse_copilot_settings(part: dict) -> CopilotSettings:
        return CopilotSettings(raw=_decode_part_json(part))

    @staticmethod
    def _parse_copilot_version(part: dict) -> CopilotVersion:
        return CopilotVersion(raw=_decode_part_json(part))


# ------------------------------------------------------------------
# Helpers (private to this module)
# ------------------------------------------------------------------

def _iter_parts(definition: dict):
    return ((definition or {}).get("definition") or {}).get("parts") or []


def _primitive_for_path(path: str) -> str | None:
    for prefix in COPILOT_PATH_PREFIXES:
        if path.startswith(prefix):
            return PRIMITIVE_BY_PREFIX[prefix]
    return None


def _decode_part_bytes(part: dict) -> bytes:
    payload = part.get("payload")
    payload_type = part.get("payloadType", "InlineBase64")
    if payload is None:
        raise ValueError("Copilot part has no 'payload'.")
    if payload_type != "InlineBase64":
        raise ValueError(f"Unsupported payloadType {payload_type!r}; expected InlineBase64.")
    return base64.b64decode(payload)


def _decode_part_json(part: dict) -> Any:
    return json.loads(_decode_part_bytes(part).decode("utf-8"))
```

- [ ] **Step 4: Run both initial tests**

```
pytest tests/test_copilot_reader.py -v
```

Expected: both PASS.

- [ ] **Step 5: Commit**

```bash
git add src/fabric_ai_meta/generator/copilot_reader.py tests/test_copilot_reader.py
git commit -m "feat(generator): add CopilotReader.from_definition pure parser"
```

### Task 3.2: AI Instructions parsing

- [ ] **Step 1: Add the tests**

Append to `tests/test_copilot_reader.py`:

```python
def test_ai_instructions_extracted_with_markdown_and_raw_bytes():
    from fabric_ai_meta.generator.copilot_reader import CopilotReader

    bundle = CopilotReader.from_definition(_envelope([
        {
            "path": "Copilot/Instructions/instructions.md",
            "payload": _b64("# AI Instructions\n\nAlways prefer DISTINCT()."),
            "payloadType": "InlineBase64",
        },
    ]))
    assert bundle.ai_instructions is not None
    assert bundle.ai_instructions.markdown.startswith("# AI Instructions")
    assert bundle.ai_instructions.raw_bytes == b"# AI Instructions\n\nAlways prefer DISTINCT()."


def test_ai_instructions_raw_bytes_round_trips_exact_input():
    from fabric_ai_meta.generator.copilot_reader import CopilotReader

    original = b"line one\nline two\nUTF-8 \xe2\x9c\x93"  # checkmark
    bundle = CopilotReader.from_definition(_envelope([
        {
            "path": "Copilot/Instructions/instructions.md",
            "payload": base64.b64encode(original).decode("ascii"),
            "payloadType": "InlineBase64",
        },
    ]))
    assert bundle.ai_instructions is not None
    assert bundle.ai_instructions.raw_bytes == original


def test_ai_instructions_invalid_utf8_falls_back_to_replacement(caplog):
    import logging
    from fabric_ai_meta.generator.copilot_reader import CopilotReader

    bad = b"\xff\xfe not valid utf8"
    with caplog.at_level(logging.WARNING, logger="fabric_ai_meta.generator.copilot_reader"):
        bundle = CopilotReader.from_definition(_envelope([
            {
                "path": "Copilot/Instructions/instructions.md",
                "payload": base64.b64encode(bad).decode("ascii"),
                "payloadType": "InlineBase64",
            },
        ]))
    assert bundle.ai_instructions is not None
    assert bundle.ai_instructions.raw_bytes == bad
    # markdown should be a string (with replacement chars); never raise
    assert isinstance(bundle.ai_instructions.markdown, str)
    assert any("not valid UTF-8" in r.message for r in caplog.records)
```

- [ ] **Step 2: Run them**

```
pytest tests/test_copilot_reader.py -v
```

Expected: all PASS (parser already handles this case from Task 3.1).

- [ ] **Step 3: Commit**

```bash
git add tests/test_copilot_reader.py
git commit -m "test(copilot_reader): cover AI Instructions parse + UTF-8 fallback"
```

### Task 3.3: Verified Answers parsing

- [ ] **Step 1: Add the tests**

Append to `tests/test_copilot_reader.py`:

```python
def test_verified_answers_strip_path_prefix_and_keep_basename():
    from fabric_ai_meta.generator.copilot_reader import CopilotReader

    bundle = CopilotReader.from_definition(_envelope([
        {
            "path": "Copilot/VerifiedAnswers/answer-zeta.json",
            "payload": _b64({"question": "What is total sales?", "dax": "..."}),
            "payloadType": "InlineBase64",
        },
        {
            "path": "Copilot/VerifiedAnswers/answer-alpha.json",
            "payload": _b64({"question": "What is margin?"}),
            "payloadType": "InlineBase64",
        },
    ]))
    # Sorted by filename
    assert [va.filename for va in bundle.verified_answers] == [
        "answer-alpha.json",
        "answer-zeta.json",
    ]
    # Best-effort question extraction
    assert bundle.verified_answers[0].question == "What is margin?"
    assert bundle.verified_answers[1].question == "What is total sales?"
    # Full payload always preserved
    assert bundle.verified_answers[1].raw["dax"] == "..."


def test_verified_answer_without_recognizable_question_key_keeps_none():
    from fabric_ai_meta.generator.copilot_reader import CopilotReader

    bundle = CopilotReader.from_definition(_envelope([
        {
            "path": "Copilot/VerifiedAnswers/unknown.json",
            "payload": _b64({"foo": "bar"}),
            "payloadType": "InlineBase64",
        },
    ]))
    assert len(bundle.verified_answers) == 1
    assert bundle.verified_answers[0].question is None
    assert bundle.verified_answers[0].raw == {"foo": "bar"}


def test_malformed_verified_answer_is_skipped_warning_logged(caplog):
    import logging
    from fabric_ai_meta.generator.copilot_reader import CopilotReader

    with caplog.at_level(logging.WARNING, logger="fabric_ai_meta.generator.copilot_reader"):
        bundle = CopilotReader.from_definition(_envelope([
            {
                "path": "Copilot/VerifiedAnswers/good.json",
                "payload": _b64({"question": "valid"}),
                "payloadType": "InlineBase64",
            },
            {
                "path": "Copilot/VerifiedAnswers/bad.json",
                "payload": "not-base64-not-json!!!",
                "payloadType": "InlineBase64",
            },
        ]))
    # Bad one skipped, good one kept
    assert [va.filename for va in bundle.verified_answers] == ["good.json"]
    assert any("Copilot/VerifiedAnswers/bad.json" in r.message for r in caplog.records)
```

- [ ] **Step 2: Run them**

```
pytest tests/test_copilot_reader.py -v
```

Expected: all PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/test_copilot_reader.py
git commit -m "test(copilot_reader): cover VerifiedAnswers basename, question, malformed skip"
```

### Task 3.4: AI Data Schema, Example Prompts, Settings, Version

- [ ] **Step 1: Add the tests**

Append to `tests/test_copilot_reader.py`:

```python
def test_ai_data_schema_keeps_raw_dict():
    from fabric_ai_meta.generator.copilot_reader import CopilotReader

    schema = {"tables": [{"name": "Sales", "columns": ["amount"]}]}
    bundle = CopilotReader.from_definition(_envelope([
        {"path": "Copilot/schema.json", "payload": _b64(schema), "payloadType": "InlineBase64"},
    ]))
    assert bundle.ai_data_schema is not None
    assert bundle.ai_data_schema.raw == schema


def test_example_prompts_flat_list_shape():
    from fabric_ai_meta.generator.copilot_reader import CopilotReader

    bundle = CopilotReader.from_definition(_envelope([
        {
            "path": "Copilot/examplePrompts.json",
            "payload": _b64(["What is total sales?", "Top 5 customers?"]),
            "payloadType": "InlineBase64",
        },
    ]))
    assert bundle.example_prompts is not None
    assert bundle.example_prompts.prompts == ["What is total sales?", "Top 5 customers?"]


def test_example_prompts_object_with_prompts_key_shape():
    from fabric_ai_meta.generator.copilot_reader import CopilotReader

    bundle = CopilotReader.from_definition(_envelope([
        {
            "path": "Copilot/examplePrompts.json",
            "payload": _b64({"prompts": [{"prompt": "Show sales by region"}]}),
            "payloadType": "InlineBase64",
        },
    ]))
    assert bundle.example_prompts is not None
    assert bundle.example_prompts.prompts == ["Show sales by region"]


def test_settings_and_version_keep_raw_dict():
    from fabric_ai_meta.generator.copilot_reader import CopilotReader

    bundle = CopilotReader.from_definition(_envelope([
        {"path": "Copilot/settings.json", "payload": _b64({"enabled": True}), "payloadType": "InlineBase64"},
        {"path": "Copilot/version.json", "payload": _b64({"version": "1.0"}), "payloadType": "InlineBase64"},
    ]))
    assert bundle.settings is not None and bundle.settings.raw == {"enabled": True}
    assert bundle.version is not None and bundle.version.raw == {"version": "1.0"}


def test_non_inline_base64_payload_type_skipped(caplog):
    import logging
    from fabric_ai_meta.generator.copilot_reader import CopilotReader

    with caplog.at_level(logging.WARNING, logger="fabric_ai_meta.generator.copilot_reader"):
        bundle = CopilotReader.from_definition(_envelope([
            {
                "path": "Copilot/Instructions/instructions.md",
                "payload": "ignored",
                "payloadType": "RemoteFile",
            },
        ]))
    assert bundle.ai_instructions is None
    assert any("Unsupported payloadType" in r.message or "payloadType" in r.message for r in caplog.records)
```

- [ ] **Step 2: Run them**

```
pytest tests/test_copilot_reader.py -v
```

Expected: all PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/test_copilot_reader.py
git commit -m "test(copilot_reader): cover schema, examplePrompts shape variants, settings, version, unsupported payload"
```

### Task 3.5: Integration test — full envelope through the parser

- [ ] **Step 1: Add the test**

Append to `tests/test_copilot_reader.py`:

```python
def test_full_envelope_with_all_six_primitives_populates_every_field():
    from fabric_ai_meta.generator.copilot_reader import CopilotReader

    bundle = CopilotReader.from_definition(_envelope([
        {"path": "definition/model.tmdl", "payload": _b64("ignored"), "payloadType": "InlineBase64"},
        {"path": "Copilot/Instructions/instructions.md",
         "payload": _b64("# Instructions"), "payloadType": "InlineBase64"},
        {"path": "Copilot/schema.json",
         "payload": _b64({"tables": []}), "payloadType": "InlineBase64"},
        {"path": "Copilot/examplePrompts.json",
         "payload": _b64(["one", "two"]), "payloadType": "InlineBase64"},
        {"path": "Copilot/settings.json",
         "payload": _b64({"enabled": True}), "payloadType": "InlineBase64"},
        {"path": "Copilot/version.json",
         "payload": _b64({"version": "1"}), "payloadType": "InlineBase64"},
        {"path": "Copilot/VerifiedAnswers/q1.json",
         "payload": _b64({"question": "Q1?"}), "payloadType": "InlineBase64"},
        {"path": "Copilot/VerifiedAnswers/q2.json",
         "payload": _b64({"question": "Q2?"}), "payloadType": "InlineBase64"},
    ]))
    assert bundle.ai_instructions is not None
    assert bundle.ai_data_schema is not None
    assert bundle.example_prompts is not None
    assert bundle.settings is not None
    assert bundle.version is not None
    assert [va.filename for va in bundle.verified_answers] == ["q1.json", "q2.json"]
```

- [ ] **Step 2: Run it**

```
pytest tests/test_copilot_reader.py -v
```

Expected: PASS.

- [ ] **Step 3: Run full suite**

```
pytest tests/ -x -q
```

Expected: ~410 passed, 1 skipped (depending on exact count above).

- [ ] **Step 4: Commit**

```bash
git add tests/test_copilot_reader.py
git commit -m "test(copilot_reader): cover all-six-primitives full envelope path"
```

---

## Chunk 4: Fixture files

**Goal:** Hand-authored sidecar fixtures so MockExtractor's `--with-copilot` mode has something to load.

**Files:**
- Create: `tests/fixtures/adventure_works.copilot.json`
- Create: `tests/fixtures/enterprise_sales.copilot.json`

### Task 4.1: Adventure Works sidecar fixture

- [ ] **Step 1: Create the fixture**

The fixture is the raw `getDefinition` envelope shape, with `payload` values base64-encoded. To avoid hand-encoding base64 in the fixture by hand, generate the file with a one-off Python script run from the project root:

```python
# Throwaway: do not commit this script. Run from project root.
import base64
import json
import os

OUT = "tests/fixtures/adventure_works.copilot.json"

def b64_bytes(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")

def b64_json(obj) -> str:
    return b64_bytes(json.dumps(obj).encode("utf-8"))

instructions_md = (
    b"# Adventure Works AI Instructions\n\n"
    b"- Always prefer DISTINCTCOUNT() over COUNT() for customer counts.\n"
    b"- Total Sales lives on the Sales table, not Orders.\n"
    b"- Date filters should use the Date table, never raw OrderDate columns.\n"
)

envelope = {
    "definition": {
        "parts": [
            {"path": "Copilot/Instructions/instructions.md",
             "payload": b64_bytes(instructions_md),
             "payloadType": "InlineBase64"},
            {"path": "Copilot/schema.json",
             "payload": b64_json({
                 "version": "1.0",
                 "tables": [
                     {"name": "Sales", "columns": ["TotalAmount", "OrderDate", "CustomerKey"]},
                     {"name": "Date", "columns": ["Date", "Year", "MonthName"]},
                 ],
             }),
             "payloadType": "InlineBase64"},
            {"path": "Copilot/examplePrompts.json",
             "payload": b64_json([
                 "What were total sales last quarter?",
                 "Show top 5 customers by revenue.",
             ]),
             "payloadType": "InlineBase64"},
            {"path": "Copilot/VerifiedAnswers/total-sales-by-year.json",
             "payload": b64_json({
                 "question": "What were total sales by year?",
                 "dax": "EVALUATE SUMMARIZECOLUMNS('Date'[Year], \"Total\", [Total Sales])",
             }),
             "payloadType": "InlineBase64"},
            {"path": "Copilot/VerifiedAnswers/top-customers.json",
             "payload": b64_json({
                 "question": "Who are the top 5 customers?",
                 "dax": "EVALUATE TOPN(5, Customers, [Total Sales], DESC)",
             }),
             "payloadType": "InlineBase64"},
            {"path": "Copilot/settings.json",
             "payload": b64_json({"enabled": True, "model": "default"}),
             "payloadType": "InlineBase64"},
            {"path": "Copilot/version.json",
             "payload": b64_json({"version": "1.0"}),
             "payloadType": "InlineBase64"},
        ]
    }
}

os.makedirs("tests/fixtures", exist_ok=True)
with open(OUT, "w", encoding="utf-8") as f:
    json.dump(envelope, f, indent=2)
print(f"Wrote {OUT}")
```

Save as `scripts/_one_off_make_copilot_fixture.py`, run with `python scripts/_one_off_make_copilot_fixture.py`, **delete the script after** (it's a one-time fixture generator; the fixture is the artifact we keep).

- [ ] **Step 2: Verify the fixture parses through CopilotReader**

Add a temporary self-check test (will be promoted to a proper test later — keep it):

Append to `tests/test_copilot_reader.py`:

```python
def test_adventure_works_sidecar_fixture_parses_cleanly():
    import json
    from pathlib import Path

    from fabric_ai_meta.generator.copilot_reader import CopilotReader

    fixture = Path("tests/fixtures/adventure_works.copilot.json")
    envelope = json.loads(fixture.read_text(encoding="utf-8"))
    bundle = CopilotReader.from_definition(envelope)

    assert bundle.ai_instructions is not None
    assert "DISTINCTCOUNT" in bundle.ai_instructions.markdown
    assert bundle.ai_data_schema is not None
    assert any(t["name"] == "Sales" for t in bundle.ai_data_schema.raw["tables"])
    assert bundle.example_prompts is not None
    assert len(bundle.example_prompts.prompts) == 2
    assert [va.filename for va in bundle.verified_answers] == [
        "top-customers.json",
        "total-sales-by-year.json",
    ]
    assert bundle.settings is not None
    assert bundle.version is not None
```

- [ ] **Step 3: Run**

```
pytest tests/test_copilot_reader.py::test_adventure_works_sidecar_fixture_parses_cleanly -v
```

Expected: PASS.

- [ ] **Step 4: Commit (fixture + test; do NOT commit the generator script)**

```bash
git add tests/fixtures/adventure_works.copilot.json tests/test_copilot_reader.py
git commit -m "test(fixtures): add adventure_works.copilot.json sidecar with all six primitives"
```

### Task 4.2: Enterprise Sales sidecar fixture

- [ ] **Step 1: Generate the larger fixture**

Repeat the script with different content: target file `tests/fixtures/enterprise_sales.copilot.json`. Include three Verified Answers (e.g., `pipeline-by-quarter.json`, `win-rate.json`, `deal-size-distribution.json`), a larger AI Instructions Markdown (more bullets), and a schema with 5+ tables.

- [ ] **Step 2: Self-check test**

Append to `tests/test_copilot_reader.py`:

```python
def test_enterprise_sales_sidecar_fixture_parses_cleanly():
    import json
    from pathlib import Path

    from fabric_ai_meta.generator.copilot_reader import CopilotReader

    fixture = Path("tests/fixtures/enterprise_sales.copilot.json")
    envelope = json.loads(fixture.read_text(encoding="utf-8"))
    bundle = CopilotReader.from_definition(envelope)

    assert bundle.ai_instructions is not None
    assert bundle.ai_data_schema is not None
    assert len(bundle.verified_answers) >= 3
    # Sorted by filename — verify order is deterministic, not insertion-order
    names = [va.filename for va in bundle.verified_answers]
    assert names == sorted(names)
```

- [ ] **Step 3: Run**

```
pytest tests/test_copilot_reader.py::test_enterprise_sales_sidecar_fixture_parses_cleanly -v
```

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add tests/fixtures/enterprise_sales.copilot.json tests/test_copilot_reader.py
git commit -m "test(fixtures): add enterprise_sales.copilot.json sidecar with 3 Verified Answers"
```

---

## Chunk 5: Extractor wiring

**Goal:** Extractors populate `model.copilot` when called with `with_copilot=True`. Default is False. Existing callers stay green.

**Files:**
- Modify: `src/fabric_ai_meta/extractor/base.py`
- Modify: `src/fabric_ai_meta/extractor/mock.py`
- Modify: `src/fabric_ai_meta/extractor/semantic_link.py`
- Modify: `tests/test_extractor.py`

### Task 5.1: Extend `BaseExtractor.extract` signature

- [ ] **Step 1: Write the failing signature test**

Append to `tests/test_extractor.py`:

```python
def test_baseextractor_extract_accepts_with_copilot_kwarg():
    """v1.4.0: extract() gains a kw-only with_copilot flag (default False)."""
    import inspect
    from fabric_ai_meta.extractor.base import BaseExtractor

    sig = inspect.signature(BaseExtractor.extract)
    assert "with_copilot" in sig.parameters
    param = sig.parameters["with_copilot"]
    assert param.kind is inspect.Parameter.KEYWORD_ONLY
    assert param.default is False
```

- [ ] **Step 2: Run it**

```
pytest tests/test_extractor.py::test_baseextractor_extract_accepts_with_copilot_kwarg -v
```

Expected: FAIL — parameter not yet present.

- [ ] **Step 3: Modify `BaseExtractor.extract` signature**

Open `src/fabric_ai_meta/extractor/base.py`. Change:

```python
    @abstractmethod
    def extract(self, model_name: str, workspace: str) -> SemanticModelMeta:
        """Extract metadata for a semantic model and return a SemanticModelMeta."""
        ...
```

to:

```python
    @abstractmethod
    def extract(
        self, model_name: str, workspace: str, *, with_copilot: bool = False
    ) -> SemanticModelMeta:
        """Extract metadata for a semantic model.

        Args:
            model_name: Name of the semantic model.
            workspace: Workspace name.
            with_copilot: If True, also fetch and populate `SemanticModelMeta.copilot`
                with the model's `Copilot/` folder (AI Instructions, Verified Answers,
                etc.). When False (default), `copilot` is left None.
        """
        ...
```

- [ ] **Step 4: Run the signature test + full suite**

```
pytest tests/test_extractor.py::test_baseextractor_extract_accepts_with_copilot_kwarg tests/ -x -q
```

Expected: signature test PASS, full suite still green (`with_copilot` is kw-only with default, so all existing positional callers are unaffected).

- [ ] **Step 5: Commit**

```bash
git add src/fabric_ai_meta/extractor/base.py tests/test_extractor.py
git commit -m "feat(extractor): add kw-only with_copilot flag to BaseExtractor.extract"
```

### Task 5.2: `MockExtractor` with_copilot in `fixture_path` mode

- [ ] **Step 1: Write the failing test**

Append to `tests/test_extractor.py`:

```python
def test_mockextractor_fixture_path_loads_copilot_sidecar_when_flag_set():
    from fabric_ai_meta.extractor.mock import MockExtractor

    ex = MockExtractor(fixture_path="tests/fixtures/adventure_works.json")
    # Default: copilot stays None
    model_no = ex.extract("Adventure Works", "ws")
    assert model_no.copilot is None
    # With flag: sidecar loaded
    model_yes = ex.extract("Adventure Works", "ws", with_copilot=True)
    assert model_yes.copilot is not None
    assert model_yes.copilot.ai_instructions is not None


def test_mockextractor_fixture_path_no_sidecar_leaves_copilot_none(tmp_path):
    """When the fixture has no .copilot.json sidecar, copilot stays None — not an error."""
    import json

    from fabric_ai_meta.extractor.mock import MockExtractor

    fixture = tmp_path / "tiny.json"
    fixture.write_text(json.dumps({
        "name": "Tiny",
        "workspace": "W",
        "description": None,
        "tables": [],
        "relationships": [],
        "ai_readiness_score": None,
        "scoring_breakdown": {},
        "extraction_timestamp": "2026-01-01T00:00:00Z",
        "extraction_method": "mock",
    }))
    ex = MockExtractor(fixture_path=str(fixture))
    model = ex.extract("Tiny", "W", with_copilot=True)
    assert model.copilot is None  # absence-of-sidecar is OK
```

- [ ] **Step 2: Run them**

```
pytest tests/test_extractor.py -k mockextractor_fixture_path -v
```

Expected: FAIL — `MockExtractor.extract` does not accept `with_copilot`.

- [ ] **Step 3: Modify `MockExtractor`**

Open `src/fabric_ai_meta/extractor/mock.py`. At the top, add the imports we'll need:

```python
from fabric_ai_meta.generator.copilot_reader import CopilotReader
```

Change the `extract` signature and add sidecar loading at the bottom of each return path. Replace the existing `extract` method with:

```python
    def extract(
        self,
        model_name: str,
        workspace: str | None = None,
        *,
        with_copilot: bool = False,
    ) -> SemanticModelMeta:
        """Load and return a SemanticModelMeta.

        fixture_path mode: loads that file directly.
        fixture_dir mode:  finds the fixture whose model name matches.
        When `with_copilot=True`, also loads a sibling `<base>.copilot.json`
        sidecar if it exists; absence is not an error.
        """
        if self.fixture_path is not None:
            model = self._load(self.fixture_path)
            if with_copilot:
                self._attach_copilot(model, self.fixture_path)
            return model

        target_slug = _slugify(model_name)
        for fname in sorted(os.listdir(self.fixture_dir)):
            if not fname.endswith(".json"):
                continue
            if fname.endswith(".copilot.json"):
                continue   # skip sidecar files when scanning for model fixtures
            fpath = os.path.join(self.fixture_dir, fname)
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                candidate_name = data.get("name", fname[:-5])
                if _slugify(candidate_name) == target_slug:
                    model = from_dict(data)
                    if with_copilot:
                        self._attach_copilot(model, fpath)
                    return model
            except Exception:
                pass

        raise FileNotFoundError(
            f"No fixture found for model '{model_name}' in '{self.fixture_dir}'"
        )

    @staticmethod
    def _attach_copilot(model: SemanticModelMeta, fixture_file: str) -> None:
        """Load `<base>.copilot.json` next to `fixture_file` into model.copilot.

        No-op if the sidecar file does not exist. JSON decode errors propagate.
        """
        base, _ext = os.path.splitext(fixture_file)
        sidecar = base + ".copilot.json"
        if not os.path.exists(sidecar):
            return
        with open(sidecar, "r", encoding="utf-8") as f:
            envelope = json.load(f)
        model.copilot = CopilotReader.from_definition(envelope)
```

Also update `list_models` to skip `.copilot.json` files (otherwise the fixture-dir scan would surface them as bogus models):

Find the existing loop in `list_models` that does `for fname in sorted(os.listdir(self.fixture_dir))`. After the `if not fname.endswith(".json"): continue` line, add:

```python
            if fname.endswith(".copilot.json"):
                continue
```

- [ ] **Step 4: Run the two tests**

```
pytest tests/test_extractor.py -k mockextractor_fixture_path -v
```

Expected: both PASS.

- [ ] **Step 5: Commit**

```bash
git add src/fabric_ai_meta/extractor/mock.py tests/test_extractor.py
git commit -m "feat(extractor): MockExtractor loads .copilot.json sidecar when with_copilot=True"
```

### Task 5.3: `MockExtractor` `fixture_dir` mode

- [ ] **Step 1: Write the failing test**

Append to `tests/test_extractor.py`:

```python
def test_mockextractor_fixture_dir_loads_copilot_sidecar():
    from fabric_ai_meta.extractor.mock import MockExtractor

    ex = MockExtractor(fixture_dir="tests/fixtures")
    model = ex.extract("Adventure Works", "ws", with_copilot=True)
    assert model.copilot is not None
    assert model.copilot.ai_instructions is not None


def test_mockextractor_fixture_dir_list_models_skips_copilot_sidecars():
    from fabric_ai_meta.extractor.mock import MockExtractor

    ex = MockExtractor(fixture_dir="tests/fixtures")
    models = ex.list_models("ws")
    # No model named "adventure_works.copilot" should appear
    assert not any(m.lower().endswith(".copilot") for m in models)
    assert not any(".copilot.json" in m for m in models)
```

- [ ] **Step 2: Run**

```
pytest tests/test_extractor.py -k mockextractor_fixture_dir -v
```

Expected: PASS (already implemented in Task 5.2).

- [ ] **Step 3: Run full suite to catch regressions**

```
pytest tests/ -x -q
```

Expected: all green.

- [ ] **Step 4: Commit**

```bash
git add tests/test_extractor.py
git commit -m "test(extractor): cover MockExtractor fixture_dir copilot sidecar + list_models filter"
```

### Task 5.4: `SemanticLinkExtractor` Copilot path

- [ ] **Step 1: Write the failing test (uses mocks; no Fabric runtime needed)**

Append to `tests/test_extractor.py`:

```python
def test_semantic_link_extractor_with_copilot_calls_tmdl_client_and_parses():
    """SemanticLinkExtractor.extract(..., with_copilot=True) should:
    - resolve workspace + model GUIDs via sempy.fabric resolvers
    - obtain a bearer token via notebookutils
    - call TMDLClient.get_definition
    - run the response through CopilotReader
    - attach result to model.copilot
    All Fabric/sempy/notebookutils calls are mocked.
    """
    import sys
    import types
    from unittest.mock import MagicMock, patch

    import pandas as pd

    # Stub sempy.fabric BEFORE constructing the extractor.
    fake_sempy_fabric = MagicMock()
    fake_sempy_fabric.list_tables.return_value = pd.DataFrame()
    fake_sempy_fabric.list_measures.return_value = pd.DataFrame()
    fake_sempy_fabric.list_relationships.return_value = pd.DataFrame()
    fake_sempy_fabric.resolve_workspace_id.return_value = "WS-GUID"
    fake_sempy_fabric.resolve_item_id.return_value = "MODEL-GUID"

    # Stub notebookutils.credentials.getToken to return a fixed token.
    fake_creds = MagicMock()
    fake_creds.getToken.return_value = "FAKE-BEARER-TOKEN"
    fake_notebookutils = types.ModuleType("notebookutils")
    fake_notebookutils.credentials = fake_creds

    # Patch sys.modules so the deferred imports inside the extractor pick these up.
    sys_modules_patch = patch.dict(sys.modules, {
        "sempy": types.ModuleType("sempy"),
        "sempy.fabric": fake_sempy_fabric,
        "notebookutils": fake_notebookutils,
    })

    # detect_notebook_environment() guard must return True so __init__ succeeds.
    with sys_modules_patch, \
         patch("fabric_ai_meta.extractor.semantic_link.detect_notebook_environment",
               return_value=True), \
         patch("fabric_ai_meta.writeback.tmdl_client.TMDLClient.get_definition") as gd:
        gd.return_value = {
            "definition": {
                "parts": [
                    {
                        "path": "Copilot/Instructions/instructions.md",
                        "payload": __import__("base64").b64encode(b"# Hi").decode("ascii"),
                        "payloadType": "InlineBase64",
                    },
                ]
            }
        }
        from fabric_ai_meta.extractor.semantic_link import SemanticLinkExtractor

        ex = SemanticLinkExtractor(workspace="MyWorkspace")
        model = ex.extract("MyModel", "MyWorkspace", with_copilot=True)

    assert model.copilot is not None
    assert model.copilot.ai_instructions is not None
    assert model.copilot.ai_instructions.markdown.startswith("# Hi")
    fake_sempy_fabric.resolve_workspace_id.assert_called_with("MyWorkspace")
    fake_sempy_fabric.resolve_item_id.assert_called_once()
    fake_creds.getToken.assert_called_with("pbi")
    gd.assert_called_once_with("MODEL-GUID")


def test_semantic_link_extractor_without_with_copilot_skips_tmdl_path():
    import sys
    import types
    from unittest.mock import MagicMock, patch

    import pandas as pd

    fake_sempy_fabric = MagicMock()
    fake_sempy_fabric.list_tables.return_value = pd.DataFrame()
    fake_sempy_fabric.list_measures.return_value = pd.DataFrame()
    fake_sempy_fabric.list_relationships.return_value = pd.DataFrame()

    sys_modules_patch = patch.dict(sys.modules, {
        "sempy": types.ModuleType("sempy"),
        "sempy.fabric": fake_sempy_fabric,
    })
    with sys_modules_patch, \
         patch("fabric_ai_meta.extractor.semantic_link.detect_notebook_environment",
               return_value=True), \
         patch("fabric_ai_meta.writeback.tmdl_client.TMDLClient.get_definition") as gd:
        from fabric_ai_meta.extractor.semantic_link import SemanticLinkExtractor

        ex = SemanticLinkExtractor(workspace="W")
        model = ex.extract("M", "W")  # no with_copilot

    assert model.copilot is None
    gd.assert_not_called()
```

- [ ] **Step 2: Run**

```
pytest tests/test_extractor.py -k semantic_link_extractor_with -v
```

Expected: FAIL — `SemanticLinkExtractor.extract` doesn't accept `with_copilot` yet.

- [ ] **Step 3: Modify `SemanticLinkExtractor`**

Open `src/fabric_ai_meta/extractor/semantic_link.py`. Make three additions.

(a) At the top of the file (with other imports inside the class scope, but lazily — Fabric-only paths stay deferred):

No new top-level imports needed. All Fabric/notebookutils imports are inside method bodies.

(b) Modify the `extract` signature and add the copilot block at the end. Locate the method and change its signature + add the trailing block:

```python
    def extract(
        self,
        model_name: str,
        workspace: str | None = None,
        *,
        with_copilot: bool = False,
    ) -> SemanticModelMeta:
        """Extract full metadata for a semantic model.

        Args:
            model_name: Name of the Power BI / Fabric semantic model.
            workspace: Workspace to use; defaults to self.workspace.
            with_copilot: If True, also fetch the Copilot/ folder via
                Fabric REST getDefinition and populate model.copilot.

        Returns:
            A fully populated SemanticModelMeta object.
        """
        ws = workspace or self.workspace
        # ... existing body unchanged ...
        model = SemanticModelMeta(
            # ... existing constructor args unchanged ...
        )

        if with_copilot:
            model.copilot = self._extract_copilot(model_name, ws)

        return model
```

> **Engineer note:** Do not rewrite the body of `extract`. Only (a) change the signature, (b) replace the bare `return SemanticModelMeta(...)` at the end with the variable assignment + conditional + `return model` pattern shown above.

(c) Add two new private methods to the class:

```python
    def _extract_copilot(self, model_name: str, workspace: str):
        """Fetch and parse the Copilot/ folder. Returns CopilotBundle or None.

        Resolution failures (workspace name or model name not found by sempy)
        log a warning and return None — never raise.
        """
        from fabric_ai_meta.generator.copilot_reader import CopilotReader
        from fabric_ai_meta.writeback.tmdl_client import TMDLClient

        fabric = self._fabric
        try:
            workspace_id = fabric.resolve_workspace_id(workspace)
        except Exception as exc:
            logger.warning(
                "Cannot resolve workspace id for %r: %s. Skipping Copilot extract.",
                workspace, exc,
            )
            return None
        if not workspace_id:
            logger.warning(
                "Workspace %r not found by sempy. Skipping Copilot extract.", workspace
            )
            return None

        try:
            model_id = fabric.resolve_item_id(
                model_name, type="SemanticModel", workspace=workspace
            )
        except Exception as exc:
            logger.warning(
                "Cannot resolve model id for %r: %s. Skipping Copilot extract.",
                model_name, exc,
            )
            return None
        if not model_id:
            logger.warning(
                "Model %r not found in workspace %r. Skipping Copilot extract.",
                model_name, workspace,
            )
            return None

        token = self._fabric_bearer_token()
        client = TMDLClient(token, workspace_id)
        envelope = client.get_definition(model_id)
        return CopilotReader.from_definition(envelope)

    def _fabric_bearer_token(self) -> str:
        """Obtain a Power BI / Fabric bearer token from the Fabric notebook runtime."""
        import notebookutils  # type: ignore[import-not-found]  # only in Fabric runtime
        return notebookutils.credentials.getToken("pbi")
```

- [ ] **Step 4: Run the two new tests + full suite**

```
pytest tests/test_extractor.py -k semantic_link_extractor -v
pytest tests/ -x -q
```

Expected: both new tests PASS; full suite green.

- [ ] **Step 5: Commit**

```bash
git add src/fabric_ai_meta/extractor/semantic_link.py tests/test_extractor.py
git commit -m "feat(extractor): SemanticLinkExtractor populates model.copilot when with_copilot=True"
```

---

## Chunk 6: `CopilotExporter` + registry

**Goal:** New `CopilotExporter` (BaseExporter subclass) that mirrors the Microsoft `Copilot/` folder layout under `{output_dir}/{slug}/copilot/`. Registered in `BUILTIN_EXPORTERS` so it appears in `discover_exporters()` and as `fabric-ai-meta export copilot`.

**Files:**
- Create: `src/fabric_ai_meta/generator/export_copilot.py`
- Modify: `src/fabric_ai_meta/generator/builtin_exporters.py`
- Create: `tests/test_export_copilot.py`

### Task 6.1: Exporter class — `generate()` contract

- [ ] **Step 1: Write the failing test**

Create `tests/test_export_copilot.py`:

```python
"""Tests for CopilotExporter."""

import json
import os
from pathlib import Path

import pytest


def _build_model_with_full_bundle():
    """Helper: SemanticModelMeta carrying a fully populated CopilotBundle."""
    from fabric_ai_meta.models.copilot import (
        AIDataSchema,
        AIInstructions,
        CopilotBundle,
        CopilotSettings,
        CopilotVersion,
        ExamplePrompts,
        VerifiedAnswer,
    )
    from fabric_ai_meta.models.metadata import SemanticModelMeta

    return SemanticModelMeta(
        name="Adventure Works",
        workspace="W",
        description=None,
        tables=[],
        relationships=[],
        ai_readiness_score=None,
        scoring_breakdown={},
        extraction_timestamp="2026-01-01T00:00:00Z",
        extraction_method="mock",
        copilot=CopilotBundle(
            ai_instructions=AIInstructions(markdown="# Hi", raw_bytes=b"# Hi"),
            verified_answers=[
                VerifiedAnswer(filename="q1.json", question="Q1?", raw={"question": "Q1?"}),
                VerifiedAnswer(filename="q2.json", question="Q2?", raw={"question": "Q2?"}),
            ],
            ai_data_schema=AIDataSchema(raw={"tables": []}),
            example_prompts=ExamplePrompts(prompts=["p1"], raw=["p1"]),
            settings=CopilotSettings(raw={"enabled": True}),
            version=CopilotVersion(raw={"v": 1}),
        ),
    )


def test_generate_returns_to_dict_when_copilot_present():
    from fabric_ai_meta.generator.export_copilot import CopilotExporter

    model = _build_model_with_full_bundle()
    payload = CopilotExporter().generate(model)
    assert payload == model.copilot.to_dict()


def test_generate_raises_exporter_error_when_copilot_is_none():
    from fabric_ai_meta.generator.base import ExporterError
    from fabric_ai_meta.generator.export_copilot import CopilotExporter
    from fabric_ai_meta.models.metadata import SemanticModelMeta

    model = SemanticModelMeta(
        name="X", workspace="W", description=None, tables=[], relationships=[],
        ai_readiness_score=None, scoring_breakdown={},
        extraction_timestamp="2026-01-01T00:00:00Z", extraction_method="mock",
    )
    with pytest.raises(ExporterError, match="with_copilot"):
        CopilotExporter().generate(model)
```

- [ ] **Step 2: Run them**

```
pytest tests/test_export_copilot.py -k generate -v
```

Expected: `ModuleNotFoundError: No module named 'fabric_ai_meta.generator.export_copilot'`.

- [ ] **Step 3: Create the exporter**

Create `src/fabric_ai_meta/generator/export_copilot.py`:

```python
"""Mirror Microsoft's Copilot/ folder layout under {output_dir}/{model-slug}/copilot/.

Exporter for the Prep for AI primitives (AI Instructions, Verified Answers,
AI Data Schema, example prompts, settings, version). Read-only; companion to
the future CopilotWriter that does the inverse via updateDefinition.
"""

from __future__ import annotations

import json
import os
from typing import ClassVar

from fabric_ai_meta.generator.base import BaseExporter, ExporterError, _slugify
from fabric_ai_meta.models.metadata import SemanticModelMeta


class CopilotExporter(BaseExporter):
    name: ClassVar[str] = "copilot"
    # write() is fully overridden — output is a directory tree, not a single file.
    output_filename: ClassVar[str] = ""
    description: ClassVar[str] = (
        "Microsoft Copilot/ folder mirror (AI Instructions, Verified Answers, "
        "AI Data Schema, example prompts, settings, version)."
    )

    def generate(self, model: SemanticModelMeta) -> dict:
        """JSON-serializable view of the bundle. Used by tests and future schema validation."""
        if model.copilot is None:
            raise ExporterError(
                "model.copilot is None. Re-run extract with with_copilot=True "
                "(CLI: --with-copilot, or use `fabric-ai-meta export copilot`)."
            )
        return model.copilot.to_dict()

    def write(self, model: SemanticModelMeta, output_dir: str) -> str:
        """Write the Copilot/ folder layout under {output_dir}/{slug}/copilot/.

        Returns the absolute path of the copilot/ directory on success, or an
        empty string if the bundle had nothing to write (no primitives present).
        """
        if model.copilot is None:
            raise ExporterError(
                "model.copilot is None. Re-run extract with with_copilot=True."
            )

        slug = _slugify(model.name) if model.name else "model"
        copilot_dir = os.path.join(output_dir, slug, "copilot")
        b = model.copilot
        wrote = False

        if b.ai_instructions is not None:
            instr_dir = os.path.join(copilot_dir, "Instructions")
            os.makedirs(instr_dir, exist_ok=True)
            with open(os.path.join(instr_dir, "instructions.md"), "wb") as f:
                f.write(b.ai_instructions.raw_bytes)
            wrote = True

        if b.ai_data_schema is not None:
            os.makedirs(copilot_dir, exist_ok=True)
            with open(os.path.join(copilot_dir, "schema.json"), "w", encoding="utf-8") as f:
                json.dump(b.ai_data_schema.raw, f, indent=2)
            wrote = True

        if b.example_prompts is not None:
            os.makedirs(copilot_dir, exist_ok=True)
            with open(os.path.join(copilot_dir, "examplePrompts.json"), "w", encoding="utf-8") as f:
                json.dump(b.example_prompts.raw, f, indent=2)
            wrote = True

        if b.settings is not None:
            os.makedirs(copilot_dir, exist_ok=True)
            with open(os.path.join(copilot_dir, "settings.json"), "w", encoding="utf-8") as f:
                json.dump(b.settings.raw, f, indent=2)
            wrote = True

        if b.version is not None:
            os.makedirs(copilot_dir, exist_ok=True)
            with open(os.path.join(copilot_dir, "version.json"), "w", encoding="utf-8") as f:
                json.dump(b.version.raw, f, indent=2)
            wrote = True

        if b.verified_answers:
            va_dir = os.path.join(copilot_dir, "VerifiedAnswers")
            os.makedirs(va_dir, exist_ok=True)
            for va in b.verified_answers:
                with open(os.path.join(va_dir, va.filename), "w", encoding="utf-8") as f:
                    json.dump(va.raw, f, indent=2)
            wrote = True

        return copilot_dir if wrote else ""
```

- [ ] **Step 4: Run the tests**

```
pytest tests/test_export_copilot.py -k generate -v
```

Expected: both PASS.

- [ ] **Step 5: Commit**

```bash
git add src/fabric_ai_meta/generator/export_copilot.py tests/test_export_copilot.py
git commit -m "feat(generator): add CopilotExporter generate() honoring with_copilot contract"
```

### Task 6.2: Exporter `write()` — full bundle to disk

- [ ] **Step 1: Add the test**

Append to `tests/test_export_copilot.py`:

```python
def test_write_full_bundle_creates_correct_directory_tree(tmp_path):
    from fabric_ai_meta.generator.export_copilot import CopilotExporter

    model = _build_model_with_full_bundle()
    result = CopilotExporter().write(model, str(tmp_path))
    assert result.endswith(os.path.join("adventure-works", "copilot"))

    base = Path(tmp_path) / "adventure-works" / "copilot"
    assert (base / "Instructions" / "instructions.md").exists()
    assert (base / "schema.json").exists()
    assert (base / "examplePrompts.json").exists()
    assert (base / "settings.json").exists()
    assert (base / "version.json").exists()
    assert (base / "VerifiedAnswers" / "q1.json").exists()
    assert (base / "VerifiedAnswers" / "q2.json").exists()


def test_write_instructions_md_is_byte_perfect(tmp_path):
    """raw_bytes is written verbatim, not re-encoded through markdown."""
    from fabric_ai_meta.generator.export_copilot import CopilotExporter
    from fabric_ai_meta.models.copilot import AIInstructions, CopilotBundle
    from fabric_ai_meta.models.metadata import SemanticModelMeta

    raw = b"original bytes including CRLF\r\nand tab\there"
    model = SemanticModelMeta(
        name="m", workspace="w", description=None, tables=[], relationships=[],
        ai_readiness_score=None, scoring_breakdown={},
        extraction_timestamp="2026-01-01T00:00:00Z", extraction_method="mock",
        copilot=CopilotBundle(ai_instructions=AIInstructions(markdown=raw.decode(), raw_bytes=raw)),
    )
    CopilotExporter().write(model, str(tmp_path))
    written = (Path(tmp_path) / "m" / "copilot" / "Instructions" / "instructions.md").read_bytes()
    assert written == raw


def test_write_verified_answers_use_basename_filenames(tmp_path):
    from fabric_ai_meta.generator.export_copilot import CopilotExporter

    model = _build_model_with_full_bundle()
    CopilotExporter().write(model, str(tmp_path))
    va_dir = Path(tmp_path) / "adventure-works" / "copilot" / "VerifiedAnswers"
    # Files use basenames, no nested Copilot/ path
    files = sorted(p.name for p in va_dir.iterdir())
    assert files == ["q1.json", "q2.json"]


def test_write_empty_bundle_returns_empty_string_and_writes_nothing(tmp_path):
    """A CopilotBundle with no primitives is a legitimate state. Exporter returns
    empty string and creates no files (CLI handler treats this as a notice condition)."""
    from fabric_ai_meta.generator.export_copilot import CopilotExporter
    from fabric_ai_meta.models.copilot import CopilotBundle
    from fabric_ai_meta.models.metadata import SemanticModelMeta

    model = SemanticModelMeta(
        name="m", workspace="w", description=None, tables=[], relationships=[],
        ai_readiness_score=None, scoring_breakdown={},
        extraction_timestamp="2026-01-01T00:00:00Z", extraction_method="mock",
        copilot=CopilotBundle(),
    )
    result = CopilotExporter().write(model, str(tmp_path))
    assert result == ""
    # No copilot/ directory should have been created
    assert not (Path(tmp_path) / "m" / "copilot").exists()
```

- [ ] **Step 2: Run them**

```
pytest tests/test_export_copilot.py -k write -v
```

Expected: all PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/test_export_copilot.py
git commit -m "test(export_copilot): write full bundle, byte-perfect markdown, empty bundle notice"
```

### Task 6.3: Register in `BUILTIN_EXPORTERS`

- [ ] **Step 1: Write the failing registry test**

Append to `tests/test_export_copilot.py`:

```python
def test_copilot_exporter_registered_in_discover_exporters():
    from fabric_ai_meta.generator.export_copilot import CopilotExporter
    from fabric_ai_meta.generator.registry import discover_exporters, get_exporter

    exporters = discover_exporters()
    assert "copilot" in exporters
    assert exporters["copilot"] is CopilotExporter
    assert get_exporter("copilot") is CopilotExporter
```

- [ ] **Step 2: Run it**

```
pytest tests/test_export_copilot.py::test_copilot_exporter_registered_in_discover_exporters -v
```

Expected: FAIL — `copilot` not in registry yet.

- [ ] **Step 3: Add CopilotExporter to `BUILTIN_EXPORTERS`**

Open `src/fabric_ai_meta/generator/builtin_exporters.py`. Find the `BUILTIN_EXPORTERS` tuple at the bottom (around L52). Read the surrounding imports.

At the top of the file with the other imports:

```python
from fabric_ai_meta.generator.export_copilot import CopilotExporter
```

In the `BUILTIN_EXPORTERS` tuple, add `CopilotExporter` as the last entry:

```python
BUILTIN_EXPORTERS: tuple[type[BaseExporter], ...] = (
    LangChainExporter,
    OpenAIExporter,
    SemanticKernelExporter,
    AutoGenExporter,
    CopilotExporter,
)
```

- [ ] **Step 4: Run the registry test + full suite**

```
pytest tests/test_export_copilot.py -v
pytest tests/ -x -q
```

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/fabric_ai_meta/generator/builtin_exporters.py tests/test_export_copilot.py
git commit -m "feat(generator): register CopilotExporter in BUILTIN_EXPORTERS"
```

---

## Chunk 7: CLI wiring

**Goal:** `--with-copilot` flag on `analyze` and `scan`; `_export_single` accepts the flag; `_register_exporter_commands` sets `with_copilot=True` automatically for the `copilot` exporter only.

**Files:**
- Modify: `src/fabric_ai_meta/cli.py`
- Modify: `tests/test_cli.py`

### Task 7.1: `_export_single` threads `with_copilot`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_cli.py`:

```python
def test_export_single_passes_with_copilot_to_extractor(monkeypatch):
    """_export_single(..., with_copilot=True) must pass it to extractor.extract."""
    from unittest.mock import MagicMock

    import fabric_ai_meta.cli as cli

    captured_kwargs = {}

    class StubExtractor:
        def extract(self, model_name, workspace, **kwargs):
            captured_kwargs.update(kwargs)
            from fabric_ai_meta.models.metadata import SemanticModelMeta
            return SemanticModelMeta(
                name=model_name, workspace=workspace, description=None,
                tables=[], relationships=[],
                ai_readiness_score=None, scoring_breakdown={},
                extraction_timestamp="2026-01-01T00:00:00Z", extraction_method="mock",
            )

    monkeypatch.setattr(
        "fabric_ai_meta.extractor.mock.MockExtractor",
        lambda fixture_path: StubExtractor()
    )
    monkeypatch.setattr(cli, "_get_fixture_path", lambda name: "/tmp/whatever.json")

    fake_exporter = MagicMock()
    fake_exporter.write.return_value = "/tmp/out/x"

    cli._export_single(
        "Adventure Works", "Production", fake_exporter,
        mock=True, with_copilot=True,
    )
    assert captured_kwargs == {"with_copilot": True}
```

- [ ] **Step 2: Run it**

```
pytest tests/test_cli.py::test_export_single_passes_with_copilot_to_extractor -v
```

Expected: FAIL — `_export_single` does not accept `with_copilot` kwarg.

- [ ] **Step 3: Modify `_export_single`**

Open `src/fabric_ai_meta/cli.py`. Find `_export_single` (around L461). Change the signature and the single `extractor.extract` call:

```python
def _export_single(
    model_name: str,
    workspace: str,
    exporter,
    mock: bool = False,
    *,
    with_copilot: bool = False,
) -> None:
    """Run a single `BaseExporter` against the extracted model and write its output."""
    cfg = load_config()
    workspace = workspace or cfg.extraction.default_workspace
    output = cfg.output.output_dir

    console.print(Panel(
        f"[bold]export {exporter.name}[/bold]  model=[cyan]{model_name}[/cyan]  "
        f"workspace=[cyan]{workspace}[/cyan]  mock=[cyan]{mock}[/cyan]",
        title="fabric-ai-meta"
    ))

    if mock:
        from fabric_ai_meta.extractor.mock import MockExtractor
        extractor = MockExtractor(fixture_path=_get_fixture_path(model_name))
    else:
        from fabric_ai_meta.auth.entra import FabricEnvironmentError, detect_notebook_environment
        if not detect_notebook_environment():
            raise FabricEnvironmentError()
        from fabric_ai_meta.extractor.semantic_link import SemanticLinkExtractor
        extractor = SemanticLinkExtractor(workspace=workspace)

    model = extractor.extract(model_name, workspace, with_copilot=with_copilot)
    path = exporter.write(model, output)
    if path:
        console.print(f"[green]Written:[/green] {path}")
    else:
        console.print("[yellow]No Copilot/ parts in model definition. Nothing exported.[/yellow]")
```

- [ ] **Step 4: Run the test**

```
pytest tests/test_cli.py::test_export_single_passes_with_copilot_to_extractor -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/fabric_ai_meta/cli.py tests/test_cli.py
git commit -m "feat(cli): _export_single threads with_copilot to extractor; empty-write notice path"
```

### Task 7.2: `_register_exporter_commands` auto-sets `with_copilot` for `copilot` exporter

- [ ] **Step 1: Write the failing test**

Append to `tests/test_cli.py`:

```python
def test_export_copilot_cli_invocation_populates_copilot_via_mock(tmp_path, monkeypatch):
    """`fabric-ai-meta export copilot Adventure --mock` must:
    - implicitly pass with_copilot=True to extractor
    - write the copilot/ tree to disk
    """
    from click.testing import CliRunner

    from fabric_ai_meta.cli import main

    # Redirect output_dir to tmp_path via env or by monkeypatching load_config
    import fabric_ai_meta.cli as cli
    from fabric_ai_meta.config import Config, ExtractionConfig, OutputConfig
    monkeypatch.setattr(cli, "load_config", lambda: Config(
        extraction=ExtractionConfig(default_workspace="W"),
        output=OutputConfig(output_dir=str(tmp_path)),
    ))

    runner = CliRunner()
    result = runner.invoke(main, ["export", "copilot", "Adventure Works", "--mock"])

    assert result.exit_code == 0, result.output
    # Folder mirror exists on disk
    assert (tmp_path / "adventure-works" / "copilot" / "Instructions" / "instructions.md").exists()


def test_export_langchain_cli_does_not_pass_with_copilot(monkeypatch):
    """Non-copilot exporters must not trigger Copilot extraction."""
    from click.testing import CliRunner

    captured = {}
    class StubExtractor:
        def extract(self, model_name, workspace, **kwargs):
            captured.update(kwargs)
            from fabric_ai_meta.models.metadata import SemanticModelMeta
            return SemanticModelMeta(
                name=model_name, workspace=workspace, description=None,
                tables=[], relationships=[],
                ai_readiness_score=None, scoring_breakdown={},
                extraction_timestamp="2026-01-01T00:00:00Z", extraction_method="mock",
            )

    monkeypatch.setattr(
        "fabric_ai_meta.extractor.mock.MockExtractor",
        lambda fixture_path: StubExtractor()
    )

    from fabric_ai_meta.cli import main
    runner = CliRunner()
    runner.invoke(main, ["export", "langchain", "Adventure Works", "--mock"])
    assert captured.get("with_copilot") is False
```

- [ ] **Step 2: Run them**

```
pytest tests/test_cli.py -k export_copilot_cli -v
pytest tests/test_cli.py -k export_langchain_cli_does_not -v
```

Expected: FAIL — `_register_exporter_commands` doesn't yet pass `with_copilot=(ep_name == "copilot")`.

- [ ] **Step 3: Modify `_register_exporter_commands`**

Open `src/fabric_ai_meta/cli.py`. Find `_register_exporter_commands` (around L488). Replace the inner `_cmd` body:

```python
def _register_exporter_commands() -> None:
    """Register every discovered exporter (built-in + plugins) as a CLI subcommand."""
    from fabric_ai_meta.generator.registry import discover_exporters

    for ep_name, exporter_cls in discover_exporters().items():
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

        export_group.add_command(_make_cmd())
```

- [ ] **Step 4: Run the two tests + full suite**

```
pytest tests/test_cli.py -k export_copilot_cli -v
pytest tests/test_cli.py -k export_langchain_cli_does_not -v
pytest tests/ -x -q
```

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/fabric_ai_meta/cli.py tests/test_cli.py
git commit -m "feat(cli): export copilot auto-enables with_copilot; other exporters unchanged"
```

### Task 7.3: `--with-copilot` flag on `analyze`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_cli.py`:

```python
def test_analyze_with_copilot_flag_populates_copilot(tmp_path, monkeypatch):
    from click.testing import CliRunner

    import fabric_ai_meta.cli as cli
    from fabric_ai_meta.cli import main
    from fabric_ai_meta.config import Config, ExtractionConfig, OutputConfig
    monkeypatch.setattr(cli, "load_config", lambda: Config(
        extraction=ExtractionConfig(default_workspace="W"),
        output=OutputConfig(output_dir=str(tmp_path)),
    ))

    runner = CliRunner()
    result = runner.invoke(main, [
        "analyze", "Adventure Works", "--mock", "--with-copilot",
        "--output", str(tmp_path),
    ])
    assert result.exit_code == 0, result.output
    # The analyze handler does not (in v1.4.0) write the copilot/ tree itself —
    # that's CopilotExporter's job. But the analyze run should not error and
    # should leave the existing analyze artifacts on disk.
    assert any(p.name == "ai-ready-schema.json" for p in (tmp_path / "adventure-works").iterdir())
```

> **If the test passes without the flag** (i.e. analyze does not reject `--with-copilot`): great, but we still need to confirm extractor gets the flag. Add a second test that monkeypatches `MockExtractor` like in Task 7.1 and asserts `captured["with_copilot"] is True`.

```python
def test_analyze_with_copilot_flag_passes_to_extractor(monkeypatch, tmp_path):
    from click.testing import CliRunner

    import fabric_ai_meta.cli as cli
    from fabric_ai_meta.cli import main
    from fabric_ai_meta.config import Config, ExtractionConfig, OutputConfig

    captured = {}

    class StubExtractor:
        def extract(self, model_name, workspace, **kwargs):
            captured.update(kwargs)
            from fabric_ai_meta.models.metadata import SemanticModelMeta
            return SemanticModelMeta(
                name=model_name, workspace=workspace, description=None,
                tables=[], relationships=[],
                ai_readiness_score=None, scoring_breakdown={},
                extraction_timestamp="2026-01-01T00:00:00Z", extraction_method="mock",
            )

    monkeypatch.setattr(
        "fabric_ai_meta.extractor.mock.MockExtractor",
        lambda fixture_path: StubExtractor()
    )
    monkeypatch.setattr(cli, "load_config", lambda: Config(
        extraction=ExtractionConfig(default_workspace="W"),
        output=OutputConfig(output_dir=str(tmp_path)),
    ))

    runner = CliRunner()
    result = runner.invoke(main, [
        "analyze", "Adventure Works", "--mock", "--with-copilot",
    ])
    assert result.exit_code == 0, result.output
    assert captured.get("with_copilot") is True
```

- [ ] **Step 2: Run them**

```
pytest tests/test_cli.py -k analyze_with_copilot -v
```

Expected: FAIL — `--with-copilot` not yet on `analyze`.

- [ ] **Step 3: Add the flag to `analyze`**

Open `src/fabric_ai_meta/cli.py`. Find the `analyze` command (around L290) and its `_run_analysis` helper (around L77). Two changes:

(a) On the `analyze` Click command (right next to its other `@click.option` lines), add:

```python
@click.option("--with-copilot", is_flag=True, default=False,
              help="Also fetch the Copilot/ folder via Fabric REST getDefinition.")
```

(b) In the `analyze` handler body, the function signature gains `with_copilot` (Click maps option to kwarg automatically). The call to `_run_analysis(...)` must pass it through. Update both signatures:

```python
def _run_analysis(
    model_name: str, workspace: str, output: str, fmt: str,
    # ... other existing params ...
    with_copilot: bool = False,
) -> None:
    # ... existing body unchanged until the extractor.extract call ...
    model = extractor.extract(model_name, workspace, with_copilot=with_copilot)
    # ... rest unchanged ...
```

And in the `analyze` Click handler that wraps `_run_analysis`:

```python
def analyze(model_name, workspace, output, fmt, ..., with_copilot):
    _run_analysis(model_name, workspace, output, fmt, ..., with_copilot=with_copilot)
```

> **Engineer note:** The exact parameter list of `analyze` and `_run_analysis` is longer than shown — read the actual signatures and insert `with_copilot` at the end of both. Click will pick up the new option automatically and pass it.

- [ ] **Step 4: Run the tests + full suite**

```
pytest tests/test_cli.py -k analyze_with_copilot -v
pytest tests/ -x -q
```

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/fabric_ai_meta/cli.py tests/test_cli.py
git commit -m "feat(cli): analyze --with-copilot flag threaded through _run_analysis"
```

### Task 7.4: `--with-copilot` flag on `scan`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_cli.py`:

```python
def test_scan_with_copilot_flag_passes_to_extractor(monkeypatch, tmp_path):
    from click.testing import CliRunner

    import fabric_ai_meta.cli as cli
    from fabric_ai_meta.cli import main
    from fabric_ai_meta.config import Config, ExtractionConfig, OutputConfig

    captured_calls = []

    class StubExtractor:
        def list_models(self, workspace):
            return ["Adventure Works"]
        def extract(self, model_name, workspace, **kwargs):
            captured_calls.append(kwargs)
            from fabric_ai_meta.models.metadata import SemanticModelMeta
            return SemanticModelMeta(
                name=model_name, workspace=workspace, description=None,
                tables=[], relationships=[],
                ai_readiness_score=None, scoring_breakdown={},
                extraction_timestamp="2026-01-01T00:00:00Z", extraction_method="mock",
            )

    monkeypatch.setattr(
        "fabric_ai_meta.extractor.mock.MockExtractor",
        lambda fixture_dir=None: StubExtractor()
    )
    monkeypatch.setattr(cli, "load_config", lambda: Config(
        extraction=ExtractionConfig(default_workspace="W"),
        output=OutputConfig(output_dir=str(tmp_path)),
    ))

    runner = CliRunner()
    result = runner.invoke(main, [
        "scan", "--workspace", "W", "--mock", "--with-copilot",
        "--output", str(tmp_path),
    ])
    assert result.exit_code == 0, result.output
    assert all(c.get("with_copilot") is True for c in captured_calls)
```

- [ ] **Step 2: Run**

```
pytest tests/test_cli.py::test_scan_with_copilot_flag_passes_to_extractor -v
```

Expected: FAIL — flag not on `scan` yet.

- [ ] **Step 3: Add flag to `scan`**

Open `src/fabric_ai_meta/cli.py`. Find the `scan` command (around L325). Add the `--with-copilot` option. In the body, find the inner extractor loop's `extractor.extract(...)` call (around L355–360) and update it to pass `with_copilot=with_copilot`. Mirror Task 7.3's pattern.

- [ ] **Step 4: Run the test + full suite**

```
pytest tests/test_cli.py::test_scan_with_copilot_flag_passes_to_extractor -v
pytest tests/ -x -q
```

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/fabric_ai_meta/cli.py tests/test_cli.py
git commit -m "feat(cli): scan --with-copilot flag threaded through extractor"
```

---

## Chunk 8: Public API exports + documentation + version bump

**Goal:** Promote the right names at the top-level package, update README/CHANGELOG/CLAUDE.md/user-guide, bump version markers. No code changes beyond `__init__.py`.

**Files:**
- Modify: `src/fabric_ai_meta/__init__.py`
- Modify: `src/fabric_ai_meta/__init__.py` (`__version__`)
- Modify: `pyproject.toml`
- Modify: `README.md`
- Modify: `CHANGELOG.md`
- Modify: `CLAUDE.md`
- Modify: `docs/user-guide.md`

### Task 8.1: Promote public API in `__init__.py`

- [ ] **Step 1: Write the failing import test**

Append to `tests/test_copilot_models.py`:

```python
def test_public_api_exports():
    """v1.4.0 promotes the high-confidence Copilot symbols to the top-level package."""
    from fabric_ai_meta import (
        AIDataSchema,
        AIInstructions,
        CopilotBundle,
        CopilotReader,
        VerifiedAnswer,
    )
    assert AIInstructions is not None
    assert VerifiedAnswer is not None
    assert AIDataSchema is not None
    assert CopilotBundle is not None
    assert CopilotReader is not None
```

- [ ] **Step 2: Run**

```
pytest tests/test_copilot_models.py::test_public_api_exports -v
```

Expected: FAIL — not exported.

- [ ] **Step 3: Modify `__init__.py`**

Open `src/fabric_ai_meta/__init__.py`. Update `__version__` and add the 5 new public exports.

(a) Top of file:

```python
__version__ = "1.4.0"
```

(b) With the other `from fabric_ai_meta.models.metadata import (...)` block, add a new import block:

```python
from fabric_ai_meta.models.copilot import (
    AIDataSchema,
    AIInstructions,
    CopilotBundle,
    VerifiedAnswer,
)
from fabric_ai_meta.generator.copilot_reader import CopilotReader
```

(c) Extend `__all__`. Add a new "Copilot (Prep for AI)" section between "Data model" and "Extractors":

```python
__all__ = [
    # Version
    "__version__",
    # Data model
    "ColumnMeta",
    "ColumnRole",
    "HierarchyMeta",
    "MeasureCategory",
    "MeasureMeta",
    "RelationshipMeta",
    "SemanticModelMeta",
    "TableMeta",
    "TableType",
    "from_dict",
    # Copilot (Prep for AI) — v1.4.0
    "AIDataSchema",
    "AIInstructions",
    "CopilotBundle",
    "VerifiedAnswer",
    "CopilotReader",
    # ... rest unchanged ...
]
```

> **Engineer note:** Do **not** export `ExamplePrompts`, `CopilotSettings`, `CopilotVersion`. They are intentionally not in the top-level surface (see spec Decision #12 / Versioning).

- [ ] **Step 4: Run**

```
pytest tests/test_copilot_models.py::test_public_api_exports -v
pytest tests/ -x -q
```

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/fabric_ai_meta/__init__.py tests/test_copilot_models.py
git commit -m "feat: promote CopilotBundle, AIInstructions, VerifiedAnswer, AIDataSchema, CopilotReader to public API; bump __version__ to 1.4.0"
```

### Task 8.2: `pyproject.toml` version bump

- [ ] **Step 1: Edit**

Open `pyproject.toml`. Change:

```
version = "1.3.5"
```

to:

```
version = "1.4.0"
```

- [ ] **Step 2: Commit**

```bash
git add pyproject.toml
git commit -m "release: bump version to 1.4.0"
```

### Task 8.3: README updates

- [ ] **Step 1: Bump version badge**

In `README.md`, change:

```
![Version](https://img.shields.io/badge/version-1.3.5-238636?style=flat-square)
```

to:

```
![Version](https://img.shields.io/badge/version-1.4.0-238636?style=flat-square)
```

- [ ] **Step 2: Update test count badge if needed**

Count after this work should be ~430 (399 baseline + ~30 new). Update:

```
![Tests](https://img.shields.io/badge/tests-430%20passing-1a7f37?style=flat-square)
```

Replace `430` with the actual number from `pytest tests/ -q | tail -3`.

- [ ] **Step 3: Add `export copilot` row to Usage `<details>` index**

Locate the Usage section (around README line 181). Insert a new `<details>` block in the same style as the existing exporter blocks. Use:

```markdown
<details>
<summary><strong>export copilot</strong>: dump the Microsoft Copilot/ folder as files on disk</summary>

```bash
# Local dev with sidecar fixture
fabric-ai-meta export copilot "Adventure Works" --workspace "Production" --mock

# Live model (inside a Fabric notebook)
fabric-ai-meta export copilot "Adventure Works" --workspace "Production"
```

Mirrors Microsoft's `Copilot/` folder layout under `{output}/{model-slug}/copilot/`: `Instructions/instructions.md`, `VerifiedAnswers/*.json`, `schema.json`, `examplePrompts.json`, `settings.json`, `version.json`. Read-only. The future `apply-copilot` command will write the inverse.

**No `--with-copilot` needed:** this command implicitly enables Copilot extraction. Use `analyze --with-copilot` or `scan --with-copilot` to populate `model.copilot` alongside the other extractor outputs.
</details>
```

Also add `export copilot` mentions in the persona workflows (Fabric Architect path, and AI engineer path) where relevant. Look for the existing `apply-descriptions` line in the Fabric Architect block and add an `export copilot` step before it.

- [ ] **Step 4: Update the Notebooks table caption**

Find the `notebooks/tmdl-spike.ipynb` row in the Notebooks table. Change its Purpose column from "Research spike: …" to:

```
| [`notebooks/tmdl-spike.ipynb`](https://github.com/psistla/fabric-ai-meta/blob/master/notebooks/tmdl-spike.ipynb) | Read-only Copilot/ folder inspection: shows the raw `getDefinition` envelope the new `CopilotReader` API parses. Companion to [`docs/research/tmdl-prep-for-ai-spike.md`](https://github.com/psistla/fabric-ai-meta/blob/master/docs/research/tmdl-prep-for-ai-spike.md). |
```

- [ ] **Step 5: Commit**

```bash
git add README.md
git commit -m "docs(README): add export copilot, --with-copilot mentions, bump version + test count"
```

### Task 8.4: CHANGELOG entry

- [ ] **Step 1: Insert a new `[1.4.0]` block above `[1.3.5]`**

In `CHANGELOG.md`, insert above the existing `## [1.3.5]` heading:

```markdown
## [1.4.0] - 2026-05-16

### Added
- `CopilotBundle`, `AIInstructions`, `VerifiedAnswer`, `AIDataSchema`, `ExamplePrompts`, `CopilotSettings`, `CopilotVersion` dataclasses under `fabric_ai_meta.models.copilot`. Every JSON-shaped primitive keeps a `raw: dict` escape hatch so downstream code is not locked to inferred field shapes.
- `CopilotReader.from_definition(envelope) -> CopilotBundle` pure parser. Walks a Fabric REST `getDefinition` response and produces a typed bundle. Lenient on a per-part basis: malformed individual parts are logged and skipped, the rest of the envelope still parses.
- `SemanticModelMeta.copilot: CopilotBundle | None` optional field on the core model dataclass. Defaults to `None`, so existing constructors and fixtures are unaffected.
- `--with-copilot` flag on `analyze` and `scan`. Opt-in. When set, the extractor also fetches the model's `Copilot/` folder via Fabric REST `getDefinition` and attaches it to `model.copilot`. When unset, behavior matches v1.3.x exactly.
- `fabric-ai-meta export copilot MODEL` CLI command. Writes the Copilot/ folder layout under `{output}/{slug}/copilot/` mirroring Microsoft's on-disk structure (`Instructions/instructions.md`, `VerifiedAnswers/*.json`, `schema.json`, `examplePrompts.json`, `settings.json`, `version.json`). Implicitly enables Copilot extraction.
- `MockExtractor` now reads a sidecar `<fixture>.copilot.json` file when called with `with_copilot=True`. Absence of the sidecar is not an error. `list_models()` excludes `.copilot.json` files from the model list.
- `BaseExtractor.extract` gains a kw-only `with_copilot: bool = False` parameter. Additive ABI change; all existing positional callers are source-compatible.

### Changed
- `__all__` count grows from 35 to 40 (5 new top-level exports: `CopilotBundle`, `AIInstructions`, `VerifiedAnswer`, `AIDataSchema`, `CopilotReader`). The narrower `ExamplePrompts`, `CopilotSettings`, `CopilotVersion` are intentionally not promoted to the top-level package surface.
- `CopilotExporter` registered in `BUILTIN_EXPORTERS`, so it appears in `discover_exporters()` and `fabric-ai-meta export --help` alongside the four pre-existing exporters.

### Notes
- Write half (the future `CopilotWriter` and `apply-copilot` CLI) is out of scope for this release. v1.4.0 is read-only.
- `notebooks/tmdl-spike.ipynb` continues to work unchanged; the `TMDLClient.find_prep_for_ai_settings()` snippet API is preserved.
```

- [ ] **Step 2: Commit**

```bash
git add CHANGELOG.md
git commit -m "docs(changelog): add [1.4.0] CopilotReader + export copilot entry"
```

### Task 8.5: CLAUDE.md updates

- [ ] **Step 1: Bump "Last updated" and add v1.4.0 to Current State**

In `CLAUDE.md`:

(a) Top:

```
> **Last updated:** v1.4.0 released and live on PyPI (May 16, 2026)
```

(b) Under Current State, add after the v1.3.5 bullet:

```
- **v1.4.0**: read half of Prep for AI writeback. New `CopilotBundle` data model (AI Instructions, Verified Answers, AI Data Schema, example prompts, settings, version). New `CopilotReader.from_definition()` pure parser. New `--with-copilot` opt-in flag on `analyze` / `scan` populates `SemanticModelMeta.copilot`. New `fabric-ai-meta export copilot` CLI mirrors Microsoft's `Copilot/` folder layout to disk. `MockExtractor` reads a `<fixture>.copilot.json` sidecar when the flag is set. Write half (`CopilotWriter`, `apply-copilot`) deferred to a later release.
```

(c) Update "Test suite" line:

```
Test suite: ~430 tests passing, 0 ruff errors as of v1.4.0.
```

(replace `~430` with actual count)

(d) Update the in-tree tags list in Git Workflow:

```
Current tags: `v1.0.0`, `v1.1.0`, `v1.1.1`, `v1.1.2`, `v1.2.0`, `v1.3.0`, `v1.3.1`, `v1.3.2`, `v1.3.3`, `v1.3.4`, `v1.3.5`, `v1.4.0`
```

(e) Update the Module Map. Under `models/` add `copilot.py`. Under `generator/` add `copilot_reader.py` and `export_copilot.py`.

(f) Update CLI Command Tree to add `export copilot` and `--with-copilot` mentions.

- [ ] **Step 2: Commit (CLAUDE.md is gitignored — skip the commit, just save the edit)**

> **Engineer note:** `CLAUDE.md` is in `.gitignore`. Save the edit but do not run `git add CLAUDE.md`. There is nothing to commit for this step.

### Task 8.6: user-guide.md section

- [ ] **Step 1: Open `docs/user-guide.md` and add a new section**

Add a new top-level section "Exporting Copilot artifacts" with a four-step workflow:

```markdown
## Exporting Copilot artifacts (`export copilot`)

Microsoft Fabric stores Prep for AI primitives — AI Instructions, Verified Answers, AI Data Schema, example prompts, Copilot settings — in a `Copilot/` folder inside the semantic model. fabric-ai-meta v1.4.0 reads that folder via the Fabric REST `getDefinition` endpoint and writes it to your local disk in the same layout, so you can diff, version-control, and review it outside Fabric.

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

- Read-only in v1.4.0. The inverse writeback (`apply-copilot`) is planned for a later release.
- Models with no Copilot configuration produce an empty bundle and the exporter prints a notice (no `copilot/` directory written).
- Outside a Fabric notebook, `--with-copilot` without `--mock` raises `FabricEnvironmentError`.
```

Cross-link from the Fabric Architect persona section.

- [ ] **Step 2: Commit**

```bash
git add docs/user-guide.md
git commit -m "docs(user-guide): add Exporting Copilot artifacts section for v1.4.0"
```

---

## Chunk 9: Release

**Goal:** Run the full pipeline, tag v1.4.0, push, verify PyPI publish + attestations.

### Task 9.1: Final test pass

- [ ] **Step 1: Run the full suite**

```
pytest tests/ -x -q
```

Expected: ~430 passed, 1 skipped, 0 failures.

- [ ] **Step 2: Run ruff**

```
python -m ruff check .
```

Expected: "All checks passed!"

- [ ] **Step 3: If either fails, stop. Fix and re-run before tagging.**

### Task 9.2: Tag and push

- [ ] **Step 1: Verify working tree is clean**

```
git status
```

Expected: clean (everything committed in prior chunks).

- [ ] **Step 2: Tag v1.4.0**

```bash
git tag -a v1.4.0 \
  -m "v1.4.0: read half of Prep for AI writeback" \
  -m "" \
  -m "Adds CopilotBundle data model, CopilotReader parser, SemanticModelMeta.copilot field, --with-copilot opt-in flag on analyze/scan, and fabric-ai-meta export copilot CLI that mirrors Microsoft's Copilot/ folder layout to disk."
```

- [ ] **Step 3: Push tag**

```bash
git push origin v1.4.0
```

### Task 9.3: Verify publish + PyPI

- [ ] **Step 1: Watch the publish workflow**

```
gh run list --workflow=publish.yml --limit=1
gh run watch <RUN_ID> --exit-status
```

Expected: build, attach-to-release, publish-pypi all succeed.

- [ ] **Step 2: Verify PyPI shows v1.4.0**

```
curl -s https://pypi.org/pypi/fabric-ai-meta/json | python -c "import sys,json; print('latest:', json.load(sys.stdin)['info']['version'])"
```

Expected: `latest: 1.4.0`.

- [ ] **Step 3: Verify attestations**

```
curl -s -o /tmp/prov.json -w "HTTP %{http_code}\n" \
  "https://pypi.org/integrity/fabric-ai-meta/1.4.0/fabric_ai_meta-1.4.0-py3-none-any.whl/provenance"
```

Expected: `HTTP 200`.

### Task 9.4: GitHub release notes

- [ ] **Step 1: Edit auto-created release**

`publish.yml`'s `attach-to-release` job auto-creates a placeholder release. Replace its notes:

```bash
gh release edit v1.4.0 \
  --title "v1.4.0: read half of Prep for AI writeback" \
  --notes "$(cat <<'EOF'
### Added
- CopilotBundle data model + CopilotReader parser surface the Microsoft Copilot/ folder (AI Instructions, Verified Answers, AI Data Schema, example prompts, settings, version) as typed Python objects.
- New \`--with-copilot\` opt-in flag on \`analyze\` and \`scan\` populates \`SemanticModelMeta.copilot\` alongside the existing extractor outputs.
- New \`fabric-ai-meta export copilot MODEL\` CLI mirrors Microsoft's Copilot/ folder layout to \`./output/<slug>/copilot/\` on disk.
- MockExtractor reads a sidecar \`<fixture>.copilot.json\` file when called with \`with_copilot=True\`.

### Notes
- Read-only in v1.4.0; the future \`CopilotWriter\` / \`apply-copilot\` CLI does the inverse.

### Install
\`\`\`bash
pip install --upgrade fabric-ai-meta
\`\`\`

Full changelog: https://github.com/psistla/fabric-ai-meta/blob/master/CHANGELOG.md
EOF
)"
```

### Task 9.5: Post-release sanity check

- [ ] **Step 1: Fresh install from PyPI in a throwaway venv**

```bash
python -m venv /tmp/v140check
source /tmp/v140check/bin/activate    # or .\Scripts\activate on Windows
pip install --upgrade fabric-ai-meta
python -c "
import fabric_ai_meta as f
print('Version:', f.__version__)
print('Has CopilotReader:', hasattr(f, 'CopilotReader'))
print('Has CopilotBundle:', hasattr(f, 'CopilotBundle'))
print('Has AIInstructions:', hasattr(f, 'AIInstructions'))
print('Has VerifiedAnswer:', hasattr(f, 'VerifiedAnswer'))
print('Has AIDataSchema:', hasattr(f, 'AIDataSchema'))
"
deactivate
```

Expected: `Version: 1.4.0` and every `Has X: True`.

- [ ] **Step 2: Done**

Plan complete. Mark all checklist items above. Notify the user with the v1.4.0 release URL, PyPI URL, and the GitHub commit range.

---

## Skills referenced

- `superpowers:test-driven-development` — every task above writes a failing test first
- `superpowers:verification-before-completion` — every chunk ends with running tests + ruff before commit/tag
- `superpowers:subagent-driven-development` — recommended execution mode in Claude Code

## Out-of-scope reminders

- No write path to Fabric (`updateDefinition`) — that is the `CopilotWriter` work in a later release.
- No LRO polling, no permission probe, no refresh-latency warnings.
- No new fields on `workspace-summary.json` for Copilot signals — deferred until governance use cases are defined.
- No changes to `export prep-for-ai` or `apply-descriptions`.
