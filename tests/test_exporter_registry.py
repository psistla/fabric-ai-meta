"""Tests for the exporter plugin contract and registry."""

import json
import os
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from fabric_ai_meta.cli import main
from fabric_ai_meta.generator.base import BaseExporter, ExporterError
from fabric_ai_meta.generator.builtin_exporters import (
    AutoGenExporter,
    LangChainExporter,
    OpenAIExporter,
    SemanticKernelExporter,
)
from fabric_ai_meta.generator.export_langchain import to_langchain_tool_definition
from fabric_ai_meta.generator.registry import discover_exporters, get_exporter

# ── BaseExporter contract ───────────────────────────────────────────────────


class TestBaseExporter:
    def test_subclass_must_implement_generate(self):
        class Incomplete(BaseExporter):
            name = "incomplete"
            output_filename = "out.json"

        with pytest.raises(TypeError):
            Incomplete()

    def test_write_without_name_raises(self, adventure_works_model, tmp_path):
        class NoName(BaseExporter):
            output_filename = "out.json"

            def generate(self, model):
                return {"ok": True}

        with pytest.raises(ExporterError):
            NoName().write(adventure_works_model, str(tmp_path))

    def test_write_without_filename_raises(self, adventure_works_model, tmp_path):
        class NoFilename(BaseExporter):
            name = "noname"

            def generate(self, model):
                return {"ok": True}

        with pytest.raises(ExporterError):
            NoFilename().write(adventure_works_model, str(tmp_path))

    def test_write_creates_dir_and_serializes_json(self, adventure_works_model, tmp_path):
        class Minimal(BaseExporter):
            name = "minimal"
            output_filename = "minimal.json"

            def generate(self, model):
                return {"model_name": model.name, "table_count": len(model.tables)}

        path = Minimal().write(adventure_works_model, str(tmp_path))
        assert os.path.isfile(path)
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        assert data["model_name"] == adventure_works_model.name
        assert data["table_count"] == len(adventure_works_model.tables)


# ── Built-in exporters ──────────────────────────────────────────────────────


class TestBuiltinExporters:
    def test_langchain_exporter_matches_function_output(self, adventure_works_model):
        cls_output = LangChainExporter().generate(adventure_works_model)
        fn_output = to_langchain_tool_definition(adventure_works_model)
        assert cls_output == fn_output

    def test_each_builtin_has_required_attrs(self):
        for cls in (LangChainExporter, OpenAIExporter, SemanticKernelExporter, AutoGenExporter):
            assert cls.name
            assert cls.output_filename
            assert cls.description

    def test_builtin_write_produces_valid_json(self, adventure_works_model, tmp_path):
        path = OpenAIExporter().write(adventure_works_model, str(tmp_path))
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        assert isinstance(data, dict)


# ── Registry discovery ─────────────────────────────────────────────────────


class TestDiscoverExporters:
    def test_returns_four_builtins_by_name(self):
        registry = discover_exporters()
        for name in ("langchain", "openai", "semantic-kernel", "autogen"):
            assert name in registry

    def test_built_in_classes_are_baseexporter_subclasses(self):
        registry = discover_exporters()
        for cls in registry.values():
            assert issubclass(cls, BaseExporter)

    def test_plugin_overrides_builtin_with_same_name(self):
        class CustomLangChain(BaseExporter):
            name = "langchain"
            output_filename = "custom-langchain.json"
            description = "Custom override"

            def generate(self, model):
                return {"custom": True}

        with patch(
            "fabric_ai_meta.generator.registry._iter_plugin_exporter_classes",
            return_value=iter([("langchain", CustomLangChain)]),
        ):
            registry = discover_exporters()
            assert registry["langchain"] is CustomLangChain

    def test_plugin_adds_new_name_alongside_builtins(self):
        class DbtExporter(BaseExporter):
            name = "dbt"
            output_filename = "dbt-sources.yml"
            description = "dbt sources definition"

            def generate(self, model):
                return {"version": 2, "sources": []}

        with patch(
            "fabric_ai_meta.generator.registry._iter_plugin_exporter_classes",
            return_value=iter([("dbt", DbtExporter)]),
        ):
            registry = discover_exporters()
            assert "dbt" in registry
            assert "langchain" in registry  # built-ins still there

    def test_broken_plugin_does_not_crash_discovery(self):
        # A misbehaving entry point (returns a non-class, or non-BaseExporter
        # subclass) should be skipped silently, leaving built-ins intact.
        with patch(
            "fabric_ai_meta.generator.registry._iter_plugin_exporter_classes",
            return_value=iter([("broken", "not a class")]),
        ):
            registry = discover_exporters()
            assert "langchain" in registry


# ── get_exporter ───────────────────────────────────────────────────────────


class TestGetExporter:
    def test_returns_builtin_by_name(self):
        cls = get_exporter("openai")
        assert cls is OpenAIExporter

    def test_unknown_name_raises_with_helpful_message(self):
        with pytest.raises(ExporterError) as exc_info:
            get_exporter("does-not-exist")
        msg = str(exc_info.value)
        assert "does-not-exist" in msg
        assert "langchain" in msg or "Available" in msg

    def test_lookup_returns_instantiable_class(self, adventure_works_model):
        cls = get_exporter("langchain")
        instance = cls()
        result = instance.generate(adventure_works_model)
        assert isinstance(result, dict)


# ── CLI integration ────────────────────────────────────────────────────────


class TestCLIExportGroup:
    def test_export_help_lists_all_four_builtins(self):
        runner = CliRunner()
        result = runner.invoke(main, ["export", "--help"])
        assert result.exit_code == 0
        for name in ("langchain", "openai", "semantic-kernel", "autogen"):
            assert name in result.output

    def test_export_langchain_mock_still_works(self, tmp_path):
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            result = runner.invoke(main, [
                "export", "langchain", "Adventure Works", "--mock",
            ])
            assert result.exit_code == 0, result.output

    def test_export_openai_mock_still_works(self, tmp_path):
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            result = runner.invoke(main, [
                "export", "openai", "Adventure Works", "--mock",
            ])
            assert result.exit_code == 0, result.output

    def test_export_autogen_mock_still_works(self, tmp_path):
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            result = runner.invoke(main, [
                "export", "autogen", "Adventure Works", "--mock",
            ])
            assert result.exit_code == 0, result.output
