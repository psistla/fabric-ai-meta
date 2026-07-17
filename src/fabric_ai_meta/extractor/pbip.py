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

from fabric_ai_meta.models.metadata import TableMeta, TableType


def _unquote(name: str) -> str:
    """Strip TMDL single-quotes from a name (`'Sales Order'` -> `Sales Order`)."""
    if len(name) >= 2 and name[0] == "'" and name[-1] == "'":
        return name[1:-1]
    return name


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


def _parse_table_file(path: str) -> TableMeta:
    """Parse one `definition/tables/<name>.tmdl` into a TableMeta.

    Task 10 scope: name, `///` description, table-level `isHidden`. Columns,
    measures, and partition mode are populated by later parser tasks.
    """
    with open(path, encoding="utf-8") as f:
        text = f.read()

    root = _parse_tree(text)
    node = _find(root, "table ")
    if node is None:
        raise ValueError(f"No `table` declaration found in {path}")

    name = _unquote(node.header[len("table ") :].strip())
    is_hidden = node.has_flag("isHidden", node.depth + 1)

    return TableMeta(
        name=name,
        description=node.description,
        ai_description=None,
        table_type=TableType.UNKNOWN,
        grain=None,
        columns=[],
        measures=[],
        is_hidden=is_hidden,
    )
