"""Tests for generators: AI-ready JSON schema (Task 06), framework exports (Task 07),
and Prep for AI config (Task 11)."""

import json
from unittest.mock import MagicMock

from fabric_ai_meta.generator.schema import generate_ai_ready_schema, write_schema_to_file
from fabric_ai_meta.generator.export_langchain import to_langchain_tool_definition
from fabric_ai_meta.generator.export_openai import to_openai_function
from fabric_ai_meta.generator.export_semantic_kernel import to_semantic_kernel_plugin
from fabric_ai_meta.generator.prep_for_ai import generate_prep_for_ai, PrepForAIConfig
from fabric_ai_meta.models.metadata import ColumnRole


EXPECTED_TOP_LEVEL_KEYS = {
    "$schema", "version", "model", "tables", "measures",
    "query_guidance", "scoring",
}


def test_schema_produces_valid_json(adventure_works_model):
    """generate_ai_ready_schema output is JSON-serializable."""
    schema = generate_ai_ready_schema(adventure_works_model)
    raw = json.dumps(schema)
    parsed = json.loads(raw)
    assert isinstance(parsed, dict)


def test_top_level_keys_match_spec(adventure_works_model):
    """Output must contain exactly the keys defined in SPEC.md Section 5.2."""
    schema = generate_ai_ready_schema(adventure_works_model)
    assert set(schema.keys()) == EXPECTED_TOP_LEVEL_KEYS


def test_schema_version_and_url(adventure_works_model):
    schema = generate_ai_ready_schema(adventure_works_model)
    assert schema["$schema"] == "https://fabric-ai-meta.dev/schema/v1.json"
    assert schema["version"] == "1.0"


def test_hidden_tables_excluded(adventure_works_model):
    """Non-hidden tables appear; hidden tables do not."""
    # Mark one table hidden for this test
    adventure_works_model.tables[0].is_hidden = False  # FactInternetSales visible
    schema = generate_ai_ready_schema(adventure_works_model)
    table_names = [t["name"] for t in schema["tables"]]
    for t in adventure_works_model.tables:
        if t.is_hidden:
            assert t.name not in table_names
        else:
            assert t.name in table_names


def test_hidden_columns_excluded(adventure_works_model):
    """Hidden columns must not appear in the output tables."""
    schema = generate_ai_ready_schema(adventure_works_model)
    for table_out in schema["tables"]:
        src_table = next(
            t for t in adventure_works_model.tables if t.name == table_out["name"]
        )
        hidden_col_names = {c.name for c in src_table.columns if c.is_hidden}
        output_col_names = {c["name"] for c in table_out["columns"]}
        assert hidden_col_names.isdisjoint(output_col_names), (
            f"Hidden columns leaked into output for table {table_out['name']}: "
            f"{hidden_col_names & output_col_names}"
        )


def test_all_measure_names_match_source(adventure_works_model):
    """Every non-hidden measure in the source model must appear in the output."""
    schema = generate_ai_ready_schema(adventure_works_model)
    source_names = {
        m.name
        for t in adventure_works_model.tables
        for m in t.measures
        if not m.is_hidden
    }
    output_names = {m["name"] for m in schema["measures"]}
    assert output_names == source_names


def test_scoring_populated(adventure_works_model):
    """Scoring section must be present with overall and breakdown."""
    schema = generate_ai_ready_schema(adventure_works_model)
    scoring = schema["scoring"]
    assert "overall" in scoring
    assert "breakdown" in scoring
    assert 0.0 <= scoring["overall"] <= 1.0


def test_model_section(adventure_works_model):
    schema = generate_ai_ready_schema(adventure_works_model)
    model_sec = schema["model"]
    assert model_sec["name"] == "Adventure Works"
    assert model_sec["workspace"] == "Production Analytics"
    assert "ai_readiness_score" in model_sec


def test_query_guidance_structure(adventure_works_model):
    schema = generate_ai_ready_schema(adventure_works_model)
    qg = schema["query_guidance"]
    assert "valid_filter_paths" in qg
    assert "common_pitfalls" in qg
    assert "recommended_aggregations" in qg
    assert isinstance(qg["valid_filter_paths"], list)
    assert isinstance(qg["common_pitfalls"], list)
    assert isinstance(qg["recommended_aggregations"], dict)


