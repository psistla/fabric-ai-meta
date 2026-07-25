"""Tests for MockExtractor and fixture loading."""

import json
import os

import pytest

from fabric_ai_meta.extractor.mock import MockExtractor
from fabric_ai_meta.models.metadata import SemanticModelMeta, from_dict

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


def test_mock_extractor_returns_semantic_model_meta(adventure_works_model):
    assert isinstance(adventure_works_model, SemanticModelMeta)


def test_adventure_works_table_count(adventure_works_model):
    assert len(adventure_works_model.tables) == 4


def test_adventure_works_table_names(adventure_works_model):
    names = {t.name for t in adventure_works_model.tables}
    assert names == {"FactInternetSales", "DimProduct", "DimCustomer", "DimDate"}


def test_adventure_works_relationship_count(adventure_works_model):
    assert len(adventure_works_model.relationships) == 3


def test_adventure_works_extraction_method(adventure_works_model):
    assert adventure_works_model.extraction_method == "mock"


def test_adventure_works_ai_readiness_score_null(adventure_works_model):
    assert adventure_works_model.ai_readiness_score is None


def test_adventure_works_fact_table_measures(adventure_works_model):
    fact = next(t for t in adventure_works_model.tables if t.name == "FactInternetSales")
    measure_names = {m.name for m in fact.measures}
    assert "[Internet Total Sales]" in measure_names
    assert "[Internet Sales Amount YTD]" in measure_names
    assert "[Internet Distinct Count Customers]" in measure_names


def test_contoso_model_returns_semantic_model_meta(contoso_model):
    assert isinstance(contoso_model, SemanticModelMeta)


def test_contoso_model_table_count(contoso_model):
    assert len(contoso_model.tables) >= 3


def test_contoso_model_measure_count(contoso_model):
    total_measures = sum(len(t.measures) for t in contoso_model.tables)
    assert total_measures >= 5


def test_contoso_model_relationship_count(contoso_model):
    assert len(contoso_model.relationships) >= 2


def test_to_dict_round_trip(adventure_works_model):
    """to_dict() → json.dumps() → json.loads() → from_dict() produces an identical model."""
    original_dict = adventure_works_model.to_dict()
    json_str = json.dumps(original_dict)
    restored_dict = json.loads(json_str)
    restored_model = from_dict(restored_dict)

    assert restored_model.name == adventure_works_model.name
    assert restored_model.workspace == adventure_works_model.workspace
    assert len(restored_model.tables) == len(adventure_works_model.tables)
    assert len(restored_model.relationships) == len(adventure_works_model.relationships)


def test_to_dict_is_json_serializable(adventure_works_model):
    d = adventure_works_model.to_dict()
    result = json.dumps(d)
    assert isinstance(result, str)
    assert len(result) > 0


def test_list_models_returns_model_names():
    """list_models calls fabric.list_datasets and returns model name strings."""
    from unittest.mock import MagicMock

    import pandas as pd

    from fabric_ai_meta.extractor.semantic_link import SemanticLinkExtractor

    mock_fabric = MagicMock()
    mock_df = pd.DataFrame({"Dataset Name": ["Adventure Works", "Contoso Sales"]})
    mock_fabric.list_datasets.return_value = mock_df

    # Bypass __init__ (requires Fabric runtime) by creating instance directly
    extractor = object.__new__(SemanticLinkExtractor)
    extractor.workspace = "test"
    extractor._fabric = mock_fabric

    names = extractor.list_models("test")

    assert "Adventure Works" in names
    assert "Contoso Sales" in names
    assert len(names) == 2


def test_list_models_empty_when_no_datasets():
    """list_models returns empty list when no known column is present."""
    from unittest.mock import MagicMock

    import pandas as pd

    from fabric_ai_meta.extractor.semantic_link import SemanticLinkExtractor

    mock_fabric = MagicMock()
    mock_fabric.list_datasets.return_value = pd.DataFrame()

    extractor = object.__new__(SemanticLinkExtractor)
    extractor.workspace = "test"
    extractor._fabric = mock_fabric

    names = extractor.list_models("test")
    assert names == []


def test_mock_extractor_fixture_path(tmp_path):
    """MockExtractor uses the fixture_path provided at construction."""
    fixture = tmp_path / "model.json"
    fixture.write_text(json.dumps({
        "name": "Test Model",
        "workspace": "Test WS",
        "description": None,
        "tables": [],
        "relationships": [],
        "ai_readiness_score": None,
        "scoring_breakdown": {},
        "extraction_timestamp": None,
        "extraction_method": "mock"
    }))
    extractor = MockExtractor(str(fixture))
    model = extractor.extract("Test Model", "Test WS")
    assert model.name == "Test Model"
    assert model.tables == []


