# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.6.0] - 2026-07-17

Local extraction. The tool now reads real semantic models from disk with no Fabric notebook, no tenant, and no auth.

### Added
- `PbipExtractor` under `fabric_ai_meta.extractor.pbip`: parses a Power BI `*.SemanticModel` folder of TMDL (`definition/**/*.tmdl`) into `SemanticModelMeta`, and reads the sibling `Copilot/` folder via the existing `CopilotReader.from_directory()`. Hand-rolled tab-indent TMDL parser covering tables, columns, measures (single-line and indentation-continuation DAX), relationships, and partition mode. Auto-generated date tables (`LocalDateTable_*`, `DateTableTemplate_*`) and their relationships are skipped. New top-level export; `__all__` grows from 45 to 46.
- `--pbip PATH` option on `analyze`, `scan`, `score` (including `--all`), `governance`, and every `export <framework>` command. Accepts either a single `*.SemanticModel` folder or a directory of them (a Git Integration repo). Mutually exclusive with `--mock` and `--workspace`; conflicts raise a usage error. Copilot discovery is automatic in this mode since reading a local folder is free.
- `extractor/factory.py` (`_build_extractor`) and `analyzer/pipeline.py` (`classify_model_in_place`): shared construction and classification paths used by both the CLI and the MCP server, so the two surfaces can no longer return different results for the same model.

### Fixed
- Measure dependencies computed by `parse_measure_dependencies` are now written onto `MeasureMeta` (`depends_on_measures`, `depends_on_columns`, `implicit_filters`). Previously they were computed and discarded, so in live Fabric mode `ai-ready-schema.json` silently dropped three keys and the `business_rules_documented` scoring dimension always read zero. **This activates a scoring dimension that never ran against real data, so existing users' readiness scores can move up or down, and any `scripts/ci-governance-check.py` threshold may flip.**
- `export <framework>` now classifies the model before writing, so exporters emit real measure categories instead of `"unknown"` in live Fabric mode. Mock fixtures had masked this by pre-baking `category`.
- `score --all --mock` no longer raises `FabricEnvironmentError`; it had no mock branch despite the documented `--mock` parity.
- `governance --mock` no longer depends on the working directory; it used a relative fixtures path and broke when run outside the repo root.

## [1.5.0] - 2026-05-17

### Added
- `CopilotWriter` ABC + `MockCopilotWriter` + `SemanticLinkCopilotWriter` under `fabric_ai_meta.writeback.copilot_writer`. Closes the write half of Prep for AI started in v1.4.0. `SemanticLinkCopilotWriter` resolves workspace and model ids via `sempy.fabric`, calls Fabric REST `getDefinition`, splices the bundle's Copilot parts into the full TMDL envelope, then posts the result through `updateDefinition` and polls the long-running operation to completion.
- `CopilotWritebackResult` dataclass: per-primitive counts + planned changes list + `dry_run` + `succeeded` + `errors`. JSON-serializable via `to_dict()`.
- `splice_copilot_into_envelope(envelope, bundle) -> (new_envelope, changes)` pure helper. Replace semantics: any existing `Copilot/` part not present in the new bundle is removed; non-Copilot parts (TMDL under `definition/`, project metadata) are preserved byte-for-byte.
- `fabric-ai-meta apply-copilot COPILOT_DIR --model M --workspace W [--dry-run/--no-dry-run] [--mock]` CLI command. Reads a Copilot/ folder produced by `export copilot`, applies it to a live semantic model via Fabric REST.
- `CopilotReader.from_directory(path) -> CopilotBundle` inverse of `CopilotExporter.write`. Round-trip pattern: `export copilot` → edit local folder → `apply-copilot`.
- `CopilotBundle.signals() -> dict` returns seven canonical governance signals: `has_ai_instructions`, `ai_instructions_length`, `verified_answer_count`, `ai_data_schema_table_count`, `example_prompt_count`, `copilot_enabled`, `copilot_version`.
- `CopilotBundle.from_dict(data)` inverse of `to_dict()`. `SemanticModelMeta.from_dict()` now round-trips the `copilot` field; previously dropped silently.
- `scan --with-copilot` populates per-model `copilot` block + top-level `copilot_summary` rollup (`models_with_copilot`, `models_without_ai_instructions`, `total_verified_answers`) in `workspace-summary.json`.
- `governance --with-copilot` populates `copilot_completeness` section in the governance report and emits a recommendation per model missing AI Instructions.
- `compare_workspace_summaries` surfaces Copilot regressions in `model_delta.copilot_changes` (added/removed AI Instructions, verified-answer count delta, schema-table count delta, prompt count delta). Removal of AI Instructions on an otherwise-unchanged model downgrades the model's status to `degraded`.
- `TMDLClient.update_definition(model_id, definition)` method with built-in LRO polling. Honors `Location` header, distinguishes synchronous 200 from async 202, raises on `Failed` terminal status or timeout.
- `BaseExporter.requires_copilot: ClassVar[bool] = False` opt-in flag. The CLI export dispatch uses this so third-party plugins can request `with_copilot=True` extraction without monkey-patching the registration code. `CopilotExporter.requires_copilot = True`.
- Shared `copilot_core_signals` `$ref` definition in `schemas/workspace-summary/v1.json` and `schemas/governance-report/v1.json`. Single source of truth for the seven-signal shape across both output formats.