def test_pitfalls_for_non_additive_measures(adventure_works_model):
    """Non-additive measures should generate a pitfall warning."""
    schema = generate_ai_ready_schema(adventure_works_model)
    pitfalls = schema["query_guidance"]["common_pitfalls"]
    pitfall_text = " ".join(pitfalls)
    assert "non-additive" in pitfall_text.lower() or "do not SUM" in pitfall_text


def test_pitfalls_for_time_intelligence_measures(adventure_works_model):
    """Time intelligence measures should generate a date-filter warning."""
    schema = generate_ai_ready_schema(adventure_works_model)
    pitfalls = schema["query_guidance"]["common_pitfalls"]
    pitfall_text = " ".join(pitfalls)
    assert "date filter" in pitfall_text.lower()


def test_recommended_aggregations_exist(adventure_works_model):
    """At least one SUMMARIZECOLUMNS example should be generated."""
    schema = generate_ai_ready_schema(adventure_works_model)
    aggs = schema["query_guidance"]["recommended_aggregations"]
    assert len(aggs) > 0
    for val in aggs.values():
        assert "SUMMARIZECOLUMNS" in val


def test_write_schema_to_file(adventure_works_model, tmp_path):
    """write_schema_to_file produces a parseable JSON file."""
    out = tmp_path / "schema.json"
    result_path = write_schema_to_file(adventure_works_model, str(out))
    assert result_path == str(out)
    with open(out, encoding="utf-8") as f:
        data = json.load(f)
    assert set(data.keys()) == EXPECTED_TOP_LEVEL_KEYS


def test_time_intelligence_measure_has_requires_date_filter(adventure_works_model):
    schema = generate_ai_ready_schema(adventure_works_model)
    ti_measures = [m for m in schema["measures"] if m["category"] == "time_intelligence"]
    assert len(ti_measures) > 0
    for m in ti_measures:
        assert m.get("requires_date_filter") is True


# ---------------------------------------------------------------------------
# Task 07 — LangChain export tests
# ---------------------------------------------------------------------------


def test_langchain_export_valid_dict(adventure_works_model):
    """LangChain export produces a dict with name, description, parameters, metadata."""
    result = to_langchain_tool_definition(adventure_works_model)
    assert isinstance(result, dict)
    assert "name" in result
    assert "description" in result
    assert "parameters" in result
    assert "metadata" in result


def test_langchain_export_name_sanitized(adventure_works_model):
    result = to_langchain_tool_definition(adventure_works_model)
    assert result["name"].startswith("query_")
    # Name should be lowercase with underscores, no spaces
    name_part = result["name"][len("query_"):]
    assert " " not in name_part
    assert name_part == name_part.lower()


def test_langchain_export_is_json_serializable(adventure_works_model):
    result = to_langchain_tool_definition(adventure_works_model)
    raw = json.dumps(result)
    parsed = json.loads(raw)
    assert isinstance(parsed, dict)


def test_langchain_metadata_has_expected_keys(adventure_works_model):
    result = to_langchain_tool_definition(adventure_works_model)
    metadata = result["metadata"]
    assert "model_context" in metadata
    assert "valid_filter_paths" in metadata
    assert "common_pitfalls" in metadata


# ---------------------------------------------------------------------------
# Task 07 — OpenAI export tests
# ---------------------------------------------------------------------------


def test_openai_export_valid_dict(adventure_works_model):
    """OpenAI export produces a dict with type == 'function'."""
    result = to_openai_function(adventure_works_model)
    assert isinstance(result, dict)
    assert result["type"] == "function"


def test_openai_export_function_structure(adventure_works_model):
    result = to_openai_function(adventure_works_model)
    func = result["function"]
    assert "name" in func
    assert "description" in func
    assert "parameters" in func


