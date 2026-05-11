# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
