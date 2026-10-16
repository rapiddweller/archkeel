# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Project Dart syntax into immutable facts; parser nodes stay inside this module."""

from __future__ import annotations

import re
from bisect import bisect_right
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, replace
from enum import StrEnum
from typing import Literal, overload

import tree_sitter_dart
from tree_sitter import Language, Parser
from tree_sitter import Node as RawNode

from .syntax import (
    Combinator as Combinator,
)
from .syntax import (
    Concern as Concern,
)
from .syntax import (
    ConcernKind as ConcernKind,
)
from .syntax import (
    Definition as Definition,
)
from .syntax import (
    DefinitionKind as DefinitionKind,
)
from .syntax import (
    Directive as Directive,
)
from .syntax import (
    DirectiveKind as DirectiveKind,
)
from .syntax import (
    Member as Member,
)
from .syntax import (
    MemberKind as MemberKind,
)
from .syntax import (
    Modifier as Modifier,
)
from .syntax import (
    Parameter as Parameter,
)
from .syntax import (
    ParameterKind as ParameterKind,
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


class _NodeKind(StrEnum):
    EMPTY = ""
    COLON = ":"
    EQUALS = "="
    INDEX = "[]"
    INDEX_ASSIGN = "[]="
    ANNOTATION = "annotation"
    ARGUMENT = "argument"
    ARGUMENT_PART = "argument_part"
    ARGUMENTS = "arguments"
    ASSIGNABLE_EXPRESSION = "assignable_expression"
    ASSIGNMENT_EXPRESSION = "assignment_expression"
    BINARY_OPERATOR = "binary_operator"
    BLOCK = "block"
    BODY = "body"
    CLASS_BODY = "class_body"
    CLASS_DEFINITION = "class_definition"
    COMBINATOR = "combinator"
    COMMENT = "comment"
    COMPOUND_ASSIGNMENT_EXPRESSION = "compound_assignment_expression"
    CONFIGURABLE_URI = "configurable_uri"
    CONFIGURATION_URI = "configuration_uri"
    CONFIGURATION_URI_CONDITION = "configuration_uri_condition"
    CONST_BUILTIN = "const_builtin"
    CONST_OBJECT_EXPRESSION = "const_object_expression"
    CONSTANT_CONSTRUCTOR_SIGNATURE = "constant_constructor_signature"
    CONSTRUCTOR_PARAM = "constructor_param"
    CONSTRUCTOR_SIGNATURE = "constructor_signature"
    DECLARATION = "declaration"
    DEFAULT_FORMAL_PARAMETER = "default_formal_parameter"
    DOCUMENTATION_COMMENT = "documentation_comment"
    ENUM_BODY = "enum_body"
    ENUM_CONSTANT = "enum_constant"
    ENUM_DECLARATION = "enum_declaration"
    EXPORT_SPECIFICATION = "export_specification"
    EXPRESSION_STATEMENT = "expression_statement"
    EXTENSION_DECLARATION = "extension_declaration"
    EXTENSION_TYPE_DECLARATION = "extension_type_declaration"
    FACTORY_CONSTRUCTOR_SIGNATURE = "factory_constructor_signature"
    FIELD_FORMAL_PARAMETER = "field_formal_parameter"
    FINAL_BUILTIN = "final_builtin"
    FORMAL_PARAMETER = "formal_parameter"
    FORMAL_PARAMETER_LIST = "formal_parameter_list"
    FUNCTION_BODY = "function_body"
    FUNCTION_DECLARATION = "function_declaration"
    FUNCTION_EXPRESSION = "function_expression"
    FUNCTION_EXPRESSION_BODY = "function_expression_body"
    FUNCTION_SIGNATURE = "function_signature"
    FUNCTION_TYPE = "function_type"
    FUNCTION_TYPE_ALIAS = "function_type_alias"
    GENERIC_TYPE = "generic_type"
    GETTER_SIGNATURE = "getter_signature"
    IDENTIFIER = "identifier"
    IMPORT_OR_EXPORT = "import_or_export"
    IMPORT_PREFIX = "import_prefix"
    IMPORT_SPECIFICATION = "import_specification"
    INDEX_SELECTOR = "index_selector"
    INITIALIZED_IDENTIFIER = "initialized_identifier"
    INITIALIZED_IDENTIFIER_LIST = "initialized_identifier_list"
    INITIALIZED_VARIABLE_DEFINITION = "initialized_variable_definition"
    INITIALIZERS = "initializers"
    INTERFACE = "interface"
    INTERFACES = "interfaces"
    LATE_BUILTIN = "late_builtin"
    LEFT = "left"
    LIBRARY_EXPORT = "library_export"
    LIBRARY_IMPORT = "library_import"
    LIBRARY_NAME = "library_name"
    LOCAL_VARIABLE_DECLARATION = "local_variable_declaration"
    METADATA = "metadata"
    METHOD_DECLARATION = "method_declaration"
    METHOD_SIGNATURE = "method_signature"
    MIXIN_DECLARATION = "mixin_declaration"
    MIXINS = "mixins"
    NAME = "name"
    NEW_EXPRESSION = "new_expression"
    NULLABLE_TYPE = "nullable_type"
    ON = "on"
    OPERATOR_SIGNATURE = "operator_signature"
    OPTIONAL_FORMAL_PARAMETERS = "optional_formal_parameters"
    PARAMETERS = "parameters"
    PART_DIRECTIVE = "part_directive"
    PART_OF_DIRECTIVE = "part_of_directive"
    PROGRAM = "program"
    QUALIFIED_TYPE = "qualified_type"
    RAW_STRING_LITERAL = "raw_string_literal"
    REDIRECTING_FACTORY_CONSTRUCTOR_SIGNATURE = "redirecting_factory_constructor_signature"
    REDIRECTION = "redirection"
    RIGHT = "right"
    SELECTOR = "selector"
    SETTER_SIGNATURE = "setter_signature"
    STATIC_BUILTIN = "static_builtin"
    STATIC_FINAL_DECLARATION_LIST = "static_final_declaration_list"
    STRING_LITERAL = "string_literal"
    SUPER_FORMAL_PARAMETER = "super_formal_parameter"
    SUPER_PARAMETER = "super_parameter"
    SUPERCLASS = "superclass"
    TOP_LEVEL_VARIABLE_DECLARATION = "top_level_variable_declaration"
    TYPE_ALIAS = "type_alias"
    TYPE_ANNOTATION = "type_annotation"
    TYPE_ARGUMENTS = "type_arguments"
    TYPE_IDENTIFIER = "type_identifier"
    TYPE_NAME = "type_name"
    TYPE_PARAMETER = "type_parameter"
    TYPE_PARAMETERS = "type_parameters"
    UNARY_OPERATOR = "unary_operator"
    UNCONDITIONAL_ASSIGNABLE_SELECTOR = "unconditional_assignable_selector"
    URI = "uri"
    VALUE = "value"


class _Lexeme(StrEnum):
    COMMA = ","
    OPEN_PAREN = "("
    CLOSE_PAREN = ")"
    OPEN_BRACKET = "["
    CLOSE_BRACKET = "]"
    OPEN_BRACE = "{"
    CLOSE_BRACE = "}"
    DOT = "."
    NULL_DOT = "?."
    NULL_CASCADE = "?.."
    CASCADE = ".."
    NULL_INDEX = "?[]"
    ASSERT_DOT = "!."
    NULL_OPEN_INDEX = "?["
    EQUALS = "="
    ARROW = "=>"
    PLUS = "+"
    MINUS = "-"
    STAR = "*"
    SLASH = "/"
    TRUNCATE = "~/"
    MODULO = "%"
    COALESCE = "??"
    AND = "&&"
    OR = "||"
    EQUAL = "=="
    NOT_EQUAL = "!="
    LESS = "<"
    GREATER = ">"
    LESS_EQUAL = "<="
    GREATER_EQUAL = ">="
    COALESCE_ASSIGN = "??="


def _lexeme(value: str) -> _Lexeme | None:
    try:
        return _Lexeme(value)
    except ValueError:
        return None


class _Tree:
    """A parse-local identity map; raw nodes never leave the syntax implementation."""

    __slots__ = ("_nodes",)

    def __init__(self) -> None:
        self._nodes: dict[int, _Node] = {}

    def clear(self) -> None:
        self._nodes.clear()

    def wrap(self, raw: RawNode) -> _Node:
        cached = self._nodes.get(raw.id)
        if cached is None:
            cached = _Node(raw, self)
            self._nodes[raw.id] = cached
        return cached


class _Node:
    """Decode a concrete grammar kind once and delegate only operations we consume."""

    __slots__ = ("_raw", "_tree", "kind")

    def __init__(self, raw: RawNode, tree: _Tree) -> None:
        self._raw = raw
        self._tree = tree
        try:
            self.kind: _NodeKind | None = _NodeKind(raw.type)
        except ValueError:
            self.kind = None

    @property
    def start_byte(self) -> int:
        return self._raw.start_byte

    @property
    def end_byte(self) -> int:
        return self._raw.end_byte

    @property
    def is_error(self) -> bool:
        return self._raw.is_error

    @property
    def is_missing(self) -> bool:
        return self._raw.is_missing

    @property
    def children(self) -> list[_Node]:
        return [self._tree.wrap(child) for child in self._raw.children]

    @property
    def named_children(self) -> list[_Node]:
        return [self._tree.wrap(child) for child in self._raw.named_children]

    @property
    def parent(self) -> _Node | None:
        raw = self._raw.parent
        return self._tree.wrap(raw) if raw is not None else None

    def child_by_field_name(self, name: _NodeKind) -> _Node | None:
        raw = self._raw.child_by_field_name(name.value)
        return self._tree.wrap(raw) if raw is not None else None


_LINE_BREAK = re.compile(rb"\r\n|[\n\r]|\xe2\x80[\xa8\xa9]")
_PARSER = Parser(Language(tree_sitter_dart.language()))
_DECLARATIONS = frozenset(
    {
        _NodeKind.CLASS_DEFINITION,
        _NodeKind.MIXIN_DECLARATION,
        _NodeKind.ENUM_DECLARATION,
        _NodeKind.EXTENSION_DECLARATION,
        _NodeKind.EXTENSION_TYPE_DECLARATION,
        _NodeKind.TYPE_ALIAS,
        _NodeKind.FUNCTION_TYPE_ALIAS,
    }
)


@dataclass(frozen=True, slots=True)
class _Source:
    data: bytes
    starts: tuple[int, ...]

    def text(self, node: _Node) -> str:
        return self.data[node.start_byte : node.end_byte].decode("utf-8", "replace")

    def span(self, node: _Node) -> Span:
        line = bisect_right(self.starts, node.start_byte)
        prefix = self.data[self.starts[line - 1] : node.start_byte].decode("utf-8", "replace")
        end_line = bisect_right(self.starts, node.end_byte)
        return Span(
            line,
            end_line,
            len(prefix.encode("utf-16-le")) // 2,
            self.text(node)[:400],
            node.start_byte,
            node.end_byte,
        )


def parse(content: bytes) -> Syntax:
    """Read declarations, directives and lexical sites from one Dart source unit."""
    tree = _Tree()
    try:
        return _parse_tree(content, tree.wrap(_PARSER.parse(content).root_node))
    finally:
        tree.clear()


def _parse_tree(content: bytes, root: _Node) -> Syntax:
    source = _Source(content, (0, *(item.end() for item in _LINE_BREAK.finditer(content))))
    concerns = [
        Concern(
            ConcernKind.SYNTAX_ERROR,
            "Tree-sitter could not parse this Dart syntax completely.",
            source.span(node),
        )
        for node in _walk(root)
        if node.is_error or node.is_missing
    ]
    unclosed_comment = _unclosed_block_comment(content)
    if unclosed_comment is not None:
        concerns.append(
            Concern(
                ConcernKind.SYNTAX_ERROR,
                "Dart source ends inside a nested block comment.",
                _span_bytes(source, unclosed_comment, len(content)),
            )
        )
    try:
        content.decode("utf-8")
    except UnicodeDecodeError as error:
        concerns.append(
            Concern(
                ConcernKind.INVALID_ENCODING,
                "Dart source is not valid UTF-8.",
                _span_bytes(source, error.start, error.end),
            )
        )
    language_version = _language_version(content, source, concerns)
    directives = _directives(root, source, concerns)
    concerns.extend(_unsupported_concerns(root, source))
    definitions = _definitions(root, source)
    sites = _sites(root, source, definitions, directives)
    concerns.sort(key=lambda item: (item.span.start_byte, item.kind))
    errors = [
        item.span
        for item in concerns
        if item.kind
        in {
            ConcernKind.SYNTAX_ERROR,
            ConcernKind.INVALID_ENCODING,
            ConcernKind.LANGUAGE_VERSION_ERROR,
        }
    ]
    return Syntax(
        definitions,
        directives,
        sites,
        tuple(concerns),
        min(errors, key=lambda item: item.start_byte) if errors else None,
        not concerns,
        language_version,
    )


def _language_version(content: bytes, source: _Source, concerns: list[Concern]) -> str | None:
    match = re.search(rb"(?m)^\s*//\s*@dart=(\d+)\.(\d+)(?:\.\d+)?\s*$", content)
    if match is None:
        return None
    version = (int(match.group(1)), int(match.group(2)))
    value = f"{version[0]}.{version[1]}"
    if version < (2, 12) or version > (3, 12):
        concerns.append(
            Concern(
                ConcernKind.LANGUAGE_VERSION_ERROR,
                "Dart language override is outside supported range 2.12 through 3.12.",
                _span_bytes(source, match.start(), match.end()),
            )
        )
    return value


def _walk(node: _Node) -> Iterator[_Node]:
    yield node
    for child in node.children:
        yield from _walk(child)


def _span_bytes(source: _Source, start: int, end: int) -> Span:
    line = bisect_right(source.starts, start)
    end_line = bisect_right(source.starts, end)
    prefix = source.data[source.starts[line - 1] : start].decode("utf-8", "replace")
    return Span(
        line,
        end_line,
        len(prefix.encode("utf-16-le")) // 2,
        source.data[start:end].decode("utf-8", "replace")[:400],
        start,
        end,
    )


def _named(node: _Node, kind: _NodeKind) -> _Node | None:
    field = node.child_by_field_name(kind)
    if field is not None:
        return field
    return next((child for child in node.named_children if child.kind == kind), None)


def _named_all(node: _Node | None, kind: _NodeKind) -> tuple[_Node, ...]:
    if node is None:
        return ()
    return tuple(child for child in node.named_children if child.kind == kind)


def _first_identifier(node: _Node | None, source: _Source) -> str | None:
    if node is None:
        return None
    found = next(
        (
            child
            for child in _walk(node)
            if child.kind in {_NodeKind.IDENTIFIER, _NodeKind.TYPE_IDENTIFIER}
        ),
        None,
    )
    return source.text(found) if found is not None else None


def _literal_uri(node: _Node | None, source: _Source) -> str | None:
    if node is None:
        return None
    scanned = _string_sequence(source.data, node.start_byte, node.end_byte)
    if scanned is not None:
        return scanned
    literals = tuple(
        child
        for child in _walk(node)
        if child.kind in {_NodeKind.STRING_LITERAL, _NodeKind.RAW_STRING_LITERAL}
        and not any(
            descendant.kind in {_NodeKind.STRING_LITERAL, _NodeKind.RAW_STRING_LITERAL}
            for descendant in child.named_children
        )
    )
    if not literals:
        return None
    pieces = tuple(_decode_dart_string(source.text(item)) for item in literals)
    if any(piece is None for piece in pieces):
        return None
    return "".join(piece for piece in pieces if piece is not None)


def _decode_dart_string(raw: str) -> str | None:
    opening = re.match(r"""(?P<raw>[rR])?(?P<quote>'''|\x22\x22\x22|'|\x22)""", raw)
    if opening is None:
        return None
    delimiter = opening.group("quote")
    if len(raw) < opening.end() + len(delimiter) or not raw.endswith(delimiter):
        return None
    content = raw[opening.end() : -len(delimiter)]
    if opening.group("raw") is not None:
        return content if re.search(r"\$", content) is None else None
    decoded: list[str] = []
    end = 0
    # This is the Dart string escape grammar, including the unchanged rejection of
    # interpolation, unknown escapes and Unicode codepoints above the scalar limit.
    pattern = re.compile(
        r"""(?P<text>[^\\$]+)|\\(?:(?P<simple>[\\'\x22$])|(?P<short>[nrtbfv])"""
        r"""|x(?P<hex>[0-9A-Fa-f]{2})"""
        r"""|u(?:\{(?P<long>[0-9A-Fa-f]{1,6})\}|(?P<unicode>[0-9A-Fa-f]{4})))"""
    )
    escapes = {"n": "\n", "r": "\r", "t": "\t", "b": "\b", "f": "\f", "v": "\v"}
    for token in pattern.finditer(content):
        if token.start() != end:
            return None
        text, simple, short = token.group("text", "simple", "short")
        if text is not None:
            decoded.append(text)
        elif simple is not None:
            decoded.append(simple)
        elif short is not None:
            decoded.append(escapes[short])
        else:
            digits = token.group("hex") or token.group("long") or token.group("unicode")
            codepoint = int(digits, 16)
            if codepoint > 0x10FFFF:
                return None
            decoded.append(chr(codepoint))
        end = token.end()
    return "".join(decoded) if end == len(content) else None


def _unclosed_block_comment(content: bytes) -> int | None:
    index = 0
    block_start: int | None = None
    block_depth = 0
    quote = b""
    raw_string = False
    while index < len(content):
        if block_depth:
            if content.startswith(b"/*", index):
                block_depth += 1
                index += 2
            elif content.startswith(b"*/", index):
                block_depth -= 1
                index += 2
                if block_depth == 0:
                    block_start = None
            else:
                index += 1
            continue
        if quote:
            if not raw_string and content[index] == 0x5C:
                index += 2
            elif content.startswith(quote, index):
                index += len(quote)
                quote = b""
                raw_string = False
            else:
                index += 1
            continue
        if content.startswith(b"//", index):
            newline = content.find(b"\n", index + 2)
            index = len(content) if newline < 0 else newline + 1
            continue
        if content.startswith(b"/*", index):
            block_start = index
            block_depth = 1
            index += 2
            continue
        raw_string = (
            re.fullmatch(rb"[rR]", content[index : index + 1]) is not None
            and index + 1 < len(content)
            and re.fullmatch(rb"[\x27\x22]", content[index + 1 : index + 2]) is not None
        )
        if raw_string:
            index += 1
        if re.fullmatch(rb"[\x27\x22]", content[index : index + 1]) is not None:
            quote_byte = content[index : index + 1]
            quote = quote_byte * (3 if content.startswith(quote_byte * 3, index) else 1)
            index += len(quote)
            continue
        index += 1
    return block_start if block_depth else None


def _directive_uri(node: _Node, source: _Source) -> str | None:
    start = node.start_byte
    end = node.end_byte
    keyword = re.match(rb"(?:import|export|part)\b", source.data[start:end])
    if keyword is None:
        return None
    return _string_sequence(source.data, start + keyword.end(), end)


def _string_sequence(data: bytes, start: int, end: int) -> str | None:
    index = _skip_trivia(data, start, end)
    pieces: list[str] = []
    while index < end:
        token_end = _string_end(data, index, end)
        if token_end is None:
            break
        decoded = _decode_dart_string(data[index:token_end].decode("utf-8", "replace"))
        if decoded is None:
            return None
        pieces.append(decoded)
        index = _skip_trivia(data, token_end, end)
    return "".join(pieces) if pieces else None


def _skip_trivia(data: bytes, index: int, end: int) -> int:
    while index < end:
        if re.match(rb"[ \t\r\n]", data[index : index + 1]) is not None:
            index += 1
        elif data.startswith(b"//", index):
            newline = data.find(b"\n", index + 2, end)
            index = end if newline < 0 else newline + 1
        elif data.startswith(b"/*", index):
            depth = 1
            index += 2
            while index < end and depth:
                if data.startswith(b"/*", index):
                    depth += 1
                    index += 2
                elif data.startswith(b"*/", index):
                    depth -= 1
                    index += 2
                else:
                    index += 1
        else:
            break
    return index


def _string_end(data: bytes, index: int, end: int) -> int | None:
    if (
        re.fullmatch(rb"[rR]", data[index : index + 1]) is not None
        and re.fullmatch(rb"[\x27\x22]", data[index + 1 : index + 2]) is not None
    ):
        index += 1
    quote = data[index : index + 1]
    if re.fullmatch(rb"[\x27\x22]", quote) is None:
        return None
    delimiter = quote * (3 if data.startswith(quote * 3, index) else 1)
    cursor = index + len(delimiter)
    raw = re.fullmatch(rb"[rR]", data[max(0, index - 1) : index]) is not None
    while cursor < end:
        if not raw and re.fullmatch(rb"\\\\", data[cursor : cursor + 1]) is not None:
            cursor += 2
        elif data.startswith(delimiter, cursor):
            return cursor + len(delimiter)
        else:
            cursor += 1
    return None


def _directives(root: _Node, source: _Source, concerns: list[Concern]) -> tuple[Directive, ...]:
    result: list[Directive] = []
    for node in root.named_children:
        if node.kind == _NodeKind.LIBRARY_NAME:
            result.append(
                Directive(DirectiveKind.LIBRARY, source.span(node), _text_children(node, source))
            )
        elif node.kind == _NodeKind.PART_DIRECTIVE:
            uri = _named(node, _NodeKind.URI)
            target = _literal_uri(uri, source)
            if target is None:
                concerns.append(
                    Concern(
                        ConcernKind.UNSUPPORTED_DIRECTIVE,
                        "Part URI is not a plain string.",
                        source.span(node),
                    )
                )
            result.append(Directive(DirectiveKind.PART, source.span(node), target))
        elif node.kind == _NodeKind.PART_OF_DIRECTIVE:
            uri = _named(node, _NodeKind.URI)
            target = _literal_uri(uri, source) if uri is not None else _text_children(node, source)
            if target is None:
                concerns.append(
                    Concern(
                        ConcernKind.UNSUPPORTED_DIRECTIVE,
                        "Part owner is not a literal or library name.",
                        source.span(node),
                    )
                )
            result.append(Directive(DirectiveKind.PART_OF, source.span(node), target))
        elif node.kind == _NodeKind.IMPORT_OR_EXPORT:
            directive = next(
                (
                    item
                    for item in node.named_children
                    if item.kind in {_NodeKind.LIBRARY_IMPORT, _NodeKind.LIBRARY_EXPORT}
                ),
                None,
            )
            if directive is not None:
                result.append(_library_directive(directive, source, concerns))
    return tuple(sorted(result, key=lambda item: item.span.start_byte))


def _library_directive(node: _Node, source: _Source, concerns: list[Concern]) -> Directive:
    kind: DirectiveKind = (
        DirectiveKind.IMPORT if node.kind == _NodeKind.LIBRARY_IMPORT else DirectiveKind.EXPORT
    )
    spec = _named(node, _NodeKind.IMPORT_SPECIFICATION) or _named(
        node, _NodeKind.EXPORT_SPECIFICATION
    )
    if spec is None:
        spec = node
    uri = None
    if spec is not None:
        uri = _named(spec, _NodeKind.CONFIGURABLE_URI) or _named(spec, _NodeKind.URI)
        if uri is None:
            uri = next(
                (item for item in _walk(spec) if item.kind == _NodeKind.CONFIGURABLE_URI),
                None,
            )
    primary_node = _named(uri, _NodeKind.URI) if uri is not None else None
    if primary_node is None:
        primary_node = uri
    primary = _directive_uri(node, source) or _literal_uri(primary_node, source)
    alternatives = _conditional_uris(uri, source, concerns)
    if primary is None:
        concerns.append(
            Concern(
                ConcernKind.UNSUPPORTED_DIRECTIVE,
                "Import/export URI is not a plain string.",
                source.span(node),
            )
        )
    combinators: list[tuple[Combinator, tuple[str, ...]]] = []
    show: list[str] = []
    hide: list[str] = []
    if spec is not None:
        for item in _named_all(spec, _NodeKind.COMBINATOR):
            mode = Combinator(source.text(item.children[0]))
            names = [
                source.text(child)
                for child in item.named_children
                if child.kind == _NodeKind.IDENTIFIER
            ]
            combinators.append((mode, tuple(names)))
            (show if mode == Combinator.SHOW else hide).extend(names)
    prefix = None
    deferred = False
    if spec is not None:
        text = source.text(spec)
        deferred = bool(re.search(r"\bdeferred\s+as\b", text))
        prefix_node = _named(spec, _NodeKind.IMPORT_PREFIX)
        prefix = (
            _first_identifier(prefix_node, source)
            if prefix_node is not None
            else next(
                (source.text(item) for item in _named_all(spec, _NodeKind.IDENTIFIER)),
                None,
            )
        )
    return Directive(
        kind,
        source.span(node),
        primary,
        prefix,
        deferred,
        tuple(show),
        tuple(hide),
        tuple(combinators),
        alternatives,
    )


def _conditional_uris(
    uri: _Node | None, source: _Source, concerns: list[Concern]
) -> tuple[tuple[str, str], ...]:
    alternatives: list[tuple[str, str]] = []
    if uri is not None:
        configurable = uri if uri.kind == _NodeKind.CONFIGURABLE_URI else None
        for choice in _named_all(configurable, _NodeKind.CONFIGURATION_URI):
            condition_node = _named(choice, _NodeKind.CONFIGURATION_URI_CONDITION)
            alternative = _literal_uri(_named(choice, _NodeKind.URI), source)
            if condition_node is None or alternative is None:
                concerns.append(
                    Concern(
                        ConcernKind.UNSUPPORTED_DIRECTIVE,
                        "Conditional URI is not literal.",
                        source.span(choice),
                    )
                )
                continue
            condition = source.text(condition_node).strip()[1:-1].strip()
            alternatives.append((condition, alternative))
    return tuple(alternatives)


def _text_children(node: _Node, source: _Source) -> str:
    return ".".join(
        source.text(child) for child in _walk(node) if child.kind == _NodeKind.IDENTIFIER
    )


def _definitions(root: _Node, source: _Source) -> tuple[Definition, ...]:
    result: list[Definition] = []
    for node in root.named_children:
        if node.kind in _DECLARATIONS:
            result.append(_classifier(node, source))
        elif node.kind == _NodeKind.FUNCTION_SIGNATURE:
            result.append(_function(node, source))
        elif node.kind in {_NodeKind.GETTER_SIGNATURE, _NodeKind.SETTER_SIGNATURE}:
            result.append(_top_level_accessor(node, source))
        elif node.kind == _NodeKind.TOP_LEVEL_VARIABLE_DECLARATION:
            declaration = next(
                (item for item in node.named_children if item.kind == _NodeKind.DECLARATION), node
            )
            result.extend(_variables(declaration, source, DefinitionKind.VARIABLE))
        elif node.kind in {
            _NodeKind.STATIC_FINAL_DECLARATION_LIST,
            _NodeKind.INITIALIZED_IDENTIFIER_LIST,
        }:
            result.extend(_variables(node, source, DefinitionKind.VARIABLE))
        elif node.kind == _NodeKind.DECLARATION:
            result.extend(_variables(node, source, DefinitionKind.VARIABLE))
    return tuple(sorted(result, key=lambda item: item.span.start_byte))


def _classifier(node: _Node, source: _Source) -> Definition:
    name_node = _named(node, _NodeKind.NAME) or next(
        (
            child
            for child in node.named_children
            if child.kind in {_NodeKind.IDENTIFIER, _NodeKind.TYPE_IDENTIFIER}
        ),
        None,
    )
    name = source.text(name_node) if name_node is not None else ""
    kind = _classifier_kind(node)
    extends, with_types, implements, type_parameters = _classifier_relations(node, source)
    body = _named(node, _NodeKind.BODY) or next(
        (
            child
            for child in node.named_children
            if child.kind in {_NodeKind.CLASS_BODY, _NodeKind.ENUM_BODY}
        ),
        None,
    )
    members, enum_members, enum_member_spans = _classifier_members(node, body, source)
    alias = _classifier_alias(node, kind, name_node, source)
    modifiers = _classifier_modifiers(node, name_node, source)
    return Definition(
        name,
        kind,
        source.span(node),
        _visibility(name),
        type_parameters,
        extends,
        with_types,
        implements,
        alias,
        enum_members,
        members,
        modifiers=modifiers,
        enum_member_spans=enum_member_spans,
    )


def _classifier_kind(
    node: _Node,
) -> DefinitionKind:
    if node.kind == _NodeKind.CLASS_DEFINITION:
        return (
            DefinitionKind.INTERFACE
            if any(child.kind == _NodeKind.INTERFACE for child in node.children)
            else DefinitionKind.CLASS
        )
    if node.kind == _NodeKind.MIXIN_DECLARATION:
        return DefinitionKind.MIXIN
    if node.kind == _NodeKind.ENUM_DECLARATION:
        return DefinitionKind.ENUM
    if node.kind == _NodeKind.EXTENSION_DECLARATION:
        return DefinitionKind.EXTENSION
    if node.kind == _NodeKind.EXTENSION_TYPE_DECLARATION:
        return DefinitionKind.EXTENSION_TYPE
    return DefinitionKind.TYPEDEF


def _classifier_relations(
    node: _Node, source: _Source
) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
    superclass = _named(node, _NodeKind.SUPERCLASS)
    extends = _type_children(superclass, source)
    mixins = (_named(superclass, _NodeKind.MIXINS) if superclass is not None else None) or _named(
        node, _NodeKind.MIXINS
    )
    with_types = _type_children(mixins, source)
    implements = _type_children(_named(node, _NodeKind.INTERFACES), source)
    type_node = _named(node, _NodeKind.TYPE_PARAMETERS)
    type_parameters = (
        tuple(
            source.text(child.named_children[0])
            for child in _named_all(type_node, _NodeKind.TYPE_PARAMETER)
            if child.named_children
        )
        if type_node is not None
        else ()
    )
    return extends[:1], with_types, implements, type_parameters


def _type_children(node: _Node | None, source: _Source) -> tuple[str, ...]:
    if node is None:
        return ()
    children = node.named_children
    names: list[str] = []
    index = 0
    while index < len(children):
        child = children[index]
        if child.kind in {_NodeKind.TYPE_IDENTIFIER, _NodeKind.TYPE_NAME, _NodeKind.GENERIC_TYPE}:
            value = source.text(child)
            if index + 1 < len(children) and children[index + 1].kind == _NodeKind.TYPE_ARGUMENTS:
                value += source.text(children[index + 1])
                index += 1
            names.append(value)
        index += 1
    return tuple(names)


def _classifier_members(
    node: _Node, body: _Node | None, source: _Source
) -> tuple[tuple[Member, ...], tuple[str, ...], tuple[Span, ...]]:
    if body is None:
        return (), (), ()
    literals: tuple[tuple[str, Span], ...] = ()
    if node.kind == _NodeKind.ENUM_DECLARATION:
        literals = tuple(
            (source.text(name), source.span(name))
            for constant in _named_all(body, _NodeKind.ENUM_CONSTANT)
            if (name := _named(constant, _NodeKind.NAME)) is not None
        )
    members: list[Member] = []
    children = body.named_children
    for index, child in enumerate(children):
        following = (
            children[index + 1]
            if index + 1 < len(children)
            and children[index + 1].kind
            in {_NodeKind.FUNCTION_BODY, _NodeKind.FUNCTION_EXPRESSION_BODY}
            else None
        )
        if child.kind == _NodeKind.DECLARATION:
            members.extend(_member_declaration(child, source))
        elif child.kind == _NodeKind.METHOD_SIGNATURE:
            members.append(_member_method(child, following, source))
    return (
        tuple(members),
        tuple(name for name, _ in literals),
        tuple(span for _, span in literals),
    )


def _classifier_alias(
    node: _Node,
    kind: DefinitionKind,
    name_node: _Node | None,
    source: _Source,
) -> str | None:
    if kind != DefinitionKind.TYPEDEF:
        return None
    position = next((i for i, child in enumerate(node.named_children) if child == name_node), -1)
    alias_node = next(
        (
            child
            for child in node.named_children[position + 1 :]
            if child.kind
            in {_NodeKind.FUNCTION_TYPE, _NodeKind.TYPE_IDENTIFIER, _NodeKind.GENERIC_TYPE}
        ),
        None,
    )
    return source.text(alias_node) if alias_node is not None else None


def _classifier_modifiers(
    node: _Node, name_node: _Node | None, source: _Source
) -> tuple[Modifier, ...]:
    prefix = (
        source.data[node.start_byte : name_node.start_byte].decode("utf-8", "replace")
        if name_node is not None
        else _prefix(node, source)
    )
    return tuple(word for word in Modifier if re.search(rf"\b{word}\b", prefix))


def _member_declaration(node: _Node, source: _Source) -> list[Member]:
    constructor = next(
        (
            child
            for child in node.named_children
            if child.kind
            in {
                _NodeKind.CONSTRUCTOR_SIGNATURE,
                _NodeKind.CONSTANT_CONSTRUCTOR_SIGNATURE,
                _NodeKind.REDIRECTING_FACTORY_CONSTRUCTOR_SIGNATURE,
            }
        ),
        None,
    )
    if constructor is not None:
        name_nodes = [
            child for child in constructor.named_children if child.kind == _NodeKind.IDENTIFIER
        ]
        name = (
            ".".join(source.text(item) for item in name_nodes)
            or _first_identifier(constructor, source)
            or ""
        )
        params = _parameters(_parameter_list(constructor), source)
        initializers = _named(node, _NodeKind.INITIALIZERS)
        redirects = _redirect(node, source)
        return [
            Member(
                name,
                MemberKind.CONSTRUCTOR,
                _member_span(node, None, source),
                visibility=_visibility(name),
                parameters=params,
                constructor_initializers=tuple(
                    source.text(item) for item in initializers.named_children
                )
                if initializers
                else (),
                redirect=redirects,
                factory=constructor.kind
                in {
                    _NodeKind.FACTORY_CONSTRUCTOR_SIGNATURE,
                    _NodeKind.REDIRECTING_FACTORY_CONSTRUCTOR_SIGNATURE,
                },
                constant=source.text(node).lstrip().startswith("const"),
            )
        ]
    signature = next(
        (
            child
            for child in node.named_children
            if child.kind
            in {
                _NodeKind.FUNCTION_SIGNATURE,
                _NodeKind.GETTER_SIGNATURE,
                _NodeKind.SETTER_SIGNATURE,
            }
        ),
        None,
    )
    if signature is not None:
        return [_member_method(node, None, source)]
    return _variables(node, source, MemberKind.FIELD)


def _member_method(node: _Node, body: _Node | None, source: _Source) -> Member:
    inner = node.named_children[0] if node.named_children else node
    signature = _named(inner, _NodeKind.FUNCTION_SIGNATURE) or inner
    factory = inner.kind == _NodeKind.FACTORY_CONSTRUCTOR_SIGNATURE
    constructor = factory or inner.kind in {
        _NodeKind.CONSTRUCTOR_SIGNATURE,
        _NodeKind.CONSTANT_CONSTRUCTOR_SIGNATURE,
        _NodeKind.REDIRECTING_FACTORY_CONSTRUCTOR_SIGNATURE,
    }
    getter = inner.kind == _NodeKind.GETTER_SIGNATURE
    setter = inner.kind == _NodeKind.SETTER_SIGNATURE
    operator = inner.kind == _NodeKind.OPERATOR_SIGNATURE
    name_node = _named(signature, _NodeKind.NAME) or _named(inner, _NodeKind.NAME)
    if constructor:
        name_nodes = [item for item in inner.named_children if item.kind == _NodeKind.IDENTIFIER]
        name = ".".join(source.text(item) for item in name_nodes)
    else:
        name = source.text(name_node) if name_node is not None else _operator_name(inner, source)
    kind: MemberKind = (
        MemberKind.CONSTRUCTOR
        if constructor
        else MemberKind.GETTER
        if getter
        else MemberKind.SETTER
        if setter
        else MemberKind.OPERATOR
        if operator
        else MemberKind.METHOD
    )
    return_type = _return_type(signature, name_node, source)
    params = _parameters(_parameter_list(signature), source)
    modifiers = source.data[node.start_byte : signature.start_byte].decode("utf-8", "replace")
    modifiers += _prefix(node, source)
    return Member(
        name,
        kind,
        _member_span(node, body, source),
        return_type=return_type,
        visibility=_visibility(name),
        static=re.search(r"\bstatic\b", modifiers) is not None,
        abstract=body is None or re.search(r"\babstract\b", modifiers) is not None,
        parameters=params,
        factory=factory,
        redirect=_redirect(node, source),
    )


def _member_span(node: _Node, body: _Node | None, source: _Source) -> Span:
    start = node.start_byte
    parent = node.parent
    if parent is not None:
        siblings = parent.named_children
        position = next((index for index, item in enumerate(siblings) if item == node), -1)
        while position > 0 and siblings[position - 1].kind in {
            _NodeKind.ANNOTATION,
            _NodeKind.DOCUMENTATION_COMMENT,
            _NodeKind.METADATA,
        }:
            position -= 1
            start = siblings[position].start_byte
    end = body.end_byte if body is not None else node.end_byte
    return _span_bytes(source, start, end)


def _parameter_list(node: _Node) -> _Node | None:
    return _named(node, _NodeKind.PARAMETERS) or _named(node, _NodeKind.FORMAL_PARAMETER_LIST)


def _redirect(node: _Node, source: _Source) -> str | None:
    redirect = next(
        (
            child
            for child in node.named_children
            if child.kind
            in {_NodeKind.REDIRECTION, _NodeKind.REDIRECTING_FACTORY_CONSTRUCTOR_SIGNATURE}
        ),
        None,
    )
    if redirect is None:
        return None
    raw = source.text(redirect)
    marker = "=" if redirect.kind == _NodeKind.REDIRECTING_FACTORY_CONSTRUCTOR_SIGNATURE else ":"
    return raw.split(marker, 1)[1].strip() if marker in raw else raw


def _operator_name(node: _Node, source: _Source) -> str:
    operator = next(
        (
            child
            for child in node.named_children
            if child.kind in {_NodeKind.BINARY_OPERATOR, _NodeKind.UNARY_OPERATOR}
        ),
        None,
    )
    if operator is not None:
        return f"operator{source.text(operator)}"
    token = next(
        (
            child
            for child in node.children
            if child.kind in {_NodeKind.INDEX, _NodeKind.INDEX_ASSIGN}
        ),
        None,
    )
    return f"operator{source.text(token)}" if token is not None else MemberKind.OPERATOR


def _top_level_accessor(node: _Node, source: _Source) -> Definition:
    name_node = _named(node, _NodeKind.NAME)
    name = source.text(name_node) if name_node is not None else ""
    kind: DefinitionKind = (
        DefinitionKind.GETTER if node.kind == _NodeKind.GETTER_SIGNATURE else DefinitionKind.SETTER
    )
    return Definition(
        name,
        kind,
        source.span(node),
        _visibility(name),
        return_type=_return_type(node, name_node, source),
        parameters=_parameters(_parameter_list(node), source),
    )


def _function(node: _Node, source: _Source) -> Definition:
    signature = _named(node, _NodeKind.FUNCTION_SIGNATURE) or node
    name_node = _named(signature, _NodeKind.NAME)
    name = source.text(name_node) if name_node is not None else ""
    return_type = _return_type(signature, name_node, source)
    return Definition(
        name,
        DefinitionKind.FUNCTION,
        source.span(node),
        _visibility(name),
        parameters=_parameters(_parameter_list(signature), source),
        return_type=return_type,
    )


def _return_type(signature: _Node, name_node: _Node | None, source: _Source) -> str | None:
    if name_node is None:
        return None
    annotation = _annotation_before(signature, name_node, source)
    if annotation is not None:
        annotation = re.sub(r"\s+(?:get|set)\s*$", "", annotation)
        if re.fullmatch(r"set", annotation) is not None:
            return None
    return annotation


def _parameters(node: _Node | None, source: _Source) -> tuple[Parameter, ...]:
    if node is None:
        return ()
    result: list[Parameter] = []
    for group in node.named_children:
        if group.kind == _NodeKind.FORMAL_PARAMETER:
            result.append(_parameter(group, ParameterKind.POSITIONAL, source))
        elif group.kind == _NodeKind.OPTIONAL_FORMAL_PARAMETERS:
            kind: ParameterKind = (
                ParameterKind.NAMED
                if source.text(group).lstrip().startswith("{")
                else ParameterKind.POSITIONAL
            )
            result.extend(
                _parameter(item, kind, source)
                for item in _named_all(group, _NodeKind.FORMAL_PARAMETER)
            )
    return tuple(result)


def _parameter(node: _Node, kind: ParameterKind, source: _Source) -> Parameter:
    field = next(
        (
            item
            for item in _walk(node)
            if item.kind in {_NodeKind.CONSTRUCTOR_PARAM, _NodeKind.FIELD_FORMAL_PARAMETER}
        ),
        None,
    )
    super_formal = any(
        item.kind in {_NodeKind.SUPER_FORMAL_PARAMETER, _NodeKind.SUPER_PARAMETER}
        for item in _walk(node)
    )
    ids = [
        item
        for item in node.named_children
        if item.kind in {_NodeKind.IDENTIFIER, _NodeKind.TYPE_IDENTIFIER}
    ]
    name_node = (
        ids[-1]
        if ids
        else next((item for item in _walk(node) if item.kind == _NodeKind.IDENTIFIER), None)
    )
    name = source.text(name_node) if name_node is not None else source.text(node)
    annotation = (
        _annotation_before(node, name_node, source)
        if name_node is not None and field is None and not super_formal
        else None
    )
    nested_parameters = _parameter_list(node)
    if annotation is not None and nested_parameters is not None:
        annotation = f"{annotation} Function{source.text(nested_parameters)}"
    default = _parameter_default(node, source)
    before = source.data[node.parent.start_byte : node.start_byte] if node.parent else b""
    required = re.search(rb"\brequired\b", before.rsplit(b",", 1)[-1]) is not None
    optional = kind == ParameterKind.NAMED and not required
    if node.parent is not None and node.parent.kind == _NodeKind.OPTIONAL_FORMAL_PARAMETERS:
        optional = source.text(node.parent).lstrip().startswith("[") or optional
    nullable_or_dynamic = (
        annotation is None
        or annotation.endswith("?")
        or re.fullmatch(r"dynamic", annotation) is not None
    )
    if default is None and optional and nullable_or_dynamic:
        default = "null"
    return Parameter(
        name,
        annotation,
        kind,
        default,
        not super_formal,
        source.span(node),
        field is not None,
        super_formal,
        optional,
        required,
    )


def _parameter_default(node: _Node, source: _Source) -> str | None:
    default = None
    for index, child in enumerate(node.children[:-1]):
        if child.kind in {_NodeKind.EQUALS, _NodeKind.COLON}:
            default = source.text(node.children[index + 1])
            break
    if default is None and node.parent is not None:
        siblings = node.parent.named_children
        position = next((index for index, item in enumerate(siblings) if item == node), -1)
        if position >= 0 and position + 1 < len(siblings):
            following = siblings[position + 1]
            if re.search(rb"=", source.data[node.end_byte : following.start_byte]) is not None:
                default = source.text(following)
    if default is None:
        candidate = next(
            (
                item
                for item in node.named_children
                if item.kind == _NodeKind.DEFAULT_FORMAL_PARAMETER
            ),
            None,
        )
        if candidate is not None:
            default = next(
                (
                    source.text(item)
                    for item in candidate.named_children
                    if item.kind not in {_NodeKind.EMPTY}
                ),
                None,
            )
    return default


@overload
def _variables(node: _Node, source: _Source, kind: Literal[MemberKind.FIELD]) -> list[Member]: ...


@overload
def _variables(
    node: _Node, source: _Source, kind: Literal[DefinitionKind.VARIABLE]
) -> list[Definition]: ...


def _variables(
    node: _Node, source: _Source, kind: MemberKind | DefinitionKind
) -> list[Member] | list[Definition]:
    """Read declaration names and exact annotation/initializer for each comma item."""
    list_node = _variable_list_node(node)
    if list_node is None:
        return []
    items = (
        list_node.named_children
        if list_node.kind
        in {_NodeKind.INITIALIZED_IDENTIFIER_LIST, _NodeKind.STATIC_FINAL_DECLARATION_LIST}
        else (list_node,)
    )
    if kind == MemberKind.FIELD:
        return _field_members(node, items, source)
    return _top_level_variables(node, items, source)


def _variable_list_node(node: _Node) -> _Node | None:
    declaration_types = {
        _NodeKind.INITIALIZED_IDENTIFIER_LIST,
        _NodeKind.STATIC_FINAL_DECLARATION_LIST,
        _NodeKind.INITIALIZED_VARIABLE_DEFINITION,
        _NodeKind.INITIALIZED_IDENTIFIER,
    }
    return (
        node
        if node.kind in declaration_types
        else next((item for item in node.named_children if item.kind in declaration_types), None)
    )


def _field_members(node: _Node, items: Sequence[_Node], source: _Source) -> list[Member]:
    declaration_text = source.text(node)
    members: list[Member] = []
    for item in items:
        name_node = next(
            (child for child in item.named_children if child.kind == _NodeKind.IDENTIFIER), None
        )
        if name_node is None:
            continue
        value = _initializer(item, source)
        name = source.text(name_node)
        members.append(
            Member(
                name,
                MemberKind.FIELD,
                source.span(item),
                annotation=_annotation_before(node, name_node, source),
                visibility=_visibility(name),
                static=re.search(r"\bstatic\b", declaration_text) is not None,
                initializer=value,
                literal=value,
                constant=re.search(r"\bconst\b", declaration_text) is not None,
                final=re.search(r"\bfinal\b", declaration_text) is not None,
                late=re.search(r"\blate\b", declaration_text) is not None,
            )
        )
    return members


def _top_level_variables(node: _Node, items: Sequence[_Node], source: _Source) -> list[Definition]:
    declaration_text = _declaration_text(node, source)
    definitions: list[Definition] = []
    for item in items:
        name_node = next(
            (child for child in item.named_children if child.kind == _NodeKind.IDENTIFIER), None
        )
        if name_node is None:
            continue
        name = source.text(name_node)
        value = _initializer(item, source)
        definitions.append(
            Definition(
                name,
                DefinitionKind.VARIABLE,
                source.span(item),
                _visibility(name),
                return_type=_annotation_before(node, name_node, source),
                initializer=value,
                literal=value,
                constant=re.search(r"\bconst\b", declaration_text) is not None,
                final=re.search(r"\bfinal\b", declaration_text) is not None,
                late=re.search(r"\blate\b", declaration_text) is not None,
            )
        )
    return definitions


def _initializer(node: _Node, source: _Source) -> str | None:
    equal = next(
        (index for index, child in enumerate(node.children) if child.kind == _NodeKind.EQUALS), None
    )
    return (
        source.text(node.children[equal + 1])
        if equal is not None and equal + 1 < len(node.children)
        else None
    )


def _declaration_text(node: _Node, source: _Source) -> str:
    if node.parent is None:
        return source.text(node)
    siblings = node.parent.named_children
    position = next((index for index, item in enumerate(siblings) if item == node), -1)
    modifiers: list[str] = []
    for sibling in reversed(siblings[:position]):
        if sibling.kind in {
            _NodeKind.CONST_BUILTIN,
            _NodeKind.FINAL_BUILTIN,
            _NodeKind.LATE_BUILTIN,
            _NodeKind.STATIC_BUILTIN,
        }:
            modifiers.append(source.text(sibling))
            continue
        if sibling.kind in {
            _NodeKind.TYPE_IDENTIFIER,
            _NodeKind.TYPE_NAME,
            _NodeKind.GENERIC_TYPE,
            _NodeKind.NULLABLE_TYPE,
        }:
            continue
        break
    return " ".join(reversed(modifiers)) or source.text(node)


def _unsupported_concerns(root: _Node, source: _Source) -> tuple[Concern, ...]:
    return tuple(
        Concern(
            ConcernKind.UNSUPPORTED_DECLARATION,
            "Mixin on-constraints are not modeled by this parser.",
            source.span(node),
        )
        for node in _walk(root)
        if node.kind == _NodeKind.MIXIN_DECLARATION
        and any(child.kind == _NodeKind.ON for child in node.children)
    )


def _prefix(node: _Node, source: _Source) -> str:
    if node.parent is None:
        return ""
    siblings = node.parent.named_children
    position = next((index for index, item in enumerate(siblings) if item == node), -1)
    start = siblings[position - 1].end_byte if position > 0 else node.parent.start_byte
    return source.data[start : node.start_byte].decode("utf-8", "replace")


def _visibility(name: str) -> Visibility:
    return Visibility.PRIVATE if name.startswith("_") else Visibility.PUBLIC


def _sites(
    root: _Node,
    source: _Source,
    definitions: tuple[Definition, ...],
    directives: tuple[Directive, ...],
) -> tuple[Site, ...]:
    receiver_names = _typed_receiver_names(root, source, definitions)
    prefixes = frozenset(
        directive.prefix for directive in directives if directive.prefix is not None
    )
    callables = tuple(
        (body, source.text(name))
        for candidate in _walk(root)
        if candidate.kind in {_NodeKind.FUNCTION_SIGNATURE, _NodeKind.METHOD_SIGNATURE}
        if (body := _callable_body(candidate)) is not None
        if (name := _callable_decl_name(candidate)) is not None
    )
    scopes = tuple(
        (node, _scope_name(node, source, callables))
        for node in _walk(root)
        if node.kind
        in {_NodeKind.FUNCTION_BODY, _NodeKind.FUNCTION_EXPRESSION_BODY, _NodeKind.BLOCK}
    )
    result: list[Site] = []
    for node in _walk(root):
        if _inside_directive(node):
            continue
        active = tuple(
            pair
            for pair in scopes
            if pair[0].start_byte <= node.start_byte and node.end_byte <= pair[0].end_byte
        )
        scope_node, scope = max(active, key=lambda pair: pair[0].start_byte, default=(None, None))
        context = (scope, source.span(scope_node) if scope_node is not None else None, len(active))
        parameter_nodes = [
            item for item in _ancestors(node) if item.kind == _NodeKind.FORMAL_PARAMETER
        ]
        parameter_node = parameter_nodes[-1] if parameter_nodes else None
        if node.kind == _NodeKind.FORMAL_PARAMETER:
            parameter_node = node
        if parameter_node is not None:
            parameter_context = _parameter_context(parameter_node, source, scopes)
            if parameter_context is not None:
                context = parameter_context
        elif scope_node is None:
            callable_context = _callable_context(node, source, scopes)
            if callable_context is not None:
                context = callable_context
        closure_scope = _inside_function_expression(node)
        result.extend(
            replace(site, closure_scope=closure_scope)
            for site in _binding_sites(node, source, context, root)
        )
        site = _expression_site(node, source, context, root)
        if site is not None:
            result.append(replace(site, closure_scope=closure_scope))
        result.extend(
            replace(site, closure_scope=closure_scope)
            for site in _reference_sites(node, source, context, receiver_names, prefixes)
        )
    return tuple(sorted(result, key=lambda item: (item.span.start_byte, item.kind)))


def _inside_function_expression(node: _Node) -> bool:
    return any(parent.kind == _NodeKind.FUNCTION_EXPRESSION for parent in _ancestors(node))


def _typed_receiver_names(
    root: _Node, source: _Source, definitions: tuple[Definition, ...]
) -> frozenset[str]:
    names = {
        member.name
        for definition in definitions
        for member in definition.members
        if member.kind == MemberKind.FIELD and member.annotation is not None
    }
    names.update(
        definition.name
        for definition in definitions
        if definition.kind
        in {
            DefinitionKind.CLASS,
            DefinitionKind.INTERFACE,
            DefinitionKind.MIXIN,
            DefinitionKind.ENUM,
            DefinitionKind.EXTENSION_TYPE,
        }
    )
    parameters = (
        parameter
        for definition in definitions
        for parameter in (
            *definition.parameters,
            *(parameter for member in definition.members for parameter in member.parameters),
        )
    )
    names.update(parameter.name for parameter in parameters if parameter.annotation is not None)
    for node in _walk(root):
        if node.kind == _NodeKind.LOCAL_VARIABLE_DECLARATION:
            for definition in _walk(node):
                if definition.kind != _NodeKind.INITIALIZED_VARIABLE_DEFINITION:
                    continue
                name = _named(definition, _NodeKind.NAME)
                if name is not None and _variable_annotation(definition, name, source) is not None:
                    names.add(source.text(name))
        elif node.kind == _NodeKind.FORMAL_PARAMETER:
            parameter = _parameter(node, ParameterKind.POSITIONAL, source)
            if parameter.annotation is not None:
                names.add(parameter.name)
    return frozenset(names)


def _callable_decl_name(node: _Node) -> _Node | None:
    name = _named(node, _NodeKind.NAME)
    if name is not None:
        return name
    signature = next(
        (child for child in node.named_children if child.kind == _NodeKind.FUNCTION_SIGNATURE),
        None,
    )
    return _named(signature, _NodeKind.NAME) if signature is not None else None


def _scope_name(
    node: _Node,
    source: _Source,
    callables: tuple[tuple[_Node, str], ...],
) -> str | None:
    containing = tuple(
        (body.end_byte - body.start_byte, name)
        for body, name in callables
        if body.start_byte <= node.start_byte and node.end_byte <= body.end_byte
    )
    if containing:
        return min(containing, key=lambda item: item[0])[1]
    return _callable_name(node, source)


def _parameter_context(
    node: _Node,
    source: _Source,
    scopes: tuple[tuple[_Node, str | None], ...],
) -> tuple[str | None, Span | None, int] | None:
    ancestors = tuple(_ancestors(node))
    if any(item.kind == _NodeKind.FORMAL_PARAMETER for item in ancestors):
        return None
    callable_node = next(
        (
            item
            for item in ancestors
            if item.kind
            in {
                _NodeKind.FUNCTION_SIGNATURE,
                _NodeKind.FUNCTION_EXPRESSION,
                _NodeKind.CONSTRUCTOR_SIGNATURE,
                _NodeKind.CONSTANT_CONSTRUCTOR_SIGNATURE,
                _NodeKind.FACTORY_CONSTRUCTOR_SIGNATURE,
                _NodeKind.REDIRECTING_FACTORY_CONSTRUCTOR_SIGNATURE,
            }
        ),
        None,
    )
    if callable_node is None:
        return None
    return _callable_context_for(callable_node, source, scopes)


def _callable_context(
    node: _Node,
    source: _Source,
    scopes: tuple[tuple[_Node, str | None], ...],
) -> tuple[str | None, Span | None, int] | None:
    signatures = {
        _NodeKind.FUNCTION_SIGNATURE,
        _NodeKind.METHOD_SIGNATURE,
        _NodeKind.CONSTRUCTOR_SIGNATURE,
        _NodeKind.CONSTANT_CONSTRUCTOR_SIGNATURE,
        _NodeKind.FACTORY_CONSTRUCTOR_SIGNATURE,
        _NodeKind.REDIRECTING_FACTORY_CONSTRUCTOR_SIGNATURE,
        _NodeKind.GETTER_SIGNATURE,
        _NodeKind.SETTER_SIGNATURE,
    }
    callable_node = next((item for item in _ancestors(node) if item.kind in signatures), None)
    if callable_node is None:
        callable_node = next(
            (
                child
                for ancestor in _ancestors(node)
                for child in ancestor.named_children
                if child.kind in signatures
                and child.start_byte <= node.start_byte
                and node.end_byte <= ancestor.end_byte
            ),
            None,
        )
    return (
        _callable_context_for(callable_node, source, scopes) if callable_node is not None else None
    )


def _callable_context_for(
    callable_node: _Node,
    source: _Source,
    scopes: tuple[tuple[_Node, str | None], ...],
) -> tuple[str | None, Span | None, int]:
    owner = callable_node
    if owner.parent is not None and owner.parent.kind == _NodeKind.METHOD_SIGNATURE:
        owner = owner.parent
    body = _callable_body(owner)
    scope_name = _callable_name(callable_node, source)
    if callable_node.kind in {
        _NodeKind.CONSTRUCTOR_SIGNATURE,
        _NodeKind.CONSTANT_CONSTRUCTOR_SIGNATURE,
        _NodeKind.FACTORY_CONSTRUCTOR_SIGNATURE,
        _NodeKind.REDIRECTING_FACTORY_CONSTRUCTOR_SIGNATURE,
    }:
        names = tuple(
            source.text(child)
            for child in callable_node.named_children
            if child.kind == _NodeKind.IDENTIFIER
        )
        scope_name = ".".join(names) if names else scope_name
    if body is None:
        return scope_name, source.span(owner), 0
    body_scopes = tuple(
        candidate for candidate, _ in scopes if candidate == body or candidate.parent == body
    )
    scope_node = max(body_scopes, key=lambda item: item.start_byte, default=body)
    depth = sum(
        1
        for candidate, _ in scopes
        if candidate.start_byte <= scope_node.start_byte
        and scope_node.end_byte <= candidate.end_byte
    )
    return scope_name, source.span(scope_node), depth


def _callable_body(owner: _Node) -> _Node | None:
    if owner.kind == _NodeKind.FUNCTION_EXPRESSION:
        return next(
            (
                child
                for child in owner.named_children
                if child.kind == _NodeKind.FUNCTION_EXPRESSION_BODY
            ),
            None,
        )
    parent = owner.parent
    if parent is None:
        return None
    siblings = parent.named_children
    position = next((index for index, item in enumerate(siblings) if item == owner), -1)
    if position < 0:
        return None
    for sibling in siblings[position + 1 :]:
        if sibling.kind in {_NodeKind.FUNCTION_BODY, _NodeKind.FUNCTION_EXPRESSION_BODY}:
            return sibling
        if sibling.kind in {
            _NodeKind.FUNCTION_SIGNATURE,
            _NodeKind.METHOD_SIGNATURE,
            _NodeKind.FUNCTION_EXPRESSION,
        }:
            break
    return None


def _binding_sites(
    node: _Node,
    source: _Source,
    context: tuple[str | None, Span | None, int],
    root: _Node,
) -> tuple[Site, ...]:
    scope, scope_span, scope_depth = context
    if node.kind == _NodeKind.LOCAL_VARIABLE_DECLARATION:
        return tuple(
            Site(
                SiteKind.BINDING,
                source.text(child),
                source.span(child),
                source.text(name),
                assigned_name=source.text(name),
                initializer=_local_initializer(child, source),
                initializer_source=_canonical_local_initializer(root, child, source),
                assignment_annotation=_variable_annotation(child, name, source),
                scope=scope,
                scope_span=scope_span,
                scope_depth=scope_depth,
            )
            for child in _walk(node)
            if child.kind == _NodeKind.INITIALIZED_VARIABLE_DEFINITION
            if (name := _named(child, _NodeKind.NAME)) is not None
        )
    if node.kind != _NodeKind.FORMAL_PARAMETER:
        return ()
    if any(parent.kind == _NodeKind.FORMAL_PARAMETER for parent in _ancestors(node)):
        return ()
    parameter = _parameter(node, ParameterKind.POSITIONAL, source)
    sites = [
        Site(
            SiteKind.BINDING,
            source.text(node),
            source.span(node),
            parameter.name,
            assignment_annotation=parameter.annotation,
            initializer=parameter.default,
            scope=scope,
            scope_span=scope_span,
            scope_depth=scope_depth,
        )
    ]
    if parameter.field_formal or parameter.super_formal:
        kind: SiteKind = SiteKind.FIELD_FORMAL if parameter.field_formal else SiteKind.SUPER_FORMAL
        sites.append(
            Site(
                kind,
                source.text(node),
                source.span(node),
                parameter.name,
                use=SiteUse.TYPE,
                scope=scope,
                scope_span=scope_span,
                scope_depth=scope_depth,
            )
        )
    return tuple(sites)


def _local_initializer(node: _Node, source: _Source) -> str | None:
    value = _named(node, _NodeKind.VALUE)
    if value is None:
        return None
    selectors = _named_all(node, _NodeKind.SELECTOR)
    return source.text(value) + "".join(source.text(item) for item in selectors)


def _canonical_local_initializer(root: _Node, node: _Node, source: _Source) -> str | None:
    value = _named(node, _NodeKind.VALUE)
    if value is None:
        return None
    selectors = _named_all(node, _NodeKind.SELECTOR)
    end = selectors[-1].end_byte if selectors else value.end_byte
    return _canonical_range(root, source, value.start_byte, end)


def _canonical_range(root: _Node, source: _Source, start: int, end: int) -> str:
    tokens = list(_source_tokens(root, start, end))
    output = ""
    previous_word = False
    for token in tokens:
        value = source.text(token)
        lexeme = _lexeme(value)
        closes_group = lexeme in {
            _Lexeme.CLOSE_PAREN, _Lexeme.CLOSE_BRACKET, _Lexeme.CLOSE_BRACE
        }
        if lexeme == _Lexeme.COMMA:
            output = output.rstrip() + ", "
            previous_word = False
        elif lexeme in {
            _Lexeme.CLOSE_PAREN,
            _Lexeme.CLOSE_BRACKET,
            _Lexeme.CLOSE_BRACE,
            _Lexeme.DOT,
            _Lexeme.NULL_DOT,
            _Lexeme.NULL_CASCADE,
            _Lexeme.CASCADE,
            _Lexeme.NULL_INDEX,
            _Lexeme.ASSERT_DOT,
            _Lexeme.NULL_OPEN_INDEX,
        }:
            output = output.rstrip() + value
            prefix = output[:-1].rstrip()
            if closes_group and prefix.endswith(","):
                output = prefix[:-1].rstrip() + value
            previous_word = closes_group
        elif lexeme in {_Lexeme.OPEN_PAREN, _Lexeme.OPEN_BRACKET, _Lexeme.OPEN_BRACE}:
            output = output.rstrip() + value
            previous_word = False
        elif lexeme in {
            _Lexeme.EQUALS,
            _Lexeme.ARROW,
            _Lexeme.PLUS,
            _Lexeme.MINUS,
            _Lexeme.STAR,
            _Lexeme.SLASH,
            _Lexeme.TRUNCATE,
            _Lexeme.MODULO,
            _Lexeme.COALESCE,
            _Lexeme.AND,
            _Lexeme.OR,
            _Lexeme.EQUAL,
            _Lexeme.NOT_EQUAL,
            _Lexeme.LESS,
            _Lexeme.GREATER,
            _Lexeme.LESS_EQUAL,
            _Lexeme.GREATER_EQUAL,
            _Lexeme.COALESCE_ASSIGN,
        }:
            if lexeme in {_Lexeme.LESS, _Lexeme.GREATER} and any(
                parent.kind == _NodeKind.TYPE_ARGUMENTS for parent in _ancestors(token)
            ):
                output = output.rstrip() + value
                previous_word = lexeme == _Lexeme.GREATER
            else:
                output = output.rstrip() + f" {value} "
                previous_word = False
        else:
            word = bool(value) and (value[0].isalnum() or re.match(r"[_$\"']", value) is not None)
            if previous_word and word:
                output += " "
            output += value
            previous_word = word
    return output.strip()


def _source_tokens(node: _Node, start: int, end: int) -> Iterator[_Node]:
    if node.end_byte <= start or node.start_byte >= end:
        return
    if node.kind in {_NodeKind.COMMENT, _NodeKind.DOCUMENTATION_COMMENT}:
        return
    if node.kind == _NodeKind.STRING_LITERAL:
        yield node
        return
    if not node.children:
        if node.kind not in {_NodeKind.COMMENT, _NodeKind.DOCUMENTATION_COMMENT}:
            yield node
        return
    for child in node.children:
        if child.start_byte >= end:
            break
        yield from _source_tokens(child, start, end)


def _expression_site(
    node: _Node,
    source: _Source,
    context: tuple[str | None, Span | None, int],
    root: _Node,
) -> Site | None:
    scope, scope_span, scope_depth = context
    if node.kind in {_NodeKind.NEW_EXPRESSION, _NodeKind.CONST_OBJECT_EXPRESSION}:
        return _creation(node, source, scope, scope_span, scope_depth, root)
    if node.kind in {_NodeKind.ASSIGNMENT_EXPRESSION, _NodeKind.COMPOUND_ASSIGNMENT_EXPRESSION}:
        left, right = _named(node, _NodeKind.LEFT), _named(node, _NodeKind.RIGHT)
        name, receiver, computed = _member_parts(left, source) if left else (None, None, False)
        return Site(
            SiteKind.ASSIGNMENT,
            source.text(node),
            source.span(node),
            name,
            receiver,
            initializer=source.text(right) if right else None,
            use=_assignment_use(node, source),
            computed=computed,
            scope=scope,
            scope_span=scope_span,
            scope_depth=scope_depth,
        )
    if node.kind == _NodeKind.ARGUMENTS:
        return _call_site(node, source, scope, scope_span, scope_depth, root)
    return None


def _reference_sites(
    node: _Node,
    source: _Source,
    context: tuple[str | None, Span | None, int],
    receiver_names: frozenset[str],
    prefixes: frozenset[str],
) -> tuple[Site, ...]:
    scope, scope_span, scope_depth = context
    if node.kind in {_NodeKind.TYPE_IDENTIFIER, _NodeKind.GENERIC_TYPE, _NodeKind.FUNCTION_TYPE}:
        if node.parent is None or node.parent.kind in {
            _NodeKind.TYPE_PARAMETERS,
            _NodeKind.TYPE_PARAMETER,
        }:
            return ()
        name, receiver, computed = _member_parts(node, source)
        return (
            Site(
                _type_site_kind(node),
                source.text(node),
                source.span(node),
                name,
                receiver,
                use=SiteUse.TYPE,
                computed=computed,
                scope=scope,
                scope_span=scope_span,
                scope_depth=scope_depth,
            ),
        )
    if node.kind != _NodeKind.IDENTIFIER or _is_declaration_name(node):
        return ()
    if _is_member_receiver(node):
        name = source.text(node)
        if name in receiver_names and name not in prefixes and _receiver_needs_site(node):
            return (
                Site(
                    SiteKind.REFERENCE,
                    name,
                    source.span(node),
                    name,
                    scope=scope,
                    scope_span=scope_span,
                    scope_depth=scope_depth,
                ),
            )
        return ()
    if _is_member_selector(node):
        if _is_call_selector(node):
            return ()
        name, receiver, computed, expression, member_span = _member_reference(node, source)
        return (
            Site(
                SiteKind.REFERENCE,
                expression,
                member_span,
                name,
                receiver,
                use=_reference_use(node, source),
                computed=computed,
                scope=scope,
                scope_span=scope_span,
                scope_depth=scope_depth,
            ),
        )
    if _is_type_context(node) or _is_call_callee(node):
        return ()
    return (
        Site(
            SiteKind.REFERENCE,
            source.text(node),
            source.span(node),
            source.text(node),
            use=_reference_use(node, source),
            scope=scope,
            scope_span=scope_span,
            scope_depth=scope_depth,
        ),
    )


def _ancestors(node: _Node) -> Iterator[_Node]:
    parent = node.parent
    while parent is not None:
        yield parent
        parent = parent.parent


def _inside_directive(node: _Node) -> bool:
    return any(
        parent.kind
        in {
            _NodeKind.IMPORT_OR_EXPORT,
            _NodeKind.LIBRARY_NAME,
            _NodeKind.PART_DIRECTIVE,
            _NodeKind.PART_OF_DIRECTIVE,
        }
        for parent in _ancestors(node)
    )


def _type_site_kind(
    node: _Node,
) -> SiteKind:
    for parent in _ancestors(node):
        if parent.kind == _NodeKind.INTERFACES:
            return SiteKind.IMPLEMENTS
        if parent.kind == _NodeKind.MIXINS:
            return SiteKind.WITH
        if parent.kind == _NodeKind.SUPERCLASS:
            return SiteKind.EXTENDS
        if parent.kind in {_NodeKind.CLASS_BODY, _NodeKind.PROGRAM}:
            break
    return SiteKind.TYPE


def _is_call_selector(node: _Node) -> bool:
    selector = node.parent.parent if node.parent is not None else None
    if selector is None or selector.kind != _NodeKind.SELECTOR or selector.parent is None:
        return False
    siblings = selector.parent.named_children
    position = next((index for index, item in enumerate(siblings) if item == selector), -1)
    return any(
        item.kind == _NodeKind.SELECTOR and _named(item, _NodeKind.ARGUMENT_PART) is not None
        for item in siblings[position + 1 :]
    )


def _is_member_receiver(node: _Node) -> bool:
    parent = node.parent
    if parent is None:
        return False
    siblings = parent.named_children
    position = next((index for index, item in enumerate(siblings) if item == node), -1)
    return position >= 0 and any(
        item.kind == _NodeKind.SELECTOR
        and any(
            child.kind == _NodeKind.UNCONDITIONAL_ASSIGNABLE_SELECTOR
            for child in item.named_children
        )
        for item in siblings[position + 1 :]
    )


def _receiver_needs_site(node: _Node) -> bool:
    parent = node.parent
    if parent is None:
        return False
    siblings = parent.named_children
    position = next((index for index, item in enumerate(siblings) if item == node), -1)
    selectors = tuple(item for item in siblings[position + 1 :] if item.kind == _NodeKind.SELECTOR)
    if any(
        _named(item, _NodeKind.ARGUMENT_PART) is not None or _selector_has_index(item)
        for item in selectors
    ):
        return True
    return any(
        any(
            child.kind == _NodeKind.UNCONDITIONAL_ASSIGNABLE_SELECTOR
            for child in item.named_children
        )
        for item in selectors
    )


def _selector_has_index(node: _Node) -> bool:
    selector = next(
        (
            item
            for item in node.named_children
            if item.kind == _NodeKind.UNCONDITIONAL_ASSIGNABLE_SELECTOR
        ),
        None,
    )
    return selector is not None and _named(selector, _NodeKind.INDEX_SELECTOR) is not None


def _is_call_callee(node: _Node) -> bool:
    parent = node.parent
    if parent is None:
        return False
    siblings = parent.named_children
    position = next((index for index, item in enumerate(siblings) if item == node), -1)
    return position >= 0 and any(
        item.kind == _NodeKind.SELECTOR and _named(item, _NodeKind.ARGUMENT_PART) is not None
        for item in siblings[position + 1 :]
    )


def _callable_name(node: _Node, source: _Source) -> str | None:
    for parent in (node, *_ancestors(node)):
        if parent.kind in {
            _NodeKind.FUNCTION_SIGNATURE,
            _NodeKind.METHOD_SIGNATURE,
            _NodeKind.METHOD_DECLARATION,
            _NodeKind.FUNCTION_DECLARATION,
            _NodeKind.GETTER_SIGNATURE,
            _NodeKind.SETTER_SIGNATURE,
            _NodeKind.FUNCTION_EXPRESSION,
        }:
            name = _named(parent, _NodeKind.NAME)
            if name is not None:
                return source.text(name)
        if (
            parent.kind in {_NodeKind.FUNCTION_BODY, _NodeKind.FUNCTION_EXPRESSION_BODY}
            and parent.parent is not None
        ):
            siblings = parent.parent.named_children
            index = next((i for i, item in enumerate(siblings) if item == parent), -1)
            for signature in reversed(siblings[:index]):
                if signature.kind in {_NodeKind.FUNCTION_SIGNATURE, _NodeKind.METHOD_SIGNATURE}:
                    name = _named(signature, _NodeKind.NAME)
                    if name is not None:
                        return source.text(name)
    return None


def _creation(
    node: _Node,
    source: _Source,
    scope: str | None,
    scope_span: Span | None,
    scope_depth: int,
    root: _Node,
) -> Site:
    type_node = next(
        (
            child
            for child in node.named_children
            if child.kind
            in {
                _NodeKind.TYPE_IDENTIFIER,
                _NodeKind.TYPE_NAME,
                _NodeKind.GENERIC_TYPE,
                _NodeKind.QUALIFIED_TYPE,
            }
        ),
        None,
    )
    args = _named(node, _NodeKind.ARGUMENTS)
    arguments = (
        tuple(source.text(item) for item in _named_all(args, _NodeKind.ARGUMENT)) if args else ()
    )
    name = None
    if type_node is not None:
        suffix = tuple(
            source.text(child)
            for child in node.named_children
            if child.kind == _NodeKind.IDENTIFIER and child.start_byte > type_node.end_byte
        )
        name = ".".join((source.text(type_node), *suffix))
    return Site(
        SiteKind.CREATION,
        source.text(node),
        source.span(node),
        name,
        arguments=arguments,
        scope=scope,
        scope_span=scope_span,
        scope_depth=scope_depth,
        expression_source=_canonical_range(root, source, node.start_byte, node.end_byte),
    )


def _call_site(
    node: _Node,
    source: _Source,
    scope: str | None,
    scope_span: Span | None,
    scope_depth: int,
    root: _Node,
) -> Site | None:
    parent = node.parent
    if parent is None or parent.kind != _NodeKind.ARGUMENT_PART:
        return None
    selector = parent.parent
    if selector is None or selector.kind != _NodeKind.SELECTOR:
        return None
    parent = selector.parent
    previous = None
    if parent is not None:
        siblings = parent.named_children
        position = next((i for i, item in enumerate(siblings) if item == selector), -1)
        if position > 0:
            previous = siblings[position - 1]
    start = previous.start_byte if previous is not None else selector.start_byte
    while previous is not None and parent is not None:
        siblings = parent.named_children
        position = next((i for i, item in enumerate(siblings) if item == previous), -1)
        if position <= 0:
            break
        earlier = siblings[position - 1]
        if earlier.kind not in {
            _NodeKind.IDENTIFIER,
            _NodeKind.TYPE_IDENTIFIER,
            _NodeKind.SELECTOR,
            _NodeKind.ASSIGNABLE_EXPRESSION,
        }:
            break
        gap = source.data[earlier.end_byte : previous.start_byte]
        if gap.strip():
            break
        previous = earlier
        start = previous.start_byte
    end = selector.end_byte
    call_text = source.data[start:end].decode("utf-8", "replace")
    prior = source.data[start : selector.start_byte].decode("utf-8", "replace").strip()
    name, receiver, computed = _call_name(prior)
    arguments = tuple(source.text(item) for item in _named_all(node, _NodeKind.ARGUMENT))
    return Site(
        SiteKind.CALL,
        call_text,
        _span_bytes(source, start, end),
        name,
        receiver,
        arguments=arguments,
        computed=computed,
        scope=scope,
        scope_span=scope_span,
        scope_depth=scope_depth,
        expression_source=_canonical_range(root, source, start, end),
    )


def _call_name(text: str) -> tuple[str | None, str | None, bool]:
    value = text.rstrip()
    if value.endswith("."):
        value = value[:-1]
    if re.search(r"\.", value) is not None:
        receiver, name = value.rsplit(".", 1)
        return name or None, receiver or None, re.search(r"\[", receiver) is not None
    return value.rsplit(" ", 1)[-1] or None, None, re.search(r"\[", value) is not None


def _member_parts(node: _Node | None, source: _Source) -> tuple[str | None, str | None, bool]:
    if node is None:
        return None, None, False
    text = source.text(node)
    if re.search(r"\.", text) is not None:
        receiver, name = text.rsplit(".", 1)
        return name, receiver, re.search(r"\[", receiver) is not None
    return text, None, re.search(r"\[", text) is not None


def _member_reference(
    node: _Node, source: _Source
) -> tuple[str | None, str | None, bool, str, Span]:
    selector = node.parent
    if selector is None or selector.parent is None:
        return source.text(node), None, False, source.text(node), source.span(node)
    outer_selector = selector.parent
    chain = outer_selector.parent
    previous = None
    if chain is not None:
        siblings = chain.named_children
        index = next((i for i, item in enumerate(siblings) if item == outer_selector), -1)
        if index > 0:
            previous = siblings[index - 1]
    start = previous.start_byte if previous is not None else outer_selector.start_byte
    while previous is not None and chain is not None:
        siblings = chain.named_children
        index = next((i for i, item in enumerate(siblings) if item == previous), -1)
        if index <= 0:
            break
        earlier = siblings[index - 1]
        if earlier.kind not in {
            _NodeKind.IDENTIFIER,
            _NodeKind.TYPE_IDENTIFIER,
            _NodeKind.SELECTOR,
        }:
            break
        if source.data[earlier.end_byte : previous.start_byte].strip():
            break
        previous = earlier
        start = previous.start_byte
    receiver = (
        source.data[start : selector.start_byte].decode("utf-8", "replace") if previous else None
    )
    if receiver is None:
        for ancestor in _ancestors(node):
            if ancestor.kind not in {
                _NodeKind.ASSIGNMENT_EXPRESSION,
                _NodeKind.COMPOUND_ASSIGNMENT_EXPRESSION,
            }:
                continue
            left = _named(ancestor, _NodeKind.LEFT)
            if left is not None and left.start_byte <= node.start_byte < left.end_byte:
                _, receiver, _ = _member_parts(left, source)
                break
    name = source.text(node)
    end = outer_selector.end_byte
    expression = source.data[start:end].decode("utf-8", "replace")
    return (
        name,
        receiver,
        re.search(r"\[", receiver or "") is not None,
        expression,
        _span_bytes(source, start, end),
    )


def _assignment_use(node: _Node, source: _Source) -> SiteUse:
    left = _named(node, _NodeKind.LEFT)
    right = _named(node, _NodeKind.RIGHT)
    if left is None or right is None:
        return SiteUse.WRITE
    operator = source.data[left.end_byte : right.start_byte].strip()
    return SiteUse.WRITE if re.fullmatch(rb"=", operator) is not None else SiteUse.READ_WRITE


def _reference_use(node: _Node, source: _Source) -> SiteUse:
    for parent in _ancestors(node):
        if parent.kind in {
            _NodeKind.ASSIGNMENT_EXPRESSION,
            _NodeKind.COMPOUND_ASSIGNMENT_EXPRESSION,
        }:
            left = _named(parent, _NodeKind.LEFT)
            if left is not None and left.start_byte <= node.start_byte < left.end_byte:
                return _assignment_use(parent, source)
            break
        if parent.kind in {
            _NodeKind.FUNCTION_BODY,
            _NodeKind.BLOCK,
            _NodeKind.EXPRESSION_STATEMENT,
        }:
            break
    return SiteUse.READ


def _is_declaration_name(node: _Node) -> bool:
    parent = node.parent
    return parent is not None and (
        parent.child_by_field_name(_NodeKind.NAME) == node
        or parent.kind
        in {
            _NodeKind.TYPE_IDENTIFIER,
            _NodeKind.ENUM_CONSTANT,
            _NodeKind.LIBRARY_NAME,
            _NodeKind.INITIALIZED_IDENTIFIER,
        }
        or parent.kind == _NodeKind.CONSTRUCTOR_PARAM
        or parent.kind == _NodeKind.SUPER_FORMAL_PARAMETER
    )


def _is_type_context(node: _Node) -> bool:
    return any(
        parent.kind
        in {
            _NodeKind.TYPE_IDENTIFIER,
            _NodeKind.TYPE_ANNOTATION,
            _NodeKind.TYPE_PARAMETERS,
            _NodeKind.TYPE_PARAMETER,
            _NodeKind.TYPE_ALIAS,
            _NodeKind.FUNCTION_TYPE,
            _NodeKind.GENERIC_TYPE,
            _NodeKind.NULLABLE_TYPE,
            _NodeKind.SUPERCLASS,
            _NodeKind.INTERFACES,
            _NodeKind.MIXINS,
        }
        for parent in _ancestors(node)
    )


def _is_member_selector(node: _Node) -> bool:
    parent = node.parent
    return parent is not None and parent.kind == _NodeKind.UNCONDITIONAL_ASSIGNABLE_SELECTOR


def _variable_annotation(node: _Node, name: _Node, source: _Source) -> str | None:
    return _annotation_before(node, name, source)


def _annotation_before(node: _Node, name: _Node, source: _Source) -> str | None:
    value = source.data[node.start_byte : name.start_byte].decode("utf-8", "replace")
    value = re.sub(
        r"^\s*(?:(?:static|const|final|late|external|covariant|required|var)\s+)*",
        "",
        value,
    ).strip()
    return value or None
