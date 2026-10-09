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
from collections.abc import Iterator
from dataclasses import dataclass
from functools import cache
from typing import Final, Literal

import tree_sitter_typescript
from tree_sitter import Language, Node, Parser, Query, QueryCursor

Form = Literal["import", "reexport", "import_equals", "dynamic_import", "import_type", "require"]
Grammar = Literal["typescript", "tsx"]
DefinitionKind = Literal[
    "class", "interface", "enum", "method", "function", "type_alias", "constant"
]

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
class Parameter:
    name: str
    annotation: str | None
    optional: bool
    rest: bool
    default: str | None


@dataclass(frozen=True, slots=True)
class Member:
    name: str
    span: Span
    annotation: str | None
    visibility: str | None
    static: bool
    literal: str | None = None


@dataclass(frozen=True, slots=True)
class Base:
    name: str
    relationship: Literal["inherits", "realizes"]
    span: Span


@dataclass(frozen=True, slots=True)
class Definition:
    name: str
    kind: DefinitionKind
    span: Span
    parent: str | None
    visibility: str | None
    static: bool
    exported: bool
    annotation: str | None
    parameters: tuple[Parameter, ...]
    returns: str | None
    bases: tuple[Base, ...]
    members: tuple[Member, ...]
    decorators: bool
    abstract: bool
    members_complete: bool = True
    overload_signature: bool = False
    top_level: bool = False
    signature_complete: bool = True
    parent_line: int | None = None
    parent_column: int | None = None
    is_async: bool = False


@dataclass(frozen=True, slots=True)
class Site:
    kind: Literal["call", "new", "reference"]
    expression: str
    span: Span
    scope: str | None
    scope_line: int | None
    assigned_name: str | None = None
    name: str | None = None
    receiver: str | None = None
    computed: bool = False
    shadowed_names: tuple[str, ...] = ()
    assignment_span: Span | None = None
    assignment_annotation: str | None = None
    initializer: str | None = None
    use: Literal["type", "value", "member"] = "value"
    scope_ambiguous: bool = False
    scope_column: int | None = None


@dataclass(frozen=True, slots=True)
class ImportBinding:
    span: Span
    imported: str
    local: str
    namespace: bool = False
    type_only: bool = False


@dataclass(frozen=True, slots=True)
class Syntax:
    references: tuple[Reference, ...]
    concerns: tuple[Concern, ...]
    # A `require` name that is not a plain call may be a local binding, not the loader.
    shadows_require: bool
    first_error: Span | None
    definitions: tuple[Definition, ...] = ()
    sites: tuple[Site, ...] = ()
    import_bindings: tuple[ImportBinding, ...] = ()
    rebound_names: tuple[str, ...] = ()


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
        prefix: str = str(self.data[self.starts[line - 1] : first], "utf-8", "replace")
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
        *_inner(source),
        _import_bindings(source),
        _rebound_names(source),
    )


def _inner(source: _Source) -> tuple[tuple[Definition, ...], tuple[Site, ...]]:
    definitions: list[Definition] = []
    declaration_nodes: dict[Node, str] = {}
    scopes: list[tuple[Node, str, int]] = []
    for node in _walk(source.root):
        if source.root.has_error and _in_error(node):
            continue
        if any(parent.type == "internal_module" for parent in _ancestors(node)):
            continue
        if _in_unmodeled_block(node):
            continue
        if node.type not in {
            "class_declaration",
            "interface_declaration",
            "enum_declaration",
            "function_declaration",
            "function_signature",
            "method_definition",
            "method_signature",
            "type_alias_declaration",
        }:
            continue
        name_node = node.child_by_field_name("name")
        name = _text(name_node) if name_node else ""
        if not name or name_node is None or name_node.type == "computed_property_name":
            continue
        if node.type in ("method_definition", "method_signature") and not _class_member(node):
            continue
        parent_scope = next((item for item in reversed(scopes) if _contains(item[0], node)), None)
        parent_name = parent_scope[1] if parent_scope else None
        kinds: dict[str, DefinitionKind] = {
            "class_declaration": "class",
            "interface_declaration": "interface",
            "enum_declaration": "enum",
            "function_declaration": "function",
            "function_signature": "function",
            "method_definition": "method",
            "method_signature": "method",
            "type_alias_declaration": "type_alias",
        }
        kind = kinds[node.type]
        parent_location = source.span(parent_scope[0]) if parent_scope else None
        definition = _definition(
            node,
            name,
            kind,
            parent_name,
            source,
            parent_location,
        )
        definitions.append(definition)
        declaration_nodes[name_node] = kind
        scopes.append(
            (node, f"{parent_name}.{name}" if parent_name else name, definition.span.line)
        )
    definitions.extend(_variables(source, scopes, declaration_nodes))
    sites = _sites(source, scopes, declaration_nodes)
    return tuple(sorted(definitions, key=lambda item: (item.span.line, item.span.column))), tuple(
        sorted(sites, key=lambda item: (item.span.line, item.span.column, item.kind))
    )


