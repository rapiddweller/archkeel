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
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field, replace
from enum import Enum
from functools import cache
from typing import Final

import tree_sitter_typescript
from tree_sitter import Language, Parser, Query, QueryCursor
from tree_sitter import Node as _RawNode

from .source_input import FileSuffix, SourceKind, classify_file
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
    ScriptAlias,
    ScriptDestructure,
    ScriptFactory,
    ScriptFactoryMember,
    ScriptGlobal,
    ScriptNamespace,
    ScriptRoot,
    StringComparison,
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
    ARRAY_PATTERN = "array_pattern"
    ARROW_FUNCTION = "arrow_function"
    AS = "as"
    AS_EXPRESSION = "as_expression"
    ASSIGNMENT_EXPRESSION = "assignment_expression"
    ASSIGNMENT_PATTERN = "assignment_pattern"
    AUGMENTED_ASSIGNMENT_EXPRESSION = "augmented_assignment_expression"
    ASYNC = "async"
    BINARY_EXPRESSION = "binary_expression"
    EQUAL = "=="
    NOT_EQUAL = "!="
    STRICT_EQUAL = "==="
    STRICT_NOT_EQUAL = "!=="
    CALL_EXPRESSION = "call_expression"
    CATCH_CLAUSE = "catch_clause"
    CLASS = "class"
    CLASS_BODY = "class_body"
    CLASS_DECLARATION = "class_declaration"
    CLASS_EXPRESSION = "class_expression"
    CLASS_HERITAGE = "class_heritage"
    CLASS_STATIC_BLOCK = "class_static_block"
    COMMENT = "comment"
    COMPUTED_PROPERTY_NAME = "computed_property_name"
    CONST = "const"
    DECLARE = "declare"
    DEFAULT = "default"
    DELETE = "delete"
    DECORATOR = "decorator"
    ENUM_ASSIGNMENT = "enum_assignment"
    ENUM_DECLARATION = "enum_declaration"
    ELSE_CLAUSE = "else_clause"
    ESCAPE_SEQUENCE = "escape_sequence"
    EXPORT_CLAUSE = "export_clause"
    EXPORT_SPECIFIER = "export_specifier"
    EXPORT_STATEMENT = "export_statement"
    EXPRESSION_STATEMENT = "expression_statement"
    EXTENDS_CLAUSE = "extends_clause"
    EXTENDS_TYPE_CLAUSE = "extends_type_clause"
    FALSE = "false"
    FOR_IN_STATEMENT = "for_in_statement"
    FOR_STATEMENT = "for_statement"
    FORMAL_PARAMETERS = "formal_parameters"
    FUNCTION_DECLARATION = "function_declaration"
    FUNCTION_EXPRESSION = "function_expression"
    FUNCTION_SIGNATURE = "function_signature"
    GENERATOR_FUNCTION = "generator_function"
    GENERATOR_FUNCTION_DECLARATION = "generator_function_declaration"
    GET = "get"
    HASH_BANG_LINE = "hash_bang_line"
    IDENTIFIER = "identifier"
    IF_STATEMENT = "if_statement"
    IMPLEMENTS_CLAUSE = "implements_clause"
    IMPORT_ALIAS = "import_alias"
    IMPORT_CLAUSE = "import_clause"
    IMPORT_REQUIRE_CLAUSE = "import_require_clause"
    IMPORT_SPECIFIER = "import_specifier"
    IMPORT_STATEMENT = "import_statement"
    INTERFACE_BODY = "interface_body"
    INTERFACE_DECLARATION = "interface_declaration"
    INTERNAL_MODULE = "internal_module"
    JSX_ATTRIBUTE = "jsx_attribute"
    JSX_NAMESPACE_NAME = "jsx_namespace_name"
    LEXICAL_DECLARATION = "lexical_declaration"
    MEMBER_EXPRESSION = "member_expression"
    METHOD_DEFINITION = "method_definition"
    METHOD_SIGNATURE = "method_signature"
    MODULE = "module"
    NAMED_IMPORTS = "named_imports"
    NESTED_IDENTIFIER = "nested_identifier"
    NAMESPACE_EXPORT = "namespace_export"
    NAMESPACE_IMPORT = "namespace_import"
    NEW_EXPRESSION = "new_expression"
    NON_NULL_EXPRESSION = "non_null_expression"
    NULL = "null"
    NUMBER = "number"
    OBJECT = "object"
    OBJECT_PATTERN = "object_pattern"
    OBJECT_ASSIGNMENT_PATTERN = "object_assignment_pattern"
    PAIR = "pair"
    PAIR_PATTERN = "pair_pattern"
    OPTIONAL_PARAMETER = "optional_parameter"
    OPTIONAL_CHAIN = "optional_chain"
    OPTIONAL_CHAIN_OPERATOR = "?."
    OVERRIDE = "override"
    PARENTHESIZED_EXPRESSION = "parenthesized_expression"
    PRIVATE_PROPERTY_IDENTIFIER = "private_property_identifier"
    PROGRAM = "program"
    PROPERTY_IDENTIFIER = "property_identifier"
    PROPERTY_SIGNATURE = "property_signature"
    PUBLIC_FIELD_DEFINITION = "public_field_definition"
    READONLY = "readonly"
    REQUIRED_PARAMETER = "required_parameter"
    REST_PARAMETER = "rest_parameter"
    REST_PATTERN = "rest_pattern"
    RETURN_STATEMENT = "return_statement"
    SATISFIES_EXPRESSION = "satisfies_expression"
    SET = "set"
    SHORTHAND_PROPERTY_IDENTIFIER = "shorthand_property_identifier"
    SHORTHAND_PROPERTY_IDENTIFIER_PATTERN = "shorthand_property_identifier_pattern"
    STATEMENT_BLOCK = "statement_block"
    STATIC = "static"
    STRING = "string"
    STRING_FRAGMENT = "string_fragment"
    SWITCH_CASE = "switch_case"
    SWITCH_BODY = "switch_body"
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
    UPDATE_EXPRESSION = "update_expression"
    VAR = "var"
    VARIABLE_DECLARATION = "variable_declaration"
    VARIABLE_DECLARATOR = "variable_declarator"
    WITH_STATEMENT = "with_statement"
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
    DEFAULT = "default"


class _SpecialName(Enum):
    CONSTRUCTOR = "constructor"
    REQUIRE = "require"
    EVAL = "eval"
    FUNCTION = "Function"
    REFLECT = "Reflect"
    GET_PROTOTYPE_OF = "getPrototypeOf"
    GET_OWN_PROPERTY_DESCRIPTOR = "getOwnPropertyDescriptor"
    GET_OWN_PROPERTY_DESCRIPTORS = "getOwnPropertyDescriptors"
    DEFINE_PROPERTY = "defineProperty"
    DEFINE_PROPERTIES = "defineProperties"
    SET_PROTOTYPE_OF = "setPrototypeOf"
    PROTO = "__proto__"
    SET_TIMEOUT = "setTimeout"
    SET_INTERVAL = "setInterval"


class _LoaderModule(Enum):
    MODULE = "module"
    NODE_MODULE = "node:module"


_NODE_KINDS: Final[dict[str, _NodeKind]] = {item.value: item for item in _NodeKind}
_MODIFIER_WORDS: Final[dict[str, _Modifier]] = {item.value: item for item in _Modifier}
_SPECIAL_NAMES: Final[dict[str, _SpecialName]] = {item.value: item for item in _SpecialName}
_SCRIPT_EFFECT_NAMES: Final = frozenset(
    {
        _SpecialName.CONSTRUCTOR,
        _SpecialName.EVAL,
        _SpecialName.FUNCTION,
        _SpecialName.REFLECT,
        _SpecialName.GET_PROTOTYPE_OF,
        _SpecialName.GET_OWN_PROPERTY_DESCRIPTOR,
        _SpecialName.GET_OWN_PROPERTY_DESCRIPTORS,
        _SpecialName.DEFINE_PROPERTY,
        _SpecialName.DEFINE_PROPERTIES,
        _SpecialName.SET_PROTOTYPE_OF,
        _SpecialName.PROTO,
        _SpecialName.SET_TIMEOUT,
        _SpecialName.SET_INTERVAL,
    }
)
_LOADER_MODULES: Final[dict[str, _LoaderModule]] = {item.value: item for item in _LoaderModule}
_SCRIPT_ROOTS: Final = frozenset(item.value for item in ScriptRoot)
_SCRIPT_FUNCTIONS: Final = frozenset(
    {
        _NodeKind.FUNCTION_DECLARATION,
        _NodeKind.FUNCTION_EXPRESSION,
        _NodeKind.GENERATOR_FUNCTION_DECLARATION,
        _NodeKind.GENERATOR_FUNCTION,
        _NodeKind.ARROW_FUNCTION,
        _NodeKind.METHOD_DEFINITION,
    }
)
_SCRIPT_VAR_SCOPES: Final = _SCRIPT_FUNCTIONS | {
    _NodeKind.PROGRAM,
    _NodeKind.CLASS_STATIC_BLOCK,
}
_SCRIPT_SCOPES: Final = _SCRIPT_VAR_SCOPES | {
    _NodeKind.STATEMENT_BLOCK,
    _NodeKind.CATCH_CLAUSE,
    _NodeKind.FOR_IN_STATEMENT,
    _NodeKind.FOR_STATEMENT,
    _NodeKind.SWITCH_BODY,
    _NodeKind.CLASS,
    _NodeKind.CLASS_DECLARATION,
    _NodeKind.CLASS_BODY,
}
_SCRIPT_RECEIVER_SCOPES: Final = (_SCRIPT_FUNCTIONS - {_NodeKind.ARROW_FUNCTION}) | {
    _NodeKind.CLASS_STATIC_BLOCK
}
_SCRIPT_CALLABLE_VALUES: Final = _SCRIPT_FUNCTIONS | {
    _NodeKind.CLASS,
    _NodeKind.CLASS_DECLARATION,
}


def _node_kind(raw: _RawNode) -> _NodeKind | None:
    return _NODE_KINDS.get(raw.type)


def _special_name(value: str | None) -> _SpecialName | None:
    return _SPECIAL_NAMES.get(value) if value is not None else None


_LOADER: Final = "Node module loader is not observed"


class _JSDocType(Enum):
    """How a JSDoc tag can name a module; tsc 5.9.3 reads these only in JavaScript (#744)."""

    BRACED = "braced"
    BARE = "bare"  # The type can omit its braces.
    TEMPLATE = "template"  # A `[name=default]` also holds a type.
    IMPORT = "import"


_JSDOC_TAGS: Final = {
    "import": _JSDocType.IMPORT,
    "template": _JSDocType.TEMPLATE,
    **dict.fromkeys(
        ("type", "this", "enum", "extends", "augments", "implements", "satisfies"), _JSDocType.BARE
    ),
    **dict.fromkeys(
        (
            "return",
            "returns",
            "param",
            "arg",
            "argument",
            "prop",
            "property",
            "typedef",
            "throws",
            "exception",
        ),
        _JSDocType.BRACED,
    ),
}
# Only a `/**` comment is a JSDoc block. tsc starts a tag at `@` after whitespace or a margin
# `*`, so `a@type` is no tag.
_JSDOC_TOKEN: Final = re.compile(
    r"(?P<block>\A/\*\*)|(?<![^\s*])@(?P<tag>\w+)(?P<braced>[\s*]*\{)?"
    r"|(?P<open>\{)|(?P<close>\})|(?P<bracket>\[)|(?P<end>\])|(?P<quote>['\"`])"
    r"|(?P<call>\bimport[\s*]*\()"
)


_TRIPLE_SLASH: Final = re.compile(r"^///\s*<reference\s+(?:path|lib)\s*=\s*(['\"])(.*?)\1")
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
    "umd_writes": """
        [(with_statement) (function_declaration) (function_expression)
         (generator_function_declaration) (generator_function) (arrow_function)
         (method_definition) (catch_clause) (for_in_statement)
         (class) (class_declaration) (variable_declarator)] @binding
        [(assignment_expression) (augmented_assignment_expression)
         (for_in_statement) (update_expression) (unary_expression)] @write
        [(call_expression) (new_expression)] @call
        """,
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
    root: _RawNode
    data: bytes
    script_mode: bool
    starts: list[int]
    scope_names: dict[_RawNode, tuple[str, ...]] = field(default_factory=dict)

    def names_in_scope(self, node: _RawNode) -> tuple[str, ...]:
        if node not in self.scope_names:
            self.scope_names[node] = _scope_names(node)
        return self.scope_names[node]

    def captures(self, query: str, scope: _RawNode | None = None) -> dict[str, list[_RawNode]]:
        return QueryCursor(_query(self.kind, query)).captures(scope or self.root)

    def span(self, node: _RawNode, start: _RawNode | None = None) -> Span:
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


def _parse_root(kind: _Grammar, data: bytes) -> _RawNode:
    return Parser(_grammar(kind)).parse(data).root_node


def _line_starts(data: bytes) -> list[int]:
    return [0, *(found.end() for found in _LINE_BREAK.finditer(data))]


def parse(rel_path: str, data: bytes) -> Syntax:
    # JSX and JavaScript need the TSX grammar; `<T>x` assertions exist only without it.
    # Preserve the old filename regex boundary: $ also accepted one final newline.
    suffix = classify_file(rel_path.removesuffix("\n"))
    kind = _Grammar.TYPESCRIPT if suffix is not None and suffix.parser_typescript else _Grammar.TSX
    root = _parse_root(kind, data)
    script_mode = (
        suffix is not None
        and suffix.source_kind is SourceKind.JAVASCRIPT
        and suffix.format_hint is None
        and not _module_exports(root)[0]
    )
    source = _Source(kind, root, data, script_mode, _line_starts(data))
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
        concerns.append(Concern(_LOADER, min(loaders, key=lambda span: (span.line, span.column))))
    if re.search(rb"/\*\*|///", data):
        concerns.extend(_comment_concerns(source, suffix))
    errors = sorted(source.captures("errors").get("error", []), key=lambda item: item.start_byte)
    bindings, ambiguous_bindings = _script_bindings(source)
    if script_mode:
        concerns.extend(
            Concern("Script binding scope is not statically known", source.span(node))
            for node in sorted(ambiguous_bindings, key=lambda item: item.start_byte)
        )
    definitions, sites, comparisons = _inner(source, bindings, ambiguous_bindings)
    script_globals, script_writes = _script_globals(source, bindings, ambiguous_bindings)
    declarations, writes, paths, top_paths = _script_declarations(source, definitions, bindings)
    script_globals = tuple(
        replace(publication, source_members=declarations.get(publication.span, ()))
        for publication in script_globals
    )
    return Syntax(
        tuple(
            sorted(trusted, key=lambda item: (item.span.line, item.span.column, item.form.value))
        ),
        tuple(concerns),
        shadows,
        source.span(errors[0]) if errors else None,
        definitions,
        sites,
        _module_import_bindings(source, bindings, ambiguous_bindings),
        _rebound_names(source),
        comparisons,
        script_globals if script_mode else (),
        script_writes,
        script_mode,
        _script_aliases(source, bindings, ambiguous_bindings) if script_mode else (),
        _script_factories(source, definitions, bindings) if script_mode else (),
        writes,
        paths,
        top_paths,
        _script_destructures(source, bindings, ambiguous_bindings) if script_mode else (),
        tuple(sorted(bindings.get(source.root, ()))),
        _script_namespaces(source, bindings) if script_mode else (),
        _module_export_bindings(source, bindings, ambiguous_bindings),
        *_ambient_scope(source, suffix),
    )


