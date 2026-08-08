"""Parse a Power BI `*.SemanticModel` folder of TMDL into the metadata model.

Local extraction path (v1.6): no Fabric runtime, no notebook. Reads the TMDL
that Power BI Desktop writes under `definition/`. Only the subset this tool
models is parsed; unrecognized TMDL constructs (perspectives, cultures,
annotations, lineage tags, variations, M source) are skipped. A malformed
`.tmdl` file is fatal, naming the file.

Grounded strictly in the committed fixtures under tests/fixtures/pbip/
(see PROVENANCE.md). TMDL indentation is hard tabs; nesting depth = tab count.
"""

from __future__ import annotations

import json
import logging
import os
import re

from fabric_ai_meta.extractor.base import BaseExtractor
from fabric_ai_meta.generator.copilot_reader import CopilotReader
from fabric_ai_meta.models.metadata import (
    ColumnMeta,
    ColumnRole,
    MeasureCategory,
    MeasureMeta,
    RelationshipMeta,
    SemanticModelMeta,
    TableMeta,
    TableType,
)

logger = logging.getLogger(__name__)

_AUTO_DATE_TABLE = re.compile(r"^(LocalDateTable_|DateTableTemplate_)")


def _unquote(name: str) -> str:
    """Strip TMDL single-quotes from a name (`'Sales Order'` -> `Sales Order`).

    A literal apostrophe inside a quoted identifier is escaped by doubling
    (`'Bob''s Data'` -> `Bob's Data`), per TOM/TMDL serialization.
    """
    name = name.strip()
    if len(name) >= 2 and name[0] == "'" and name[-1] == "'":
        return name[1:-1].replace("''", "'")
    return name


def _unquote_opt(name: str | None) -> str | None:
    """`_unquote` for optional properties: absent stays absent."""
    return None if name is None else _unquote(name)


def _split_first_unquoted(s: str, sep: str) -> tuple[str, str | None]:
    """Split `s` on the first `sep` that sits outside a single-quoted span.

    Doubled quotes toggle in/out twice (net no state change), which is correct
    for locating a separator that only ever appears at quote-depth zero.
    """
    in_quote = False
    for i, ch in enumerate(s):
        if ch == "'":
            in_quote = not in_quote
        elif ch == sep and not in_quote:
            return s[:i], s[i + 1 :]
    return s, None


def _split_ref(ref: str) -> tuple[str, str]:
    """Split a `Table.Column` relationship endpoint into (table, column).

    Either side may be single-quoted with spaces (`'All Items'.'Order Date'`);
    the split is on the `.` outside the quotes, and both sides are unquoted.
    """
    table, column = _split_first_unquoted(ref, ".")
    return _unquote(table), _unquote(column or "")


def _tokenize(text: str):
    """Yield (depth, content) per non-blank line; depth = leading tab count.

    Only leading tabs are stripped, so DAX sub-indentation (spaces after the
    tabs) survives for the measure parser.
    """
    for raw in text.splitlines():
        if not raw.strip():
            continue
        stripped = raw.lstrip("\t")
        depth = len(raw) - len(stripped)
        yield depth, stripped.rstrip()


class _Node:
    """One TMDL line as a tree node. Props and block headers are both nodes;
    a block header is simply a node that has children (deeper lines)."""

    __slots__ = ("header", "description", "depth", "children")

    def __init__(self, header: str, description: str | None, depth: int):
        self.header = header
        self.description = description
        self.depth = depth
        self.children: list[_Node] = []

    def child_props(self, depth: int) -> list[str]:
        """Headers of direct children sitting exactly `depth` levels in."""
        return [c.header for c in self.children if c.depth == depth]

    def has_flag(self, flag: str, depth: int) -> bool:
        return flag in self.child_props(depth)

    def prop_value(self, key: str, depth: int) -> str | None:
        """Value of a `key: value` child at `depth`, or None if absent."""
        prefix = key + ":"
        for c in self.children:
            if c.depth == depth and c.header.startswith(prefix):
                return c.header[len(prefix):].strip()
        return None


def _parse_tree(text: str) -> _Node:
    """Build a depth-nested tree. Consecutive `///` lines attach as the
    description of the node that follows them."""
    root = _Node("<root>", None, -1)
    stack: list[_Node] = [root]
    pending_desc: list[str] = []

    for depth, content in _tokenize(text):
        if content.startswith("///"):
            pending_desc.append(content[3:].strip())
            continue
        desc = "\n".join(pending_desc) if pending_desc else None
        pending_desc = []
        node = _Node(content, desc, depth)
        while len(stack) > 1 and stack[-1].depth >= depth:
            stack.pop()
        stack[-1].children.append(node)
        stack.append(node)

    return root