def _walk(node: Node) -> Iterator[Node]:
    yield node
    for child in node.named_children:
        yield from _walk(child)


def _contains(parent: Node, child: Node) -> bool:
    return parent.start_byte <= child.start_byte and parent.end_byte >= child.end_byte


def _modifiers(node: Node) -> set[str]:
    return {
        _text(child)
        for child in node.children
        if child.type
        in {"accessibility_modifier", "static", "abstract", "override", "readonly", "declare"}
    }


def _visibility(node: Node) -> str | None:
    modifiers = _modifiers(node)
    if any(child.type == "private_property_identifier" for child in node.children):
        return "private"
    name = node.child_by_field_name("name")
    if name is not None and name.type == "private_property_identifier":
        return "private"
    return next((name for name in ("public", "protected", "private") if name in modifiers), None)


def _type(node: Node | None) -> str | None:
    if node is None:
        return None
    value: str = _text(node)
    return value[1:].strip() if node.type == "type_annotation" else value


def _parameters(node: Node | None) -> tuple[Parameter, ...]:
    if node is None:
        return ()
    result = []
    for item in node.named_children:
        pattern = item.child_by_field_name("pattern") or item.child_by_field_name("name")
        if pattern is None and item.named_children:
            pattern = item.named_children[0]
        name = _text(pattern) if pattern is not None else ""
        rest = item.type == "rest_parameter" or name.startswith("...")
        if rest:
            name = name.removeprefix("...")
        value = item.child_by_field_name("value")
        result.append(
            Parameter(
                name,
                _type(item.child_by_field_name("type")),
                item.type == "optional_parameter" or "?" in _text(item).split(":", 1)[0],
                rest,
                _text(value) if value is not None else None,
            )
        )
    return tuple(result)


def _definition(
    node: Node,
    name: str,
    kind: DefinitionKind,
    parent: str | None,
    source: _Source,
    parent_location: Span | None,
) -> Definition:
    members: list[Member] = []
    bases: list[Base] = []
    body = node.child_by_field_name("body")
    if kind in {"class", "interface", "enum"} and body is not None:
        for item in body.named_children:
            if item.type in (
                "public_field_definition",
                "property_signature",
                "enum_assignment",
            ) or (kind == "enum" and item.type in {"property_identifier", "identifier"}):
                member = _member(item, source)
                if member is not None:
                    members.append(member)
        for heritage in node.named_children:
            clauses = (
                heritage.named_children
                if heritage.type == "class_heritage"
                else (heritage,)
                if heritage.type == "extends_type_clause"
                else ()
            )
            for clause in clauses:
                if clause.type not in (
                    "extends_clause",
                    "implements_clause",
                    "extends_type_clause",
                ):
                    continue
                relationship: Literal["inherits", "realizes"] = (
                    "realizes" if clause.type == "implements_clause" else "inherits"
                )
                for named in clause.named_children:
                    candidate = named.child_by_field_name("name") or named
                    bases.append(Base(_text(candidate), relationship, source.span(candidate)))
    return Definition(
        name,
        kind,
        source.span(node),
        parent,
        _visibility(node),
        "static" in _modifiers(node),
        _exported(node),
        _type(node.child_by_field_name("type") or node.child_by_field_name("value")),
        _parameters(node.child_by_field_name("parameters")),
        _type(node.child_by_field_name("return_type")),
        tuple(bases),
        tuple(members),
        any(child.type == "decorator" for child in node.children),
        "abstract" in _modifiers(node),
        _members_complete(body),
        node.child_by_field_name("body") is None,
        node.parent is not None
        and (
            node.parent.type == "program"
            or (
                node.parent.type == "export_statement"
                and node.parent.parent is not None
                and node.parent.parent.type == "program"
            )
        ),
        _signature_complete(node),
        parent_location.line if parent_location else None,
        parent_location.column if parent_location else None,
        is_async=any(child.type == "async" for child in node.children),
    )