def test_openai_export_required_question(adventure_works_model):
    """Parameters must have required: ['question']."""
    result = to_openai_function(adventure_works_model)
    params = result["function"]["parameters"]
    assert params["required"] == ["question"]


def test_openai_export_is_json_serializable(adventure_works_model):
    result = to_openai_function(adventure_works_model)
    raw = json.dumps(result)
    parsed = json.loads(raw)
    assert isinstance(parsed, dict)


# ---------------------------------------------------------------------------
# Task 07 — Semantic Kernel export tests
# ---------------------------------------------------------------------------


def test_semantic_kernel_export_valid_dict(adventure_works_model):
    """Semantic Kernel export has schema_version and functions list."""
    result = to_semantic_kernel_plugin(adventure_works_model)
    assert isinstance(result, dict)
    assert "schema_version" in result
    assert "functions" in result
    assert isinstance(result["functions"], list)


def test_semantic_kernel_export_schema_version(adventure_works_model):
    result = to_semantic_kernel_plugin(adventure_works_model)
    assert result["schema_version"] == "v1"


def test_semantic_kernel_export_has_query_function(adventure_works_model):
    result = to_semantic_kernel_plugin(adventure_works_model)
    func_names = [f["name"] for f in result["functions"]]
    assert "query" in func_names


def test_semantic_kernel_export_query_parameters(adventure_works_model):
    result = to_semantic_kernel_plugin(adventure_works_model)
    query_func = result["functions"][0]
    param_names = [p["name"] for p in query_func["parameters"]]
    assert "question" in param_names
    assert "tables" in param_names
    assert "measures" in param_names


def test_semantic_kernel_export_is_json_serializable(adventure_works_model):
    result = to_semantic_kernel_plugin(adventure_works_model)
    raw = json.dumps(result)
    parsed = json.loads(raw)
    assert isinstance(parsed, dict)


# ---------------------------------------------------------------------------
# S4-03 — AutoGen export tests
# ---------------------------------------------------------------------------


def test_autogen_export_valid_dict(adventure_works_model):
    """AutoGen export produces a dict with type, function, and model_context."""
    from fabric_ai_meta.generator.export_autogen import to_autogen_tool
    result = to_autogen_tool(adventure_works_model)
    assert isinstance(result, dict)
    assert result["type"] == "function"
    assert "function" in result
    assert "model_context" in result


def test_autogen_export_function_structure(adventure_works_model):
    """Function section has name, description, and parameters."""
    from fabric_ai_meta.generator.export_autogen import to_autogen_tool
    result = to_autogen_tool(adventure_works_model)
    fn = result["function"]
    assert "name" in fn
    assert fn["name"].startswith("query_")
    assert "description" in fn
    assert "parameters" in fn
    assert fn["parameters"]["required"] == ["question"]


def test_autogen_export_tables_in_context(adventure_works_model):
    """model_context includes table schemas with columns and measures."""
    from fabric_ai_meta.generator.export_autogen import to_autogen_tool
    result = to_autogen_tool(adventure_works_model)
    tables = result["model_context"]["tables"]
    assert len(tables) > 0
    for t in tables:
        assert "name" in t
        assert "type" in t
        assert "columns" in t
        assert "measures" in t


def test_autogen_export_relationships_in_context(adventure_works_model):
    """model_context includes relationships."""
    from fabric_ai_meta.generator.export_autogen import to_autogen_tool
    result = to_autogen_tool(adventure_works_model)
    rels = result["model_context"]["relationships"]
    assert isinstance(rels, list)
    assert len(rels) > 0
    for r in rels:
        assert "from" in r
        assert "to" in r
        assert "cardinality" in r


def test_autogen_export_pitfalls_in_context(adventure_works_model):
    """model_context includes pitfalls list."""
    from fabric_ai_meta.generator.export_autogen import to_autogen_tool
    result = to_autogen_tool(adventure_works_model)
    assert "pitfalls" in result["model_context"]
    assert isinstance(result["model_context"]["pitfalls"], list)