_DEFINITION_KINDS: Final = {
    _NodeKind.CLASS_DECLARATION: DefinitionKind.CLASS,
    _NodeKind.INTERFACE_DECLARATION: DefinitionKind.INTERFACE,
    _NodeKind.ENUM_DECLARATION: DefinitionKind.ENUM,
    _NodeKind.FUNCTION_DECLARATION: DefinitionKind.FUNCTION,
    _NodeKind.FUNCTION_SIGNATURE: DefinitionKind.FUNCTION,
    _NodeKind.METHOD_DEFINITION: DefinitionKind.METHOD,
    _NodeKind.METHOD_SIGNATURE: DefinitionKind.METHOD,
    _NodeKind.TYPE_ALIAS_DECLARATION: DefinitionKind.TYPE_ALIAS,
}


def _inner(
    source: _Source,
    bindings: dict[_RawNode, dict[str, int]],
    ambiguous_bindings: set[_RawNode],
) -> tuple[tuple[Definition, ...], tuple[Site, ...], tuple[StringComparison, ...]]:
    definitions: list[Definition] = []
    declaration_nodes: dict[_RawNode, DefinitionKind] = {}
    scopes: list[tuple[_RawNode, str, int]] = []
    module_syntax, exported_names, visible_names, exports_complete = _module_exports(source.root)
    for node in _walk(source.root):
        if source.root.has_error and _in_error(node):
            continue
        if any(_node_kind(parent) == _NodeKind.INTERNAL_MODULE for parent in _ancestors(node)):
            continue
        if _in_unmodeled_block(node):
            continue
        node_kind = _node_kind(node)
        if node_kind is None or node_kind not in _DEFINITION_KINDS:
            continue
        name_node = node.child_by_field_name("name")
        name = _text(name_node) if name_node else ""
        if _supported_constructor(node):
            name = "constructor"
        if (
            not name
            or name_node is None
            or _node_kind(name_node) in {None, _NodeKind.COMPUTED_PROPERTY_NAME}
        ):
            continue
        if node_kind in (
            _NodeKind.METHOD_DEFINITION,
            _NodeKind.METHOD_SIGNATURE,
        ) and not _class_member(node):
            continue
        parent_scope = next((item for item in reversed(scopes) if _contains(item[0], node)), None)
        parent_name = parent_scope[1] if parent_scope else None
        kind = _DEFINITION_KINDS[node_kind]
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
    sites, comparisons = _sites(source, scopes, declaration_nodes, bindings, ambiguous_bindings)
    return (
        tuple(sorted(definitions, key=lambda item: (item.span.line, item.span.column))),
        tuple(sorted(sites, key=lambda item: (item.span.line, item.span.column, item.kind.value))),
        tuple(comparisons),
    )


def _specifier_names(specifier: _RawNode) -> tuple[_RawNode | None, _RawNode | None]:
    """Read the local/imported name and optional public/local alias from one specifier."""
    return (
        specifier.child_by_field_name("name"),
        specifier.child_by_field_name("alias"),
    )


def _module_exports(root: _RawNode) -> tuple[bool, set[str], set[str], bool]:
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
    statements = [
        item for item in root.named_children if _node_kind(item) == _NodeKind.EXPORT_STATEMENT
    ]
    module_syntax = bool(statements) or any(
        _node_kind(item) in imports for item in root.named_children
    )
    exported_names: set[str] = set()
    visible_names: set[str] = set()
    complete = True
    for statement in statements:
        if any(_node_kind(item) in declarations for item in statement.named_children):
            continue
        clause = next(
            (
                item
                for item in statement.named_children
                if _node_kind(item) == _NodeKind.EXPORT_CLAUSE
            ),
            None,
        )
        if clause is None:
            if any(_node_kind(item) == _NodeKind.STRING for item in statement.named_children):
                continue
            complete = False
            continue
        if any(_node_kind(item) == _NodeKind.STRING for item in statement.named_children):
            continue
        statement_is_type_only = any(
            _node_kind(item) == _NodeKind.TYPE for item in statement.children
        )
        for candidate in clause.named_children:
            if _node_kind(candidate) != _NodeKind.EXPORT_SPECIFIER:
                continue
            specifier: _RawNode = candidate
            name, alias = _specifier_names(specifier)
            if name is None or _node_kind(name) not in {
                _NodeKind.IDENTIFIER,
                _NodeKind.TYPE_IDENTIFIER,
            }:
                complete = False
                continue
            local_name = _text(name)
            visible_names.add(local_name)
            is_alias = alias is not None and _text(alias) != local_name
            is_type_only = statement_is_type_only or any(
                _node_kind(item) == _NodeKind.TYPE for item in specifier.children
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


def _walk(node: _RawNode) -> Iterator[_RawNode]:
    yield node
    for child in node.named_children:
        yield from _walk(child)


def _contains(parent: _RawNode, child: _RawNode) -> bool:
    return parent.start_byte <= child.start_byte and parent.end_byte >= child.end_byte


def _modifiers(node: _RawNode) -> set[_Modifier]:
    return {
        modifier
        for child in node.children
        if _node_kind(child)
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


def _visibility(node: _RawNode) -> Visibility | None:
    modifiers = _modifiers(node)
    if any(_node_kind(child) is _NodeKind.PRIVATE_PROPERTY_IDENTIFIER for child in node.children):
        return Visibility.PRIVATE
    name = node.child_by_field_name("name")
    if name is not None and _node_kind(name) is _NodeKind.PRIVATE_PROPERTY_IDENTIFIER:
        return Visibility.PRIVATE
    choices = {
        _Modifier.PUBLIC: Visibility.PUBLIC,
        _Modifier.PROTECTED: Visibility.PROTECTED,
        _Modifier.PRIVATE: Visibility.PRIVATE,
    }
    return next((value for modifier, value in choices.items() if modifier in modifiers), None)


def _type(node: _RawNode | None) -> str | None:
    if node is None:
        return None
    value: str = _text(node)
    return value[1:].strip() if _node_kind(node) == _NodeKind.TYPE_ANNOTATION else value


def _parameters(node: _RawNode | None) -> tuple[Parameter, ...]:
    if node is None:
        return ()
    result = []
    for item in node.named_children:
        pattern = item.child_by_field_name("pattern") or item.child_by_field_name("name")
        if pattern is None and item.named_children:
            pattern = item.named_children[0]
        name = _text(pattern) if pattern is not None else ""
        rest = _node_kind(item) is _NodeKind.REST_PARAMETER or (
            pattern is not None and _node_kind(pattern) is _NodeKind.REST_PATTERN
        )
        if rest:
            name = name.removeprefix("...")
        value = item.child_by_field_name("value")
        result.append(
            Parameter(
                name,
                _type(item.child_by_field_name("type")),
                _node_kind(item) is _NodeKind.OPTIONAL_PARAMETER
                or any(_node_kind(child) is _NodeKind.QUESTION for child in item.children),
                rest,
                _text(value) if value is not None else None,
            )
        )
    return tuple(result)


def _definition(
    node: _RawNode,
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
                if _node_kind(heritage) == _NodeKind.CLASS_HERITAGE
                else (heritage,)
                if _node_kind(heritage) == _NodeKind.EXTENDS_TYPE_CLAUSE
                else ()
            )
            for clause in clauses:
                if _node_kind(clause) not in (
                    _NodeKind.EXTENDS_CLAUSE,
                    _NodeKind.IMPLEMENTS_CLAUSE,
                    _NodeKind.EXTENDS_TYPE_CLAUSE,
                ):
                    continue
                relationship = (
                    BaseRelationship.REALIZES
                    if _node_kind(clause) is _NodeKind.IMPLEMENTS_CLAUSE
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
            _node_kind(node.parent) == _NodeKind.PROGRAM
            or (
                _node_kind(node.parent) == _NodeKind.EXPORT_STATEMENT
                and node.parent.parent is not None
                and _node_kind(node.parent.parent) == _NodeKind.PROGRAM
            )
        ),
        _signature_complete(node),
        parent_location.line if parent_location else None,
        parent_location.column if parent_location else None,
        is_async=any(_node_kind(child) == _NodeKind.ASYNC for child in node.children),
        decorator_sources=tuple((_text(item), source.span(item)) for item in _decorators(node)),
    )


def _supported_constructor(node: _RawNode) -> bool:
    name = _RawNode.child_by_field_name(node, "name")
    previous = node.prev_named_sibling
    while previous is not None and _node_kind(previous) == _NodeKind.COMMENT:
        previous = previous.prev_named_sibling
    return (
        _instance_constructor(node)
        and name is not None
        and _special_name(_static_member_name(_text(name))) is _SpecialName.CONSTRUCTOR
        and not any(
            _node_kind(child)
            in {
                _NodeKind.GET,
                _NodeKind.SET,
                _NodeKind.ASYNC,
                _NodeKind.ASTERISK,
                _NodeKind.DECORATOR,
            }
            for child in node.children
        )
        and (previous is None or _node_kind(previous) != _NodeKind.DECORATOR)
    )


def _static_member_name(raw: str) -> str | None:
    if re.search(r"\\", raw):
        return None
    return raw[1:-1] if re.match(r"""['"]""", raw) else raw


def _parameter_properties(node: _RawNode) -> tuple[_RawNode, ...] | None:
    if _node_kind(node) not in {_NodeKind.METHOD_DEFINITION, _NodeKind.METHOD_SIGNATURE}:
        return ()
    parameters = _RawNode.child_by_field_name(node, "parameters")
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
        not _supported_constructor(node) or _RawNode.child_by_field_name(node, "body") is None
    ):
        return None
    for item in properties:
        pattern = _RawNode.child_by_field_name(item, "pattern") or _RawNode.child_by_field_name(
            item, "name"
        )
        if (
            item.has_error
            or _node_kind(item) not in {_NodeKind.REQUIRED_PARAMETER, _NodeKind.OPTIONAL_PARAMETER}
            or pattern is None
            or _node_kind(pattern) != _NodeKind.IDENTIFIER
            or _static_member_name(_text(pattern)) is None
            or len(_modifiers(item) & {_Modifier.PUBLIC, _Modifier.PRIVATE, _Modifier.PROTECTED})
            > 1
        ):
            return None
    return properties