def _members_complete(body: Node | None) -> bool:
    if body is None:
        return False
    supported = {
        "public_field_definition",
        "property_signature",
        "method_definition",
        "method_signature",
        "enum_assignment",
        "property_identifier",
        "identifier",
        "comment",
    }
    for child in body.named_children:
        if child.type not in supported:
            return False
        if child.type in {
            "public_field_definition",
            "property_signature",
            "method_definition",
            "method_signature",
            "enum_assignment",
        }:
            name = child.child_by_field_name("name")
            if child.type in {"property_identifier", "identifier"}:
                continue
            if name is None or name.type == "computed_property_name":
                return False
            if child.type == "method_definition" and _text(name) == "constructor":
                parameters = child.child_by_field_name("parameters")
                if parameters is not None and any(
                    _modifiers(parameter) & {"public", "private", "protected"}
                    for parameter in parameters.named_children
                ):
                    return False
    return True


def _class_member(node: Node) -> bool:
    parent = node.parent
    if parent is None or parent.type not in {"class_body", "interface_body"}:
        return False
    owner = parent.parent
    return owner is not None and owner.type in {
        "class_declaration",
        "interface_declaration",
    }


def _member(node: Node, source: _Source) -> Member | None:
    name_node = node.child_by_field_name("name") or (
        node if node.type in {"property_identifier", "identifier"} else None
    )
    if name_node is None or name_node.type == "computed_property_name":
        return None
    value = node.child_by_field_name("value")
    literal = (
        _text(value)
        if value is not None and value.type in {"string", "number", "true", "false", "null"}
        else None
    )
    return Member(
        _text(name_node),
        source.span(name_node),
        _type(node.child_by_field_name("type")),
        _visibility(node),
        "static" in _modifiers(node)
        or node.type in {"enum_assignment", "property_identifier", "identifier"},
        literal,
    )


def _signature_complete(node: Node) -> bool:
    parameters = node.child_by_field_name("parameters")
    return parameters is None or all(
        item.type == "required_parameter"
        and (pattern := item.child_by_field_name("pattern") or item.child_by_field_name("name"))
        is not None
        and pattern.type == "identifier"
        and item.child_by_field_name("value") is None
        and "?" not in _text(item).split(":", 1)[0]
        for item in parameters.named_children
    )


def _exported(node: Node) -> bool:
    parent = node.parent
    return parent is not None and parent.type == "export_statement"


def _variables(
    source: _Source, scopes: list[tuple[Node, str, int]], declarations: dict[Node, str]
) -> list[Definition]:
    result = []
    for node in _walk(source.root):
        if node.type != "variable_declarator":
            continue
        name_node = node.child_by_field_name("name")
        value = node.child_by_field_name("value")
        parent = node.parent
        if name_node is None or name_node.type != "identifier" or value is None:
            continue
        declaration = (
            parent if parent is not None and parent.type == "lexical_declaration" else None
        )
        kind_node = declaration.child_by_field_name("kind") if declaration else None
        if (
            kind_node is None
            or _text(kind_node) != "const"
            or value.type not in {"string", "number", "true", "false", "null"}
        ):
            continue
        name = _text(name_node)
        owner = next((item for item, _, _ in reversed(scopes) if _contains(item, node)), None)
        parent_name = next((qualified for item, qualified, _ in scopes if item is owner), None)
        owner_span = source.span(owner) if owner is not None else None
        declaration_parent = declaration.parent if declaration is not None else None
        exported = declaration_parent is not None and declaration_parent.type == "export_statement"
        result.append(
            Definition(
                name,
                "constant",
                source.span(node),
                parent_name,
                None,
                False,
                exported,
                _type(node.child_by_field_name("type")),
                (),
                None,
                (),
                (),
                False,
                False,
                top_level=(
                    declaration_parent is not None
                    and (
                        declaration_parent.type == "program"
                        or (
                            declaration_parent.type == "export_statement"
                            and declaration_parent.parent is not None
                            and declaration_parent.parent.type == "program"
                        )
                    )
                ),
                parent_line=owner_span.line if owner_span else None,
                parent_column=owner_span.column if owner_span else None,
            )
        )
        declarations[name_node] = "constant"
    return result