def test_autogen_export_is_json_serializable(adventure_works_model):
    from fabric_ai_meta.generator.export_autogen import to_autogen_tool
    result = to_autogen_tool(adventure_works_model)
    raw = json.dumps(result)
    parsed = json.loads(raw)
    assert isinstance(parsed, dict)


def test_autogen_export_contoso(contoso_model):
    """AutoGen export works with Contoso fixture too."""
    from fabric_ai_meta.generator.export_autogen import to_autogen_tool
    result = to_autogen_tool(contoso_model)
    assert result["type"] == "function"
    tables = result["model_context"]["tables"]
    assert len(tables) > 0


def test_autogen_export_hidden_tables_excluded(adventure_works_model):
    """Hidden tables should not appear in model_context."""
    from fabric_ai_meta.generator.export_autogen import to_autogen_tool
    # Mark a table hidden
    target = adventure_works_model.tables[0]
    original = target.is_hidden
    target.is_hidden = True

    result = to_autogen_tool(adventure_works_model)
    table_names = [t["name"] for t in result["model_context"]["tables"]]
    assert target.name not in table_names

    target.is_hidden = original  # restore


# ---------------------------------------------------------------------------
# Task 11 — Prep for AI config tests
# ---------------------------------------------------------------------------


def _make_mock_llm():
    """Return a FabricLLMClient mock with sensible return values."""
    llm = MagicMock()
    llm.call.return_value = "Use [Internet Total Sales] for revenue questions."
    llm.generate_description.return_value = "Auto-generated business description."
    return llm


def test_prep_for_ai_returns_dataclass(adventure_works_model):
    """generate_prep_for_ai returns a PrepForAIConfig instance."""
    llm = _make_mock_llm()
    result = generate_prep_for_ai(adventure_works_model, llm)
    assert isinstance(result, PrepForAIConfig)


def test_prep_for_ai_included_tables(adventure_works_model):
    """included_tables contains non-hidden, non-staging tables."""
    llm = _make_mock_llm()
    result = generate_prep_for_ai(adventure_works_model, llm)
    assert isinstance(result.included_tables, list)
    assert len(result.included_tables) > 0
    # No hidden tables
    hidden_names = {t.name for t in adventure_works_model.tables if t.is_hidden}
    for name in result.included_tables:
        assert name not in hidden_names


def test_prep_for_ai_hidden_columns_excluded(adventure_works_model):
    """Hidden columns appear in excluded_columns."""
    # Mark a column hidden so we can assert on it
    target_table = adventure_works_model.tables[0]
    target_col = target_table.columns[0]
    original_hidden = target_col.is_hidden
    target_col.is_hidden = True

    llm = _make_mock_llm()
    result = generate_prep_for_ai(adventure_works_model, llm)

    assert target_table.name in result.excluded_columns
    assert target_col.name in result.excluded_columns[target_table.name]

    target_col.is_hidden = original_hidden  # restore


def test_prep_for_ai_sort_columns_excluded(adventure_works_model):
    """SORT role columns appear in excluded_columns."""
    target_table = adventure_works_model.tables[0]
    target_col = target_table.columns[0]
    original_role = target_col.role
    target_col.role = ColumnRole.SORT

    llm = _make_mock_llm()
    result = generate_prep_for_ai(adventure_works_model, llm)

    assert target_table.name in result.excluded_columns
    assert target_col.name in result.excluded_columns[target_table.name]

    target_col.role = original_role  # restore


def test_prep_for_ai_ai_instructions_populated(adventure_works_model):
    """ai_instructions is a non-empty string from the LLM."""
    llm = _make_mock_llm()
    result = generate_prep_for_ai(adventure_works_model, llm)
    assert isinstance(result.ai_instructions, str)
    assert len(result.ai_instructions) > 0
    llm.call.assert_called_once()


def test_prep_for_ai_verified_answers_for_ti_measures(adventure_works_model):
    """verified_answers is generated for time-intelligence measures."""
    llm = _make_mock_llm()
    result = generate_prep_for_ai(adventure_works_model, llm)
    assert isinstance(result.verified_answers, list)
    for answer in result.verified_answers:
        assert "question" in answer
        assert "dax" in answer
        assert "description" in answer