# ── MockExtractor directory mode ─────────────────────────────────────────────


def test_mock_extractor_dir_list_models_returns_both_fixture_names():
    extractor = MockExtractor(fixture_dir=FIXTURES_DIR)
    names = extractor.list_models("any")
    assert "Adventure Works" in names
    assert "Contoso Sales" in names


def test_mock_extractor_dir_list_models_sorted():
    extractor = MockExtractor(fixture_dir=FIXTURES_DIR)
    names = extractor.list_models("any")
    assert names == sorted(names)


def test_mock_extractor_dir_extract_adventure_works():
    extractor = MockExtractor(fixture_dir=FIXTURES_DIR)
    model = extractor.extract("Adventure Works", "any")
    assert model.name == "Adventure Works"
    assert len(model.tables) == 4


def test_mock_extractor_dir_extract_case_insensitive():
    extractor = MockExtractor(fixture_dir=FIXTURES_DIR)
    model = extractor.extract("adventure works", "any")
    assert model.name == "Adventure Works"


def test_mock_extractor_dir_extract_nonexistent_raises():
    extractor = MockExtractor(fixture_dir=FIXTURES_DIR)
    with pytest.raises(FileNotFoundError):
        extractor.extract("Nonexistent Model", "any")


def test_mock_extractor_fixture_path_list_models_single_item():
    extractor = MockExtractor(fixture_path=os.path.join(FIXTURES_DIR, "adventure_works.json"))
    names = extractor.list_models("any")
    assert names == ["Adventure Works"]


def test_mock_extractor_backward_compat_single_file():
    """Single-file usage must still work identically for backward compatibility."""
    extractor = MockExtractor(fixture_path=os.path.join(FIXTURES_DIR, "adventure_works.json"))
    model = extractor.extract("Adventure Works", "test")
    assert isinstance(model, SemanticModelMeta)
    assert len(model.tables) == 4


# ── Enterprise fixture + multi-model (3 fixtures) ──────────────────────────


def test_mock_extractor_dir_list_models_returns_three_fixtures():
    """list_models with fixture_dir picks up all 3 JSON fixtures."""
    extractor = MockExtractor(fixture_dir=FIXTURES_DIR)
    names = extractor.list_models("any")
    assert "Adventure Works" in names
    assert "Contoso Sales" in names
    assert "Enterprise Sales" in names
    assert len(names) == 3


def test_mock_extractor_dir_extract_enterprise_sales():
    """Extracting Enterprise Sales from fixture_dir works."""
    extractor = MockExtractor(fixture_dir=FIXTURES_DIR)
    model = extractor.extract("Enterprise Sales", "any")
    assert model.name == "Enterprise Sales"
    assert len(model.tables) == 14


def test_enterprise_model_has_expected_table_count(enterprise_sales_model):
    """Enterprise model should have 14 tables."""
    assert len(enterprise_sales_model.tables) == 14


def test_enterprise_model_has_expected_measure_count(enterprise_sales_model):
    """Enterprise model should have 20+ measures."""
    total = sum(len(t.measures) for t in enterprise_sales_model.tables)
    assert total >= 20


def test_enterprise_model_has_expected_relationship_count(enterprise_sales_model):
    """Enterprise model should have 10+ relationships."""
    assert len(enterprise_sales_model.relationships) >= 10


def test_enterprise_model_has_hierarchies(enterprise_sales_model):
    """Enterprise model should have 2+ hierarchies."""
    total = sum(len(t.hierarchies) for t in enterprise_sales_model.tables)
    assert total >= 2


def test_enterprise_model_round_trip(enterprise_sales_model):
    """to_dict -> JSON -> from_dict round-trip preserves enterprise model."""
    original_dict = enterprise_sales_model.to_dict()
    json_str = json.dumps(original_dict)
    restored_dict = json.loads(json_str)
    restored_model = from_dict(restored_dict)
    assert restored_model.name == enterprise_sales_model.name
    assert len(restored_model.tables) == len(enterprise_sales_model.tables)
    assert len(restored_model.relationships) == len(enterprise_sales_model.relationships)


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