def _sites(
    source: _Source, scopes: list[tuple[Node, str, int]], declarations: dict[Node, str]
) -> list[Site]:
    sites: list[Site] = []
    for node in _walk(source.root):
        if source.root.has_error and _in_error(node):
            continue
        if node.type in ("call_expression", "new_expression"):
            target = node.child_by_field_name("function") or node.child_by_field_name("constructor")
            if target is None:
                continue
            scope = next((item for item, _, _ in reversed(scopes) if _contains(item, node)), None)
            scope_name = next((name for item, name, _ in scopes if item is scope), None)
            scope_line = next((line for item, _, line in scopes if item is scope), None)
            assigned = _assigned_name(node)
            name, receiver, computed = _target_name(target)
            shadowed, ambiguous_scope = _active_scope_names(node, scope)
            sites.append(
                Site(
                    "new" if node.type == "new_expression" else "call",
                    _text(target),
                    source.span(node),
                    scope_name,
                    scope_line,
                    assigned,
                    name,
                    receiver,
                    computed,
                    shadowed,
                    _assignment_span(node, source),
                    _assignment_annotation(node),
                    _text(node) if node.type == "new_expression" else None,
                    scope_ambiguous=ambiguous_scope,
                    scope_column=source.span(scope).column if scope is not None else None,
                )
            )
        if node.type not in ("identifier", "type_identifier", "property_identifier"):
            continue
        if node in declarations or _declaration_name(node) or _is_member_name(node):
            continue
        if _inside_site_callee(node):
            continue
        scope = next((item for item, _, _ in reversed(scopes) if _contains(item, node)), None)
        scope_name = next((name for item, name, _ in scopes if item is scope), None)
        scope_line = next((line for item, _, line in scopes if item is scope), None)
        name, receiver, computed = (
            _target_name(node.parent)
            if node.parent is not None
            and node.parent.type == "member_expression"
            and node.parent.child_by_field_name("property") == node
            else (_text(node), None, False)
        )
        shadowed, ambiguous_scope = _active_scope_names(node, scope)
        sites.append(
            Site(
                "reference",
                f"{receiver}.{name}" if receiver and name else _text(node),
                source.span(node),
                scope_name,
                scope_line,
                name=name,
                receiver=receiver,
                computed=computed,
                shadowed_names=shadowed,
                use="type" if node.type == "type_identifier" else "member" if receiver else "value",
                scope_ambiguous=ambiguous_scope,
                scope_column=source.span(scope).column if scope is not None else None,
            )
        )
    return sites


def _declaration_name(node: Node) -> bool:
    parent = node.parent
    return parent is not None and any(
        parent.child_by_field_name(field) == node for field in ("name", "pattern")
    )


def _target_name(node: Node) -> tuple[str | None, str | None, bool]:
    if node.type in ("identifier", "type_identifier"):
        return _text(node), None, False
    if node.type == "member_expression":
        receiver = node.child_by_field_name("object")
        name = node.child_by_field_name("property")
        return (
            _text(name) if name is not None and name.type == "property_identifier" else None,
            _text(receiver) if receiver is not None else None,
            name is None or name.type != "property_identifier",
        )
    return None, None, True


def _scope_names(node: Node) -> tuple[str, ...]:
    names: set[str] = set()
    parameters = node.child_by_field_name("parameters")
    if parameters is not None:
        names.update(
            _text(child)
            for child in _walk(parameters)
            if child.type == "identifier" and _declaration_name(child)
        )
    body = node.child_by_field_name("body")
    if body is not None:
        for child in _walk(body):
            if child.type == "variable_declarator":
                name = child.child_by_field_name("name")
                if name is not None and name.type == "identifier":
                    names.add(_text(name))
            if child.type == "assignment_expression":
                left = child.child_by_field_name("left")
                if left is not None and left.type == "identifier":
                    names.add(_text(left))
    return tuple(sorted(names))


