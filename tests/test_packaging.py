"""Guards on the declared dependency surface.

This file exists because every defect in the v1.8.0 audit was drift between
what the package declares and what it does. These are the cheapest possible checks.
"""
import sys

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib


def _pyproject():
    from pathlib import Path
    p = Path(__file__).resolve().parent.parent / "pyproject.toml"
    with open(p, "rb") as f:
        return tomllib.load(f)


def test_extras_are_exactly_the_declared_set():
    extras = set(_pyproject()["project"]["optional-dependencies"])
    assert extras == {"fabric", "llm", "mcp", "dev"}


def test_anthropic_is_not_a_dependency():
    deps = " ".join(_pyproject()["project"]["dependencies"])
    assert "anthropic" not in deps


def test_base_install_has_no_fabric_dependencies():
    deps = " ".join(_pyproject()["project"]["dependencies"])
    for name in ("semantic-link-sempy", "semantic-link-labs", "azure-identity"):
        assert name not in deps
