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
from collections import Counter as _Counter
from collections.abc import Iterator
from dataclasses import dataclass, replace
from enum import Enum
from functools import cache
from typing import Final

import tree_sitter_typescript
from tree_sitter import Language, Parser, Query, QueryCursor
from tree_sitter import Node as _RawNode

from .syntax import (
    Base as Base,
)
from .syntax import (
    BaseRelationship as BaseRelationship,
)
from .syntax import (
    Concern as Concern,
)
from .syntax import (
    Definition as Definition,
)
from .syntax import (
    DefinitionKind as DefinitionKind,
)
from .syntax import (
    ImportBinding as ImportBinding,
)
from .syntax import (
    Member as Member,
)
from .syntax import (
    Parameter as Parameter,
)
from .syntax import (
    ReceiverKind as ReceiverKind,
)
from .syntax import (
    Reference as Reference,
)
from .syntax import (
    ReferenceForm as ReferenceForm,
)
from .syntax import (
    Site as Site,
)
from .syntax import (
    SiteKind as SiteKind,
)
from .syntax import (
    SiteUse as SiteUse,
)
from .syntax import (
    Span as Span,
)
from .syntax import (
    Syntax as Syntax,
)
from .syntax import (
    Visibility as Visibility,
)


class _NodeKind(Enum):
    ASTERISK = "*"
    ABSTRACT = "abstract"
    ABSTRACT_CLASS_DECLARATION = "abstract_class_declaration"
    ACCESSIBILITY_MODIFIER = "accessibility_modifier"
    AMBIENT_DECLARATION = "ambient_declaration"
    ARGUMENTS = "arguments"
    ARRAY = "array"
    ARROW_FUNCTION = "arrow_function"
    AS = "as"
    AS_EXPRESSION = "as_expression"
    ASSIGNMENT_EXPRESSION = "assignment_expression"
    ASYNC = "async"
    CALL_EXPRESSION = "call_expression"
    CLASS_BODY = "class_body"
    CLASS_DECLARATION = "class_declaration"
    CLASS_EXPRESSION = "class_expression"
    CLASS_HERITAGE = "class_heritage"
    COMMENT = "comment"
    COMPUTED_PROPERTY_NAME = "computed_property_name"
    CONST = "const"
    DECLARE = "declare"
    DECORATOR = "decorator"
    ENUM_ASSIGNMENT = "enum_assignment"
    ENUM_DECLARATION = "enum_declaration"
    ESCAPE_SEQUENCE = "escape_sequence"
    EXPORT_CLAUSE = "export_clause"
    EXPORT_SPECIFIER = "export_specifier"
    EXPORT_STATEMENT = "export_statement"
    EXPRESSION_STATEMENT = "expression_statement"
    EXTENDS_CLAUSE = "extends_clause"
    EXTENDS_TYPE_CLAUSE = "extends_type_clause"
    FALSE = "false"
    FOR_IN_STATEMENT = "for_in_statement"
    FUNCTION_DECLARATION = "function_declaration"
    FUNCTION_EXPRESSION = "function_expression"
    FUNCTION_SIGNATURE = "function_signature"
    GENERATOR_FUNCTION = "generator_function"
    GENERATOR_FUNCTION_DECLARATION = "generator_function_declaration"
    GET = "get"
    HASH_BANG_LINE = "hash_bang_line"
    IDENTIFIER = "identifier"
    IMPLEMENTS_CLAUSE = "implements_clause"
    IMPORT_ALIAS = "import_alias"
    IMPORT_CLAUSE = "import_clause"
    IMPORT_REQUIRE_CLAUSE = "import_require_clause"
    IMPORT_SPECIFIER = "import_specifier"
    IMPORT_STATEMENT = "import_statement"
    INTERFACE_BODY = "interface_body"
    INTERFACE_DECLARATION = "interface_declaration"
    INTERNAL_MODULE = "internal_module"
    LEXICAL_DECLARATION = "lexical_declaration"
    MEMBER_EXPRESSION = "member_expression"
    METHOD_DEFINITION = "method_definition"
    METHOD_SIGNATURE = "method_signature"
    NAMED_IMPORTS = "named_imports"
    NAMESPACE_IMPORT = "namespace_import"
    NEW_EXPRESSION = "new_expression"
    NULL = "null"
    NUMBER = "number"
    OBJECT = "object"
    OPTIONAL_PARAMETER = "optional_parameter"
    OVERRIDE = "override"
    PRIVATE_PROPERTY_IDENTIFIER = "private_property_identifier"
    PROGRAM = "program"
    PROPERTY_IDENTIFIER = "property_identifier"
    PROPERTY_SIGNATURE = "property_signature"
    PUBLIC_FIELD_DEFINITION = "public_field_definition"
    READONLY = "readonly"
    REQUIRED_PARAMETER = "required_parameter"
    REST_PARAMETER = "rest_parameter"
    REST_PATTERN = "rest_pattern"
    SATISFIES_EXPRESSION = "satisfies_expression"
    SET = "set"
    STATEMENT_BLOCK = "statement_block"
    STATIC = "static"
    STRING = "string"
    SUBSCRIPT_EXPRESSION = "subscript_expression"
    TEMPLATE_STRING = "template_string"
    TEMPLATE_SUBSTITUTION = "template_substitution"
    THIS = "this"
    TRUE = "true"
    TYPE = "type"
    TYPE_ALIAS_DECLARATION = "type_alias_declaration"
    TYPE_ANNOTATION = "type_annotation"
    TYPE_ARGUMENTS = "type_arguments"
    TYPE_IDENTIFIER = "type_identifier"
    TYPE_PARAMETER = "type_parameter"
    TYPE_QUERY = "type_query"
    TYPEOF = "typeof"
    UNARY_EXPRESSION = "unary_expression"
    VAR = "var"
    VARIABLE_DECLARATION = "variable_declaration"
    VARIABLE_DECLARATOR = "variable_declarator"
    QUESTION = "?"


class _Grammar(Enum):
    TYPESCRIPT = "typescript"
    TSX = "tsx"


class _Modifier(Enum):
    PUBLIC = "public"
    PROTECTED = "protected"
    PRIVATE = "private"
    STATIC = "static"
    ABSTRACT = "abstract"
    OVERRIDE = "override"
    READONLY = "readonly"
    DECLARE = "declare"


class _SpecialName(Enum):
    CONSTRUCTOR = "constructor"
    REQUIRE = "require"


class _LoaderModule(Enum):
    MODULE = "module"
    NODE_MODULE = "node:module"


_NODE_KINDS: Final[dict[str, _NodeKind]] = {item.value: item for item in _NodeKind}
_MODIFIER_WORDS: Final[dict[str, _Modifier]] = {item.value: item for item in _Modifier}
_SPECIAL_NAMES: Final[dict[str, _SpecialName]] = {item.value: item for item in _SpecialName}
_LOADER_MODULES: Final[dict[str, _LoaderModule]] = {item.value: item for item in _LoaderModule}


class _Tree:
    """One parse's bounded node identity map; no parser objects escape the syntax boundary."""

    nodes: dict[int, _Node]

    def __init__(self) -> None:
        self.nodes = {}

    def node(self, raw: _RawNode) -> _Node:
        found = self.nodes.get(raw.id)
        if found is None:
            found = _Node(raw, self)
            self.nodes[raw.id] = found
        return found

    def optional(self, raw: _RawNode | None) -> _Node | None:
        return self.node(raw) if raw is not None else None

    def clear(self) -> None:
        nodes: dict[int, _Node] = self.nodes
        nodes.clear()