def _active_scope_names(node: Node, scope: Node | None) -> tuple[tuple[str, ...], bool]:
    names: set[str] = set(_scope_names(scope)) if scope is not None else set()
    ambiguous = False
    parent = node.parent
    while parent is not None and parent != scope:
        if parent.type in {"internal_module", "class_expression", "object"}:
            ambiguous = True
        if parent.type == "statement_block":
            owner = parent.parent
            if owner is None or owner.child_by_field_name("body") != parent:
                ambiguous = True
        if parent.type in {"arrow_function", "function_expression", "generator_function"}:
            names.update(_scope_names(parent))
            ambiguous = True
        elif parent.type == "method_definition" and not _class_member(parent):
            names.update(_scope_names(parent))
            ambiguous = True
        parent = parent.parent
    return tuple(sorted(names)), ambiguous


def _is_member_name(node: Node) -> bool:
    parent = node.parent
    if parent is None:
        return False
    if parent.type == "member_expression":
        return False
    return (
        parent.type
        in {
            "method_definition",
            "method_signature",
            "public_field_definition",
            "property_signature",
        }
        and parent.child_by_field_name("name") == node
    )


def _inside_site_callee(node: Node) -> bool:
    child, parent = node, node.parent
    while parent is not None and parent.type in ("member_expression", "subscript_expression"):
        child, parent = parent, parent.parent
    return (
        parent is not None
        and parent.type in ("call_expression", "new_expression")
        and (
            parent.child_by_field_name("function") == child
            or parent.child_by_field_name("constructor") == child
        )
    )


def _assigned_name(node: Node) -> str | None:
    parent = node.parent
    if parent is not None and parent.type == "arguments":
        parent = parent.parent
    if (
        parent is not None
        and parent.type == "variable_declarator"
        and parent.child_by_field_name("value") == node
    ):
        name = parent.child_by_field_name("name")
        return _text(name) if name is not None and name.type == "identifier" else None
    return None


def _assignment_node(node: Node) -> Node | None:
    parent = node.parent
    return (
        parent
        if parent is not None
        and parent.type == "variable_declarator"
        and parent.child_by_field_name("value") == node
        else None
    )


def _assignment_span(node: Node, source: _Source) -> Span | None:
    assignment = _assignment_node(node)
    name = assignment.child_by_field_name("name") if assignment is not None else None
    return source.span(name) if name is not None else None


def _assignment_annotation(node: Node) -> str | None:
    assignment = _assignment_node(node)
    return _type(assignment.child_by_field_name("type")) if assignment is not None else None


def _import_bindings(source: _Source) -> tuple[ImportBinding, ...]:
    result = []
    for statement in source.captures("references").get("import", []):
        clause = next(iter(_children(statement, "import_clause")), None)
        if clause is None:
            continue
        span = source.span(statement)
        default = next(iter(_children(clause, "identifier")), None)
        if default is not None:
            result.append(
                ImportBinding(
                    span,
                    "default",
                    _text(default),
                    type_only=any(child.type == "type" for child in statement.children),
                )
            )
        named = next(iter(_children(clause, "named_imports")), None)
        for item in _children(named, "import_specifier"):
            imported = item.child_by_field_name("name")
            local = item.child_by_field_name("alias") or imported
            if imported is not None and local is not None:
                result.append(
                    ImportBinding(
                        span,
                        _text(imported),
                        _text(local),
                        type_only=any(child.type == "type" for child in item.children)
                        or any(child.type == "type" for child in statement.children),
                    )
                )
        namespace = next(iter(_children(clause, "namespace_import")), None)
        if namespace is not None:
            local = next(iter(namespace.named_children), None)
            if local is not None:
                result.append(ImportBinding(span, "*", _text(local), True))
    return tuple(result)


def _rebound_names(source: _Source) -> tuple[str, ...]:
    result = set()
    for node in _walk(source.root):
        if node.type != "assignment_expression":
            continue
        if any(
            parent.type in ("function_declaration", "method_definition", "arrow_function")
            for parent in _ancestors(node)
        ):
            continue
        left = node.child_by_field_name("left")
        if left is not None and left.type == "identifier":
            result.add(_text(left))
    return tuple(sorted(result))


def _ancestors(node: Node) -> Iterator[Node]:
    parent = node.parent
    while parent is not None:
        yield parent
        parent = parent.parent


def _in_unmodeled_block(node: Node) -> bool:
    return any(
        block.type == "statement_block"
        and (block.parent is None or block.parent.child_by_field_name("body") != block)
        for block in _ancestors(node)
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