### Changed
- `__all__` count grows from 40 to 45. Five new top-level exports: `CopilotWriter`, `MockCopilotWriter`, `SemanticLinkCopilotWriter`, `CopilotWritebackResult`, `splice_copilot_into_envelope`.
- `apply-descriptions` now exits non-zero when errors occur in a non-dry-run invocation. Brings it to parity with `apply-copilot`. CI gates that consume the exit code will now distinguish a clean writeback from one that hit XMLA errors.
- `MockCopilotWriter` reports planned changes with `operation` values from the same `{create, update, delete}` vocabulary as `SemanticLinkCopilotWriter`, instead of the v0 `write` placeholder. Tests pinned to this enum.
- `TMDLClient.update_definition` floors `poll_interval_seconds` at 0.5s in production to avoid rate-limiting the Fabric API; tests opt out by passing 0 explicitly.

### Fixed
- `MockExtractor._attach_copilot` no longer crashes the whole model extract when the `<fixture>.copilot.json` sidecar contains malformed JSON or fails to open; logs a warning and leaves `model.copilot = None`.
- `_compute_copilot_changes` returns `None` (not a phantom diff) when only one snapshot was scanned with `--with-copilot`. Prevents false `ai_instructions_removed` / `degraded` status alerts when the flag is toggled between scans.
- `splice_copilot_into_envelope` filters out parts with empty or `None` paths from the existing envelope rather than forwarding them to `updateDefinition`.
- `_bundle_to_copilot_parts` validates `VerifiedAnswer.filename` is a safe basename. Rejects path-traversal segments (`..`, `/`, `\`) that could be introduced programmatically.
- `CopilotWritebackResult.dry_run` now accurately reflects the requested mode even when the write fails; the new `succeeded` flag carries the success signal independently. CLI prints `DRY RUN` / `APPLIED` / `FAILED` labels accordingly.
- `format_delta_text` renders all three Copilot count deltas (verified answers, schema tables, example prompts), matching the JSON output. Previously only verified-answer count was shown.

### Notes
- The first real Fabric notebook run with `apply-copilot --no-dry-run` will verify the assumed `sempy.fabric.resolve_workspace_id` / `resolve_item_id` helper names against the actual sempy 0.8 surface; resolver failures raise a clear `RuntimeError` rather than silently no-op.
- Refresh-latency warning for DirectQuery / Direct Lake models on `apply-copilot` is intentionally deferred. The Fabric REST `updateDefinition` LRO returns success on the metadata write itself; downstream cache invalidation for DQ / Direct Lake is out of scope for v1.5.0.
- Write semantics are full-replace within `Copilot/`. To preserve a primitive untouched, round-trip it: `CopilotReader.from_definition` (or `from_directory`) → mutate → `apply-copilot`. Non-Copilot parts of the model definition are always preserved.

## [1.4.0] - 2026-05-17

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

## [1.3.5] - 2026-05-16

### Changed
- `attestations: true` is now pinned explicitly in the `pypa/gh-action-pypi-publish` step of `.github/workflows/publish.yml`. The action defaults to generating PEP 740 sigstore attestations since v1.10, so every release on PyPI was already shipping with provenance signatures; this commit makes the contract explicit in source so a future action default change cannot silently drop attestations from the wheel and sdist.

## [1.3.4] - 2026-05-16

### Changed
- GitHub repository flipped from private to public so the sidebar links on the PyPI project page (Repository, Issues, Changelog, Documentation, Releases), the CI status badge, and the JSON Schema `$id` URLs all resolve for anonymous visitors. Previously the package installed fine but every link on https://pypi.org/project/fabric-ai-meta/ returned a GitHub 404 or login wall.

### Fixed
- README rewrote all relative file links (`docs/user-guide.md`, `docs/ci-cd-guide.md`, `docs/plugin-development.md`, `docs/research/tmdl-prep-for-ai-spike.md`, `notebooks/quickstart.ipynb`, `notebooks/tmdl-spike.ipynb`, `scripts/ci-governance-check.py`, `.mcp.json`, `schemas/`) to absolute `github.com/psistla/fabric-ai-meta/blob/master/...` URLs. PyPI does not rewrite relative paths when rendering the README, so the previous links resolved to `https://pypi.org/project/fabric-ai-meta/docs/...` and returned 404. They now open the file on GitHub from either site.

## [1.3.3] - 2026-05-11

### Added
- Full PyPI project metadata in `pyproject.toml`: `description` (matches the GitHub About blurb), `readme = "README.md"` so the README renders on the PyPI project page, `authors`, `license`, `keywords`, `classifiers`, and a `[project.urls]` block with Homepage, Repository, Issues, Changelog, Documentation, and Releases links

### Changed
- The PyPI project page at https://pypi.org/project/fabric-ai-meta/ now shows the full README body, tagline, author, license, and the sidebar link strip; previously only the package name and version were visible

## [1.3.2] - 2026-05-11

### Added
- First PyPI publish of `fabric-ai-meta`. The package is now installable with `pip install fabric-ai-meta` from PyPI; the GitHub release continues to host the same wheel and source distribution as downloadable assets for airgapped users
- `publish-pypi` job in the release workflow now runs (gated behind the `PYPI_PUBLISH_ENABLED` repository variable) and uploads to PyPI via Trusted Publishing on every `v*` tag push, with no API token stored in the repo

## [1.3.1] - 2026-05-11

### Added
- Built `.whl` and `.tar.gz` distribution artifacts attached to every GitHub release, so users can `pip install` from a release URL without cloning the repo
- `.github/workflows/publish.yml` GitHub Actions workflow that builds the wheel and source distribution on every `v*` tag push and uploads them as release assets; an optional PyPI publish step is wired up via trusted publishing (OIDC) and activates once the project is claimed on PyPI

### Changed
- README and `docs/user-guide.md` install instructions corrected to reflect actual distribution channels: the package is installable from GitHub today (either `git+https://...` or release wheel URL) while PyPI publish is pending
- Quickstart notebook (`notebooks/quickstart.ipynb`) and TMDL spike notebook (`notebooks/tmdl-spike.ipynb`) updated to `%pip install` from the GitHub release URL rather than `pip install fabric-ai-meta`, which was never valid

### Fixed
- `pip install fabric-ai-meta` references throughout the README, user guide, and bundled notebooks pointed at a PyPI name that has not yet been published, leaving new users with a "No matching distribution found" error; all references now use a working install command

## [1.3.0] - 2026-05-10

### Added
- Plugin architecture for custom exporters. Third parties subclass `BaseExporter` and register the class via the `fabric_ai_meta.exporters` Python entry-point group; the class then appears as `fabric-ai-meta export <name>` with `--workspace` and `--mock` flags wired up automatically
- `BaseExporter` ABC + `ExporterError` in `fabric_ai_meta.generator.base`; default `write()` serializes `generate()` as indented JSON under `{output}/{model-slug}/{output_filename}`
- `discover_exporters()` and `get_exporter()` registry helpers; entry-point plugins with conflicting names override built-ins (documented behavior)
- Built-in exporters wrapped as `BaseExporter` subclasses (`LangChainExporter`, `OpenAIExporter`, `SemanticKernelExporter`, `AutoGenExporter`) without breaking the function-style API (`to_langchain_tool_definition`, etc.) that existing users rely on
- New public API exports: `BaseExporter`, `ExporterError`, `discover_exporters`, `get_exporter` (`__all__` count now 35)
- `docs/plugin-development.md` walks through the contract, entry-point registration, a complete worked dbt example, local testing, and name-conflict rules
- `tests/test_exporter_registry.py` covers contract enforcement, built-in parity with function-style exports, plugin override semantics, broken-plugin tolerance, and CLI integration

### Changed
- The `export` CLI group is now built dynamically from the registry on import; the four built-in subcommands behave exactly as before but now share a single code path with any installed plugin

## [1.2.0] - 2026-05-10

### Added
- Multi-provider LLM support via LiteLLM. Ten provider routes ship in `LiteLLMBackend`: `anthropic`, `openai`, `google` (Gemini), `xai` (Grok), `mistral`, `cohere`, `bedrock` (AWS), `azure` (Azure OpenAI), `vertex` (Google Vertex AI), and `openai-compatible` for Groq, Together, Fireworks, Ollama, LM Studio, vLLM, or any custom OpenAI-API endpoint
- New abstract base class `BaseLLMClient` with shared cache, cumulative cost tracking, and budget enforcement; subclasses implement a single `_raw_call()` and reuse all prompt construction
- New `LLMCallResult` dataclass that normalizes responses across backends
- New `load_llm_client(config)` factory in `fabric_ai_meta.llm` for building a client from `LLMConfig`
- `LLMConfig` gained optional `base_url`, `azure_endpoint`, `azure_api_version`, `vertex_project`, and `vertex_location` fields
- New `[llm]` optional extra: `pip install 'fabric-ai-meta[llm]'` installs LiteLLM
- `tests/test_litellm_backend.py` with 37 new tests covering provider dispatch, API key resolution, JSON-mode routing, cost limits, cache reuse, and the `openai-compatible` escape hatch

### Changed
- `FabricLLMClient` is now a thin `LiteLLMBackend` subclass; its public surface (`call`, `classify_table`, `detect_grain`, `generate_description`, `generate_descriptions_batch`, token counters, `CostLimitExceededError`) is unchanged so existing user code keeps working
- `cli._run_llm_enrichment` and `export prep-for-ai --llm-enrich` now build the client via `load_llm_client(cfg)`, picking up `cfg.llm.provider` and friends from `.fabric-ai-meta.toml`
- README LLM Enrichment section restructured around a provider matrix plus per-provider config snippets

## [1.1.2] - 2026-05-10

### Fixed
- `tomli` is now declared as a dependency for Python 3.10 so `load_config()` no longer raises `ImportError` when the runtime is 3.10 and a `.fabric-ai-meta.toml` is present
- `export langchain|openai|semantic-kernel|autogen` now accept `--mock`, matching the documentation in README and bringing them in line with `analyze`, `scan`, `score`, `governance`, and `export prep-for-ai`
- `MAX_CONTEXT_TOKENS` budget in `llm/client.py` raised from 190,000 to 950,000 to reflect Claude Sonnet 4.6's actual 1,000,000-token context window (the previous comment was outdated)

### Changed
- `mcp[cli]` pin tightened to `>=1.0,<2.0` so an eventual `mcp` 2.0 release (which reworks `FastMCP`, transports, and auth) cannot silently break the MCP server
- `click` pin tightened to `>=8.1,<9.0` to avoid pulling 9.0 once it ships and removes deprecated APIs
- JSON Schema `$id` and output `$schema` URLs migrated from the placeholder `fabric-ai-meta.dev` domain (unregistered) to resolvable GitHub raw URLs at `raw.githubusercontent.com/psistla/fabric-ai-meta/master/schemas/`

## [1.1.1] - 2026-04-29

### Added
- JSON Schema file `schemas/prep-for-ai/v1.json` plus a validation test for the `export prep-for-ai` output, closing the last documented-but-unshipped schema reference
- `py.typed` marker so consumers get full type information from mypy and pyright
- Python 3.13 to the CI test matrix

### Changed
- `.mcp.json` now invokes the `fabric-ai-meta serve` console script instead of running `python src/fabric_ai_meta/mcp_server.py`, so the bundled MCP config works for installed packages, not just from the repo root
- CI lint step broadened from `ruff check src/ tests/` to `ruff check .` so notebooks stay clean alongside the package

### Fixed
- Five ruff issues in `notebooks/quickstart.ipynb` (three unsorted import blocks, one unused `json` import, one f-string with no placeholders) that the previous CI scope was hiding

### Documentation
- Punctuation alignment pass on `.fabric-ai-meta.toml.example` to match the rest of the repo's style

## [1.1.0] - 2026-04-20

### Added
- Description writeback through XMLA / TOM with the `apply-descriptions` CLI command and `MockWriter` / `SemanticLinkWriter` classes
- MCP server exposing `list_models`, `analyze_model`, `score_model`, `generate_schema`, `governance_report`, and `diff_summaries` to AI agents (Claude Code, Claude Desktop), launched via `fabric-ai-meta serve`; project-root `.mcp.json` for auto-discovery
- TMDL / Copilot research client (`TMDLClient`) and accompanying spike documentation that locates Prep for AI primitives (AI Instructions, AI Data Schema, Verified Answers) inside the Fabric REST `getDefinition` payload
- CI/CD integration guide (`docs/ci-cd-guide.md`) with ready-to-paste GitHub Actions and Azure DevOps workflows, plus a standalone `scripts/ci-governance-check.py` threshold script
- Public API exports for `DescriptionWriter`, `MockWriter`, `SemanticLinkWriter`, `WritebackResult`
- Spike notebook (`notebooks/tmdl-spike.ipynb`) for Fabric-environment verification of the Copilot folder layout

### Changed
- Test suite expanded to 343 tests
- README restructured with MCP integration, writeback, and CI/CD sections; project-export count refreshed to 31

### Documentation
- Internal sprint and task identifiers removed from tracked source, tests, and docs
- Punctuation pass across tracked files for tone consistency

## [1.0.0] - 2026-04-04

### Added
- Cross-model governance analysis: naming inconsistencies, duplicate measures, governance scorecard
- `governance` CLI command with `--mock`, `--report`, `--output` flags
- Governance report JSON output (`governance-report.json`)
- Full test suite audit and completion checklist (210 tests)
- README redesign with badges, feature grid, Mermaid architecture diagram

### Changed
- All CLI extraction commands now support `--mock` consistently
- Test coverage expanded to verify all acceptance criteria (GOV-01 through GOV-03)

## [0.3.0] - 2026-03-26

### Added
- Prep for AI configuration generator (`export prep-for-ai` command)
- LLM-powered batch description backfill for tables, columns, and measures
- Bulk workspace scan (`scan` command) with multi-model mock support
- `--llm-enrich` flag for LLM-enhanced analysis and description generation
- Per-model output directories with workspace summary JSON

### Changed
- MockExtractor supports `fixture_dir` for multi-model scanning

## [0.1.0] - 2026-03-18

### Added
- Project scaffolding with Click CLI framework
- Data model: `SemanticModelMeta`, `TableMeta`, `ColumnMeta`, `MeasureMeta`, `RelationshipMeta`, `HierarchyMeta`
- Enums: `TableType`, `MeasureCategory`, `ColumnRole`
- Serialization: `to_dict()` / `from_dict()` on all dataclasses
- `MockExtractor` with JSON fixture support
- `SemanticLinkExtractor` for Fabric notebook runtime
- Entra ID authentication module with environment detection
- Heuristic classifiers for tables, measures, and column roles
- DAX dependency parser with `networkx` graph support
- AI Readiness Scorer with weighted scoring breakdown
- AI-ready JSON schema generator with versioned output
- Framework export generators: LangChain, OpenAI function calling, Semantic Kernel
- LLM client (`FabricLLMClient`) with Claude API integration
- Prompt templates for classification, grain detection, and description generation
- File-based LLM response cache (SHA-256 keyed)
- Full CLI: `analyze`, `score`, `export`, `auth` commands
- Adventure Works and Contoso Sales test fixtures
- UTF-8 stdout/stderr reconfiguration for Windows compatibility