class _Node:
    """Only the Tree-sitter operations this decoder uses, with kind decoded once."""

    def __init__(self, raw: _RawNode, tree: _Tree) -> None:
        self.raw = raw
        self.tree = tree
        self.kind: _NodeKind | None = _NODE_KINDS.get(raw.type)
        self.start_byte = raw.start_byte
        self.end_byte = raw.end_byte
        self.has_error = raw.has_error
        self.is_error = raw.is_error

    @property
    def children(self) -> list[_Node]:
        return [self.tree.node(child) for child in self.raw.children]

    @property
    def named_children(self) -> list[_Node]:
        return [self.tree.node(child) for child in self.raw.named_children]

    @property
    def parent(self) -> _Node | None:
        return self.tree.optional(self.raw.parent)

    @property
    def prev_named_sibling(self) -> _Node | None:
        return self.tree.optional(self.raw.prev_named_sibling)

    @property
    def next_named_sibling(self) -> _Node | None:
        return self.tree.optional(self.raw.next_named_sibling)

    @property
    def text(self) -> bytes | None:
        return self.raw.text

    def child_by_field_name(self, name: str) -> _Node | None:
        return self.tree.optional(self.raw.child_by_field_name(name))


def _special_name(value: str | None) -> _SpecialName | None:
    return _SPECIAL_NAMES.get(value) if value is not None else None


