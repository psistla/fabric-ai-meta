# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
