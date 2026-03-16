"""Tests for generators: AI-ready JSON schema (Task 06) and framework exports (Task 07)."""

import json

from fabric_ai_meta.generator.schema import generate_ai_ready_schema, write_schema_to_file
from fabric_ai_meta.generator.export_langchain import to_langchain_tool_definition
from fabric_ai_meta.generator.export_openai import to_openai_function
from fabric_ai_meta.generator.export_semantic_kernel import to_semantic_kernel_plugin


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