_LOADER: Final = "Node module loader is not observed"
# A comment opens a JSDoc block unless it is `/**/`; only those can carry typed imports.
_JSDOC_IMPORT: Final = re.compile(r"^/\*\*(?!/)[\s\S]*(?:@import\b|\bimport\s*\()")
_TRIPLE_SLASH: Final = re.compile(r"^///\s*<reference\s+(?:path|types|lib)\s*=\s*(['\"])(.*?)\1")
# Line breaks as the TypeScript compiler counts them, so reported lines agree with it.
_LINE_BREAK: Final = re.compile(rb"\r\n|[\n\r]|\xe2\x80[\xa8\xa9]")
# Constructs that hold types: a module named inside them is a type-only reference.
_TYPE_PARENTS: Final = frozenset(
    {
        _NodeKind.TYPE_ANNOTATION,
        _NodeKind.TYPE_ARGUMENTS,
        _NodeKind.TYPE_QUERY,
        _NodeKind.TYPE_ALIAS_DECLARATION,
        _NodeKind.TYPE_PARAMETER,
        _NodeKind.EXTENDS_TYPE_CLAUSE,
        _NodeKind.IMPLEMENTS_CLAUSE,
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
class _Source:
    kind: _Grammar
    root: _Node
    data: bytes
    starts: list[int]

    def captures(self, query: str, scope: _Node | None = None) -> dict[str, list[_Node]]:
        captures = QueryCursor(_query(self.kind, query)).captures((scope or self.root).raw)
        return {
            name: [self.root.tree.node(node) for node in nodes] for name, nodes in captures.items()
        }

    def span(self, node: _Node, start: _Node | None = None) -> Span:
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
def _grammar(kind: _Grammar) -> Language:
    return Language(
        tree_sitter_typescript.language_tsx()
        if kind is _Grammar.TSX
        else tree_sitter_typescript.language_typescript()
    )


@cache
def _query(kind: _Grammar, name: str) -> Query:
    return Query(_grammar(kind), _QUERIES[name])


def parse(rel_path: str, data: bytes) -> Syntax:
    # JSX and JavaScript need the TSX grammar; `<T>x` assertions exist only without it.
    kind = _Grammar.TYPESCRIPT if re.search(r"\.[cm]?ts$", rel_path) else _Grammar.TSX
    tree = _Tree()
    try:
        root = tree.node(Parser(_grammar(kind)).parse(data).root_node)
        source = _Source(
            kind, root, data, [0, *(found.end() for found in _LINE_BREAK.finditer(data))]
        )
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
        needed = re.search(rb"require|module", data) is not None
        shadows = _require_concerns(source, concerns) if needed else False
        loaders = [
            item.span
            for item in trusted
            if item.specifier is not None and _LOADER_MODULES.get(item.specifier) is not None
        ]
        if re.search(rb"createRequire", data):
            loaders.extend(
                source.span(node) for node in source.captures("create_require").get("name", [])
            )
        # One gap per file: the first use already makes every later `require` unprovable.
        if loaders:
            concerns.append(
                Concern(_LOADER, min(loaders, key=lambda span: (span.line, span.column)))
            )
        if re.search(rb"/\*\*|///", data):
            concerns.extend(_comment_concerns(source))
        errors = sorted(
            source.captures("errors").get("error", []), key=lambda item: item.start_byte
        )
        return Syntax(
            tuple(
                sorted(
                    trusted, key=lambda item: (item.span.line, item.span.column, item.form.value)
                )
            ),
            tuple(concerns),
            shadows,
            source.span(errors[0]) if errors else None,
            *_inner(source),
            _import_bindings(source),
            _rebound_names(source),
        )
    finally:
        tree.clear()


def _inner(source: _Source) -> tuple[tuple[Definition, ...], tuple[Site, ...]]:
    definitions: list[Definition] = []
    declaration_nodes: dict[_Node, DefinitionKind] = {}
    scopes: list[tuple[_Node, str, int]] = []
    module_syntax, exported_names, visible_names, exports_complete = _module_exports(source.root)
    for node in _walk(source.root):
        if source.root.has_error and _in_error(node):
            continue
        if any(parent.kind == _NodeKind.INTERNAL_MODULE for parent in _ancestors(node)):
            continue
        if _in_unmodeled_block(node):
            continue
        if node.kind is None or node.kind not in {
            _NodeKind.CLASS_DECLARATION,
            _NodeKind.INTERFACE_DECLARATION,
            _NodeKind.ENUM_DECLARATION,
            _NodeKind.FUNCTION_DECLARATION,
            _NodeKind.FUNCTION_SIGNATURE,
            _NodeKind.METHOD_DEFINITION,
            _NodeKind.METHOD_SIGNATURE,
            _NodeKind.TYPE_ALIAS_DECLARATION,
        }:
            continue
        name_node = node.child_by_field_name("name")
        name = _text(name_node) if name_node else ""
        if _supported_constructor(node):
            name = "constructor"
        if (
            not name
            or name_node is None
            or name_node.kind in {None, _NodeKind.COMPUTED_PROPERTY_NAME}
        ):
            continue
        if node.kind in (
            _NodeKind.METHOD_DEFINITION,
            _NodeKind.METHOD_SIGNATURE,
        ) and not _class_member(node):
            continue
        parent_scope = next((item for item in reversed(scopes) if _contains(item[0], node)), None)
        parent_name = parent_scope[1] if parent_scope else None
        kinds: dict[_NodeKind, DefinitionKind] = {
            _NodeKind.CLASS_DECLARATION: DefinitionKind.CLASS,
            _NodeKind.INTERFACE_DECLARATION: DefinitionKind.INTERFACE,
            _NodeKind.ENUM_DECLARATION: DefinitionKind.ENUM,
            _NodeKind.FUNCTION_DECLARATION: DefinitionKind.FUNCTION,
            _NodeKind.FUNCTION_SIGNATURE: DefinitionKind.FUNCTION,
            _NodeKind.METHOD_DEFINITION: DefinitionKind.METHOD,
            _NodeKind.METHOD_SIGNATURE: DefinitionKind.METHOD,
            _NodeKind.TYPE_ALIAS_DECLARATION: DefinitionKind.TYPE_ALIAS,
        }
        kind = kinds[node.kind]
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
    definitions = [
        _module_visibility(item, module_syntax, exported_names, visible_names, exports_complete)
        for item in definitions
    ]
    sites = _sites(source, scopes, declaration_nodes)
    return tuple(sorted(definitions, key=lambda item: (item.span.line, item.span.column))), tuple(
        sorted(sites, key=lambda item: (item.span.line, item.span.column, item.kind.value))
    )


def _specifier_names(specifier: _Node) -> tuple[_Node | None, _Node | None]:
    """Read the local/imported name and optional public/local alias from one specifier."""
    return (
        specifier.child_by_field_name("name"),
        specifier.child_by_field_name("alias"),
    )


def _module_exports(root: _Node) -> tuple[bool, set[str], set[str], bool]:
    """Return runtime local exports, visible local exports, and classification certainty."""
    imports = {_NodeKind.IMPORT_STATEMENT, _NodeKind.IMPORT_ALIAS}
    declarations = {
        _NodeKind.CLASS_DECLARATION,
        _NodeKind.ENUM_DECLARATION,
        _NodeKind.FUNCTION_DECLARATION,
        _NodeKind.FUNCTION_SIGNATURE,
        _NodeKind.INTERFACE_DECLARATION,
        _NodeKind.LEXICAL_DECLARATION,
        _NodeKind.TYPE_ALIAS_DECLARATION,
        _NodeKind.VARIABLE_DECLARATION,
    }
    statements = [item for item in root.named_children if item.kind == _NodeKind.EXPORT_STATEMENT]
    module_syntax = bool(statements) or any(item.kind in imports for item in root.named_children)
    exported_names: set[str] = set()
    visible_names: set[str] = set()
    complete = True
    for statement in statements:
        if any(item.kind in declarations for item in statement.named_children):
            continue
        clause = next(
            (item for item in statement.named_children if item.kind == _NodeKind.EXPORT_CLAUSE),
            None,
        )
        if clause is None:
            if any(item.kind == _NodeKind.STRING for item in statement.named_children):
                continue
            complete = False
            continue
        if any(item.kind == _NodeKind.STRING for item in statement.named_children):
            continue
        statement_is_type_only = any(item.kind == _NodeKind.TYPE for item in statement.children)
        for candidate in clause.named_children:
            if candidate.kind != _NodeKind.EXPORT_SPECIFIER:
                continue
            specifier: _Node = candidate
            name, alias = _specifier_names(specifier)
            if name is None or name.kind not in {_NodeKind.IDENTIFIER, _NodeKind.TYPE_IDENTIFIER}:
                complete = False
                continue
            local_name = _text(name)
            visible_names.add(local_name)
            is_alias = alias is not None and _text(alias) != local_name
            is_type_only = statement_is_type_only or any(
                item.kind == _NodeKind.TYPE for item in specifier.children
            )
            if not is_alias and not is_type_only:
                exported_names.add(local_name)
    return module_syntax, exported_names, visible_names, complete


def _module_visibility(
    definition: Definition,
    module_syntax: bool,
    exported_names: set[str],
    visible_names: set[str],
    exports_complete: bool,
) -> Definition:
    if not definition.top_level:
        return definition
    exported = definition.exported or definition.name in exported_names
    visible = definition.exported or definition.name in visible_names
    if not visible and not (module_syntax and exports_complete):
        return replace(definition, exported=exported)
    return replace(
        definition,
        exported=exported,
        visibility=definition.visibility or (Visibility.PUBLIC if visible else Visibility.PRIVATE),
    )


def _walk(node: _Node) -> Iterator[_Node]:
    yield node
    for child in node.named_children:
        yield from _walk(child)


def _contains(parent: _Node, child: _Node) -> bool:
    return parent.start_byte <= child.start_byte and parent.end_byte >= child.end_byte


def _modifiers(node: _Node) -> set[_Modifier]:
    return {
        modifier
        for child in node.children
        if child.kind
        in {
            _NodeKind.ACCESSIBILITY_MODIFIER,
            _NodeKind.STATIC,
            _NodeKind.ABSTRACT,
            _NodeKind.OVERRIDE,
            _NodeKind.READONLY,
            _NodeKind.DECLARE,
        }
        if (modifier := _MODIFIER_WORDS.get(_text(child))) is not None
    }


def _visibility(node: _Node) -> Visibility | None:
    modifiers = _modifiers(node)
    if any(child.kind is _NodeKind.PRIVATE_PROPERTY_IDENTIFIER for child in node.children):
        return Visibility.PRIVATE
    name = node.child_by_field_name("name")
    if name is not None and name.kind is _NodeKind.PRIVATE_PROPERTY_IDENTIFIER:
        return Visibility.PRIVATE
    choices = {
        _Modifier.PUBLIC: Visibility.PUBLIC,
        _Modifier.PROTECTED: Visibility.PROTECTED,
        _Modifier.PRIVATE: Visibility.PRIVATE,
    }
    return next((value for modifier, value in choices.items() if modifier in modifiers), None)


def _type(node: _Node | None) -> str | None:
    if node is None:
        return None
    value: str = _text(node)
    return value[1:].strip() if node.kind == _NodeKind.TYPE_ANNOTATION else value


def _parameters(node: _Node | None) -> tuple[Parameter, ...]:
    if node is None:
        return ()
    result = []
    for item in node.named_children:
        pattern = item.child_by_field_name("pattern") or item.child_by_field_name("name")
        if pattern is None and item.named_children:
            pattern = item.named_children[0]
        name = _text(pattern) if pattern is not None else ""
        rest = item.kind is _NodeKind.REST_PARAMETER or (
            pattern is not None and pattern.kind is _NodeKind.REST_PATTERN
        )
        if rest:
            name = name.removeprefix("...")
        value = item.child_by_field_name("value")
        result.append(
            Parameter(
                name,
                _type(item.child_by_field_name("type")),
                item.kind is _NodeKind.OPTIONAL_PARAMETER
                or any(child.kind is _NodeKind.QUESTION for child in item.children),
                rest,
                _text(value) if value is not None else None,
            )
        )
    return tuple(result)


def _definition(
    node: _Node,
    name: str,
    kind: DefinitionKind,
    parent: str | None,
    source: _Source,
    parent_location: Span | None,
) -> Definition:
    members: list[Member] = []
    bases: list[Base] = []
    body = node.child_by_field_name("body")
    if (
        kind in {DefinitionKind.CLASS, DefinitionKind.INTERFACE, DefinitionKind.ENUM}
        and body is not None
    ):
        members = _declared_members(body, kind, source)
        for heritage in node.named_children:
            clauses = (
                heritage.named_children
                if heritage.kind == _NodeKind.CLASS_HERITAGE
                else (heritage,)
                if heritage.kind == _NodeKind.EXTENDS_TYPE_CLAUSE
                else ()
            )
            for clause in clauses:
                if clause.kind not in (
                    _NodeKind.EXTENDS_CLAUSE,
                    _NodeKind.IMPLEMENTS_CLAUSE,
                    _NodeKind.EXTENDS_TYPE_CLAUSE,
                ):
                    continue
                relationship = (
                    BaseRelationship.REALIZES
                    if clause.kind is _NodeKind.IMPLEMENTS_CLAUSE
                    else BaseRelationship.INHERITS
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
        _Modifier.STATIC in _modifiers(node),
        _exported(node),
        _type(node.child_by_field_name("type") or node.child_by_field_name("value")),
        _parameters(node.child_by_field_name("parameters")),
        _type(node.child_by_field_name("return_type")),
        tuple(bases),
        tuple(members),
        bool(_decorators(node)),
        _Modifier.ABSTRACT in _modifiers(node),
        _members_complete(body),
        node.child_by_field_name("body") is None,
        node.parent is not None
        and (
            node.parent.kind == _NodeKind.PROGRAM
            or (
                node.parent.kind == _NodeKind.EXPORT_STATEMENT
                and node.parent.parent is not None
                and node.parent.parent.kind == _NodeKind.PROGRAM
            )
        ),
        _signature_complete(node),
        parent_location.line if parent_location else None,
        parent_location.column if parent_location else None,
        is_async=any(child.kind == _NodeKind.ASYNC for child in node.children),
        decorator_sources=tuple((_text(item), source.span(item)) for item in _decorators(node)),
    )


def _supported_constructor(node: _Node) -> bool:
    name = _Node.child_by_field_name(node, "name")
    previous = node.prev_named_sibling
    while previous is not None and previous.kind == _NodeKind.COMMENT:
        previous = previous.prev_named_sibling
    return (
        _instance_constructor(node)
        and name is not None
        and _special_name(_static_member_name(_text(name))) is _SpecialName.CONSTRUCTOR
        and not any(
            child.kind
            in {
                _NodeKind.GET,
                _NodeKind.SET,
                _NodeKind.ASYNC,
                _NodeKind.ASTERISK,
                _NodeKind.DECORATOR,
            }
            for child in node.children
        )
        and (previous is None or previous.kind != _NodeKind.DECORATOR)
    )


def _static_member_name(raw: str) -> str | None:
    if re.search(r"\\", raw):
        return None
    return raw[1:-1] if re.match(r"""['"]""", raw) else raw


def _parameter_properties(node: _Node) -> tuple[_Node, ...] | None:
    if node.kind not in {_NodeKind.METHOD_DEFINITION, _NodeKind.METHOD_SIGNATURE}:
        return ()
    parameters = _Node.child_by_field_name(node, "parameters")
    properties = (
        tuple(
            item
            for item in parameters.named_children
            if _modifiers(item)
            & {_Modifier.PUBLIC, _Modifier.PRIVATE, _Modifier.PROTECTED, _Modifier.READONLY}
        )
        if parameters is not None
        else ()
    )
    if properties and (
        not _supported_constructor(node) or _Node.child_by_field_name(node, "body") is None
    ):
        return None
    for item in properties:
        pattern = _Node.child_by_field_name(item, "pattern") or _Node.child_by_field_name(
            item, "name"
        )
        if (
            item.has_error
            or item.kind not in {_NodeKind.REQUIRED_PARAMETER, _NodeKind.OPTIONAL_PARAMETER}
            or pattern is None
            or pattern.kind != _NodeKind.IDENTIFIER
            or _static_member_name(_text(pattern)) is None
            or len(_modifiers(item) & {_Modifier.PUBLIC, _Modifier.PRIVATE, _Modifier.PROTECTED})
            > 1
        ):
            return None
    return properties


def _declared_members(body: _Node, kind: DefinitionKind, source: _Source) -> list[Member]:
    members: list[Member] = []
    properties: list[Member] = []
    for item in body.named_children:
        if item.kind in {
            _NodeKind.PUBLIC_FIELD_DEFINITION,
            _NodeKind.PROPERTY_SIGNATURE,
            _NodeKind.ENUM_ASSIGNMENT,
        } or (
            kind is DefinitionKind.ENUM
            and item.kind in {_NodeKind.PROPERTY_IDENTIFIER, _NodeKind.IDENTIFIER}
        ):
            member = _member(item, source)
            if member is not None:
                members.append(member)
        if kind is DefinitionKind.CLASS:
            for parameter in _parameter_properties(item) or ():
                member = _member(parameter, source)
                if member is not None:
                    properties.append(replace(member, literal=None, decorator_sources=()))
    keys = [_static_member_name(member.name) for member in members]
    if None in keys:
        return members
    names = _Counter((*keys, *(member.name for member in properties)))
    return members + [member for member in properties if names[member.name] == 1]


def _members_complete(body: _Node | None) -> bool:
    if body is None or body.has_error:
        return False
    supported = {
        _NodeKind.PUBLIC_FIELD_DEFINITION,
        _NodeKind.PROPERTY_SIGNATURE,
        _NodeKind.METHOD_DEFINITION,
        _NodeKind.METHOD_SIGNATURE,
        _NodeKind.ENUM_ASSIGNMENT,
        _NodeKind.PROPERTY_IDENTIFIER,
        _NodeKind.IDENTIFIER,
        _NodeKind.COMMENT,
    }
    attributes: set[str] = set()
    constructors = 0
    for child in body.named_children:
        if child.kind == _NodeKind.DECORATOR and _decorated_member(child) is not None:
            continue
        if child.kind not in supported:
            return False
        if child.kind in {
            _NodeKind.PUBLIC_FIELD_DEFINITION,
            _NodeKind.PROPERTY_SIGNATURE,
            _NodeKind.METHOD_DEFINITION,
            _NodeKind.METHOD_SIGNATURE,
            _NodeKind.ENUM_ASSIGNMENT,
        }:
            name = child.child_by_field_name("name")
            if child.kind in {_NodeKind.PROPERTY_IDENTIFIER, _NodeKind.IDENTIFIER}:
                continue
            if name is None or name.kind in {None, _NodeKind.COMPUTED_PROPERTY_NAME}:
                return False
            if child.kind in {_NodeKind.PUBLIC_FIELD_DEFINITION, _NodeKind.PROPERTY_SIGNATURE}:
                key = _static_member_name(_text(name))
                if key is None:
                    return False
                if key in attributes:
                    return False
                attributes.add(key)
            if child.kind in {_NodeKind.METHOD_DEFINITION, _NodeKind.METHOD_SIGNATURE}:
                if not _valid_unicode_member_name(name):
                    return False
                properties = _parameter_properties(child)
                constructor = _instance_constructor(child)
                constructors += constructor
                if (
                    constructors > 1
                    or properties is None
                    or constructor
                    and not _supported_constructor(child)
                ):
                    return False
                for parameter in properties:
                    pattern = _Node.child_by_field_name(
                        parameter, "pattern"
                    ) or _Node.child_by_field_name(parameter, "name")
                    if pattern is None or _text(pattern) in attributes:
                        return False
                    attributes.add(_text(pattern))
    return True


def _decorated_member(node: _Node) -> _Node | None:
    """A body-level decorator belongs only to the next supported lexical member."""
    candidate = node.next_named_sibling
    while candidate is not None and candidate.kind in {_NodeKind.DECORATOR, _NodeKind.COMMENT}:
        candidate = candidate.next_named_sibling
    if (
        candidate is None
        or candidate.has_error
        or candidate.kind
        not in {
            _NodeKind.METHOD_DEFINITION,
            _NodeKind.METHOD_SIGNATURE,
            _NodeKind.PUBLIC_FIELD_DEFINITION,
        }
    ):
        return None
    name = _Node.child_by_field_name(candidate, "name")
    return (
        candidate
        if name is not None
        and name.kind != _NodeKind.COMPUTED_PROPERTY_NAME
        and _valid_unicode_member_name(name)
        and not _instance_constructor(candidate)
        else None
    )


def _valid_unicode_member_name(name: _Node) -> bool:
    """String names allow code points that unvalidated escaped identifiers cannot prove."""
    if name.kind is None:
        return False
    if name.kind != _NodeKind.STRING:
        return re.search(r"\\", _text(name)) is None
    for child in name.named_children:
        if child.kind != _NodeKind.ESCAPE_SEQUENCE:
            continue
        escape = _text(child)
        if re.match(r"\\u\{", escape):
            hexadecimal = re.sub("^0*", "", escape[3:-1]) or "0"
            if len(hexadecimal) > 6 or int(hexadecimal, 16) > 0x10FFFF:
                return False
    return True


def _constructor_escape(match: re.Match[str]) -> str:
    """Decode only escape values that can occur in the ASCII name constructor."""
    hexadecimal = next((match[index] for index in (1, 2, 3) if match[index] is not None), None)
    if hexadecimal is not None:
        value = int(hexadecimal, 16)
        return chr(value) if value < 128 else match[0]
    character = match[4]
    if re.fullmatch(r"\r\n|[\n\r\u2028\u2029]", character):
        return ""
    return character if re.fullmatch(r"[cos]", character) else match[0]


def _instance_constructor(node: _Node) -> bool:
    """Recognize the restricted instance constructor name without rewriting source names."""
    name = _Node.child_by_field_name(node, "name")
    if (
        node.kind not in {_NodeKind.METHOD_DEFINITION, _NodeKind.METHOD_SIGNATURE}
        or not _class_member(node)
        or node.parent is None
        or node.parent.kind != _NodeKind.CLASS_BODY
        or _Modifier.STATIC in _modifiers(node)
        or name is None
        or name.kind is None
    ):
        return False
    spelling = _text(name)
    if name.kind == _NodeKind.STRING:
        spelling = spelling[1:-1]
    spelling = re.sub(
        r"\\(?:u(?:\{(0*[0-9a-fA-F]{1,6})\}|([0-9a-fA-F]{4}))|x([0-9a-fA-F]{2})|(\r\n|[\s\S]))",
        _constructor_escape,
        spelling,
    )
    return _special_name(spelling) is _SpecialName.CONSTRUCTOR


def _decorators(node: _Node) -> tuple[_Node, ...]:
    """Read attached decorators and the class body's contiguous sibling decorators."""
    attached = tuple(child for child in node.named_children if child.kind == _NodeKind.DECORATOR)
    parent = node.parent
    if parent is not None and parent.kind == _NodeKind.EXPORT_STATEMENT:
        attached = (
            tuple(child for child in parent.named_children if child.kind == _NodeKind.DECORATOR)
            + attached
        )
    if not _class_member(node):
        return attached
    previous = node.prev_named_sibling
    preceding = []
    while previous is not None and previous.kind in {_NodeKind.DECORATOR, _NodeKind.COMMENT}:
        if previous.kind == _NodeKind.DECORATOR and _decorated_member(previous) == node:
            preceding.append(previous)
        previous = previous.prev_named_sibling
    return (*reversed(preceding), *attached)


def _class_member(node: _Node) -> bool:
    parent = node.parent
    if parent is None or parent.kind not in {_NodeKind.CLASS_BODY, _NodeKind.INTERFACE_BODY}:
        return False
    owner = parent.parent
    return owner is not None and owner.kind in {
        _NodeKind.CLASS_DECLARATION,
        _NodeKind.INTERFACE_DECLARATION,
    }


def _member(node: _Node, source: _Source) -> Member | None:
    name_node = (
        node.child_by_field_name("name")
        or _Node.child_by_field_name(node, "pattern")
        or (node if node.kind in {_NodeKind.PROPERTY_IDENTIFIER, _NodeKind.IDENTIFIER} else None)
    )
    if name_node is None or name_node.kind in {None, _NodeKind.COMPUTED_PROPERTY_NAME}:
        return None
    value = node.child_by_field_name("value")
    literal = (
        _text(value)
        if value is not None
        and value.kind
        in {_NodeKind.STRING, _NodeKind.NUMBER, _NodeKind.TRUE, _NodeKind.FALSE, _NodeKind.NULL}
        else None
    )
    return Member(
        _text(name_node),
        source.span(name_node),
        _type(node.child_by_field_name("type")),
        _visibility(node),
        _Modifier.STATIC in _modifiers(node)
        or node.kind
        in {_NodeKind.ENUM_ASSIGNMENT, _NodeKind.PROPERTY_IDENTIFIER, _NodeKind.IDENTIFIER},
        literal,
        tuple((_text(item), source.span(item)) for item in _decorators(node)),
    )


def _signature_complete(node: _Node) -> bool:
    parameters = node.child_by_field_name("parameters")
    return parameters is None or all(
        item.kind == _NodeKind.REQUIRED_PARAMETER
        and (pattern := item.child_by_field_name("pattern") or item.child_by_field_name("name"))
        is not None
        and pattern.kind == _NodeKind.IDENTIFIER
        and item.child_by_field_name("value") is None
        and not any(child.kind is _NodeKind.QUESTION for child in item.children)
        for item in parameters.named_children
    )


def _exported(node: _Node) -> bool:
    parent = node.parent
    return parent is not None and parent.kind == _NodeKind.EXPORT_STATEMENT


def _module_array_constant(node: _Node, value: _Node) -> bool:
    """Recognize a direct module declaration, without evaluating its array elements."""
    declaration = node.parent
    statement = declaration.parent if declaration is not None else None
    if (
        _in_error(node)
        or statement is None
        or not (
            statement.kind == _NodeKind.PROGRAM
            or (
                statement.kind == _NodeKind.EXPORT_STATEMENT
                and statement.parent is not None
                and statement.parent.kind == _NodeKind.PROGRAM
            )
        )
    ):
        return False
    if value.kind == _NodeKind.AS_EXPRESSION:
        parts = [item for item in value.children if item.kind != _NodeKind.COMMENT]
        if len(parts) != 3 or parts[1].kind != _NodeKind.AS or parts[2].kind != _NodeKind.CONST:
            return False
        value = parts[0]
    return value.kind == _NodeKind.ARRAY and all(
        item.kind
        in {
            _NodeKind.IDENTIFIER,
            _NodeKind.STRING,
            _NodeKind.NUMBER,
            _NodeKind.TRUE,
            _NodeKind.FALSE,
            _NodeKind.NULL,
            _NodeKind.COMMENT,
        }
        for item in value.named_children
    )


def _module_var_array_peer(node: _Node) -> tuple[str | None, bool]:
    """A block/control-flow var still competes with a module array declaration."""
    parent = node.parent
    variable = (
        node.kind == _NodeKind.VARIABLE_DECLARATOR
        and parent is not None
        and parent.kind == _NodeKind.VARIABLE_DECLARATION
    )
    loop = node.kind == _NodeKind.FOR_IN_STATEMENT and any(
        child.kind == _NodeKind.VAR for child in node.children
    )
    if not (variable or loop) or any(
        ancestor.kind
        in {
            _NodeKind.FUNCTION_DECLARATION,
            _NodeKind.GENERATOR_FUNCTION_DECLARATION,
            _NodeKind.FUNCTION_EXPRESSION,
            _NodeKind.GENERATOR_FUNCTION,
            _NodeKind.ARROW_FUNCTION,
            _NodeKind.METHOD_DEFINITION,
            _NodeKind.CLASS_BODY,
            _NodeKind.INTERNAL_MODULE,
        }
        for ancestor in _ancestors(node)
    ):
        return None, False
    binding = next(iter(node.named_children), None)
    if binding is None or binding.kind != _NodeKind.IDENTIFIER:
        return None, True
    name = _text(binding)
    return (name, False) if name and re.search(r"\\", name) is None else (None, True)


def _uncollected_module_binding(node: _Node) -> tuple[str | None, bool]:
    """Veto new array identities beside unsupported module binding syntax."""
    peer_name, opaque = _module_var_array_peer(node)
    if peer_name is not None or opaque:
        return peer_name, opaque
    variable = node.kind == _NodeKind.VARIABLE_DECLARATOR
    defined = node.kind in {
        _NodeKind.CLASS_DECLARATION,
        _NodeKind.FUNCTION_DECLARATION,
        _NodeKind.FUNCTION_SIGNATURE,
        _NodeKind.ENUM_DECLARATION,
    }
    if (
        not defined
        and not variable
        and node.kind
        not in {
            _NodeKind.IMPORT_ALIAS,
            _NodeKind.IMPORT_REQUIRE_CLAUSE,
            _NodeKind.INTERNAL_MODULE,
            _NodeKind.GENERATOR_FUNCTION_DECLARATION,
            _NodeKind.ABSTRACT_CLASS_DECLARATION,
        }
    ):
        return None, False
    scope = node.parent
    declaration = scope if node.kind == _NodeKind.IMPORT_REQUIRE_CLAUSE else node
    if variable:
        scope = scope.parent if scope is not None else None
        if scope is None or scope.kind != _NodeKind.AMBIENT_DECLARATION:
            return None, False
    if node.kind == _NodeKind.IMPORT_REQUIRE_CLAUSE:
        scope = scope.parent if scope is not None else None
    while scope is not None and scope.kind in {
        _NodeKind.EXPORT_STATEMENT,
        _NodeKind.AMBIENT_DECLARATION,
        _NodeKind.EXPRESSION_STATEMENT,
    }:
        scope = scope.parent
    if (
        scope is None
        or scope.kind != _NodeKind.PROGRAM
        or declaration is None
        or any(child.kind == _NodeKind.TYPE for child in declaration.children)
    ):
        return None, False
    if defined:
        return None, any(
            child.kind in {_NodeKind.IDENTIFIER, _NodeKind.TYPE_IDENTIFIER}
            and re.search(r"\\", _text(child)) is not None
            for child in node.named_children
        )
    binding = next(iter(node.named_children), None)
    if binding is None or binding.kind not in {_NodeKind.IDENTIFIER, _NodeKind.TYPE_IDENTIFIER}:
        return None, True
    name = _text(binding)
    return (name, False) if name and re.search(r"\\", name) is None else (None, True)


def _constant_definition(
    node: _Node,
    name: str,
    source: _Source,
    scopes: list[tuple[_Node, str, int]],
    *,
    module_level: bool,
) -> Definition:
    owner = next((item for item, _, _ in reversed(scopes) if _contains(item, node)), None)
    parent_name = next((qualified for item, qualified, _ in scopes if item is owner), None)
    owner_span = source.span(owner) if owner is not None else None
    exported = node.parent is not None and _exported(node.parent)
    return Definition(
        name,
        DefinitionKind.CONSTANT,
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
        top_level=module_level,
        parent_line=owner_span.line if owner_span else None,
        parent_column=owner_span.column if owner_span else None,
    )


def _variables(
    source: _Source, scopes: list[tuple[_Node, str, int]], declarations: dict[_Node, DefinitionKind]
) -> list[Definition]:
    result = []
    imported = _import_bindings(source)
    omitted_module_names = {item.local for item in imported if not item.type_only}
    array_spans: set[Span] = set()
    opaque_module_binding = any(re.search(r"\\", name) is not None for name in omitted_module_names)
    for node in _walk(source.root):
        peer_name, opaque = _uncollected_module_binding(node)
        if peer_name is not None:
            omitted_module_names |= {peer_name}
        opaque_module_binding |= opaque
        if node.kind != _NodeKind.VARIABLE_DECLARATOR:
            continue
        name_node = node.child_by_field_name("name")
        value = node.child_by_field_name("value")
        parent = node.parent
        declaration_parent = parent.parent if parent is not None else None
        module_level = declaration_parent is not None and (
            declaration_parent.kind == _NodeKind.PROGRAM
            or (
                declaration_parent.kind == _NodeKind.EXPORT_STATEMENT
                and declaration_parent.parent is not None
                and declaration_parent.parent.kind == _NodeKind.PROGRAM
            )
        )
        if name_node is None or name_node.kind != _NodeKind.IDENTIFIER:
            opaque_module_binding |= module_level
            continue
        name = _text(name_node)
        opaque_module_binding |= module_level and (not name or re.search(r"\\", name) is not None)
        declaration = (
            parent if parent is not None and parent.kind == _NodeKind.LEXICAL_DECLARATION else None
        )
        kind_node = declaration.child_by_field_name("kind") if declaration else None
        is_array = value is not None and _module_array_constant(node, value)
        plain = value is not None and (
            value.kind
            in {
                _NodeKind.IDENTIFIER,
                _NodeKind.STRING,
                _NodeKind.NUMBER,
                _NodeKind.TRUE,
                _NodeKind.FALSE,
                _NodeKind.NULL,
            }
        )
        if kind_node is None or kind_node.kind is not _NodeKind.CONST or not (plain or is_array):
            if module_level:
                omitted_module_names |= {name}
            continue
        result.append(_constant_definition(node, name, source, scopes, module_level=module_level))
        if is_array:
            array_spans |= {result[-1].span}
        declarations[name_node] = DefinitionKind.CONSTANT
    return [
        item
        for item in result
        if item.span not in array_spans
        or (not opaque_module_binding and item.name not in omitted_module_names)
    ]


def _call_site(node: _Node, source: _Source, scopes: list[tuple[_Node, str, int]]) -> Site | None:
    target = node.child_by_field_name("function") or node.child_by_field_name("constructor")
    if target is None:
        return None
    scope = next((item for item, _, _ in reversed(scopes) if _contains(item, node)), None)
    scope_name = next((name for item, name, _ in scopes if item is scope), None)
    scope_line = next((line for item, _, line in scopes if item is scope), None)
    assigned = _assigned_name(node)
    target_name = _target_name(target)
    shadowed, ambiguous_scope = _active_scope_names(node, scope)
    return Site(
        SiteKind.NEW if node.kind is _NodeKind.NEW_EXPRESSION else SiteKind.CALL,
        _text(target),
        source.span(node),
        scope_name,
        scope_line,
        assigned,
        target_name.name,
        target_name.receiver,
        target_name.computed,
        shadowed,
        _assignment_span(node, source),
        _assignment_annotation(node),
        _text(node) if node.kind == _NodeKind.NEW_EXPRESSION else None,
        receiver_kind=target_name.receiver_kind,
        scope_ambiguous=ambiguous_scope,
        scope_column=source.span(scope).column if scope is not None else None,
    )


def _sites(
    source: _Source, scopes: list[tuple[_Node, str, int]], declarations: dict[_Node, DefinitionKind]
) -> list[Site]:
    sites: list[Site] = []
    for node in _walk(source.root):
        if source.root.has_error and _in_error(node):
            continue
        if node.kind in (_NodeKind.CALL_EXPRESSION, _NodeKind.NEW_EXPRESSION):
            site = _call_site(node, source, scopes)
            if site is not None:
                sites.append(site)
        if node.kind not in (
            _NodeKind.IDENTIFIER,
            _NodeKind.TYPE_IDENTIFIER,
            _NodeKind.PROPERTY_IDENTIFIER,
        ):
            continue
        if node in declarations or _declaration_name(node) or _is_member_name(node):
            continue
        if _inside_site_callee(node):
            continue
        scope = next((item for item, _, _ in reversed(scopes) if _contains(item, node)), None)
        scope_name = next((name for item, name, _ in scopes if item is scope), None)
        scope_line = next((line for item, _, line in scopes if item is scope), None)
        target_name = (
            _target_name(node.parent)
            if node.parent is not None
            and node.parent.kind == _NodeKind.MEMBER_EXPRESSION
            and node.parent.child_by_field_name("property") == node
            else _TargetName(_text(node), None, False)
        )
        shadowed, ambiguous_scope = _active_scope_names(node, scope)
        sites.append(
            Site(
                SiteKind.REFERENCE,
                f"{target_name.receiver}.{target_name.name}"
                if target_name.receiver and target_name.name
                else _text(node),
                source.span(node),
                scope_name,
                scope_line,
                name=target_name.name,
                receiver=target_name.receiver,
                computed=target_name.computed,
                receiver_kind=target_name.receiver_kind,
                shadowed_names=shadowed,
                use=SiteUse.TYPE
                if node.kind is _NodeKind.TYPE_IDENTIFIER
                else SiteUse.MEMBER
                if target_name.receiver
                else SiteUse.VALUE,
                scope_ambiguous=ambiguous_scope,
                scope_column=source.span(scope).column if scope is not None else None,
            )
        )
    return sites


def _declaration_name(node: _Node) -> bool:
    parent = node.parent
    return parent is not None and any(
        parent.child_by_field_name(field) == node for field in ("name", "pattern")
    )


@dataclass(frozen=True, slots=True)
class _TargetName:
    name: str | None
    receiver: str | None
    computed: bool
    receiver_kind: ReceiverKind = ReceiverKind.NONE


def _target_name(node: _Node) -> _TargetName:
    if node.kind in (_NodeKind.IDENTIFIER, _NodeKind.TYPE_IDENTIFIER):
        return _TargetName(_text(node), None, False)
    if node.kind is _NodeKind.MEMBER_EXPRESSION:
        receiver = node.child_by_field_name("object")
        name = node.child_by_field_name("property")
        return _TargetName(
            _text(name)
            if name is not None and name.kind is _NodeKind.PROPERTY_IDENTIFIER
            else None,
            _text(receiver) if receiver is not None else None,
            name is None or name.kind is not _NodeKind.PROPERTY_IDENTIFIER,
            ReceiverKind.THIS
            if receiver is not None and receiver.kind is _NodeKind.THIS
            else ReceiverKind.OTHER
            if receiver is not None
            else ReceiverKind.NONE,
        )
    return _TargetName(None, None, True)


def _scope_names(node: _Node) -> tuple[str, ...]:
    names: set[str] = set()
    parameters = node.child_by_field_name("parameters")
    if parameters is not None:
        names.update(
            _text(child)
            for child in _walk(parameters)
            if child.kind == _NodeKind.IDENTIFIER and _declaration_name(child)
        )
    body = node.child_by_field_name("body")
    if body is not None:
        for child in _walk(body):
            if child.kind == _NodeKind.VARIABLE_DECLARATOR:
                name = child.child_by_field_name("name")
                if name is not None and name.kind == _NodeKind.IDENTIFIER:
                    names.add(_text(name))
            if child.kind == _NodeKind.ASSIGNMENT_EXPRESSION:
                left = child.child_by_field_name("left")
                if left is not None and left.kind == _NodeKind.IDENTIFIER:
                    names.add(_text(left))
    return tuple(sorted(names))


def _active_scope_names(node: _Node, scope: _Node | None) -> tuple[tuple[str, ...], bool]:
    names: set[str] = set(_scope_names(scope)) if scope is not None else set()
    ambiguous = False
    parent = node.parent
    while parent is not None and parent != scope:
        if parent.kind in {_NodeKind.INTERNAL_MODULE, _NodeKind.CLASS_EXPRESSION, _NodeKind.OBJECT}:
            ambiguous = True
        if parent.kind == _NodeKind.STATEMENT_BLOCK:
            owner = parent.parent
            if owner is None or owner.child_by_field_name("body") != parent:
                ambiguous = True
        if parent.kind in {
            _NodeKind.ARROW_FUNCTION,
            _NodeKind.FUNCTION_EXPRESSION,
            _NodeKind.GENERATOR_FUNCTION,
        }:
            names.update(_scope_names(parent))
            ambiguous = True
        elif parent.kind == _NodeKind.METHOD_DEFINITION and not _class_member(parent):
            names.update(_scope_names(parent))
            ambiguous = True
        parent = parent.parent
    return tuple(sorted(names)), ambiguous


def _is_member_name(node: _Node) -> bool:
    parent = node.parent
    if parent is None:
        return False
    if parent.kind == _NodeKind.MEMBER_EXPRESSION:
        return False
    return (
        parent.kind
        in {
            _NodeKind.METHOD_DEFINITION,
            _NodeKind.METHOD_SIGNATURE,
            _NodeKind.PUBLIC_FIELD_DEFINITION,
            _NodeKind.PROPERTY_SIGNATURE,
        }
        and parent.child_by_field_name("name") == node
    )


def _inside_site_callee(node: _Node) -> bool:
    child, parent = node, node.parent
    while parent is not None and parent.kind in (
        _NodeKind.MEMBER_EXPRESSION,
        _NodeKind.SUBSCRIPT_EXPRESSION,
    ):
        child, parent = parent, parent.parent
    return (
        parent is not None
        and parent.kind in (_NodeKind.CALL_EXPRESSION, _NodeKind.NEW_EXPRESSION)
        and (
            parent.child_by_field_name("function") == child
            or parent.child_by_field_name("constructor") == child
        )
    )


def _assigned_name(node: _Node) -> str | None:
    parent = node.parent
    if parent is not None and parent.kind == _NodeKind.ARGUMENTS:
        parent = parent.parent
    if (
        parent is not None
        and parent.kind == _NodeKind.VARIABLE_DECLARATOR
        and parent.child_by_field_name("value") == node
    ):
        name = parent.child_by_field_name("name")
        return _text(name) if name is not None and name.kind == _NodeKind.IDENTIFIER else None
    return None


def _assignment_node(node: _Node) -> _Node | None:
    parent = node.parent
    return (
        parent
        if parent is not None
        and parent.kind == _NodeKind.VARIABLE_DECLARATOR
        and parent.child_by_field_name("value") == node
        else None
    )


def _assignment_span(node: _Node, source: _Source) -> Span | None:
    assignment = _assignment_node(node)
    name = assignment.child_by_field_name("name") if assignment is not None else None
    return source.span(name) if name is not None else None


def _assignment_annotation(node: _Node) -> str | None:
    assignment = _assignment_node(node)
    return _type(assignment.child_by_field_name("type")) if assignment is not None else None


def _import_bindings(source: _Source) -> tuple[ImportBinding, ...]:
    result = []
    for statement in source.captures("references").get("import", []):
        clause = next(iter(_children(statement, _NodeKind.IMPORT_CLAUSE)), None)
        if clause is None:
            continue
        span = source.span(statement)
        default = next(iter(_children(clause, _NodeKind.IDENTIFIER)), None)
        if default is not None:
            result.append(
                ImportBinding(
                    span,
                    "default",
                    _text(default),
                    type_only=any(child.kind == _NodeKind.TYPE for child in statement.children),
                )
            )
        named = next(iter(_children(clause, _NodeKind.NAMED_IMPORTS)), None)
        for item in _children(named, _NodeKind.IMPORT_SPECIFIER):
            imported, alias = _specifier_names(item)
            local = alias or imported
            if imported is not None and local is not None:
                result.append(
                    ImportBinding(
                        span,
                        _text(imported),
                        _text(local),
                        type_only=any(child.kind == _NodeKind.TYPE for child in item.children)
                        or any(child.kind == _NodeKind.TYPE for child in statement.children),
                    )
                )
        namespace = next(iter(_children(clause, _NodeKind.NAMESPACE_IMPORT)), None)
        if namespace is not None:
            local = next(iter(namespace.named_children), None)
            if local is not None:
                result.append(
                    ImportBinding(
                        span,
                        "*",
                        _text(local),
                        True,
                        type_only=any(child.kind == _NodeKind.TYPE for child in statement.children),
                    )
                )
    return tuple(result)


def _rebound_names(source: _Source) -> tuple[str, ...]:
    result = set()
    for node in _walk(source.root):
        if node.kind != _NodeKind.ASSIGNMENT_EXPRESSION:
            continue
        if any(
            parent.kind
            in (
                _NodeKind.FUNCTION_DECLARATION,
                _NodeKind.METHOD_DEFINITION,
                _NodeKind.ARROW_FUNCTION,
            )
            for parent in _ancestors(node)
        ):
            continue
        left = node.child_by_field_name("left")
        if left is not None and left.kind == _NodeKind.IDENTIFIER:
            result.add(_text(left))
    return tuple(sorted(result))


def _ancestors(node: _Node) -> Iterator[_Node]:
    parent = node.parent
    while parent is not None:
        yield parent
        parent = parent.parent


def _in_unmodeled_block(node: _Node) -> bool:
    return any(
        block.kind == _NodeKind.STATEMENT_BLOCK
        and (block.parent is None or block.parent.child_by_field_name("body") != block)
        for block in _ancestors(node)
    )


def _text(node: _Node) -> str:
    return str(node.text or b"", "utf-8", "replace")


def _in_error(node: _Node) -> bool:
    """A reference inside a region the parser had to repair is not a fact."""
    if node.has_error:
        return True
    parent = node.parent
    while parent is not None:
        if parent.is_error:
            return True
        parent = parent.parent
    return False


def _literal(node: _Node | None) -> str | None:
    """The module text of a string without escapes or substitutions; None means computed."""
    if (
        node is None
        or node.kind not in (_NodeKind.STRING, _NodeKind.TEMPLATE_STRING)
        or re.search(r"\\", _text(node)) is not None
    ):
        return None
    if any(child.kind == _NodeKind.TEMPLATE_SUBSTITUTION for child in node.children):
        return None
    return _text(node)[1:-1]


def _type_only(statement: _Node, specifiers: list[_Node], default: bool) -> bool:
    """`import type`, or every named specifier marked `type` with no default import."""
    marked = bool(specifiers) and all(
        any(child.kind == _NodeKind.TYPE for child in item.children) for item in specifiers
    )
    return any(child.kind == _NodeKind.TYPE for child in statement.children) or (
        marked and not default
    )


def _children(node: _Node | None, kind: _NodeKind) -> list[_Node]:
    return [child for child in node.children if child.kind == kind] if node is not None else []


def _import(node: _Node, source: _Source) -> Reference:
    clause = next(iter(_children(node, _NodeKind.IMPORT_CLAUSE)), None)
    required = next(iter(_children(node, _NodeKind.IMPORT_REQUIRE_CLAUSE)), None)
    named = _children(
        next(iter(_children(clause, _NodeKind.NAMED_IMPORTS)), None), _NodeKind.IMPORT_SPECIFIER
    )
    return Reference(
        ReferenceForm.IMPORT if required is None else ReferenceForm.IMPORT_EQUALS,
        _literal(
            next(iter(_children(node if required is None else required, _NodeKind.STRING)), None)
        ),
        _type_only(node, named, bool(_children(clause, _NodeKind.IDENTIFIER))),
        _top_level(node),
        re.search(r"resolution-mode", _text(node)) is not None,
        source.span(node),
    )


def _export(node: _Node, source: _Source) -> Reference:
    clause = next(iter(_children(node, _NodeKind.EXPORT_CLAUSE)), None)
    return Reference(
        ReferenceForm.REEXPORT,
        _literal(next(iter(_children(node, _NodeKind.STRING)), None)),
        _type_only(node, _children(clause, _NodeKind.EXPORT_SPECIFIER), False),
        _top_level(node),
        re.search(r"resolution-mode", _text(node)) is not None,
        source.span(node),
    )


def _top_level(node: _Node) -> bool:
    return node.parent is not None and node.parent.kind == _NodeKind.PROGRAM


def _argument(call: _Node) -> _Node | None:
    arguments = next(iter(_children(call, _NodeKind.ARGUMENTS)), None)
    return arguments.named_children[0] if arguments and arguments.named_children else None


def _in_type(node: _Node) -> bool:
    child, parent = node, node.parent
    while parent is not None:
        if parent.kind in _TYPE_PARENTS:
            return True
        # `value as T` and `value satisfies T` start with the value; only what follows is a type.
        if parent.kind in (_NodeKind.AS_EXPRESSION, _NodeKind.SATISFIES_EXPRESSION) and (
            child.start_byte > parent.start_byte
        ):
            return True
        child, parent = parent, parent.parent
    return False


def _query_start(node: _Node) -> _Node | None:
    """The `typeof` query an import type opens, which the compiler counts as part of it."""
    parent = node.parent
    while (
        parent is not None
        and parent.kind
        in (_NodeKind.MEMBER_EXPRESSION, _NodeKind.CALL_EXPRESSION, _NodeKind.SUBSCRIPT_EXPRESSION)
        and parent.start_byte == node.start_byte
    ):
        parent = parent.parent
    return parent if parent is not None and parent.kind == _NodeKind.TYPE_QUERY else None


def _dynamic(node: _Node, source: _Source) -> Reference:
    typed = _in_type(node)
    return Reference(
        ReferenceForm.IMPORT_TYPE if typed else ReferenceForm.DYNAMIC_IMPORT,
        _literal(_argument(node)),
        typed,
        False,
        re.search(r"resolution-mode", _text(node)) is not None,
        source.span(node, _query_start(node) if typed else None),
    )


def _require(node: _Node, source: _Source) -> Reference:
    return Reference(
        ReferenceForm.REQUIRE, _literal(_argument(node)), False, False, False, source.span(node)
    )


def _starts_with(parent: _Node | None, node: _Node, *kinds: _NodeKind) -> bool:
    return parent is not None and parent.kind in kinds and parent.start_byte == node.start_byte


def _require_concerns(source: _Source, concerns: list[Concern]) -> bool:
    """Report every `require` that is not a plain call; True when one may rebind the name."""
    shadows = False
    for node in source.captures("require_names").get("name", []):
        parent = node.parent
        if _starts_with(parent, node, _NodeKind.CALL_EXPRESSION):
            continue
        concerns.append(Concern("Indirect require use is not resolved", source.span(node)))
        # Reading `require.main` or `typeof require` does not rebind it; anything else might.
        reads = _starts_with(
            parent, node, _NodeKind.MEMBER_EXPRESSION, _NodeKind.SUBSCRIPT_EXPRESSION
        )
        typeof = (
            parent is not None
            and parent.kind == _NodeKind.UNARY_EXPRESSION
            and any(child.kind is _NodeKind.TYPEOF for child in parent.children)
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
        computed = key.kind == _NodeKind.COMPUTED_PROPERTY_NAME
        inner = key.named_children[0] if computed and key.named_children else key
        name = _literal(inner) if inner.kind == _NodeKind.STRING else _text(inner)
        # A computed key may select `require` from the module object by a name built at runtime.
        runtime_name = computed and inner.kind != _NodeKind.STRING
        if _special_name(name) is _SpecialName.REQUIRE or (runtime_name and modules):
            concerns.append(Concern("Indirect require binding is not resolved", source.span(node)))
    return shadows


def _comment_concerns(source: _Source) -> list[Concern]:
    concerns: list[Concern] = []
    # Triple-slash directives count only before the first statement of the file.
    statements = [
        child.start_byte
        for child in source.root.children
        if child.kind not in (_NodeKind.COMMENT, _NodeKind.HASH_BANG_LINE)
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