def _find(root: _Node, prefix: str) -> _Node | None:
    """First direct child whose header starts with `prefix`."""
    for c in root.children:
        if c.header.startswith(prefix):
            return c
    return None


def _parse_column(node: _Node) -> ColumnMeta:
    """A `column <name>` block into ColumnMeta. `role` is left UNKNOWN for the
    classifier. Nested `variation` blocks are ignored (they are deeper children
    and never match a column property key)."""
    d = node.depth + 1
    name = _unquote(node.header[len("column ") :].strip())
    return ColumnMeta(
        name=name,
        # lowercased to match the rest of the codebase: TMDL writes `dateTime`,
        # the classifier and every fixture use `datetime`. Same as semantic_link.
        data_type=(node.prop_value("dataType", d) or "").lower(),
        description=node.description,
        ai_description=None,
        role=ColumnRole.UNKNOWN,
        is_hidden=node.has_flag("isHidden", d),
        display_folder=None,
        format_string=node.prop_value("formatString", d),
        sort_by_column=_unquote_opt(node.prop_value("sortByColumn", d)),
    )


def _parse_measure(node: _Node) -> MeasureMeta:
    """A `measure <name> = ...` block into MeasureMeta.

    Two DAX forms both occur in the fixtures: single-line (expression after
    `= ` on the header) and indentation-continuation (nothing after `=`, DAX on
    following lines one tab deeper than the measure's own sub-properties). The
    tokenizer already stripped the leading tabs, so continuation lines join back
    into faithful DAX with their relative (space) indentation intact.
    `category` stays UNKNOWN for the classifier; `format_string` is carried by a
    `PBI_FormatHint` annotation this parser skips, so it stays None (parity).
    """
    decl = node.header[len("measure ") :]
    name_part, inline_dax = _split_first_unquoted(decl, "=")
    name = _unquote(name_part)
    inline_dax = (inline_dax or "").strip()
    if inline_dax:
        dax = inline_dax
    else:
        # Continuation DAX sits deeper than the measure's sub-properties
        # (which are at depth+1). Collect everything below that level so a
        # varying continuation indent cannot silently truncate the expression.
        dax = "\n".join(
            c.header for c in node.children if c.depth >= node.depth + 2
        )

    return MeasureMeta(
        name=name,
        dax_expression=dax,
        description=node.description,
        ai_description=None,
        category=MeasureCategory.UNKNOWN,
        display_folder=None,
        format_string=None,
        is_hidden=node.has_flag("isHidden", node.depth + 1),
    )


def _parse_table_file(path: str) -> TableMeta:
    """Parse one `definition/tables/<name>.tmdl` into a TableMeta.

    Populated so far: name, `///` description, table-level `isHidden`, and
    columns. Measures and partition mode arrive in later parser tasks.
    """
    with open(path, encoding="utf-8") as f:
        text = f.read()

    root = _parse_tree(text)
    node = _find(root, "table ")
    if node is None:
        raise ValueError(f"No `table` declaration found in {path}")

    name = _unquote(node.header[len("table ") :].strip())
    is_hidden = node.has_flag("isHidden", node.depth + 1)
    columns = [
        _parse_column(c) for c in node.children if c.header.startswith("column ")
    ]
    measures = [
        _parse_measure(c) for c in node.children if c.header.startswith("measure ")
    ]

    partition = _find(node, "partition ")
    mode = partition.prop_value("mode", partition.depth + 1) if partition else None

    return TableMeta(
        name=name,
        description=node.description,
        ai_description=None,
        table_type=TableType.UNKNOWN,
        grain=None,
        columns=columns,
        measures=measures,
        is_hidden=is_hidden,
        source_partition_type=mode.title() if mode else None,
    )


def _parse_relationships_file(path: str) -> list[RelationshipMeta]:
    """Parse the top-level `definition/relationships.tmdl` into RelationshipMeta.

    TMDL defaults when a property is absent: active (`isActive` only ever states
    `false`), single cross-filter, and many-to-one cardinality (`toCardinality`
    only ever states `many`, i.e. many-to-many).
    """
    with open(path, encoding="utf-8") as f:
        text = f.read()

    rels: list[RelationshipMeta] = []
    for node in _parse_tree(text).children:
        if not node.header.startswith("relationship "):
            continue
        d = node.depth + 1
        from_ref = node.prop_value("fromColumn", d)
        to_ref = node.prop_value("toColumn", d)
        if from_ref is None or to_ref is None:
            continue
        from_table, from_column = _split_ref(from_ref)
        to_table, to_column = _split_ref(to_ref)
        rels.append(RelationshipMeta(
            from_table=from_table,
            from_column=from_column,
            to_table=to_table,
            to_column=to_column,
            cardinality=(
                "many-to-many"
                if node.prop_value("toCardinality", d) == "many"
                else "many-to-one"
            ),
            cross_filter_direction=(
                "both"
                if node.prop_value("crossFilteringBehavior", d) == "bothDirections"
                else "single"
            ),
            is_active=node.prop_value("isActive", d) != "false",
        ))
    return rels


