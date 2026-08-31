"""Exporter registry: built-in + entry-point plugin discovery.

Plugins register a `BaseExporter` subclass under the `fabric_ai_meta.exporters`
entry-point group in their `pyproject.toml`:

    [project.entry-points."fabric_ai_meta.exporters"]
    dbt = "my_fabric_dbt_plugin:DbtExporter"

`discover_exporters()` merges built-ins with installed plugins; entry-point
plugins with conflicting names override built-ins so users can swap a bundled
exporter for a customized version.
"""

from importlib.metadata import entry_points
from typing import Iterable

from fabric_ai_meta.generator.base import BaseExporter, ExporterError
from fabric_ai_meta.generator.builtin_exporters import BUILTIN_EXPORTERS

ENTRY_POINT_GROUP = "fabric_ai_meta.exporters"


def _iter_plugin_exporter_classes() -> Iterable[tuple[str, type[BaseExporter]]]:
    """Yield (entry_point_name, exporter_class) for every installed plugin.

    Plugins that fail to load are skipped with no error; broken plugins must
    not crash discovery for healthy ones.
    """
    try:
        eps = entry_points(group=ENTRY_POINT_GROUP)
    except TypeError:
        # Python 3.9 compatibility shim; we target 3.10+ so this is defensive.
        eps = entry_points().get(ENTRY_POINT_GROUP, [])  # type: ignore[attr-defined,arg-type]

    for ep in eps:
        try:
            cls = ep.load()
        except Exception:
            continue
        if isinstance(cls, type) and issubclass(cls, BaseExporter):
            yield ep.name, cls


def discover_exporters() -> dict[str, type[BaseExporter]]:
    """Return `{name: ExporterClass}` merging built-ins with entry-point plugins.

    Built-ins are loaded first; entry-point plugins with the same name override
    a built-in (intentional behavior, documented in `docs/plugin-development.md`).
    """
    registry: dict[str, type[BaseExporter]] = {}
    for cls in BUILTIN_EXPORTERS:
        if not cls.name:
            continue
        registry[cls.name] = cls

    for _ep_name, cls in _iter_plugin_exporter_classes():
        if not (isinstance(cls, type) and issubclass(cls, BaseExporter)):
            continue
        if not cls.name:
            continue
        registry[cls.name] = cls

    return registry


def get_exporter(name: str) -> type[BaseExporter]:
    """Look up an exporter class by name. Raises `ExporterError` if not registered."""
    registry = discover_exporters()
    if name not in registry:
        available = ", ".join(sorted(registry)) or "(none)"
        raise ExporterError(
            f"No exporter registered under name '{name}'. Available: {available}."
        )
    return registry[name]
