"""Tests for the AI-ready JSON schema generator (Task 06)."""

import json

from fabric_ai_meta.generator.schema import generate_ai_ready_schema, write_schema_to_file


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