def test_baseextractor_extract_accepts_with_copilot_kwarg():
    """v1.4.0: extract() gains a kw-only with_copilot flag (default False)."""
    import inspect

    from fabric_ai_meta.extractor.base import BaseExtractor

    sig = inspect.signature(BaseExtractor.extract)
    assert "with_copilot" in sig.parameters
    param = sig.parameters["with_copilot"]
    assert param.kind is inspect.Parameter.KEYWORD_ONLY
    assert param.default is False


def test_mockextractor_fixture_path_loads_copilot_sidecar_when_flag_set():
    from fabric_ai_meta.extractor.mock import MockExtractor

    ex = MockExtractor(fixture_path="tests/fixtures/adventure_works.json")
    model_no = ex.extract("Adventure Works", "ws")
    assert model_no.copilot is None
    model_yes = ex.extract("Adventure Works", "ws", with_copilot=True)
    assert model_yes.copilot is not None
    assert model_yes.copilot.ai_instructions is not None


def test_mockextractor_fixture_path_no_sidecar_leaves_copilot_none(tmp_path):
    """When the fixture has no .copilot.json sidecar, copilot stays None - not an error."""
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
    assert model.copilot is None


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
    assert not any(m.lower().endswith(".copilot") for m in models)
    assert not any(".copilot.json" in m for m in models)


def test_semantic_link_extractor_with_copilot_calls_tmdl_client_and_parses():
    """SemanticLinkExtractor.extract(..., with_copilot=True) calls TMDLClient.get_definition
    and parses the response via CopilotReader. All Fabric/sempy/notebookutils calls mocked."""
    import sys
    import types
    from unittest.mock import MagicMock, patch

    import pandas as pd

    fake_sempy_fabric = MagicMock()
    fake_sempy_fabric.list_tables.return_value = pd.DataFrame()
    fake_sempy_fabric.list_measures.return_value = pd.DataFrame()
    fake_sempy_fabric.list_relationships.return_value = pd.DataFrame()
    fake_sempy_fabric.resolve_workspace_id.return_value = "WS-GUID"
    fake_sempy_fabric.resolve_item_id.return_value = "MODEL-GUID"

    fake_creds = MagicMock()
    fake_creds.getToken.return_value = "FAKE-BEARER-TOKEN"
    fake_notebookutils = types.ModuleType("notebookutils")
    fake_notebookutils.credentials = fake_creds

    sys_modules_patch = patch.dict(sys.modules, {
        "sempy": types.ModuleType("sempy"),
        "sempy.fabric": fake_sempy_fabric,
        "notebookutils": fake_notebookutils,
    })

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
        model = ex.extract("M", "W")

    assert model.copilot is None
    gd.assert_not_called()


# ---------------------------------------------------------------------------
# Shared extractor factory (Task 3)
# ---------------------------------------------------------------------------

def test_build_extractor_mock_single_model():
    from fabric_ai_meta.extractor.factory import _build_extractor
    from fabric_ai_meta.extractor.mock import MockExtractor

    e = _build_extractor(workspace="ws", mock=True, model_name="Adventure Works")
    assert isinstance(e, MockExtractor)


def test_build_extractor_mock_multi_model_when_no_name():
    from fabric_ai_meta.extractor.factory import _build_extractor
    from fabric_ai_meta.extractor.mock import MockExtractor

    e = _build_extractor(workspace="ws", mock=True, model_name=None)
    assert isinstance(e, MockExtractor)
    assert "adventure_works" in [n.lower().replace(" ", "_") for n in e.list_models("ws")]


def test_build_extractor_rejects_mock_and_pbip_together():
    from fabric_ai_meta.extractor.factory import _build_extractor

    with pytest.raises(ValueError, match="mutually exclusive"):
        _build_extractor(workspace=None, mock=True, pbip="some/path")


def test_unmatched_mock_model_raises_and_does_not_substitute():
    """An unrecognised --mock name must error, never fall back to Adventure Works."""
    from fabric_ai_meta.extractor.factory import _fixture_path_for
    with pytest.raises(FileNotFoundError) as exc:
        _fixture_path_for("Northwind Finance P and L")
    msg = str(exc.value)
    assert "Northwind Finance P and L" in msg
    assert "No bundled sample model" in msg
    assert "--pbip" in msg


def test_sample_model_listing_excludes_copilot_sidecars():
    from fabric_ai_meta.extractor.factory import _available_sample_models
    names = _available_sample_models()
    assert "Adventure Works" in names
    assert not any(n.endswith(".copilot") for n in names)
