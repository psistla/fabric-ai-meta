"""Shared pytest fixtures for fabric-ai-meta tests."""

import os

import pytest

from fabric_ai_meta.extractor.mock import MockExtractor
from fabric_ai_meta.models.metadata import SemanticModelMeta

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


@pytest.fixture
def adventure_works_model() -> SemanticModelMeta:
    extractor = MockExtractor(os.path.join(FIXTURES_DIR, "adventure_works.json"))
    return extractor.extract("Adventure Works", "Production Analytics")


@pytest.fixture
def contoso_model() -> SemanticModelMeta:
    extractor = MockExtractor(os.path.join(FIXTURES_DIR, "contoso_sales.json"))
    return extractor.extract("Contoso Sales", "Production Analytics")


@pytest.fixture
def enterprise_sales_model() -> SemanticModelMeta:
    extractor = MockExtractor(os.path.join(FIXTURES_DIR, "enterprise_sales.json"))
    return extractor.extract("Enterprise Sales", "Production Analytics")
