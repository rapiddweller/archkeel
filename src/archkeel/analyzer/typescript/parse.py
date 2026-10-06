# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Read module references and unprovable loader patterns from one TypeScript or JavaScript file.

This is the only module that touches parser objects. The parser runs inside the collector
process, never in the Core process, because it reads untrusted source. What it cannot read
reliably becomes a concern the collector reports as UNKNOWN.
"""

from __future__ import annotations

import re
from bisect import bisect_right
from dataclasses import dataclass
from functools import cache
from typing import Final, Literal

import tree_sitter_typescript
from tree_sitter import Language, Node, Parser, Query, QueryCursor

Form = Literal["import", "reexport", "import_equals", "dynamic_import", "import_type", "require"]
Grammar = Literal["typescript", "tsx"]

_LOADER_MODULES: Final = frozenset({"module", "node:module"})
_LOADER: Final = "Node module loader is not observed"
# A comment opens a JSDoc block unless it is `/**/`; only those can carry typed imports.
_JSDOC_IMPORT: Final = re.compile(r"^/\*\*(?!/)[\s\S]*(?:@import\b|\bimport\s*\()")
_TRIPLE_SLASH: Final = re.compile(r"^///\s*<reference\s+(?:path|types|lib)\s*=\s*(['\"])(.*?)\1")
# Line breaks as the TypeScript compiler counts them, so reported lines agree with it.
_LINE_BREAK: Final = re.compile(rb"\r\n|[\n\r]|\xe2\x80[\xa8\xa9]")
# Constructs that hold types: a module named inside them is a type-only reference.
_TYPE_PARENTS: Final = frozenset(
    {
        "type_annotation",
        "type_arguments",
        "type_query",
        "type_alias_declaration",
        "type_parameter",
        "extends_type_clause",
        "implements_clause",
    }
)
_QUERIES: Final = {
    "references": """
        (import_statement) @import
        (export_statement source: (_)) @export
        (call_expression function: (import)) @dynamic
        (call_expression function: (identifier) @callee (#eq? @callee "require")) @require
        """,
    "comments": "(comment) @comment",
    "errors": "[(ERROR) (MISSING)] @error",
    "require_names": """
        ([(identifier) (type_identifier) (shorthand_property_identifier)
          (shorthand_property_identifier_pattern)] @name (#eq? @name "require"))
        """,
    "require_members": """
        (member_expression property: (property_identifier) @name (#eq? @name "require")) @member
        (subscript_expression index: (string) @name (#match? @name "^.require.$")) @subscript
        (subscript_expression object: (identifier) @object (#eq? @object "module")) @subscript
        (pair_pattern key: (_) @key) @pair
        """,
    "module_names": '((identifier) @name (#eq? @name "module"))',
    "create_require": """
        ([(identifier) (property_identifier) (shorthand_property_identifier)
          (shorthand_property_identifier_pattern) (string_fragment)] @name
          (#eq? @name "createRequire"))
        """,
}


@dataclass(frozen=True, slots=True)
class Span:
    """A 1-based line and UTF-16 column, as the TypeScript compiler reports them."""

    line: int
    end_line: int
    column: int
    excerpt: str


@dataclass(frozen=True, slots=True)
class Reference:
    form: Form
    # None when the argument is not a plain string, so no module can be named.
    specifier: str | None
    type_only: bool
    module_level: bool
    # A `resolution-mode` attribute replaces the mode a resolver would derive.
    mode_override: bool
    span: Span


@dataclass(frozen=True, slots=True)
class Concern:
    reason: str
    span: Span


@dataclass(frozen=True, slots=True)
class Syntax:
    references: tuple[Reference, ...]
    concerns: tuple[Concern, ...]
    # A `require` name that is not a plain call may be a local binding, not the loader.
    shadows_require: bool
    first_error: Span | None


@dataclass(frozen=True, slots=True)
class _Source:
    kind: Grammar
    root: Node
    data: bytes
    starts: list[int]

    def captures(self, query: str, scope: Node | None = None) -> dict[str, list[Node]]:
        return QueryCursor(_query(self.kind, query)).captures(scope or self.root)

    def span(self, node: Node, start: Node | None = None) -> Span:
        first = (start or node).start_byte
        line = bisect_right(self.starts, first)
        prefix = str(self.data[self.starts[line - 1] : first], "utf-8", "replace")
        return Span(
            line,
            bisect_right(self.starts, node.end_byte),
            len(prefix.encode("utf-16-le")) // 2 + 1,
            _text(start or node)[:400],
        )


@cache
def _grammar(kind: Grammar) -> Language:
    return Language(
        tree_sitter_typescript.language_tsx()
        if kind == "tsx"
        else tree_sitter_typescript.language_typescript()
    )


@cache
def _query(kind: Grammar, name: str) -> Query:
    return Query(_grammar(kind), _QUERIES[name])


def parse(rel_path: str, data: bytes) -> Syntax:
    # JSX and JavaScript need the TSX grammar; `<T>x` assertions exist only without it.
    kind: Grammar = "typescript" if re.search(r"\.[cm]?ts$", rel_path) else "tsx"
    root = Parser(_grammar(kind)).parse(data).root_node
    source = _Source(kind, root, data, [0, *(found.end() for found in _LINE_BREAK.finditer(data))])
    found = source.captures("references")
    candidates = [
        *((node, _import(node, source)) for node in found.get("import", [])),
        *((node, _export(node, source)) for node in found.get("export", [])),
        *((node, _dynamic(node, source)) for node in found.get("dynamic", [])),
        *((node, _require(node, source)) for node in found.get("require", [])),
    ]
    trusted = [item for node, item in candidates if not (root.has_error and _in_error(node))]
    concerns: list[Concern] = []
    # `module[name]` can reach `require` without spelling it.
    needed = b"require" in data or b"module" in data
    shadows = _require_concerns(source, concerns) if needed else False
    loaders = [item.span for item in trusted if item.specifier in _LOADER_MODULES]
    if b"createRequire" in data:
        loaders.extend(
            source.span(node) for node in source.captures("create_require").get("name", [])
        )
    # One gap per file: the first use already makes every later `require` unprovable.
    if loaders:
        concerns.append(Concern(_LOADER, min(loaders, key=lambda span: (span.line, span.column))))
    if b"/**" in data or b"///" in data:
        concerns.extend(_comment_concerns(source))
    errors = sorted(source.captures("errors").get("error", []), key=lambda item: item.start_byte)
    return Syntax(
        tuple(sorted(trusted, key=lambda item: (item.span.line, item.span.column, item.form))),
        tuple(concerns),
        shadows,
        source.span(errors[0]) if errors else None,
    )


def _text(node: Node) -> str:
    return str(node.text or b"", "utf-8", "replace")


def _in_error(node: Node) -> bool:
    """A reference inside a region the parser had to repair is not a fact."""
    if node.has_error:
        return True
    parent = node.parent
    while parent is not None:
        if parent.is_error:
            return True
        parent = parent.parent
    return False


def _literal(node: Node | None) -> str | None:
    """The module text of a string without escapes or substitutions; None means computed."""
    if node is None or node.type not in ("string", "template_string") or "\\" in _text(node):
        return None
    if any(child.type == "template_substitution" for child in node.children):
        return None
    return _text(node)[1:-1]


def _type_only(statement: Node, specifiers: list[Node], default: bool) -> bool:
    """`import type`, or every named specifier marked `type` with no default import."""
    marked = bool(specifiers) and all(
        any(child.type == "type" for child in item.children) for item in specifiers
    )
    return any(child.type == "type" for child in statement.children) or (marked and not default)


def _children(node: Node | None, kind: str) -> list[Node]:
    return [child for child in node.children if child.type == kind] if node is not None else []


def _import(node: Node, source: _Source) -> Reference:
    clause = next(iter(_children(node, "import_clause")), None)
    required = next(iter(_children(node, "import_require_clause")), None)
    named = _children(next(iter(_children(clause, "named_imports")), None), "import_specifier")
    return Reference(
        "import" if required is None else "import_equals",
        _literal(next(iter(_children(node if required is None else required, "string")), None)),
        _type_only(node, named, bool(_children(clause, "identifier"))),
        _top_level(node),
        "resolution-mode" in _text(node),
        source.span(node),
    )


def _export(node: Node, source: _Source) -> Reference:
    clause = next(iter(_children(node, "export_clause")), None)
    return Reference(
        "reexport",
        _literal(next(iter(_children(node, "string")), None)),
        _type_only(node, _children(clause, "export_specifier"), False),
        _top_level(node),
        "resolution-mode" in _text(node),
        source.span(node),
    )


def _top_level(node: Node) -> bool:
    return node.parent is not None and node.parent.type == "program"


def _argument(call: Node) -> Node | None:
    arguments = next(iter(_children(call, "arguments")), None)
    return arguments.named_children[0] if arguments and arguments.named_children else None


def _in_type(node: Node) -> bool:
    child, parent = node, node.parent
    while parent is not None:
        if parent.type in _TYPE_PARENTS:
            return True
        # `value as T` and `value satisfies T` start with the value; only what follows is a type.
        if parent.type in ("as_expression", "satisfies_expression") and (
            child.start_byte > parent.start_byte
        ):
            return True
        child, parent = parent, parent.parent
    return False


def _query_start(node: Node) -> Node | None:
    """The `typeof` query an import type opens, which the compiler counts as part of it."""
    parent = node.parent
    while (
        parent is not None
        and parent.type in ("member_expression", "call_expression", "subscript_expression")
        and parent.start_byte == node.start_byte
    ):
        parent = parent.parent
    return parent if parent is not None and parent.type == "type_query" else None


def _dynamic(node: Node, source: _Source) -> Reference:
    typed = _in_type(node)
    return Reference(
        "import_type" if typed else "dynamic_import",
        _literal(_argument(node)),
        typed,
        False,
        "resolution-mode" in _text(node),
        source.span(node, _query_start(node) if typed else None),
    )


def _require(node: Node, source: _Source) -> Reference:
    return Reference("require", _literal(_argument(node)), False, False, False, source.span(node))


def _starts_with(parent: Node | None, node: Node, *kinds: str) -> bool:
    return parent is not None and parent.type in kinds and parent.start_byte == node.start_byte


def _require_concerns(source: _Source, concerns: list[Concern]) -> bool:
    """Report every `require` that is not a plain call; True when one may rebind the name."""
    shadows = False
    for node in source.captures("require_names").get("name", []):
        parent = node.parent
        if _starts_with(parent, node, "call_expression"):
            continue
        concerns.append(Concern("Indirect require use is not resolved", source.span(node)))
        # Reading `require.main` or `typeof require` does not rebind it; anything else might.
        reads = _starts_with(parent, node, "member_expression", "subscript_expression")
        typeof = (
            parent is not None
            and parent.type == "unary_expression"
            and _text(parent).startswith("typeof")
        )
        shadows = shadows or not (reads or typeof)
    found = source.captures("require_members")
    concerns.extend(
        Concern("Unproven require member use", source.span(node))
        for node in found.get("member", [])
    )
    concerns.extend(
        Concern("Computed require member use", source.span(node))
        for node in found.get("subscript", [])
    )
    modules = bool(source.captures("module_names").get("name"))
    for node in found.get("pair", []):
        key = node.children[0]
        computed = key.type == "computed_property_name"
        inner = key.named_children[0] if computed and key.named_children else key
        name = _literal(inner) if inner.type == "string" else _text(inner)
        # A computed key may select `require` from the module object by a name built at runtime.
        runtime_name = computed and inner.type != "string"
        if name == "require" or (runtime_name and modules):
            concerns.append(Concern("Indirect require binding is not resolved", source.span(node)))
    return shadows


def _comment_concerns(source: _Source) -> list[Concern]:
    concerns: list[Concern] = []
    # Triple-slash directives count only before the first statement of the file.
    statements = [
        child.start_byte
        for child in source.root.children
        if child.type not in ("comment", "hash_bang_line")
    ]
    first = statements[0] if statements else len(source.data)
    for node in source.captures("comments").get("comment", []):
        body = _text(node)
        directive = _TRIPLE_SLASH.match(body) if node.start_byte < first else None
        if directive is not None:
            reason = f"Unobserved triple-slash reference: {directive[2]}"
            concerns.append(Concern(reason, source.span(node)))
        if _JSDOC_IMPORT.match(body):
            concerns.append(Concern("JSDoc import is not observed", source.span(node)))
    return concerns
