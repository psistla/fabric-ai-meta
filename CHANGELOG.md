# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