def _declared_members(body: _RawNode, kind: DefinitionKind, source: _Source) -> list[Member]:
    members: list[Member] = []
    properties: list[Member] = []
    for item in body.named_children:
        if _node_kind(item) in {
            _NodeKind.PUBLIC_FIELD_DEFINITION,
            _NodeKind.PROPERTY_SIGNATURE,
            _NodeKind.ENUM_ASSIGNMENT,
        } or (
            kind is DefinitionKind.ENUM
            and _node_kind(item) in {_NodeKind.PROPERTY_IDENTIFIER, _NodeKind.IDENTIFIER}
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


def _members_complete(body: _RawNode | None) -> bool:
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
        if _node_kind(child) == _NodeKind.DECORATOR and _decorated_member(child) is not None:
            continue
        if _node_kind(child) not in supported:
            return False
        if _node_kind(child) in {
            _NodeKind.PUBLIC_FIELD_DEFINITION,
            _NodeKind.PROPERTY_SIGNATURE,
            _NodeKind.METHOD_DEFINITION,
            _NodeKind.METHOD_SIGNATURE,
            _NodeKind.ENUM_ASSIGNMENT,
        }:
            name = child.child_by_field_name("name")
            if _node_kind(child) in {_NodeKind.PROPERTY_IDENTIFIER, _NodeKind.IDENTIFIER}:
                continue
            if name is None or _node_kind(name) in {None, _NodeKind.COMPUTED_PROPERTY_NAME}:
                return False
            if _node_kind(child) in {
                _NodeKind.PUBLIC_FIELD_DEFINITION,
                _NodeKind.PROPERTY_SIGNATURE,
            }:
                key = _static_member_name(_text(name))
                if key is None:
                    return False
                if key in attributes:
                    return False
                attributes.add(key)
            if _node_kind(child) in {_NodeKind.METHOD_DEFINITION, _NodeKind.METHOD_SIGNATURE}:
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
                    pattern = _RawNode.child_by_field_name(
                        parameter, "pattern"
                    ) or _RawNode.child_by_field_name(parameter, "name")
                    if pattern is None or _text(pattern) in attributes:
                        return False
                    attributes.add(_text(pattern))
    return True


def _decorated_member(node: _RawNode) -> _RawNode | None:
    """A body-level decorator belongs only to the next supported lexical member."""
    candidate = node.next_named_sibling
    while candidate is not None and _node_kind(candidate) in {
        _NodeKind.DECORATOR,
        _NodeKind.COMMENT,
    }:
        candidate = candidate.next_named_sibling
    if (
        candidate is None
        or candidate.has_error
        or _node_kind(candidate)
        not in {
            _NodeKind.METHOD_DEFINITION,
            _NodeKind.METHOD_SIGNATURE,
            _NodeKind.PUBLIC_FIELD_DEFINITION,
        }
    ):
        return None
    name = _RawNode.child_by_field_name(candidate, "name")
    return (
        candidate
        if name is not None
        and _node_kind(name) != _NodeKind.COMPUTED_PROPERTY_NAME
        and _valid_unicode_member_name(name)
        and not _instance_constructor(candidate)
        else None
    )


def _valid_unicode_member_name(name: _RawNode) -> bool:
    """String names allow code points that unvalidated escaped identifiers cannot prove."""
    if _node_kind(name) is None:
        return False
    if _node_kind(name) != _NodeKind.STRING:
        return re.search(r"\\", _text(name)) is None
    for child in name.named_children:
        if _node_kind(child) != _NodeKind.ESCAPE_SEQUENCE:
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


def _instance_constructor(node: _RawNode) -> bool:
    """Recognize the restricted instance constructor name without rewriting source names."""
    name = _RawNode.child_by_field_name(node, "name")
    if (
        _node_kind(node) not in {_NodeKind.METHOD_DEFINITION, _NodeKind.METHOD_SIGNATURE}
        or not _class_member(node)
        or node.parent is None
        or _node_kind(node.parent) != _NodeKind.CLASS_BODY
        or _Modifier.STATIC in _modifiers(node)
        or name is None
        or _node_kind(name) is None
    ):
        return False
    spelling = _text(name)
    if _node_kind(name) == _NodeKind.STRING:
        spelling = spelling[1:-1]
    spelling = re.sub(
        r"\\(?:u(?:\{(0*[0-9a-fA-F]{1,6})\}|([0-9a-fA-F]{4}))|x([0-9a-fA-F]{2})|(\r\n|[\s\S]))",
        _constructor_escape,
        spelling,
    )
    return _special_name(spelling) is _SpecialName.CONSTRUCTOR


def _decorators(node: _RawNode) -> tuple[_RawNode, ...]:
    """Read attached decorators and the class body's contiguous sibling decorators."""
    attached = tuple(
        child for child in node.named_children if _node_kind(child) == _NodeKind.DECORATOR
    )
    parent = node.parent
    if parent is not None and _node_kind(parent) == _NodeKind.EXPORT_STATEMENT:
        attached = (
            tuple(
                child for child in parent.named_children if _node_kind(child) == _NodeKind.DECORATOR
            )
            + attached
        )
    if not _class_member(node):
        return attached
    previous = node.prev_named_sibling
    preceding = []
    while previous is not None and _node_kind(previous) in {_NodeKind.DECORATOR, _NodeKind.COMMENT}:
        if _node_kind(previous) == _NodeKind.DECORATOR and _decorated_member(previous) == node:
            preceding.append(previous)
        previous = previous.prev_named_sibling
    return (*reversed(preceding), *attached)


def _class_member(node: _RawNode) -> bool:
    parent = node.parent
    if parent is None or _node_kind(parent) not in {_NodeKind.CLASS_BODY, _NodeKind.INTERFACE_BODY}:
        return False
    owner = parent.parent
    return owner is not None and _node_kind(owner) in {
        _NodeKind.CLASS_DECLARATION,
        _NodeKind.INTERFACE_DECLARATION,
    }


def _member(node: _RawNode, source: _Source) -> Member | None:
    name_node = (
        node.child_by_field_name("name")
        or _RawNode.child_by_field_name(node, "pattern")
        or (
            node
            if _node_kind(node) in {_NodeKind.PROPERTY_IDENTIFIER, _NodeKind.IDENTIFIER}
            else None
        )
    )
    if name_node is None or _node_kind(name_node) in {None, _NodeKind.COMPUTED_PROPERTY_NAME}:
        return None
    value = node.child_by_field_name("value")
    literal = (
        _text(value)
        if value is not None
        and _node_kind(value)
        in {_NodeKind.STRING, _NodeKind.NUMBER, _NodeKind.TRUE, _NodeKind.FALSE, _NodeKind.NULL}
        else None
    )
    return Member(
        _text(name_node),
        source.span(name_node),
        _type(node.child_by_field_name("type")),
        _visibility(node),
        _Modifier.STATIC in _modifiers(node)
        or _node_kind(node)
        in {_NodeKind.ENUM_ASSIGNMENT, _NodeKind.PROPERTY_IDENTIFIER, _NodeKind.IDENTIFIER},
        literal,
        tuple((_text(item), source.span(item)) for item in _decorators(node)),
    )


def _signature_complete(node: _RawNode) -> bool:
    parameters = node.child_by_field_name("parameters")
    return parameters is None or all(
        _node_kind(item) == _NodeKind.REQUIRED_PARAMETER
        and (pattern := item.child_by_field_name("pattern") or item.child_by_field_name("name"))
        is not None
        and _node_kind(pattern) == _NodeKind.IDENTIFIER
        and item.child_by_field_name("value") is None
        and not any(_node_kind(child) is _NodeKind.QUESTION for child in item.children)
        for item in parameters.named_children
    )


def _exported(node: _RawNode) -> bool:
    parent = node.parent
    return parent is not None and _node_kind(parent) == _NodeKind.EXPORT_STATEMENT


def _module_array_constant(node: _RawNode, value: _RawNode) -> bool:
    """Recognize a direct module declaration, without evaluating its array elements."""
    declaration = node.parent
    statement = declaration.parent if declaration is not None else None
    if (
        _in_error(node)
        or statement is None
        or not (
            _node_kind(statement) == _NodeKind.PROGRAM
            or (
                _node_kind(statement) == _NodeKind.EXPORT_STATEMENT
                and statement.parent is not None
                and _node_kind(statement.parent) == _NodeKind.PROGRAM
            )
        )
    ):
        return False
    if _node_kind(value) == _NodeKind.AS_EXPRESSION:
        parts = [item for item in value.children if _node_kind(item) != _NodeKind.COMMENT]
        if (
            len(parts) != 3
            or _node_kind(parts[1]) != _NodeKind.AS
            or _node_kind(parts[2]) != _NodeKind.CONST
        ):
            return False
        value = parts[0]
    return _node_kind(value) == _NodeKind.ARRAY and all(
        _node_kind(item)
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


def _module_var_array_peer(node: _RawNode) -> tuple[str | None, bool]:
    """A block/control-flow var still competes with a module array declaration."""
    parent = node.parent
    variable = (
        _node_kind(node) == _NodeKind.VARIABLE_DECLARATOR
        and parent is not None
        and _node_kind(parent) == _NodeKind.VARIABLE_DECLARATION
    )
    loop = _node_kind(node) == _NodeKind.FOR_IN_STATEMENT and any(
        _node_kind(child) == _NodeKind.VAR for child in node.children
    )
    if not (variable or loop) or any(
        _node_kind(ancestor)
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
    if binding is None or _node_kind(binding) != _NodeKind.IDENTIFIER:
        return None, True
    name = _text(binding)
    return (name, False) if name and re.search(r"\\", name) is None else (None, True)


def _uncollected_module_binding(node: _RawNode) -> tuple[str | None, bool]:
    """Veto new array identities beside unsupported module binding syntax."""
    peer_name, opaque = _module_var_array_peer(node)
    if peer_name is not None or opaque:
        return peer_name, opaque
    variable = _node_kind(node) == _NodeKind.VARIABLE_DECLARATOR
    defined = _node_kind(node) in {
        _NodeKind.CLASS_DECLARATION,
        _NodeKind.FUNCTION_DECLARATION,
        _NodeKind.FUNCTION_SIGNATURE,
        _NodeKind.ENUM_DECLARATION,
    }
    if (
        not defined
        and not variable
        and _node_kind(node)
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
    declaration = scope if _node_kind(node) == _NodeKind.IMPORT_REQUIRE_CLAUSE else node
    if variable:
        scope = scope.parent if scope is not None else None
        if scope is None or _node_kind(scope) != _NodeKind.AMBIENT_DECLARATION:
            return None, False
    if _node_kind(node) == _NodeKind.IMPORT_REQUIRE_CLAUSE:
        scope = scope.parent if scope is not None else None
    while scope is not None and _node_kind(scope) in {
        _NodeKind.EXPORT_STATEMENT,
        _NodeKind.AMBIENT_DECLARATION,
        _NodeKind.EXPRESSION_STATEMENT,
    }:
        scope = scope.parent
    if (
        scope is None
        or _node_kind(scope) != _NodeKind.PROGRAM
        or declaration is None
        or any(_node_kind(child) == _NodeKind.TYPE for child in declaration.children)
    ):
        return None, False
    if defined:
        return None, any(
            _node_kind(child) in {_NodeKind.IDENTIFIER, _NodeKind.TYPE_IDENTIFIER}
            and re.search(r"\\", _text(child)) is not None
            for child in node.named_children
        )
    binding = next(iter(node.named_children), None)
    if binding is None or _node_kind(binding) not in {
        _NodeKind.IDENTIFIER,
        _NodeKind.TYPE_IDENTIFIER,
    }:
        return None, True
    name = _text(binding)
    return (name, False) if name and re.search(r"\\", name) is None else (None, True)


def _constant_definition(
    node: _RawNode,
    name: str,
    source: _Source,
    scopes: list[tuple[_RawNode, str, int]],
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
    source: _Source,
    scopes: list[tuple[_RawNode, str, int]],
    declarations: dict[_RawNode, DefinitionKind],
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
        if _node_kind(node) != _NodeKind.VARIABLE_DECLARATOR:
            continue
        name_node = node.child_by_field_name("name")
        value = node.child_by_field_name("value")
        parent = node.parent
        declaration_parent = parent.parent if parent is not None else None
        module_level = declaration_parent is not None and (
            _node_kind(declaration_parent) == _NodeKind.PROGRAM
            or (
                _node_kind(declaration_parent) == _NodeKind.EXPORT_STATEMENT
                and declaration_parent.parent is not None
                and _node_kind(declaration_parent.parent) == _NodeKind.PROGRAM
            )
        )
        if name_node is None or _node_kind(name_node) != _NodeKind.IDENTIFIER:
            opaque_module_binding |= module_level
            continue
        name = _text(name_node)
        opaque_module_binding |= module_level and (not name or re.search(r"\\", name) is not None)
        declaration = (
            parent
            if parent is not None and _node_kind(parent) == _NodeKind.LEXICAL_DECLARATION
            else None
        )
        kind_node = declaration.child_by_field_name("kind") if declaration else None
        is_array = value is not None and _module_array_constant(node, value)
        plain = value is not None and (
            _node_kind(value)
            in {
                _NodeKind.IDENTIFIER,
                _NodeKind.STRING,
                _NodeKind.NUMBER,
                _NodeKind.TRUE,
                _NodeKind.FALSE,
                _NodeKind.NULL,
            }
        )
        if (
            kind_node is None
            or _node_kind(kind_node) is not _NodeKind.CONST
            or not (plain or is_array)
        ):
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


def _call_site(
    node: _RawNode,
    source: _Source,
    scopes: list[tuple[_RawNode, str, int]],
    bindings: dict[_RawNode, dict[str, int]],
    ambiguous_bindings: set[_RawNode],
) -> Site | None:
    target = node.child_by_field_name("function") or node.child_by_field_name("constructor")
    if target is None:
        return None
    scope = next((item for item, _, _ in reversed(scopes) if _contains(item, node)), None)
    scope_name = next((name for item, name, _ in scopes if item is scope), None)
    scope_line = next((line for item, _, line in scopes if item is scope), None)
    receiver = _dependency_receiver(target)
    assigned = _assigned_name(node)
    target_name = _target_name(target)
    shadowed, ambiguous_scope = _active_scope_names(node, scope, source)
    return Site(
        SiteKind.NEW if _node_kind(node) is _NodeKind.NEW_EXPRESSION else SiteKind.CALL,
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
        _text(node) if _node_kind(node) == _NodeKind.NEW_EXPRESSION else None,
        receiver_kind=target_name.receiver_kind,
        scope_ambiguous=ambiguous_scope,
        scope_column=source.span(scope).column if scope is not None else None,
        path=_static_path(target) or _static_path(receiver),
        script_free=_script_free(receiver, node, bindings, ambiguous_bindings),
    )


def _comparison_literal(node: _RawNode) -> _RawNode | None:
    """Read written equality/case syntax, without evaluating names or method semantics."""
    kind = _node_kind(node)
    if kind is _NodeKind.SWITCH_CASE:
        return _written_string(_RawNode.child_by_field_name(node, "value"))
    if kind is not _NodeKind.BINARY_EXPRESSION:
        return None
    operator = _RawNode.child_by_field_name(node, "operator")
    if operator is None or _node_kind(operator) not in {
        _NodeKind.EQUAL,
        _NodeKind.NOT_EQUAL,
        _NodeKind.STRICT_EQUAL,
        _NodeKind.STRICT_NOT_EQUAL,
    }:
        return None
    return _written_string(_RawNode.child_by_field_name(node, "left")) or _written_string(
        _RawNode.child_by_field_name(node, "right")
    )


def _written_string(node: _RawNode | None) -> _RawNode | None:
    """Keep original literal evidence through known value-preserving expression wrappers."""
    while node is not None and _node_kind(node) in {
        _NodeKind.PARENTHESIZED_EXPRESSION,
        _NodeKind.AS_EXPRESSION,
        _NodeKind.SATISFIES_EXPRESSION,
        _NodeKind.NON_NULL_EXPRESSION,
    }:
        if _in_error(node):
            return None
        children = [
            item for item in node.named_children if _node_kind(item) is not _NodeKind.COMMENT
        ]
        # as const has no named type child; other as/satisfies forms carry a type.
        # Only the first expression child can supply a value, never the type syntax.
        kind = _node_kind(node)
        expected = (
            (1, 2)
            if kind is _NodeKind.AS_EXPRESSION
            else ((2,) if kind is _NodeKind.SATISFIES_EXPRESSION else (1,))
        )
        node = children[0] if len(children) in expected else None
    if node is None:
        return None
    kind = _node_kind(node)
    if kind not in {_NodeKind.STRING, _NodeKind.TEMPLATE_STRING} or _in_error(node):
        return None
    if kind is _NodeKind.STRING:
        return node
    if all(
        _node_kind(child) in {_NodeKind.STRING_FRAGMENT, _NodeKind.ESCAPE_SEQUENCE}
        for child in node.named_children
    ):
        return node
    return None


def _sites(
    source: _Source,
    scopes: list[tuple[_RawNode, str, int]],
    declarations: dict[_RawNode, DefinitionKind],
    bindings: dict[_RawNode, dict[str, int]],
    ambiguous_bindings: set[_RawNode],
) -> tuple[list[Site], list[StringComparison]]:
    sites: list[Site] = []
    comparisons: list[StringComparison] = []
    for node in _walk(source.root):
        if source.root.has_error and _in_error(node):
            continue
        literal = _comparison_literal(node)
        if literal is not None:
            scope_name = next(
                (name for scope, name, _ in reversed(scopes) if _contains(scope, node)), None
            )
            comparisons.append(StringComparison(source.span(literal), scope_name))
        if _node_kind(node) in (_NodeKind.CALL_EXPRESSION, _NodeKind.NEW_EXPRESSION):
            site = _call_site(node, source, scopes, bindings, ambiguous_bindings)
            if site is not None:
                sites.append(site)
        if _node_kind(node) not in (
            _NodeKind.IDENTIFIER,
            _NodeKind.TYPE_IDENTIFIER,
            _NodeKind.PROPERTY_IDENTIFIER,
        ) and not (
            source.script_mode and _node_kind(node) is _NodeKind.SHORTHAND_PROPERTY_IDENTIFIER
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
            and _node_kind(node.parent) == _NodeKind.MEMBER_EXPRESSION
            and node.parent.child_by_field_name("property") == node
            else _TargetName(_text(node), None, False)
        )
        shadowed, ambiguous_scope = _active_scope_names(node, scope, source)
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
                computed=target_name.computed or _subscript_receiver(node),
                receiver_kind=target_name.receiver_kind,
                shadowed_names=shadowed,
                use=SiteUse.TYPE
                if _node_kind(node) is _NodeKind.TYPE_IDENTIFIER
                else SiteUse.MEMBER
                if target_name.receiver
                else SiteUse.VALUE,
                scope_ambiguous=ambiguous_scope,
                scope_column=source.span(scope).column if scope is not None else None,
                path=_static_path(node.parent)
                if target_name.receiver and node.parent is not None
                else _static_path(node),
                script_free=not _global_publication_target(node)
                and _script_free(
                    node.parent if target_name.receiver and node.parent is not None else node,
                    node,
                    bindings,
                    ambiguous_bindings,
                ),
                script_escape=_script_escape(node),
            )
        )
    return sites, comparisons


def _subscript_receiver(node: _RawNode) -> bool:
    return (
        node.parent is not None
        and _node_kind(node.parent) is _NodeKind.SUBSCRIPT_EXPRESSION
        and node.parent.child_by_field_name("object") == node
    )


def _global_publication_target(node: _RawNode) -> bool:
    return any(
        _node_kind(parent) is _NodeKind.ASSIGNMENT_EXPRESSION
        and (left := parent.child_by_field_name("left")) is not None
        and len(path := _static_path(left)) == 2
        and path[0] in _SCRIPT_ROOTS
        and _contains(left, node)
        for parent in _ancestors(node)
    )


def _declaration_name(node: _RawNode) -> bool:
    parent = node.parent
    return parent is not None and (
        any(parent.child_by_field_name(field) == node for field in ("name", "pattern", "alias"))
        or _node_kind(parent) is _NodeKind.NAMESPACE_EXPORT
        or _node_kind(parent) is _NodeKind.PAIR_PATTERN
        and parent.child_by_field_name("key") == node
    )


@dataclass(frozen=True, slots=True)
class _TargetName:
    name: str | None
    receiver: str | None
    computed: bool
    receiver_kind: ReceiverKind = ReceiverKind.NONE


def _target_name(node: _RawNode) -> _TargetName:
    if _node_kind(node) in (_NodeKind.IDENTIFIER, _NodeKind.TYPE_IDENTIFIER):
        return _TargetName(_text(node), None, False)
    if _node_kind(node) is _NodeKind.MEMBER_EXPRESSION:
        receiver = node.child_by_field_name("object")
        name = node.child_by_field_name("property")
        return _TargetName(
            _text(name)
            if name is not None and _node_kind(name) is _NodeKind.PROPERTY_IDENTIFIER
            else None,
            _text(receiver) if receiver is not None else None,
            name is None or _node_kind(name) is not _NodeKind.PROPERTY_IDENTIFIER,
            ReceiverKind.THIS
            if receiver is not None and _node_kind(receiver) is _NodeKind.THIS
            else ReceiverKind.OTHER
            if receiver is not None
            else ReceiverKind.NONE,
        )
    return _TargetName(None, None, True)


def _dependency_receiver(node: _RawNode) -> _RawNode:
    while not _static_path(node):
        child = (
            next(iter(node.named_children), None)
            if _node_kind(node) is _NodeKind.PARENTHESIZED_EXPRESSION
            else node.child_by_field_name("object")
            if _node_kind(node) in {_NodeKind.MEMBER_EXPRESSION, _NodeKind.SUBSCRIPT_EXPRESSION}
            else None
        )
        if child is None:
            break
        node = child
    return node


def _static_path(node: _RawNode) -> tuple[str, ...]:
    if _node_kind(node) in {
        _NodeKind.IDENTIFIER,
        _NodeKind.PROPERTY_IDENTIFIER,
        _NodeKind.SHORTHAND_PROPERTY_IDENTIFIER,
        _NodeKind.SHORTHAND_PROPERTY_IDENTIFIER_PATTERN,
    }:
        return (_text(node),)
    if _node_kind(node) is _NodeKind.MEMBER_EXPRESSION:
        receiver = node.child_by_field_name("object")
        name = node.child_by_field_name("property")
        if (
            receiver is not None
            and name is not None
            and _node_kind(name) is _NodeKind.PROPERTY_IDENTIFIER
        ):
            path = _static_path(receiver)
            return (*path, _text(name)) if path else ()
    return ()


# The grammar nests `A.B.C` as a nested_identifier that holds a member_expression.
_QUALIFIED_NAMES: Final = frozenset({_NodeKind.NESTED_IDENTIFIER, _NodeKind.MEMBER_EXPRESSION})
_AMBIENT_VALUE_KINDS: Final = frozenset(
    {
        _NodeKind.LEXICAL_DECLARATION,
        _NodeKind.VARIABLE_DECLARATION,
        _NodeKind.FUNCTION_SIGNATURE,
        _NodeKind.CLASS_DECLARATION,
        _NodeKind.ABSTRACT_CLASS_DECLARATION,
        _NodeKind.ENUM_DECLARATION,
        _NodeKind.INTERNAL_MODULE,
        _NodeKind.MODULE,
    }
)


def _declared_names(source: _Source, declaration: _RawNode) -> list[tuple[str, Span]]:
    # In `declare global { }` a namespace parses as an expression statement; `export` wraps.
    while _node_kind(declaration) in {_NodeKind.EXPRESSION_STATEMENT, _NodeKind.EXPORT_STATEMENT}:
        if not declaration.named_children:
            return []
        declaration = declaration.named_children[0]
    if _node_kind(declaration) not in _AMBIENT_VALUE_KINDS:
        return []
    if _node_kind(declaration) in {_NodeKind.LEXICAL_DECLARATION, _NodeKind.VARIABLE_DECLARATION}:
        names = [item.child_by_field_name("name") for item in declaration.named_children]
    else:
        names = [declaration.child_by_field_name("name")]
    found: list[tuple[str, Span]] = []
    for name in names:
        # `namespace A.B.C` publishes `A`; `module "x"` names no global.
        while name is not None and _node_kind(name) in _QUALIFIED_NAMES:
            name = name.named_children[0]
        if name is not None and _node_kind(name) in {
            _NodeKind.IDENTIFIER,
            _NodeKind.TYPE_IDENTIFIER,
        }:
            found.append((_text(name), source.span(name)))
    return found


def _ambient_scope(
    source: _Source, suffix: FileSuffix | None
) -> tuple[tuple[tuple[str, Span], ...], tuple[tuple[str, Span], ...], bool, bool]:
    """The ambient names of a file, and whether it is a module or a declaration file (AD-274)."""
    declaration_file = suffix is not None and suffix.source_kind is SourceKind.DECLARATION
    # A module extension makes a source file a module; a declaration file stays a script (tsc).
    module_file = _module_exports(source.root)[0] or (
        suffix is not None and suffix.format_hint is not None and not declaration_file
    )
    return (*_ambient_globals(source), module_file, declaration_file)


def _ambient_globals(
    source: _Source,
) -> tuple[tuple[tuple[str, Span], ...], tuple[tuple[str, Span], ...]]:
    """Value names that `declare` adds to the global scope, from `declare global` and top level.

    A `declare global` block is global in every file. A top-level `declare` is global only when
    the file is a global script, which the collector decides from the compiler options (AD-274).
    """
    module_syntax = _module_exports(source.root)[0]
    block: list[tuple[str, Span]] = []
    top_level: list[tuple[str, Span]] = []
    for statement in source.root.named_children:
        if (
            _node_kind(statement) is not _NodeKind.AMBIENT_DECLARATION
            or not statement.named_children
        ):
            continue
        inner = statement.named_children[0]
        if _node_kind(inner) is _NodeKind.STATEMENT_BLOCK:
            for declaration in inner.named_children:
                block.extend(_declared_names(source, declaration))
        elif not module_syntax:
            top_level.extend(_declared_names(source, inner))
    return tuple(block), tuple(top_level)


def _script_bindings(
    source: _Source, nodes: Iterable[_RawNode] | None = None
) -> tuple[dict[_RawNode, dict[str, int]], set[_RawNode]]:
    bindings: dict[_RawNode, dict[str, int]] = {}
    ambiguous: set[_RawNode] = set()
    patterns: list[tuple[_RawNode, _RawNode]] = []
    for node in _walk(source.root) if nodes is None else nodes:
        kind = _node_kind(node)
        if kind is _NodeKind.WITH_STATEMENT:
            ambiguous.add(node)
        if kind in _SCRIPT_FUNCTIONS:
            parameters = node.child_by_field_name("parameters")
            parameter = node.child_by_field_name("parameter")
            if parameters is not None:
                patterns.extend((node, item) for item in parameters.named_children)
            if parameter is not None:
                patterns.append((node, parameter))
        if kind is _NodeKind.CATCH_CLAUSE:
            parameter = node.child_by_field_name("parameter")
            if parameter is not None:
                patterns.append((node, parameter))
        if kind is _NodeKind.FOR_IN_STATEMENT:
            declaration = node.child_by_field_name("kind")
            left = node.child_by_field_name("left")
            if declaration is not None and left is not None:
                scope = (
                    next(
                        (
                            parent
                            for parent in _ancestors(node)
                            if _node_kind(parent) in _SCRIPT_VAR_SCOPES
                        ),
                        source.root,
                    )
                    if _node_kind(declaration) is _NodeKind.VAR
                    else node
                )
                patterns.append((scope, left))
        if kind in {_NodeKind.FUNCTION_EXPRESSION, _NodeKind.GENERATOR_FUNCTION, _NodeKind.CLASS}:
            name = node.child_by_field_name("name")
            if name is not None:
                patterns.append((node, name))
        if kind in {
            _NodeKind.VARIABLE_DECLARATOR,
            _NodeKind.FUNCTION_DECLARATION,
            _NodeKind.GENERATOR_FUNCTION_DECLARATION,
            _NodeKind.CLASS_DECLARATION,
        }:
            patterns.extend(_script_declaration_bindings(node, source.root, ambiguous))
    for scope, pattern in set(patterns):
        scope_bindings: dict[str, int] = bindings.setdefault(scope, {})
        for target in _assignment_targets(pattern):
            if _node_kind(target) in {
                _NodeKind.IDENTIFIER,
                _NodeKind.TYPE_IDENTIFIER,
                _NodeKind.SHORTHAND_PROPERTY_IDENTIFIER_PATTERN,
            } and _valid_unicode_member_name(target):
                bound_name = _text(target)
                scope_bindings[bound_name] = scope_bindings.get(bound_name, 0) + 1
            else:
                ambiguous.add(scope)
    module_bindings: dict[str, int] = bindings.setdefault(source.root, {})
    for item in _import_bindings(source):
        module_bindings[item.local] = module_bindings.get(item.local, 0) + 1
    return bindings, ambiguous


def _script_declaration_bindings(
    node: _RawNode, root: _RawNode, ambiguous: set[_RawNode]
) -> Iterator[tuple[_RawNode, _RawNode]]:
    kind = _node_kind(node)
    name = node.child_by_field_name("name")
    if name is None:
        ambiguous.add(root)
        return
    function_scoped = (
        kind is _NodeKind.VARIABLE_DECLARATOR
        and node.parent is not None
        and _node_kind(node.parent) is _NodeKind.VARIABLE_DECLARATION
    )
    scope_kinds = _SCRIPT_VAR_SCOPES if function_scoped else _SCRIPT_SCOPES
    scope = next(
        (parent for parent in _ancestors(node) if _node_kind(parent) in scope_kinds),
        root,
    )
    yield scope, name
    # Sloppy-script block functions can also bind in their enclosing var scope.
    if kind is _NodeKind.FUNCTION_DECLARATION:
        var_scope = next(
            (parent for parent in _ancestors(node) if _node_kind(parent) in _SCRIPT_VAR_SCOPES),
            root,
        )
        yield var_scope, name


def _script_free(
    target: _RawNode,
    node: _RawNode,
    bindings: dict[_RawNode, dict[str, int]],
    ambiguous_bindings: set[_RawNode],
) -> bool:
    if _in_type(node):
        return False
    path = _static_path(target)
    parent = target.parent
    if (
        parent is not None
        and _node_kind(parent) is _NodeKind.PAIR
        and parent.child_by_field_name("key") == target
    ):
        return False
    return bool(path) and not any(
        parent in ambiguous_bindings or path[0] in bindings.get(parent, ())
        for parent in _ancestors(node)
    )


def _script_bound_scope(
    node: _RawNode, name: str, bindings: dict[_RawNode, dict[str, int]]
) -> _RawNode | None:
    return next((parent for parent in _ancestors(node) if name in bindings.get(parent, ())), None)


def _script_destructures(
    source: _Source,
    bindings: dict[_RawNode, dict[str, int]],
    ambiguous: set[_RawNode],
) -> tuple[ScriptDestructure, ...]:
    result: list[ScriptDestructure] = []
    for node in _walk(source.root):
        if _node_kind(node) is not _NodeKind.VARIABLE_DECLARATOR:
            continue
        name, value = node.child_by_field_name("name"), node.child_by_field_name("value")
        kind = node.parent.child_by_field_name("kind") if node.parent is not None else None
        if (
            name is None
            or _node_kind(name) is not _NodeKind.OBJECT_PATTERN
            or value is None
            or _node_kind(value) is not _NodeKind.MEMBER_EXPRESSION
            or kind is None
            or _node_kind(kind) is not _NodeKind.CONST
        ):
            continue
        path = _static_path(value)
        property_name = value.child_by_field_name("property")
        if (
            len(path) != 2
            or path[0] not in _SCRIPT_ROOTS
            or property_name is None
            or not _script_free(value, node, bindings, ambiguous)
        ):
            continue
        members = []
        for pair in name.named_children:
            key = pair.child_by_field_name("key")
            local = pair.child_by_field_name("value")
            if _node_kind(pair) is _NodeKind.SHORTHAND_PROPERTY_IDENTIFIER_PATTERN:
                key = local = pair
            if (
                key is None
                or local is None
                or _node_kind(local)
                not in {_NodeKind.IDENTIFIER, _NodeKind.SHORTHAND_PROPERTY_IDENTIFIER_PATTERN}
                or not _valid_unicode_member_name(key)
                or not _valid_unicode_member_name(local)
            ):
                break
            scope = _script_bound_scope(node, _text(local), bindings)
            if scope is None or bindings[scope][_text(local)] != 1:
                break
            members.append((_text(key), _text(local), source.span(key)))
        else:
            if members:
                result.append(ScriptDestructure(source.span(property_name), path, tuple(members)))
    return tuple(result)


def _script_aliases(
    source: _Source,
    bindings: dict[_RawNode, dict[str, int]],
    ambiguous_bindings: set[_RawNode],
) -> tuple[ScriptAlias, ...]:
    aliases: list[ScriptAlias] = []
    for node in _walk(source.root):
        if _node_kind(node) is not _NodeKind.VARIABLE_DECLARATOR or _in_error(node):
            continue
        declaration = node.parent
        name = node.child_by_field_name("name")
        value = node.child_by_field_name("value")
        kind = declaration.child_by_field_name("kind") if declaration is not None else None
        if (
            declaration is None
            or _node_kind(declaration) is not _NodeKind.LEXICAL_DECLARATION
            or kind is None
            or _node_kind(kind) is not _NodeKind.CONST
            or name is None
            or _node_kind(name) is not _NodeKind.IDENTIFIER
            or not _valid_unicode_member_name(name)
            or value is None
            or _node_kind(value) not in {_NodeKind.MEMBER_EXPRESSION, _NodeKind.CALL_EXPRESSION}
        ):
            continue
        factory = _node_kind(value) is _NodeKind.CALL_EXPRESSION
        target = value.child_by_field_name("function") if factory else value
        if target is None:
            continue
        path = _static_path(target)
        member = target.child_by_field_name("property")
        scope = _script_bound_scope(node, _text(name), bindings)
        if (
            (len(path) not in {2, 3} if factory else len(path) != 2 or path[0] not in _SCRIPT_ROOTS)
            or member is None
            or not _valid_unicode_member_name(member)
            or scope is None
            or bindings[scope][_text(name)] != 1
            or not _script_free(target, node, bindings, ambiguous_bindings)
            or any(
                _node_kind(child) is _NodeKind.OPTIONAL_CHAIN
                for child in (*target.children, *value.children)
            )
        ):
            continue
        if factory:
            uses = _script_factory_uses(source, scope, name, bindings, ambiguous_bindings)
            if uses is not None:
                aliases.append(
                    ScriptAlias(
                        _text(name),
                        source.span(node),
                        source.span(value),
                        path,
                        uses[0],
                        True,
                        uses[1],
                        uses[2],
                    )
                )
            else:
                aliases.append(
                    ScriptAlias(
                        _text(name),
                        source.span(node),
                        source.span(value),
                        path,
                        (),
                        factory=True,
                        complete=False,
                    )
                )
            continue
        calls = _script_alias_calls(source, scope, name, bindings, ambiguous_bindings)
        if calls is not None:
            aliases.append(
                ScriptAlias(_text(name), source.span(node), source.span(member), path, calls)
            )
    return tuple(aliases)


def _script_factory_uses(
    source: _Source,
    scope: _RawNode,
    name: _RawNode,
    bindings: dict[_RawNode, dict[str, int]],
    ambiguous_bindings: set[_RawNode],
) -> tuple[tuple[Span, ...], tuple[Span, ...], tuple[tuple[str, ...], ...]] | None:
    calls: list[Span] = []
    reads: list[Span] = []
    escapes: list[tuple[str, ...]] = []
    for reference in _walk(scope):
        if _node_kind(reference) not in {
            _NodeKind.IDENTIFIER,
            _NodeKind.SHORTHAND_PROPERTY_IDENTIFIER,
        }:
            continue
        if reference == name or _text(reference) != _text(name):
            continue
        if _script_bound_scope(reference, _text(name), bindings) != scope:
            continue
        member = reference.parent
        if (
            member is not None
            and _node_kind(member) is _NodeKind.PAIR
            and member.child_by_field_name("value") == reference
        ):
            prefix = _script_factory_publication_escape(source, member)
            if prefix is not None:
                escapes.append(prefix)
                continue
            return None
        property_name = member.child_by_field_name("property") if member is not None else None
        if (
            not _valid_unicode_member_name(reference)
            or member is None
            or _node_kind(member) is not _NodeKind.MEMBER_EXPRESSION
            or member.child_by_field_name("object") != reference
            or len(_static_path(member)) != 2
            or property_name is None
            or not _valid_unicode_member_name(property_name)
            or any(parent in ambiguous_bindings for parent in _ancestors(reference))
            or any(_node_kind(child) is _NodeKind.OPTIONAL_CHAIN for child in member.children)
        ):
            return None
        use = member
        while use.parent is not None and _node_kind(use.parent) is _NodeKind.MEMBER_EXPRESSION:
            use = use.parent
        parent = use.parent
        if parent is not None and use in tuple(_script_assignment_targets(parent)):
            return None
        call = member.parent
        if (
            call is not None
            and _node_kind(call) is _NodeKind.CALL_EXPRESSION
            and call.child_by_field_name("function") == member
        ):
            if any(
                _node_kind(child) is _NodeKind.OPTIONAL_CHAIN_OPERATOR for child in call.children
            ):
                return None
            calls.append(source.span(call))
        else:
            reads.append(source.span(property_name))
    return tuple(calls), tuple(reads), tuple(escapes)


def _script_factory_publication_escape(source: _Source, pair: _RawNode) -> tuple[str, ...] | None:
    obj = pair.parent
    assignment = obj.parent if obj is not None else None
    key = pair.child_by_field_name("key")
    target = assignment.child_by_field_name("left") if assignment is not None else None
    if (
        obj is None
        or _node_kind(obj) is not _NodeKind.OBJECT
        or assignment is None
        or _node_kind(assignment) is not _NodeKind.ASSIGNMENT_EXPRESSION
        or assignment.child_by_field_name("right") != obj
        or key is None
        or _node_kind(key) is not _NodeKind.PROPERTY_IDENTIFIER
        or target is None
    ):
        return None
    path = _static_path(target)
    if len(path) != 2 or path[0] not in _SCRIPT_ROOTS:
        return None
    prefix = (*path[1:], _text(key))
    for node in _walk(source.root):
        for written in _script_assignment_targets(node):
            route = _static_path(written)
            if route and route[0] in _SCRIPT_ROOTS:
                route = route[1:]
            if route[: len(prefix)] == prefix:
                return None
    return prefix


def _script_alias_calls(
    source: _Source,
    scope: _RawNode,
    name: _RawNode,
    bindings: dict[_RawNode, dict[str, int]],
    ambiguous_bindings: set[_RawNode],
) -> tuple[Span, ...] | None:
    calls: list[Span] = []
    for reference in _walk(scope):
        if _node_kind(reference) not in {
            _NodeKind.IDENTIFIER,
            _NodeKind.SHORTHAND_PROPERTY_IDENTIFIER,
        }:
            continue
        if not _valid_unicode_member_name(reference) or _in_error(reference):
            return None
        if reference == name or _text(reference) != _text(name):
            continue
        if _script_bound_scope(reference, _text(name), bindings) != scope:
            continue
        target = reference.parent
        call = target.parent if target is not None else None
        property_name = target.child_by_field_name("property") if target is not None else None
        if (
            target is None
            or _node_kind(target) is not _NodeKind.MEMBER_EXPRESSION
            or target.child_by_field_name("object") != reference
            or len(_static_path(target)) != 2
            or property_name is None
            or not _valid_unicode_member_name(property_name)
            or call is None
            or _node_kind(call) is not _NodeKind.CALL_EXPRESSION
            or call.child_by_field_name("function") != target
            or any(parent in ambiguous_bindings for parent in _ancestors(reference))
            or any(
                _node_kind(child) in {_NodeKind.OPTIONAL_CHAIN, _NodeKind.OPTIONAL_CHAIN_OPERATOR}
                for child in (*target.children, *call.children)
            )
        ):
            return None
        calls.append(source.span(call))
    return tuple(calls)


def _assignment_targets(node: _RawNode) -> Iterator[_RawNode]:
    kind = _node_kind(node)
    if kind in {_NodeKind.ARRAY_PATTERN, _NodeKind.OBJECT_PATTERN}:
        for child in node.named_children:
            yield from _assignment_targets(child)
    elif kind in {
        _NodeKind.ASSIGNMENT_PATTERN,
        _NodeKind.OBJECT_ASSIGNMENT_PATTERN,
        _NodeKind.PAIR_PATTERN,
        _NodeKind.REQUIRED_PARAMETER,
        _NodeKind.OPTIONAL_PARAMETER,
    }:
        field = (
            "value"
            if kind is _NodeKind.PAIR_PATTERN
            else "pattern"
            if kind in {_NodeKind.REQUIRED_PARAMETER, _NodeKind.OPTIONAL_PARAMETER}
            else "left"
        )
        target = node.child_by_field_name(field)
        if target is not None:
            yield from _assignment_targets(target)
        else:
            yield node
    elif (
        kind in {_NodeKind.REST_PATTERN, _NodeKind.PARENTHESIZED_EXPRESSION}
        and len(node.named_children) == 1
    ):
        yield from _assignment_targets(node.named_children[0])
    elif kind is not _NodeKind.COMMENT:
        yield node


def _script_escape(node: _RawNode) -> bool:
    target = (
        node.parent
        if node.parent is not None
        and _node_kind(node.parent) is _NodeKind.MEMBER_EXPRESSION
        and node.parent.child_by_field_name("property") == node
        else node
    )
    parent = target.parent
    if parent is None:
        return True
    if _node_kind(parent) is _NodeKind.PAIR and parent.child_by_field_name("key") == target:
        return False
    if _node_kind(parent) is _NodeKind.ARGUMENTS and parent.parent is not None:
        callee = parent.parent.child_by_field_name("function")
        while callee is not None and _node_kind(callee) is _NodeKind.PARENTHESIZED_EXPRESSION:
            callee = next(iter(callee.named_children), None)
        if callee is not None and _script_wrapper(callee) is not None:
            return False
    if (
        _node_kind(parent) in {_NodeKind.MEMBER_EXPRESSION, _NodeKind.SUBSCRIPT_EXPRESSION}
        and parent.child_by_field_name("object") == target
        or _node_kind(parent) is _NodeKind.UNARY_EXPRESSION
        and any(_node_kind(child) is _NodeKind.TYPEOF for child in parent.children)
    ):
        return False
    return not (
        _node_kind(parent)
        in {_NodeKind.ASSIGNMENT_EXPRESSION, _NodeKind.AUGMENTED_ASSIGNMENT_EXPRESSION}
        and parent.child_by_field_name("left") == target
        or _node_kind(parent) is _NodeKind.UPDATE_EXPRESSION
        or _node_kind(parent) is _NodeKind.UNARY_EXPRESSION
        and any(_node_kind(child) is _NodeKind.DELETE for child in parent.children)
    )


def _script_callable_bindings(
    source: _Source, bindings: dict[_RawNode, dict[str, int]]
) -> set[tuple[_RawNode, str]]:
    result: set[tuple[_RawNode, str]] = set()
    for node in _walk(source.root):
        kind = _node_kind(node)
        name = node.child_by_field_name("name")
        value = node.child_by_field_name("value")
        while value is not None and _node_kind(value) is _NodeKind.PARENTHESIZED_EXPRESSION:
            value = next(iter(value.named_children), None)
        if name is None or not (
            kind in _SCRIPT_CALLABLE_VALUES
            or kind is _NodeKind.VARIABLE_DECLARATOR
            and value is not None
            and _node_kind(value) in _SCRIPT_CALLABLE_VALUES
        ):
            continue
        spelling = _text(name)
        scope = (
            node
            if spelling in bindings.get(node, ())
            else _script_bound_scope(node, spelling, bindings)
        )
        if scope is not None:
            result.add((scope, spelling))
    return result


def _script_computed_dispatch(
    node: _RawNode,
    bindings: dict[_RawNode, dict[str, int]],
    callables: set[tuple[_RawNode, str]],
) -> bool:
    index = node.child_by_field_name("index")
    if index is not None and _node_kind(index) in {_NodeKind.STRING, _NodeKind.TEMPLATE_STRING}:
        return True
    receiver = node.child_by_field_name("object")
    while receiver is not None and _node_kind(receiver) is _NodeKind.PARENTHESIZED_EXPRESSION:
        receiver = next(iter(receiver.named_children), None)
    if receiver is not None:
        if _node_kind(receiver) in _SCRIPT_CALLABLE_VALUES:
            return True
        path = _static_path(receiver)
        if path and (_script_bound_scope(node, path[0], bindings), path[0]) in callables:
            return True
    current = node
    while current.parent is not None:
        parent = current.parent
        kind = _node_kind(parent)
        if (
            kind in {_NodeKind.MEMBER_EXPRESSION, _NodeKind.SUBSCRIPT_EXPRESSION}
            and parent.child_by_field_name("object") == current
            or kind is _NodeKind.PARENTHESIZED_EXPRESSION
        ):
            current = parent
            continue
        return kind in {_NodeKind.CALL_EXPRESSION, _NodeKind.NEW_EXPRESSION} and (
            parent.child_by_field_name("function") == current
            or parent.child_by_field_name("constructor") == current
        )
    # Getter effects are outside the declared source-binding contract.
    return False


def _script_wrapper(node: _RawNode) -> tuple[_RawNode, tuple[str, ...]] | None:
    """Only direct, synchronous IIFEs establish a statically executed script scope."""
    if _node_kind(node) not in {_NodeKind.FUNCTION_EXPRESSION, _NodeKind.ARROW_FUNCTION}:
        return None
    if any(_node_kind(child) is _NodeKind.ASYNC for child in node.children):
        return None
    callee = node
    while (
        callee.parent is not None
        and _node_kind(callee.parent) is _NodeKind.PARENTHESIZED_EXPRESSION
    ):
        callee = callee.parent
    call = callee.parent
    if (
        call is None
        or _node_kind(call) is not _NodeKind.CALL_EXPRESSION
        or call.child_by_field_name("function") != callee
    ):
        return None
    statement = call.parent
    if statement is not None and _node_kind(statement) is _NodeKind.VARIABLE_DECLARATOR:
        statement = statement.parent
    if (
        statement is not None
        and _node_kind(statement)
        in {
            _NodeKind.EXPRESSION_STATEMENT,
            _NodeKind.VARIABLE_DECLARATION,
            _NodeKind.LEXICAL_DECLARATION,
        }
        and statement.parent is not None
        and _node_kind(statement.parent) is _NodeKind.PROGRAM
    ):
        parameters = node.child_by_field_name("parameters")
        arguments = call.child_by_field_name("arguments")
        params = tuple(parameters.named_children) if parameters is not None else ()
        args = tuple(arguments.named_children) if arguments is not None else ()
        patterns = tuple(param.child_by_field_name("pattern") for param in params)
        if len(params) == len(args) and all(
            _node_kind(arg) is _NodeKind.IDENTIFIER
            and _text(arg) in _SCRIPT_ROOTS
            and _node_kind(param) is _NodeKind.REQUIRED_PARAMETER
            and pattern is not None
            and _node_kind(pattern) is _NodeKind.IDENTIFIER
            for param, pattern, arg in zip(params, patterns, args, strict=True)
        ):
            return call, tuple(_text(pattern) for pattern in patterns if pattern is not None)
    return None


def _script_intrinsic_effect(node: _RawNode) -> bool:
    kind = _node_kind(node)
    parent = node.parent
    intrinsic = (
        _SPECIAL_NAMES.get(_text(node))
        if kind
        in {
            _NodeKind.IDENTIFIER,
            _NodeKind.PROPERTY_IDENTIFIER,
            _NodeKind.SHORTHAND_PROPERTY_IDENTIFIER,
        }
        and not _declaration_name(node)
        and not (
            parent is not None
            and _node_kind(parent) is _NodeKind.PAIR
            and parent.child_by_field_name("key") == node
        )
        else None
    )
    if intrinsic in _SCRIPT_EFFECT_NAMES:
        target = (
            parent
            if parent is not None
            and _node_kind(parent) is _NodeKind.MEMBER_EXPRESSION
            and parent.child_by_field_name("property") == node
            else node
        )
        call = target.parent
        arguments = (
            call.child_by_field_name("arguments")
            if call is not None
            and _node_kind(call) is _NodeKind.CALL_EXPRESSION
            and call.child_by_field_name("function") == target
            else None
        )
        callback = (
            next(
                (
                    argument
                    for argument in arguments.named_children
                    if _node_kind(argument) is not _NodeKind.COMMENT
                ),
                None,
            )
            if arguments is not None
            else None
        )
        if not (
            intrinsic in {_SpecialName.SET_TIMEOUT, _SpecialName.SET_INTERVAL}
            and callback is not None
            and _node_kind(callback)
            in {
                _NodeKind.FUNCTION_EXPRESSION,
                _NodeKind.GENERATOR_FUNCTION,
                _NodeKind.ARROW_FUNCTION,
            }
        ):
            return True
    return False


def _script_opaque_writes(
    node: _RawNode,
    source: _Source,
    bindings: dict[_RawNode, dict[str, int]],
    ambiguous_bindings: set[_RawNode],
    callables: set[tuple[_RawNode, str]],
) -> Iterator[Span]:
    kind = _node_kind(node)
    if kind in {
        _NodeKind.IDENTIFIER,
        _NodeKind.PROPERTY_IDENTIFIER,
        _NodeKind.SHORTHAND_PROPERTY_IDENTIFIER,
    } and not _valid_unicode_member_name(node):
        yield source.span(node)
    if _script_intrinsic_effect(node):
        yield source.span(node)
    if kind is _NodeKind.SUBSCRIPT_EXPRESSION:
        receiver = node.child_by_field_name("object")
        literal = _literal(node.child_by_field_name("index"))
        indexed_intrinsic = _SPECIAL_NAMES.get(literal) if literal is not None else None
        if (
            indexed_intrinsic in _SCRIPT_EFFECT_NAMES
            or receiver is not None
            and _script_free(receiver, node, bindings, ambiguous_bindings)
            or literal is None
            and _script_computed_dispatch(node, bindings, callables)
        ):
            yield source.span(node)
    if kind is _NodeKind.PAIR_PATTERN:
        key = node.child_by_field_name("key")
        literal_key = _literal(key)
        key_intrinsic = _SPECIAL_NAMES.get(literal_key) if literal_key is not None else None
        if key is not None and (
            _node_kind(key) is _NodeKind.COMPUTED_PROPERTY_NAME
            or _node_kind(key) is _NodeKind.STRING
            and (literal_key is None or key_intrinsic in _SCRIPT_EFFECT_NAMES)
        ):
            yield source.span(node)


def _script_declaration_write(node: _RawNode, source: _Source) -> tuple[str | None, Span] | None:
    kind = _node_kind(node)
    if kind in {
        _NodeKind.VARIABLE_DECLARATOR,
        _NodeKind.FUNCTION_DECLARATION,
        _NodeKind.CLASS_DECLARATION,
    } and not any(
        _node_kind(parent)
        in {
            _NodeKind.FUNCTION_DECLARATION,
            _NodeKind.FUNCTION_EXPRESSION,
            _NodeKind.ARROW_FUNCTION,
            _NodeKind.METHOD_DEFINITION,
        }
        for parent in _ancestors(node)
    ):
        name = node.child_by_field_name("name")
        if name is not None and _node_kind(name) is _NodeKind.IDENTIFIER:
            written = _text(name)
            return None if written in _SCRIPT_ROOTS else written, source.span(node)
    return None


def _script_assignment_targets(node: _RawNode) -> Iterator[_RawNode]:
    kind = _node_kind(node)
    left = (
        node.child_by_field_name("left")
        if kind
        in {
            _NodeKind.ASSIGNMENT_EXPRESSION,
            _NodeKind.AUGMENTED_ASSIGNMENT_EXPRESSION,
            _NodeKind.FOR_IN_STATEMENT,
        }
        else node.child_by_field_name("argument")
        if kind is _NodeKind.UPDATE_EXPRESSION
        or kind is _NodeKind.UNARY_EXPRESSION
        and any(_node_kind(child) is _NodeKind.DELETE for child in node.children)
        else None
    )
    if left is not None:
        yield from _assignment_targets(left)


def _script_assignment_publication(
    node: _RawNode,
    target: _RawNode,
    wrapper: _RawNode | None,
    wrappers: dict[_RawNode, tuple[_RawNode, tuple[str, ...]]],
    source: _Source,
    bindings: dict[_RawNode, dict[str, int]],
    ambiguous_bindings: set[_RawNode],
) -> ScriptGlobal | None:
    kind = _node_kind(node)
    path = _static_path(target)
    left = node.child_by_field_name("left")
    value = node.child_by_field_name("right")
    direct = (
        node.parent is not None
        and node.parent.parent is not None
        and (
            _node_kind(node.parent.parent) is _NodeKind.PROGRAM
            or wrapper is not None
            and node.parent.parent == wrapper.child_by_field_name("body")
        )
    )
    if (
        kind is _NodeKind.ASSIGNMENT_EXPRESSION
        and target == left
        and len(path) == 2
        and value is not None
        and _node_kind(value) is _NodeKind.OBJECT
    ):
        receiver_proven = _script_free(target, node, bindings, ambiguous_bindings)
        if wrapper is not None and path[0] in wrappers[wrapper][1]:
            binding_scopes = tuple(
                parent for parent in _ancestors(node) if path[0] in bindings.get(parent, ())
            )
            arguments = wrappers[wrapper][0].child_by_field_name("arguments")
            receiver_proven |= (
                binding_scopes == (wrapper,)
                and bindings[wrapper][path[0]] == 1
                and not any(parent in ambiguous_bindings for parent in _ancestors(node))
                and arguments is not None
                and all(
                    _script_free(argument, argument, bindings, ambiguous_bindings)
                    for argument in arguments.named_children
                )
            )
        return ScriptGlobal(
            path[1],
            source.span(node),
            _script_members(value, wrapper, source),
            direct and receiver_proven and _script_reaches(node, wrapper),
            source_origin=direct and receiver_proven,
            availability=tuple(source.span(item) for item in _script_prior_returns(node, wrapper)),
        )
    return None


def _script_target_write(
    node: _RawNode, target: _RawNode, aliases: set[str] | frozenset[str], source: _Source
) -> tuple[str | None, Span]:
    path = _static_path(target)
    if path and path[0] in aliases:
        return path[1] if len(path) > 1 else None, source.span(node)
    elif path:
        return path[0], source.span(node)
    elif _node_kind(target) is _NodeKind.SUBSCRIPT_EXPRESSION:
        receiver = target.child_by_field_name("object")
        path = _static_path(receiver) if receiver is not None else ()
        if path:
            return (
                None
                if path[0] in aliases and len(path) == 1
                else path[1]
                if path[0] in aliases
                else path[0],
                source.span(node),
            )
        else:
            return None, source.span(node)
    else:
        return None, source.span(node)


def _script_call_writes(
    node: _RawNode, wrapper_calls: set[_RawNode], source: _Source
) -> Iterator[tuple[str | None, Span]]:
    kind = _node_kind(node)
    if (
        kind is _NodeKind.CALL_EXPRESSION
        and node not in wrapper_calls
        and (arguments := node.child_by_field_name("arguments")) is not None
    ):
        for argument in arguments.named_children:
            path = _static_path(argument)
            if path:
                yield (
                    None
                    if path[0] in _SCRIPT_ROOTS and len(path) == 1
                    else path[1]
                    if path[0] in _SCRIPT_ROOTS
                    else path[0],
                    source.span(argument),
                )


def _script_return_publication(
    node: _RawNode, call: _RawNode, module_syntax: bool, source: _Source
) -> ScriptGlobal | None:
    binding = call.parent
    if (
        binding is None
        or _node_kind(binding) is not _NodeKind.VARIABLE_DECLARATOR
        or module_syntax
        or binding.parent is None
        or _node_kind(binding.parent) is not _NodeKind.VARIABLE_DECLARATION
    ):
        return None
    name = binding.child_by_field_name("name")
    body = node.child_by_field_name("body")
    if name is None or _node_kind(name) is not _NodeKind.IDENTIFIER or body is None:
        return None
    returns = [
        child for child in body.named_children if _node_kind(child) is _NodeKind.RETURN_STATEMENT
    ]
    if (
        len(returns) == 1
        and len(returns[0].named_children) == 1
        and _node_kind(returns[0].named_children[0]) is _NodeKind.OBJECT
    ):
        return ScriptGlobal(
            _text(name),
            source.span(binding),
            _script_members(returns[0].named_children[0], node, source),
            _script_reaches(returns[0], node),
        )
    return None


def _script_globals(
    source: _Source,
    bindings: dict[_RawNode, dict[str, int]],
    ambiguous_bindings: set[_RawNode],
) -> tuple[tuple[ScriptGlobal, ...], tuple[tuple[str | None, Span], ...]]:
    publications: list[ScriptGlobal] = []
    writes: list[tuple[str | None, Span]] = []
    receivers: list[tuple[Span | None, Span]] = []
    wrappers = {
        node: wrapper_info
        for node in _walk(source.root)
        if (wrapper_info := _script_wrapper(node)) is not None
    }
    callables = _script_callable_bindings(source, bindings)
    wrapper_calls = {info[0] for info in wrappers.values()}
    roots = _SCRIPT_ROOTS
    root_aliases = roots | {alias for _, aliases in wrappers.values() for alias in aliases}
    module_syntax = _module_exports(source.root)[0]
    for node in _walk(source.root):
        kind = _node_kind(node)
        writes.extend(
            (None, span)
            for span in _script_opaque_writes(node, source, bindings, ambiguous_bindings, callables)
        )
        if kind is _NodeKind.THIS:
            owner = next(
                (
                    ancestor
                    for ancestor in _ancestors(node)
                    if _node_kind(ancestor) in _SCRIPT_RECEIVER_SCOPES
                ),
                None,
            )
            receivers.append((source.span(owner) if owner is not None else None, source.span(node)))
            if _script_escape(node):
                writes.append((None, source.span(node)))
        if (
            kind in {_NodeKind.IDENTIFIER, _NodeKind.SHORTHAND_PROPERTY_IDENTIFIER}
            and _text(node) in root_aliases
            and not _declaration_name(node)
            and _script_escape(node)
        ):
            writes.append((None, source.span(node)))
        if not module_syntax and (written := _script_declaration_write(node, source)) is not None:
            writes.append(written)
        for target in _script_assignment_targets(node):
            wrapper = next((parent for parent in _ancestors(node) if parent in wrappers), None)
            aliases = roots | set(wrappers[wrapper][1] if wrapper is not None else ())
            path = _static_path(target)
            writes.append(_script_target_write(node, target, aliases, source))
            if path and path[0] in aliases:
                publication = _script_assignment_publication(
                    node, target, wrapper, wrappers, source, bindings, ambiguous_bindings
                )
                if publication is not None:
                    publications.append(publication)
        writes.extend(_script_call_writes(node, wrapper_calls, source))
        wrapper_info = wrappers.get(node)
        if wrapper_info is not None:
            publication = _script_return_publication(node, wrapper_info[0], module_syntax, source)
            if publication is not None:
                publications.append(publication)
                writes.append((publication.name, publication.span))
    published_members = {span for item in publications for _, _, span in item.members}
    writes.extend(
        (None, span) for owner, span in receivers if owner is None or owner in published_members
    )
    unique_writes = {write: None for write in writes}
    return tuple(publications), tuple(unique_writes)


def _script_members(
    node: _RawNode, wrapper: _RawNode | None, source: _Source
) -> tuple[tuple[str, str, Span], ...]:
    members: list[tuple[str, str]] = []
    keys: list[str] = []
    for member in node.named_children:
        if _node_kind(member) is _NodeKind.SHORTHAND_PROPERTY_IDENTIFIER:
            keys.append(_text(member))
            members.append((_text(member), _text(member)))
        elif _node_kind(member) is _NodeKind.PAIR:
            key, value = member.child_by_field_name("key"), member.child_by_field_name("value")
            if key is None or _node_kind(key) is not _NodeKind.PROPERTY_IDENTIFIER:
                return ()
            keys.append(_text(key))
            if (
                key is not None
                and value is not None
                and _node_kind(key) is _NodeKind.PROPERTY_IDENTIFIER
                and _node_kind(value) is _NodeKind.IDENTIFIER
            ):
                members.append((_text(key), _text(value)))
        else:
            return ()
    counts = _Counter(keys)
    body = wrapper.child_by_field_name("body") if wrapper is not None else source.root
    declarations = tuple(body.named_children) if body is not None else ()
    return tuple(
        (published, local, source.span(declaration))
        for published, local in members
        if counts[published] == 1
        for declaration in declarations
        if _node_kind(declaration) is _NodeKind.FUNCTION_DECLARATION
        and (name := declaration.child_by_field_name("name")) is not None
        and _text(name) == local
    )


def _script_object_values(node: _RawNode) -> tuple[tuple[str, _RawNode], ...]:
    values: list[tuple[str, _RawNode]] = []
    for member in node.named_children:
        if _node_kind(member) is _NodeKind.SHORTHAND_PROPERTY_IDENTIFIER:
            values.append((_text(member), member))
        elif _node_kind(member) is _NodeKind.PAIR:
            key = member.child_by_field_name("key")
            value = member.child_by_field_name("value")
            if key is None or value is None or _node_kind(key) is not _NodeKind.PROPERTY_IDENTIFIER:
                return ()
            values.append((_text(key), value))
        else:
            return ()
    return tuple(values) if len({name for name, _ in values}) == len(values) else ()


def _script_local_definition(
    value: _RawNode,
    source: _Source,
    bindings: dict[_RawNode, dict[str, int]],
    definitions: tuple[Definition, ...],
) -> tuple[Definition | None, _RawNode] | None:
    name = _text(value)
    scope = _script_bound_scope(value, name, bindings)
    if scope is None or bindings[scope][name] != 1 or not _valid_unicode_member_name(value):
        return None
    declarations = [
        node
        for node in _walk(scope)
        if _node_kind(node) in {_NodeKind.FUNCTION_DECLARATION, _NodeKind.VARIABLE_DECLARATOR}
        and (bound := node.child_by_field_name("name")) is not None
        and _text(bound) == name
        and _script_bound_scope(node, name, bindings) == scope
    ]
    if len(declarations) != 1:
        return None
    declaration = declarations[0]
    if _node_kind(declaration) is _NodeKind.VARIABLE_DECLARATOR and (
        declaration.end_byte > value.start_byte
        or declaration.parent is None
        or (kind := declaration.parent.child_by_field_name("kind")) is None
        or _node_kind(kind) is not _NodeKind.CONST
    ):
        return None
    if any(
        _static_path(target) == (name,) and _script_bound_scope(target, name, bindings) == scope
        for node in _walk(scope)
        for target in _script_assignment_targets(node)
    ):
        return None
    found = [item for item in definitions if item.span == source.span(declaration)]
    return (found[0] if found else None, declaration) if len(found) <= 1 else None


def _script_declarations(
    source: _Source,
    definitions: tuple[Definition, ...],
    bindings: dict[_RawNode, dict[str, int]],
) -> tuple[
    dict[Span, tuple[tuple[str, str, Span], ...]],
    tuple[tuple[str | None, Span], ...],
    tuple[tuple[str, ...], ...],
    tuple[tuple[str, ...], ...],
]:
    objects: dict[Span, _RawNode] = {}
    writes: list[tuple[str | None, Span]] = []
    paths: list[tuple[str, ...]] = []
    top_level_paths: list[tuple[str, ...]] = []
    wrappers = {
        node: info for node in _walk(source.root) if (info := _script_wrapper(node)) is not None
    }
    for node in _walk(source.root):
        if (written := _script_declaration_write(node, source)) is not None:
            writes.append(written)
        wrapper = next((parent for parent in _ancestors(node) if parent in wrappers), None)
        aliases = _SCRIPT_ROOTS | set(wrappers[wrapper][1] if wrapper is not None else ())
        for target in _script_assignment_targets(node):
            receiver = target
            while _node_kind(receiver) in {
                _NodeKind.MEMBER_EXPRESSION,
                _NodeKind.SUBSCRIPT_EXPRESSION,
            }:
                object_node = receiver.child_by_field_name("object")
                if object_node is None:
                    break
                receiver = object_node
            if _node_kind(receiver) is not _NodeKind.CALL_EXPRESSION:
                writes.append(_script_target_write(node, target, aliases, source))
                route = _static_path(target)
                if route and (
                    route[0] in _SCRIPT_ROOTS or _script_free(target, target, bindings, set())
                ):
                    paths.append(route[1:] if route[0] in _SCRIPT_ROOTS else route)
                elif route and _script_bound_scope(target, route[0], bindings) == source.root:
                    top_level_paths.append(route)
                alias_route = (
                    _script_write_alias_path(target, source, bindings, ())
                    if len(route) > 1
                    else None
                )
                if alias_route is not None:
                    paths.append(alias_route)
        if _node_kind(node) is _NodeKind.ASSIGNMENT_EXPRESSION:
            value = node.child_by_field_name("right")
            if value is not None and _node_kind(value) is _NodeKind.OBJECT:
                objects[source.span(node)] = value
        if node in wrappers and (body := node.child_by_field_name("body")) is not None:
            call = wrappers[node][0]
            parent = call.parent
            returns = [
                item
                for item in body.named_children
                if _node_kind(item) is _NodeKind.RETURN_STATEMENT
            ]
            if parent is not None and len(returns) == 1 and len(returns[0].named_children) == 1:
                value = returns[0].named_children[0]
                if _node_kind(value) is _NodeKind.OBJECT:
                    objects[source.span(parent)] = value
    members = {
        span: _script_object_members(obj, source, bindings, definitions)
        for span, obj in objects.items()
    }
    return (
        members,
        tuple(dict.fromkeys(writes)),
        tuple(dict.fromkeys(paths)),
        tuple(dict.fromkeys(top_level_paths)),
    )


def _script_object_members(
    obj: _RawNode,
    source: _Source,
    bindings: dict[_RawNode, dict[str, int]],
    definitions: tuple[Definition, ...],
) -> tuple[tuple[str, str, Span], ...]:
    found = []
    for published, value in _script_object_values(obj):
        if _node_kind(value) not in {
            _NodeKind.IDENTIFIER,
            _NodeKind.SHORTHAND_PROPERTY_IDENTIFIER,
        }:
            continue
        source_binding = _script_local_definition(value, source, bindings, definitions)
        if source_binding is None:
            continue
        definition, declaration = source_binding
        initializer = declaration.child_by_field_name("value")
        if definition is not None:
            qualified = (
                f"{definition.parent}.{definition.name}" if definition.parent else definition.name
            )
            found.append((published, qualified, definition.span))
        elif initializer is not None and _node_kind(initializer) in {
            _NodeKind.ARROW_FUNCTION,
            _NodeKind.OBJECT,
        }:
            found.append((published, _text(value), source.span(declaration)))
    return tuple(found)


def _script_write_alias_path(
    target: _RawNode,
    source: _Source,
    bindings: dict[_RawNode, dict[str, int]],
    seen: tuple[_RawNode, ...],
    declarations_by_binding: dict[tuple[_RawNode, str], list[_RawNode]] | None = None,
    global_this_owner: _RawNode | None = None,
) -> tuple[str, ...] | None:
    target = _unparenthesized(target)
    if _node_kind(target) is _NodeKind.THIS and global_this_owner is not None:
        owner = next(
            (
                parent
                for parent in _ancestors(target)
                if _node_kind(parent) in _SCRIPT_FUNCTIONS - {_NodeKind.ARROW_FUNCTION}
            ),
            None,
        )
        return () if owner == global_this_owner else None
    path = _static_path(target)
    if not path:
        return None
    receiver = target
    while _node_kind(receiver) is _NodeKind.MEMBER_EXPRESSION:
        object_node = receiver.child_by_field_name("object")
        if object_node is None:
            return None
        receiver = object_node
    if not _valid_unicode_member_name(receiver):
        return () if declarations_by_binding is not None else None
    scope = _script_bound_scope(receiver, path[0], bindings)
    if scope is None:
        return path[1:] if path[0] in _SCRIPT_ROOTS else path
    declarations = (
        declarations_by_binding.get((scope, path[0]), [])
        if declarations_by_binding is not None
        else [
            node
            for node in _walk(scope)
            if _node_kind(node) is _NodeKind.VARIABLE_DECLARATOR
            and (name := node.child_by_field_name("name")) is not None
            and _node_kind(name) is _NodeKind.IDENTIFIER
            and _text(name) == path[0]
            and _script_bound_scope(name, path[0], bindings) == scope
        ]
    )
    if declarations_by_binding is None and (
        bindings[scope].get(path[0]) != 1 or len(declarations) != 1
    ):
        return None
    origins: list[tuple[str, ...]] = []
    for declaration in declarations:
        if declaration in seen:
            continue
        value = declaration.child_by_field_name("value")
        if value is None and declarations_by_binding is not None:
            value = declaration.child_by_field_name("right")
        if value is None:
            continue
        origin = _script_write_alias_path(
            value,
            source,
            bindings,
            (*seen, declaration),
            declarations_by_binding,
            global_this_owner,
        )
        if origin is not None:
            origins.append(origin)
    return (*min(origins, key=len), *path[1:]) if origins else None


def _script_factories(
    source: _Source,
    definitions: tuple[Definition, ...],
    bindings: dict[_RawNode, dict[str, int]],
) -> tuple[ScriptFactory, ...]:
    factories: list[ScriptFactory] = []
    by_span = {definition.span: definition for definition in definitions}
    for node in _walk(source.root):
        if _node_kind(node) is not _NodeKind.FUNCTION_DECLARATION or any(
            _node_kind(child) is _NodeKind.ASYNC for child in node.children
        ):
            continue
        definition = by_span.get(source.span(node))
        body = node.child_by_field_name("body")
        if definition is None or body is None:
            continue
        returns = [
            child
            for child in _walk(body)
            if _node_kind(child) is _NodeKind.RETURN_STATEMENT
            and next(
                (parent for parent in _ancestors(child) if _node_kind(parent) in _SCRIPT_FUNCTIONS),
                None,
            )
            == node
        ]
        if len(returns) != 1 or returns[0].parent != body or len(returns[0].named_children) != 1:
            continue
        obj = returns[0].named_children[0]
        if _node_kind(obj) is not _NodeKind.OBJECT:
            continue
        members = []
        factory_name = (
            f"{definition.parent}.{definition.name}" if definition.parent else definition.name
        )
        for published, value in _script_object_values(obj):
            target = (
                _script_local_definition(value, source, bindings, definitions)
                if _node_kind(value)
                in {_NodeKind.IDENTIFIER, _NodeKind.SHORTHAND_PROPERTY_IDENTIFIER}
                else None
            )
            if target is not None:
                local, declaration = target
                initializer = declaration.child_by_field_name("value")
                qualified = (
                    f"{local.parent}.{local.name}"
                    if local is not None and local.parent
                    else local.name
                    if local is not None
                    else f"{factory_name}.{_text(value)}"
                )
                callable_value = (
                    local is not None
                    and local.kind is DefinitionKind.FUNCTION
                    or initializer is not None
                    and _node_kind(initializer) is _NodeKind.ARROW_FUNCTION
                )
                members.append(
                    ScriptFactoryMember(
                        published,
                        source.span(value),
                        qualified,
                        source.span(declaration),
                        callable=callable_value,
                    )
                )
            elif _node_kind(value) is _NodeKind.MEMBER_EXPRESSION and len(_static_path(value)) == 2:
                property_name = value.child_by_field_name("property")
                if property_name is not None:
                    members.append(
                        ScriptFactoryMember(
                            published, source.span(value), forwarded_span=source.span(property_name)
                        )
                    )
        qualified = (
            f"{definition.parent}.{definition.name}" if definition.parent else definition.name
        )
        factories.append(ScriptFactory(qualified, definition.span, tuple(members)))
    return tuple(factories)


def _script_reaches(node: _RawNode, wrapper: _RawNode | None) -> bool:
    return not _script_prior_returns(node, wrapper)


@cache
def _script_namespace_argument() -> _RawNode:
    return (
        _parse_root(_Grammar.TSX, b"__publication || (__publication = {})")
        .named_children[0]
        .named_children[0]
    )


def _script_namespace_initializer(statement: _RawNode, name: str) -> _RawNode | None:
    if _node_kind(statement) is not _NodeKind.EXPRESSION_STATEMENT:
        return None
    call = statement.named_children[0]
    wrapper = call.child_by_field_name("function")
    arguments = call.child_by_field_name("arguments")
    while wrapper is not None and _node_kind(wrapper) is _NodeKind.PARENTHESIZED_EXPRESSION:
        wrapper = next(iter(wrapper.named_children), None)
    if (
        _node_kind(call) is not _NodeKind.CALL_EXPRESSION
        or wrapper is None
        or _node_kind(wrapper) is not _NodeKind.FUNCTION_EXPRESSION
        or any(_node_kind(child) is _NodeKind.ASYNC for child in wrapper.children)
        or arguments is None
        or len(arguments.named_children) != 1
    ):
        return None
    parameters = wrapper.child_by_field_name("parameters")
    if parameters is None or len(parameters.named_children) != 1:
        return None
    parameter = parameters.named_children[0]
    pattern = parameter.child_by_field_name("pattern")
    if (
        _node_kind(parameter) is not _NodeKind.REQUIRED_PARAMETER
        or pattern is None
        or _node_kind(pattern) is not _NodeKind.IDENTIFIER
        or _text(pattern) != name
        or parameter.child_by_field_name("value") is not None
    ):
        return None
    argument = arguments.named_children[0]
    captures: dict[_UMDSlot, _RawNode] = {}
    if not _umd_matches(argument, _script_namespace_argument(), captures):
        return None
    if _text(captures[_UMDSlot.PUBLICATION]) != name:
        return None
    return next(
        (node for node in _walk(argument) if _node_kind(node) is _NodeKind.ASSIGNMENT_EXPRESSION),
        None,
    )


def _script_namespaces(
    source: _Source, bindings: dict[_RawNode, dict[str, int]]
) -> tuple[ScriptNamespace, ...]:
    result: list[ScriptNamespace] = []
    statements = [
        node for node in source.root.named_children if _node_kind(node) is not _NodeKind.COMMENT
    ]
    for declaration, statement in zip(statements, statements[1:], strict=False):
        if _node_kind(declaration) is not _NodeKind.VARIABLE_DECLARATION:
            continue
        variables = [
            node
            for node in declaration.named_children
            if _node_kind(node) is _NodeKind.VARIABLE_DECLARATOR
        ]
        if len(variables) != 1:
            continue
        variable = variables[0]
        name = variable.child_by_field_name("name")
        if (
            name is None
            or _node_kind(name) is not _NodeKind.IDENTIFIER
            or variable.child_by_field_name("value") is not None
            or bindings.get(source.root, {}).get(_text(name)) != 1
        ):
            continue
        initializer = _script_namespace_initializer(statement, _text(name))
        if initializer is None:
            continue
        writes = [
            node
            for node in _walk(source.root)
            for target in _script_assignment_targets(node)
            if (
                _static_path(target) == (_text(name),)
                and _script_bound_scope(target, _text(name), bindings) == source.root
                or len(route := _static_path(target)) == 2
                and route[0] in _SCRIPT_ROOTS
                and route[1] == _text(name)
                and _script_free(target, target, bindings, set())
            )
        ]
        if writes == [initializer]:
            result.append(
                ScriptNamespace(_text(name), source.span(variable), source.span(initializer))
            )
    return tuple(result)


def _script_prior_returns(node: _RawNode, wrapper: _RawNode | None) -> tuple[_RawNode, ...]:
    if wrapper is None:
        return ()
    body = wrapper.child_by_field_name("body")
    if body is None:
        return (node,)
    functions = {
        _NodeKind.FUNCTION_DECLARATION,
        _NodeKind.FUNCTION_EXPRESSION,
        _NodeKind.ARROW_FUNCTION,
        _NodeKind.METHOD_DEFINITION,
    }
    return tuple(
        child.parent if child.parent is not None else child
        for child in _walk(body)
        if _node_kind(child) is _NodeKind.RETURN_STATEMENT
        and child.start_byte < node.start_byte
        and next((parent for parent in _ancestors(child) if _node_kind(parent) in functions), None)
        == wrapper
    )


def _scope_names(node: _RawNode) -> tuple[str, ...]:
    names: set[str] = set()
    parameters = node.child_by_field_name("parameters")
    if parameters is not None:
        names.update(
            _text(child)
            for child in _walk(parameters)
            if _node_kind(child) == _NodeKind.IDENTIFIER and _declaration_name(child)
        )
    body = node.child_by_field_name("body")
    if body is not None:
        for child in _walk(body):
            if _node_kind(child) == _NodeKind.VARIABLE_DECLARATOR:
                name = child.child_by_field_name("name")
                if name is not None and _node_kind(name) == _NodeKind.IDENTIFIER:
                    names.add(_text(name))
            if _node_kind(child) == _NodeKind.ASSIGNMENT_EXPRESSION:
                left = child.child_by_field_name("left")
                if left is not None and _node_kind(left) == _NodeKind.IDENTIFIER:
                    names.add(_text(left))
    return tuple(sorted(names))


def _active_scope_names(
    node: _RawNode, scope: _RawNode | None, source: _Source
) -> tuple[tuple[str, ...], bool]:
    names: set[str] = set(source.names_in_scope(scope)) if scope is not None else set()
    ambiguous = False
    parent = node.parent
    while parent is not None and parent != scope:
        if _node_kind(parent) in {
            _NodeKind.INTERNAL_MODULE,
            _NodeKind.CLASS_EXPRESSION,
            _NodeKind.OBJECT,
        }:
            ambiguous = True
        if _node_kind(parent) == _NodeKind.STATEMENT_BLOCK:
            owner = parent.parent
            if owner is None or owner.child_by_field_name("body") != parent:
                ambiguous = True
        if _node_kind(parent) in {
            _NodeKind.ARROW_FUNCTION,
            _NodeKind.FUNCTION_EXPRESSION,
            _NodeKind.GENERATOR_FUNCTION,
        }:
            names.update(source.names_in_scope(parent))
            ambiguous |= not source.script_mode or _script_wrapper(parent) is None
        elif _node_kind(parent) == _NodeKind.METHOD_DEFINITION and not _class_member(parent):
            names.update(source.names_in_scope(parent))
            ambiguous = True
        parent = parent.parent
    return tuple(sorted(names)), ambiguous


def _is_jsx_attribute_name(node: _RawNode) -> bool:
    # A namespaced name (`aria:label`) nests its identifiers one level down. Only the name
    # child is skipped: an attribute value is an expression and stays a reference.
    name = (
        node.parent
        if node.parent is not None and _node_kind(node.parent) is _NodeKind.JSX_NAMESPACE_NAME
        else node
    )
    attribute = name.parent
    return (
        attribute is not None
        and _node_kind(attribute) is _NodeKind.JSX_ATTRIBUTE
        and attribute.children[0] == name
    )


def _is_member_name(node: _RawNode) -> bool:
    parent = node.parent
    if parent is None:
        return False
    if _is_jsx_attribute_name(node):
        return True
    if _node_kind(parent) == _NodeKind.MEMBER_EXPRESSION:
        return False
    return (
        _node_kind(parent)
        in {
            _NodeKind.METHOD_DEFINITION,
            _NodeKind.METHOD_SIGNATURE,
            _NodeKind.PUBLIC_FIELD_DEFINITION,
            _NodeKind.PROPERTY_SIGNATURE,
        }
        and parent.child_by_field_name("name") == node
    )


def _inside_site_callee(node: _RawNode) -> bool:
    child, parent = node, node.parent
    while parent is not None and _node_kind(parent) in (
        _NodeKind.MEMBER_EXPRESSION,
        _NodeKind.SUBSCRIPT_EXPRESSION,
    ):
        child, parent = parent, parent.parent
    return (
        parent is not None
        and _node_kind(parent) in (_NodeKind.CALL_EXPRESSION, _NodeKind.NEW_EXPRESSION)
        and (
            parent.child_by_field_name("function") == child
            or parent.child_by_field_name("constructor") == child
        )
    )


def _assigned_name(node: _RawNode) -> str | None:
    parent = node.parent
    if parent is not None and _node_kind(parent) == _NodeKind.ARGUMENTS:
        parent = parent.parent
    if (
        parent is not None
        and _node_kind(parent) == _NodeKind.VARIABLE_DECLARATOR
        and parent.child_by_field_name("value") == node
    ):
        name = parent.child_by_field_name("name")
        return (
            _text(name) if name is not None and _node_kind(name) == _NodeKind.IDENTIFIER else None
        )
    return None


def _assignment_node(node: _RawNode) -> _RawNode | None:
    parent = node.parent
    return (
        parent
        if parent is not None
        and _node_kind(parent) == _NodeKind.VARIABLE_DECLARATOR
        and parent.child_by_field_name("value") == node
        else None
    )


def _assignment_span(node: _RawNode, source: _Source) -> Span | None:
    assignment = _assignment_node(node)
    name = assignment.child_by_field_name("name") if assignment is not None else None
    return source.span(name) if name is not None else None


def _assignment_annotation(node: _RawNode) -> str | None:
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
                    type_only=any(
                        _node_kind(child) == _NodeKind.TYPE for child in statement.children
                    ),
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
                        type_only=any(
                            _node_kind(child) == _NodeKind.TYPE for child in item.children
                        )
                        or any(_node_kind(child) == _NodeKind.TYPE for child in statement.children),
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
                        type_only=any(
                            _node_kind(child) == _NodeKind.TYPE for child in statement.children
                        ),
                    )
                )
    return tuple(result)


def _module_import_bindings(
    source: _Source, bindings: dict[_RawNode, dict[str, int]], ambiguous: set[_RawNode]
) -> tuple[ImportBinding, ...]:
    written = {
        _text(target)
        for node in _walk(source.root)
        for target in _script_assignment_targets(node)
        if _node_kind(target) is _NodeKind.IDENTIFIER
        and _script_bound_scope(target, _text(target), bindings) == source.root
    }
    return tuple(
        replace(
            item,
            source_unique=source.root not in ambiguous
            and bindings.get(source.root, {}).get(item.local) == 1
            and item.local not in written,
        )
        for item in _import_bindings(source)
    )


def _module_export_bindings(
    source: _Source, bindings: dict[_RawNode, dict[str, int]], ambiguous: set[_RawNode]
) -> tuple[tuple[str, Span, Span], ...]:
    if (
        source.root.has_error
        or source.root in ambiguous
        or any(
            _node_kind(statement) is _NodeKind.EXPORT_STATEMENT
            and statement.child_by_field_name("source") is not None
            for statement in source.root.named_children
        )
    ):
        return ()
    declarations: dict[str, list[Span]] = {}
    exports: list[tuple[str, Span]] = []
    for statement in source.root.named_children:
        exported = _node_kind(statement) is _NodeKind.EXPORT_STATEMENT
        declaration = statement.child_by_field_name("declaration") if exported else statement
        direct = exported and not any(
            _node_kind(child) in {_NodeKind.DEFAULT, _NodeKind.TYPE} for child in statement.children
        )
        candidates = (
            declaration.named_children
            if declaration is not None
            and _node_kind(declaration)
            in {_NodeKind.LEXICAL_DECLARATION, _NodeKind.VARIABLE_DECLARATION}
            else (declaration,)
            if declaration is not None
            else ()
        )
        for node in candidates:
            name = node.child_by_field_name("name")
            if (
                _node_kind(node)
                not in {
                    _NodeKind.VARIABLE_DECLARATOR,
                    _NodeKind.FUNCTION_DECLARATION,
                    _NodeKind.CLASS_DECLARATION,
                }
                or name is None
                or not _valid_unicode_member_name(name)
            ):
                continue
            declarations.setdefault(_text(name), []).append(source.span(node))
            if direct:
                exports.append((_text(name), source.span(statement)))
        clause = next(iter(_children(statement, _NodeKind.EXPORT_CLAUSE)), None) if direct else None
        if statement.child_by_field_name("source") is not None:
            continue
        for specifier in _children(clause, _NodeKind.EXPORT_SPECIFIER):
            name, alias = _specifier_names(specifier)
            if (
                name is not None
                and _valid_unicode_member_name(name)
                and alias is None
                and not any(_node_kind(child) is _NodeKind.TYPE for child in specifier.children)
            ):
                exports.append((_text(name), source.span(specifier)))
    counts = _Counter(name for name, _ in exports)
    return tuple(
        (name, declarations[name][0], span)
        for name, span in exports
        if counts[name] == 1
        and len(declarations.get(name, ())) == 1
        and bindings.get(source.root, {}).get(name) == 1
    )


def _rebound_names(source: _Source) -> tuple[str, ...]:
    result = set()
    for node in _walk(source.root):
        if _node_kind(node) != _NodeKind.ASSIGNMENT_EXPRESSION:
            continue
        if any(
            _node_kind(parent)
            in (
                _NodeKind.FUNCTION_DECLARATION,
                _NodeKind.METHOD_DEFINITION,
                _NodeKind.ARROW_FUNCTION,
            )
            for parent in _ancestors(node)
        ):
            continue
        left = node.child_by_field_name("left")
        if left is not None and _node_kind(left) == _NodeKind.IDENTIFIER:
            result.add(_text(left))
    return tuple(sorted(result))


def _ancestors(node: _RawNode) -> Iterator[_RawNode]:
    parent = node.parent
    while parent is not None:
        yield parent
        parent = parent.parent


def _in_unmodeled_block(node: _RawNode) -> bool:
    return any(
        _node_kind(block) == _NodeKind.STATEMENT_BLOCK
        and (block.parent is None or block.parent.child_by_field_name("body") != block)
        for block in _ancestors(node)
    )


def _text(node: _RawNode) -> str:
    return str(node.text or b"", "utf-8", "replace")


def _in_error(node: _RawNode) -> bool:
    """A reference inside a region the parser had to repair is not a fact."""
    if node.has_error:
        return True
    parent = node.parent
    while parent is not None:
        if parent.is_error:
            return True
        parent = parent.parent
    return False


def _literal(node: _RawNode | None) -> str | None:
    """The module text of a string without escapes or substitutions; None means computed."""
    if (
        node is None
        or _node_kind(node) not in (_NodeKind.STRING, _NodeKind.TEMPLATE_STRING)
        or re.search(r"\\", _text(node)) is not None
    ):
        return None
    if any(_node_kind(child) == _NodeKind.TEMPLATE_SUBSTITUTION for child in node.children):
        return None
    return _text(node)[1:-1]


def _type_only(statement: _RawNode, specifiers: list[_RawNode], default: bool) -> bool:
    """`import type`, or every named specifier marked `type` with no default import."""
    marked = bool(specifiers) and all(
        any(_node_kind(child) == _NodeKind.TYPE for child in item.children) for item in specifiers
    )
    return any(_node_kind(child) == _NodeKind.TYPE for child in statement.children) or (
        marked and not default
    )


def _children(node: _RawNode | None, kind: _NodeKind) -> list[_RawNode]:
    return (
        [child for child in node.children if _node_kind(child) == kind] if node is not None else []
    )


def _import(node: _RawNode, source: _Source) -> Reference:
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


def _export(node: _RawNode, source: _Source) -> Reference:
    clause = next(iter(_children(node, _NodeKind.EXPORT_CLAUSE)), None)
    return Reference(
        ReferenceForm.REEXPORT,
        _literal(next(iter(_children(node, _NodeKind.STRING)), None)),
        _type_only(node, _children(clause, _NodeKind.EXPORT_SPECIFIER), False),
        _top_level(node),
        re.search(r"resolution-mode", _text(node)) is not None,
        source.span(node),
    )


def _top_level(node: _RawNode) -> bool:
    return node.parent is not None and _node_kind(node.parent) == _NodeKind.PROGRAM


def _argument(call: _RawNode) -> _RawNode | None:
    arguments = next(iter(_children(call, _NodeKind.ARGUMENTS)), None)
    return arguments.named_children[0] if arguments and arguments.named_children else None


def _in_type(node: _RawNode) -> bool:
    child, parent = node, node.parent
    while parent is not None:
        if _node_kind(parent) in _TYPE_PARENTS:
            return True
        # `value as T` and `value satisfies T` start with the value; only what follows is a type.
        if _node_kind(parent) in (_NodeKind.AS_EXPRESSION, _NodeKind.SATISFIES_EXPRESSION) and (
            child.start_byte > parent.start_byte
        ):
            return True
        child, parent = parent, parent.parent
    return False


def _query_start(node: _RawNode) -> _RawNode | None:
    """The `typeof` query an import type opens, which the compiler counts as part of it."""
    parent = node.parent
    while (
        parent is not None
        and _node_kind(parent)
        in (_NodeKind.MEMBER_EXPRESSION, _NodeKind.CALL_EXPRESSION, _NodeKind.SUBSCRIPT_EXPRESSION)
        and parent.start_byte == node.start_byte
    ):
        parent = parent.parent
    return parent if parent is not None and _node_kind(parent) == _NodeKind.TYPE_QUERY else None


def _dynamic(node: _RawNode, source: _Source) -> Reference:
    typed = _in_type(node)
    return Reference(
        ReferenceForm.IMPORT_TYPE if typed else ReferenceForm.DYNAMIC_IMPORT,
        _literal(_argument(node)),
        typed,
        False,
        re.search(r"resolution-mode", _text(node)) is not None,
        source.span(node, _query_start(node) if typed else None),
    )


def _require(node: _RawNode, source: _Source) -> Reference:
    return Reference(
        ReferenceForm.REQUIRE, _literal(_argument(node)), False, False, False, source.span(node)
    )


def _starts_with(parent: _RawNode | None, node: _RawNode, *kinds: _NodeKind) -> bool:
    return (
        parent is not None and _node_kind(parent) in kinds and parent.start_byte == node.start_byte
    )


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
            and _node_kind(parent) == _NodeKind.UNARY_EXPRESSION
            and any(_node_kind(child) is _NodeKind.TYPEOF for child in parent.children)
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
        computed = _node_kind(key) == _NodeKind.COMPUTED_PROPERTY_NAME
        inner = key.named_children[0] if computed and key.named_children else key
        name = _literal(inner) if _node_kind(inner) == _NodeKind.STRING else _text(inner)
        # A computed key may select `require` from the module object by a name built at runtime.
        runtime_name = computed and _node_kind(inner) != _NodeKind.STRING
        if _special_name(name) is _SpecialName.REQUIRE or (runtime_name and modules):
            concerns.append(Concern("Indirect require binding is not resolved", source.span(node)))
    return shadows


def _comment_concerns(source: _Source, suffix: FileSuffix | None) -> list[Concern]:
    concerns: list[Concern] = []
    # tsc reads JSDoc types only in JavaScript files; an unknown suffix keeps the gap.
    jsdoc = suffix is None or suffix.source_kind not in (
        SourceKind.TYPESCRIPT,
        SourceKind.DECLARATION,
    )
    # Triple-slash directives count only before the first statement of the file.
    statements = [
        child.start_byte
        for child in source.root.children
        if _node_kind(child) not in (_NodeKind.COMMENT, _NodeKind.HASH_BANG_LINE)
    ]
    first = statements[0] if statements else len(source.data)
    for node in source.captures("comments").get("comment", []):
        body = _text(node)
        directive = _TRIPLE_SLASH.match(body) if node.start_byte < first else None
        # A `types` entry only adds globals, which the catalog does not model (AD-274).
        # `types` is no concern: it only adds globals, which the catalog does not model (AD-274).
        if directive is not None:
            reason = f"Unobserved triple-slash reference: {directive[2]}"
            concerns.append(Concern(reason, source.span(node)))
        if jsdoc and _jsdoc_imports(body):
            concerns.append(Concern("JSDoc import is not observed", source.span(node)))
    return concerns


def _jsdoc_imports(body: str) -> bool:
    """An `@import` tag, or `import(` in the type of a tag; prose is no type (#744)."""
    kind: _JSDocType | None = None
    depth = 0
    # `armed`: the end of a type is not known, so any later import counts.
    armed = False
    # The quotes seen an odd number of times in the open types.
    odd: set[str] = set()
    tokens = _JSDOC_TOKEN.finditer(body)
    first = next(tokens, None)
    if first is None or first["block"] is None:
        return False
    for token in tokens:
        if token["call"] is not None:
            if armed or depth:
                return True
        elif token["tag"] is not None:
            # A tag inside an open type: a broken type, or an `@` inside a string.
            armed = armed or depth > 0
            kind = _JSDOC_TAGS.get(token["tag"])
            if kind is _JSDocType.IMPORT:
                return True
            depth = 1 if kind is not None and token["braced"] is not None else 0
            # Without braces the end of the type is not known.
            armed = armed or (kind is _JSDocType.BARE and not depth)
        elif kind is None:
            continue
        elif token["open"] is not None or (
            token["bracket"] is not None and kind is _JSDocType.TEMPLATE
        ):
            depth += 1
        elif (
            token["close"] is not None or (token["end"] is not None and kind is _JSDocType.TEMPLATE)
        ) and depth:
            depth -= 1
            # An odd quote count can put this brace or bracket inside a string.
            armed = armed or bool(odd)
        elif token["quote"] is not None and depth:
            odd ^= {token["quote"]}
    return False


class _UMDSlot(Enum):
    FACTORY = "__factory"
    ROOT = "__root"
    PUBLICATION = "__publication"


_UMD_SLOTS: Final = {slot.value: slot for slot in _UMDSlot}
_UMD_ENVELOPE: Final = (
    b'(function(__factory){if(typeof exports==="object"&&typeof module!=="undefined")'
    b'{module.exports=__factory()}else if(typeof define==="function"&&define.amd)'
    b'{define([],__factory)}else{var __root;if(typeof window!=="undefined")'
    b'{__root=window}else if(typeof global!=="undefined"){__root=global}'
    b'else if(typeof self!=="undefined"){__root=self}else{__root=this}'
    b"__root.__publication=__factory()}})"
)


@cache
def _umd_envelope() -> _RawNode:
    return _parse_root(_Grammar.TSX, _UMD_ENVELOPE).named_children[0].named_children[0]


def _umd_matches(actual: _RawNode, pattern: _RawNode, captures: dict[_UMDSlot, _RawNode]) -> bool:
    kind = _node_kind(pattern)
    if kind is not _node_kind(actual):
        return False
    if kind in {_NodeKind.IDENTIFIER, _NodeKind.PROPERTY_IDENTIFIER}:
        slot = _UMD_SLOTS.get(_text(pattern))
        if slot is not None:
            previous = captures.setdefault(slot, actual)
            return _text(previous) == _text(actual)
    if kind is _NodeKind.STRING:
        return _literal(actual) == _literal(pattern)
    left = [child for child in actual.children if _node_kind(child) is not _NodeKind.COMMENT]
    right = [child for child in pattern.children if _node_kind(child) is not _NodeKind.COMMENT]
    if not left and not right:
        return _text(actual) == _text(pattern)
    return (
        kind is not None
        and len(left) == len(right)
        and all(
            _umd_matches(child, expected, captures)
            for child, expected in zip(left, right, strict=True)
        )
    )


def umd_publication(rel: str, content: bytes) -> tuple[str, Span, frozenset[str] | None] | None:
    """Recognize only a closed UMD declaration envelope; its factory remains a runtime effect."""
    suffix = classify_file(rel)
    if (
        suffix is None
        or suffix.source_kind is not SourceKind.JAVASCRIPT
        or suffix.format_hint is not None
    ):
        return None
    root = _parse_root(_Grammar.TSX, content)
    statements = [node for node in root.named_children if _node_kind(node) is not _NodeKind.COMMENT]
    if (
        root.has_error
        or len(statements) != 1
        or _node_kind(statements[0]) is not _NodeKind.EXPRESSION_STATEMENT
    ):
        return None
    call = statements[0].named_children[0]
    wrapper = call.child_by_field_name("function")
    arguments = call.child_by_field_name("arguments")
    if (
        _node_kind(call) is not _NodeKind.CALL_EXPRESSION
        or wrapper is None
        or arguments is None
        or len(arguments.named_children) != 1
    ):
        return None
    factory = arguments.named_children[0]
    parameters = factory.child_by_field_name("parameters")
    if (
        _node_kind(factory) is not _NodeKind.FUNCTION_EXPRESSION
        or parameters is None
        or parameters.named_children
        or any(_node_kind(child) is _NodeKind.ASYNC for child in factory.children)
    ):
        return None
    captures: dict[_UMDSlot, _RawNode] = {}
    if not _umd_matches(wrapper, _umd_envelope(), captures) or not all(
        _valid_unicode_member_name(node) for node in captures.values()
    ):
        return None
    factory_name, root_name = (_text(captures[slot]) for slot in (_UMDSlot.FACTORY, _UMDSlot.ROOT))
    if factory_name == root_name or {factory_name, root_name} & {
        "exports",
        "module",
        "define",
        "window",
        "global",
        "self",
    }:
        return None
    publication = captures[_UMDSlot.PUBLICATION]
    source = _Source(
        _Grammar.TSX,
        root,
        content,
        False,
        _line_starts(content),
    )
    return _text(publication), source.span(publication), _umd_factory_global_writes(factory, source)


def _umd_factory_global_writes(factory: _RawNode, source: _Source) -> frozenset[str] | None:
    captures = source.captures("umd_writes", factory)
    if captures.get("call"):
        # Publication syntax does not prove callees or argument effects.
        return None
    nodes = captures.get("binding", [])
    bindings, _ = _script_bindings(source, nodes)
    declarations: dict[tuple[_RawNode, str], list[_RawNode]] = {}
    for node in (*nodes, *captures.get("write", [])):
        name = node.child_by_field_name("name")
        if name is not None and not _valid_unicode_member_name(name):
            return None
        if (
            _node_kind(node) in {_NodeKind.VARIABLE_DECLARATOR, _NodeKind.ASSIGNMENT_EXPRESSION}
            and (name := node.child_by_field_name("name") or node.child_by_field_name("left"))
            is not None
            and _node_kind(name) is _NodeKind.IDENTIFIER
            and (scope := _script_bound_scope(name, _text(name), bindings)) is not None
        ):
            declared: list[_RawNode] = declarations.setdefault((scope, _text(name)), [])
            declared.append(node)
    written: set[str] = set()
    for node in captures.get("write", []):
        for target in _script_assignment_targets(node):
            if (
                _node_kind(target) is _NodeKind.IDENTIFIER
                and _script_bound_scope(target, _text(target), bindings) is not None
            ):
                continue
            path = _umd_global_path(target, factory, source, bindings, declarations)
            if path is not None and len(path) <= 1:
                if not path or path[0] is None:
                    return None
                written.add(path[0])
    return frozenset(written)


def _umd_global_path(
    target: _RawNode,
    factory: _RawNode,
    source: _Source,
    bindings: dict[_RawNode, dict[str, int]],
    declarations: dict[tuple[_RawNode, str], list[_RawNode]],
) -> tuple[str | None, ...] | None:
    receiver = _unparenthesized(target)
    suffix: list[str | None] = []
    while _node_kind(receiver) in {_NodeKind.MEMBER_EXPRESSION, _NodeKind.SUBSCRIPT_EXPRESSION}:
        parent = receiver.child_by_field_name("object")
        if parent is None:
            return None
        key = receiver.child_by_field_name("property")
        suffix.append(
            (_text(key) if _valid_unicode_member_name(key) else None)
            if key is not None
            else _literal(receiver.child_by_field_name("index"))
        )
        receiver = _unparenthesized(parent)
    if len(suffix) > 1:
        return tuple(suffix)
    path = _script_write_alias_path(receiver, source, bindings, (), declarations, factory)
    return (*path, *reversed(suffix)) if path is not None else None


def _unparenthesized(node: _RawNode) -> _RawNode:
    while _node_kind(node) is _NodeKind.PARENTHESIZED_EXPRESSION:
        child = next(iter(node.named_children), None)
        if child is None:
            break
        node = child
    return node