def test_prep_for_ai_generated_descriptions_dict(adventure_works_model):
    """generated_descriptions is a nested dict keyed by table then column."""
    llm = _make_mock_llm()
    result = generate_prep_for_ai(adventure_works_model, llm)
    assert isinstance(result.generated_descriptions, dict)
    for table_name, inner in result.generated_descriptions.items():
        assert isinstance(table_name, str)
        assert isinstance(inner, dict)


def test_prep_for_ai_is_json_serializable(adventure_works_model):
    """PrepForAIConfig must be JSON-serializable via dataclasses.asdict."""
    import dataclasses
    llm = _make_mock_llm()
    result = generate_prep_for_ai(adventure_works_model, llm)
    raw = json.dumps(dataclasses.asdict(result))
    parsed = json.loads(raw)
    assert "included_tables" in parsed
    assert "excluded_columns" in parsed
    assert "ai_instructions" in parsed
    assert "verified_answers" in parsed
    assert "generated_descriptions" in parsed


# ---------------------------------------------------------------------------
# Enterprise fixture — schema generation with large model
# ---------------------------------------------------------------------------


def test_enterprise_schema_all_visible_tables(enterprise_sales_model):
    """Schema generation with 14 tables should include all non-hidden tables."""
    schema = generate_ai_ready_schema(enterprise_sales_model)
    visible_source = [t.name for t in enterprise_sales_model.tables if not t.is_hidden]
    output_names = [t["name"] for t in schema["tables"]]
    assert set(output_names) == set(visible_source)
    assert "_SalesRaw" not in output_names


def test_enterprise_schema_bridge_table_present(enterprise_sales_model):
    """Bridge table CustomerProduct should appear in schema output."""
    schema = generate_ai_ready_schema(enterprise_sales_model)
    table_names = [t["name"] for t in schema["tables"]]
    assert "CustomerProduct" in table_names


def test_enterprise_schema_all_measures_present(enterprise_sales_model):
    """All non-hidden measures from enterprise model should be in schema output."""
    schema = generate_ai_ready_schema(enterprise_sales_model)
    source_measures = {
        m.name for t in enterprise_sales_model.tables
        for m in t.measures if not m.is_hidden
    }
    output_measures = {m["name"] for m in schema["measures"]}
    assert output_measures == source_measures


def test_enterprise_schema_is_json_serializable(enterprise_sales_model):
    """Enterprise schema should be fully JSON-serializable."""
    schema = generate_ai_ready_schema(enterprise_sales_model)
    raw = json.dumps(schema)
    parsed = json.loads(raw)
    assert isinstance(parsed, dict)


def test_enterprise_langchain_export(enterprise_sales_model):
    """LangChain export works with the larger enterprise model."""
    result = to_langchain_tool_definition(enterprise_sales_model)
    assert isinstance(result, dict)
    assert "parameters" in result
    raw = json.dumps(result)
    assert isinstance(json.loads(raw), dict)


def test_enterprise_openai_export(enterprise_sales_model):
    """OpenAI export works with the enterprise model."""
    result = to_openai_function(enterprise_sales_model)
    assert result["type"] == "function"
    assert "parameters" in result["function"]


def test_enterprise_semantic_kernel_export(enterprise_sales_model):
    """Semantic Kernel export works with the enterprise model."""
    result = to_semantic_kernel_plugin(enterprise_sales_model)
    assert result["schema_version"] == "v1"
    assert len(result["functions"]) > 0


def test_enterprise_autogen_export(enterprise_sales_model):
    """AutoGen export handles bridge tables and many-to-many relationships."""
    from fabric_ai_meta.generator.export_autogen import to_autogen_tool
    result = to_autogen_tool(enterprise_sales_model)
    assert result["type"] == "function"
    tables = result["model_context"]["tables"]
    table_names = [t["name"] for t in tables]
    assert "CustomerProduct" in table_names
    rels = result["model_context"]["relationships"]
    both_dir = [r for r in rels if r.get("cross_filter") == "both"]
    assert len(both_dir) >= 1