# ---------------------------------------------------------------------------
# Extractor
# ---------------------------------------------------------------------------


def _is_semantic_model_dir(path: str) -> bool:
    return (
        os.path.isdir(path)
        and path.rstrip("/\\").endswith(".SemanticModel")
        and os.path.isdir(os.path.join(path, "definition"))
    )


def _model_name(sm_dir: str) -> str:
    """Model name from `.platform` `metadata.displayName`, falling back to the
    folder stem (`model.tmdl` only carries the generic `model Model`)."""
    platform = os.path.join(sm_dir, ".platform")
    if os.path.isfile(platform):
        try:
            with open(platform, encoding="utf-8") as f:
                name = json.load(f).get("metadata", {}).get("displayName")
            if name:
                return name
        except (OSError, ValueError):
            logger.warning("Unreadable .platform in %s; using folder name", sm_dir)
    return os.path.basename(sm_dir.rstrip("/\\"))[: -len(".SemanticModel")]


def _discover_copilot(sm_dir: str):
    """Find a `Copilot/` folder case-insensitively (CI is case-sensitive Linux;
    Fabric writes `Copilot`, our reader docstring says `copilot`)."""
    for entry in os.listdir(sm_dir):
        full = os.path.join(sm_dir, entry)
        if entry.lower() == "copilot" and os.path.isdir(full):
            return CopilotReader.from_directory(full)
    return None


class PbipExtractor(BaseExtractor):
    """Extract semantic models from local Power BI TMDL, no Fabric runtime.

    Accepts either a single `*.SemanticModel` folder or a directory containing
    several (the Git Integration repo layout). `.pbip`-file input is deferred to
    v1.7. Auto-generated date tables (`LocalDateTable_*`, `DateTableTemplate_*`)
    and their relationships are skipped: Power BI internals, not user metadata.
    """

    def __init__(self, path: str) -> None:
        self.path = path
        self._dirs: dict[str, str] = {}  # model name -> *.SemanticModel dir

        if _is_semantic_model_dir(path):
            self._dirs[_model_name(path)] = path
        elif os.path.isdir(path):
            for entry in sorted(os.listdir(path)):
                child = os.path.join(path, entry)
                if _is_semantic_model_dir(child):
                    self._dirs[_model_name(child)] = child

        if not self._dirs:
            raise ValueError(
                f"{path!r} is not a *.SemanticModel folder nor a directory "
                f"containing any. Point --pbip at one of those two shapes."
            )

    def list_models(self, workspace: str) -> list[str]:
        return sorted(self._dirs)

    def extract(
        self, model_name: str, workspace: str, *, with_copilot: bool = False
    ) -> SemanticModelMeta:
        sm_dir = self._dirs.get(model_name)
        if sm_dir is None:
            raise ValueError(
                f"No model {model_name!r} under {self.path!r}. "
                f"Available: {self.list_models(workspace)}"
            )

        definition = os.path.join(sm_dir, "definition")
        tables_dir = os.path.join(definition, "tables")
        tables = []
        if os.path.isdir(tables_dir):
            for fname in sorted(os.listdir(tables_dir)):
                if not fname.endswith(".tmdl"):
                    continue
                if _AUTO_DATE_TABLE.match(fname[: -len(".tmdl")]):
                    continue
                tables.append(_parse_table_file(os.path.join(tables_dir, fname)))

        relationships = []
        rel_file = os.path.join(definition, "relationships.tmdl")
        if os.path.isfile(rel_file):
            relationships = [
                r
                for r in _parse_relationships_file(rel_file)
                if not _AUTO_DATE_TABLE.match(r.from_table)
                and not _AUTO_DATE_TABLE.match(r.to_table)
            ]

        model = SemanticModelMeta(
            name=model_name,
            workspace=workspace or os.path.basename(os.path.dirname(sm_dir.rstrip("/\\"))),
            description=None,
            tables=tables,
            relationships=relationships,
            extraction_method="pbip",
        )
        if with_copilot:
            model.copilot = _discover_copilot(sm_dir)
        return model
