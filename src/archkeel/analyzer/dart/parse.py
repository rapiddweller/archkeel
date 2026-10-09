# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Project Dart syntax into immutable facts; parser nodes stay inside this module."""

from __future__ import annotations

import re
from bisect import bisect_right
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, replace
from typing import Literal, overload

import tree_sitter_dart
from tree_sitter import Language, Node, Parser


@dataclass(frozen=True, slots=True)
class Span:
    line: int
    end_line: int
    column: int
    excerpt: str
    start_byte: int
    end_byte: int


@dataclass(frozen=True, slots=True)
class Parameter:
    name: str
    annotation: str | None
    kind: Literal["positional", "named"]
    default: str | None
    default_known: bool
    span: Span
    field_formal: bool = False
    super_formal: bool = False
    optional: bool = False
    required: bool = False


@dataclass(frozen=True, slots=True)
class Member:
    name: str
    kind: Literal["field", "method", "constructor", "getter", "setter", "operator"]
    span: Span
    annotation: str | None = None
    return_type: str | None = None
    visibility: Literal["public", "private"] = "public"
    static: bool = False
    abstract: bool = False
    parameters: tuple[Parameter, ...] = ()
    initializer: str | None = None
    literal: str | None = None
    constructor_initializers: tuple[str, ...] = ()
    redirect: str | None = None
    factory: bool = False
    constant: bool = False
    final: bool = False
    late: bool = False


@dataclass(frozen=True, slots=True)
class Definition:
    name: str
    kind: Literal[
        "class",
        "interface",
        "mixin",
        "enum",
        "extension",
        "extension_type",
        "typedef",
        "function",
        "getter",
        "setter",
        "variable",
    ]
    span: Span
    visibility: Literal["public", "private"] = "public"
    type_parameters: tuple[str, ...] = ()
    extends: tuple[str, ...] = ()
    with_types: tuple[str, ...] = ()
    implements: tuple[str, ...] = ()
    alias: str | None = None
    enum_members: tuple[str, ...] = ()
    members: tuple[Member, ...] = ()
    parameters: tuple[Parameter, ...] = ()
    return_type: str | None = None
    initializer: str | None = None
    literal: str | None = None
    modifiers: tuple[str, ...] = ()
    constant: bool = False
    final: bool = False
    late: bool = False
    enum_member_spans: tuple[Span, ...] = ()


@dataclass(frozen=True, slots=True)
class Directive:
    kind: Literal["library", "import", "export", "part", "part_of"]
    span: Span
    target: str | None = None
    prefix: str | None = None
    deferred: bool = False
    show: tuple[str, ...] = ()
    hide: tuple[str, ...] = ()
    combinators: tuple[tuple[str, tuple[str, ...]], ...] = ()
    alternatives: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True, slots=True)
class Site:
    kind: Literal[
        "reference",
        "call",
        "creation",
        "type",
        "extends",
        "implements",
        "with",
        "field_formal",
        "super_formal",
        "binding",
        "assignment",
    ]
    expression: str
    span: Span
    name: str | None = None
    receiver: str | None = None
    scope: str | None = None
    scope_span: Span | None = None
    scope_depth: int = 0
    arguments: tuple[str, ...] = ()
    assigned_name: str | None = None
    assignment_annotation: str | None = None
    initializer: str | None = None
    use: Literal["type", "read", "write", "read_write", "value"] = "value"
    computed: bool = False
    shadowed_names: tuple[str, ...] = ()
    closure_scope: bool = False
    expression_source: str | None = None
    initializer_source: str | None = None


@dataclass(frozen=True, slots=True)
class Concern:
    kind: str
    message: str
    span: Span


@dataclass(frozen=True, slots=True)
class Syntax:
    definitions: tuple[Definition, ...]
    directives: tuple[Directive, ...]
    sites: tuple[Site, ...]
    concerns: tuple[Concern, ...]
    first_error: Span | None
    complete: bool
    language_version: str | None = None


_LINE_BREAK = re.compile(rb"\r\n|[\n\r]|\xe2\x80[\xa8\xa9]")
_PARSER = Parser(Language(tree_sitter_dart.language()))
_DECLARATIONS = frozenset(
    {
        "class_definition",
        "mixin_declaration",
        "enum_declaration",
        "extension_declaration",
        "extension_type_declaration",
        "type_alias",
        "function_type_alias",
    }
)


@dataclass(frozen=True, slots=True)
class _Source:
    data: bytes
    starts: tuple[int, ...]

    def text(self, node: Node) -> str:
        return self.data[node.start_byte : node.end_byte].decode("utf-8", "replace")

    def span(self, node: Node) -> Span:
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
    root = _PARSER.parse(content).root_node
    source = _Source(content, (0, *(item.end() for item in _LINE_BREAK.finditer(content))))
    concerns = [
        Concern(
            "syntax_error",
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
                "syntax_error",
                "Dart source ends inside a nested block comment.",
                _span_bytes(source, unclosed_comment, len(content)),
            )
        )
    try:
        content.decode("utf-8")
    except UnicodeDecodeError as error:
        concerns.append(
            Concern(
                "invalid_encoding",
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
        if item.kind in {"syntax_error", "invalid_encoding", "LanguageVersionError"}
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
                "LanguageVersionError",
                "Dart language override is outside supported range 2.12 through 3.12.",
                _span_bytes(source, match.start(), match.end()),
            )
        )
    return value


def _walk(node: Node) -> Iterator[Node]:
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


def _named(node: Node, kind: str) -> Node | None:
    field = node.child_by_field_name(kind)
    if field is not None:
        return field
    return next((child for child in node.named_children if child.type == kind), None)


def _named_all(node: Node | None, kind: str) -> tuple[Node, ...]:
    if node is None:
        return ()
    return tuple(child for child in node.named_children if child.type == kind)


def _first_identifier(node: Node | None, source: _Source) -> str | None:
    if node is None:
        return None
    found = next(
        (child for child in _walk(node) if child.type in {"identifier", "type_identifier"}), None
    )
    return source.text(found) if found is not None else None


def _literal_uri(node: Node | None, source: _Source) -> str | None:
    if node is None:
        return None
    scanned = _string_sequence(source.data, node.start_byte, node.end_byte)
    if scanned is not None:
        return scanned
    literals = tuple(
        child
        for child in _walk(node)
        if child.type in {"string_literal", "raw_string_literal"}
        and not any(
            descendant.type in {"string_literal", "raw_string_literal"}
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
    prefix = raw[:1].lower() if raw[:1].lower() == "r" else ""
    value = raw[len(prefix) :]
    quote = value[:1]
    if quote not in {"'", '"'}:
        return None
    delimiter = quote * (3 if value.startswith(quote * 3) else 1)
    if len(value) < 2 * len(delimiter) or not value.endswith(delimiter):
        return None
    content = value[len(delimiter) : -len(delimiter)]
    if prefix:
        return content if "$" not in content else None
    decoded: list[str] = []
    index = 0
    escapes = {"n": "\n", "r": "\r", "t": "\t", "b": "\b", "f": "\f", "v": "\v"}
    while index < len(content):
        char = content[index]
        if char == "$":
            return None
        if char != "\\":
            decoded.append(char)
            index += 1
            continue
        index += 1
        if index >= len(content):
            return None
        escape = content[index]
        if escape in {"\\", "'", '"', "$"}:
            decoded.append(escape)
            index += 1
        elif escape in escapes:
            decoded.append(escapes[escape])
            index += 1
        elif escape == "x" and index + 2 < len(content):
            digits = content[index + 1 : index + 3]
            if not re.fullmatch(r"[0-9A-Fa-f]{2}", digits):
                return None
            decoded.append(chr(int(digits, 16)))
            index += 3
        elif escape == "u":
            if index + 1 < len(content) and content[index + 1] == "{":
                close = content.find("}", index + 2)
                digits = content[index + 2 : close] if close >= 0 else ""
                if not digits or len(digits) > 6 or not re.fullmatch(r"[0-9A-Fa-f]+", digits):
                    return None
                codepoint = int(digits, 16)
                if codepoint > 0x10FFFF:
                    return None
                decoded.append(chr(codepoint))
                index = close + 1
            else:
                digits = content[index + 1 : index + 5]
                if len(digits) != 4 or not re.fullmatch(r"[0-9A-Fa-f]{4}", digits):
                    return None
                decoded.append(chr(int(digits, 16)))
                index += 5
        else:
            return None
    return "".join(decoded)


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
            content[index : index + 1].lower() == b"r"
            and index + 1 < len(content)
            and content[index + 1 : index + 2] in {b"'", b'"'}
        )
        if raw_string:
            index += 1
        if content[index : index + 1] in {b"'", b'"'}:
            quote_byte = content[index : index + 1]
            quote = quote_byte * (3 if content.startswith(quote_byte * 3, index) else 1)
            index += len(quote)
            continue
        index += 1
    return block_start if block_depth else None


def _directive_uri(node: Node, source: _Source) -> str | None:
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
        if data[index] in b" \t\r\n":
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
    if data[index : index + 1].lower() == b"r" and data[index + 1 : index + 2] in {b"'", b'"'}:
        index += 1
    quote = data[index : index + 1]
    if quote not in {b"'", b'"'}:
        return None
    delimiter = quote * (3 if data.startswith(quote * 3, index) else 1)
    cursor = index + len(delimiter)
    raw = data[max(0, index - 1) : index].lower() == b"r"
    while cursor < end:
        if not raw and data[cursor : cursor + 1] == b"\\":
            cursor += 2
        elif data.startswith(delimiter, cursor):
            return cursor + len(delimiter)
        else:
            cursor += 1
    return None


def _directives(root: Node, source: _Source, concerns: list[Concern]) -> tuple[Directive, ...]:
    result: list[Directive] = []
    for node in root.named_children:
        if node.type == "library_name":
            result.append(Directive("library", source.span(node), _text_children(node, source)))
        elif node.type == "part_directive":
            uri = _named(node, "uri")
            target = _literal_uri(uri, source)
            if target is None:
                concerns.append(
                    Concern(
                        "unsupported_directive",
                        "Part URI is not a plain string.",
                        source.span(node),
                    )
                )
            result.append(Directive("part", source.span(node), target))
        elif node.type == "part_of_directive":
            uri = _named(node, "uri")
            target = _literal_uri(uri, source) if uri is not None else _text_children(node, source)
            if target is None:
                concerns.append(
                    Concern(
                        "unsupported_directive",
                        "Part owner is not a literal or library name.",
                        source.span(node),
                    )
                )
            result.append(Directive("part_of", source.span(node), target))
        elif node.type == "import_or_export":
            directive = next(
                (
                    item
                    for item in node.named_children
                    if item.type in {"library_import", "library_export"}
                ),
                None,
            )
            if directive is not None:
                result.append(_library_directive(directive, source, concerns))
    return tuple(sorted(result, key=lambda item: item.span.start_byte))


def _library_directive(node: Node, source: _Source, concerns: list[Concern]) -> Directive:
    kind: Literal["import", "export"] = "import" if node.type == "library_import" else "export"
    spec = _named(node, "import_specification") or _named(node, "export_specification")
    if spec is None:
        spec = node
    uri = None
    if spec is not None:
        uri = _named(spec, "configurable_uri") or _named(spec, "uri")
        if uri is None:
            uri = next(
                (item for item in _walk(spec) if item.type == "configurable_uri"),
                None,
            )
    primary_node = _named(uri, "uri") if uri is not None else None
    if primary_node is None:
        primary_node = uri
    primary = _directive_uri(node, source) or _literal_uri(primary_node, source)
    alternatives: list[tuple[str, str]] = []
    if uri is not None:
        configurable = uri if uri.type == "configurable_uri" else None
        for choice in _named_all(configurable, "configuration_uri"):
            condition_node = _named(choice, "configuration_uri_condition")
            alternative = _literal_uri(_named(choice, "uri"), source)
            if condition_node is None or alternative is None:
                concerns.append(
                    Concern(
                        "unsupported_directive",
                        "Conditional URI is not literal.",
                        source.span(choice),
                    )
                )
                continue
            condition = source.text(condition_node).strip()[1:-1].strip()
            alternatives.append((condition, alternative))
    if primary is None:
        concerns.append(
            Concern(
                "unsupported_directive",
                "Import/export URI is not a plain string.",
                source.span(node),
            )
        )
    combinators: list[tuple[str, tuple[str, ...]]] = []
    show: list[str] = []
    hide: list[str] = []
    if spec is not None:
        for item in _named_all(spec, "combinator"):
            mode = source.text(item.children[0])
            names = [
                source.text(child) for child in item.named_children if child.type == "identifier"
            ]
            combinators.append((mode, tuple(names)))
            (show if mode == "show" else hide).extend(names)
    prefix = None
    deferred = False
    if spec is not None:
        text = source.text(spec)
        deferred = bool(re.search(r"\bdeferred\s+as\b", text))
        prefix_node = _named(spec, "import_prefix")
        prefix = (
            _first_identifier(prefix_node, source)
            if prefix_node is not None
            else next(
                (source.text(item) for item in _named_all(spec, "identifier")),
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
        tuple(alternatives),
    )


def _text_children(node: Node, source: _Source) -> str:
    return ".".join(source.text(child) for child in _walk(node) if child.type == "identifier")


def _definitions(root: Node, source: _Source) -> tuple[Definition, ...]:
    result: list[Definition] = []
    for node in root.named_children:
        if node.type in _DECLARATIONS:
            result.append(_classifier(node, source))
        elif node.type == "function_signature":
            result.append(_function(node, source))
        elif node.type in {"getter_signature", "setter_signature"}:
            result.append(_top_level_accessor(node, source))
        elif node.type == "top_level_variable_declaration":
            declaration = next(
                (item for item in node.named_children if item.type == "declaration"), node
            )
            result.extend(_variables(declaration, source, "variable"))
        elif node.type in {"static_final_declaration_list", "initialized_identifier_list"}:
            result.extend(_variables(node, source, "variable"))
        elif node.type == "declaration":
            result.extend(_variables(node, source, "variable"))
    return tuple(sorted(result, key=lambda item: item.span.start_byte))


def _classifier(node: Node, source: _Source) -> Definition:
    name_node = _named(node, "name") or next(
        (child for child in node.named_children if child.type in {"identifier", "type_identifier"}),
        None,
    )
    name = source.text(name_node) if name_node is not None else ""
    kind = _classifier_kind(node)
    extends, with_types, implements, type_parameters = _classifier_relations(node, source)
    body = _named(node, "body") or next(
        (child for child in node.named_children if child.type in {"class_body", "enum_body"}), None
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
    node: Node,
) -> Literal["class", "interface", "mixin", "enum", "extension", "extension_type", "typedef"]:
    if node.type == "class_definition":
        return "interface" if any(child.type == "interface" for child in node.children) else "class"
    if node.type == "mixin_declaration":
        return "mixin"
    if node.type == "enum_declaration":
        return "enum"
    if node.type == "extension_declaration":
        return "extension"
    if node.type == "extension_type_declaration":
        return "extension_type"
    return "typedef"


def _classifier_relations(
    node: Node, source: _Source
) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
    superclass = _named(node, "superclass")
    extends = _type_children(superclass, source)
    mixins = (_named(superclass, "mixins") if superclass is not None else None) or _named(
        node, "mixins"
    )
    with_types = _type_children(mixins, source)
    implements = _type_children(_named(node, "interfaces"), source)
    type_node = _named(node, "type_parameters")
    type_parameters = (
        tuple(
            source.text(child.named_children[0])
            for child in _named_all(type_node, "type_parameter")
            if child.named_children
        )
        if type_node is not None
        else ()
    )
    return extends[:1], with_types, implements, type_parameters


def _type_children(node: Node | None, source: _Source) -> tuple[str, ...]:
    if node is None:
        return ()
    children = node.named_children
    names: list[str] = []
    index = 0
    while index < len(children):
        child = children[index]
        if child.type in {"type_identifier", "type_name", "generic_type"}:
            value = source.text(child)
            if index + 1 < len(children) and children[index + 1].type == "type_arguments":
                value += source.text(children[index + 1])
                index += 1
            names.append(value)
        index += 1
    return tuple(names)


def _classifier_members(
    node: Node, body: Node | None, source: _Source
) -> tuple[tuple[Member, ...], tuple[str, ...], tuple[Span, ...]]:
    if body is None:
        return (), (), ()
    literals: tuple[tuple[str, Span], ...] = ()
    if node.type == "enum_declaration":
        literals = tuple(
            (source.text(name), source.span(name))
            for constant in _named_all(body, "enum_constant")
            if (name := _named(constant, "name")) is not None
        )
    members: list[Member] = []
    children = body.named_children
    for index, child in enumerate(children):
        following = (
            children[index + 1]
            if index + 1 < len(children)
            and children[index + 1].type in {"function_body", "function_expression_body"}
            else None
        )
        if child.type == "declaration":
            members.extend(_member_declaration(child, source))
        elif child.type == "method_signature":
            members.append(_member_method(child, following, source))
    return (
        tuple(members),
        tuple(name for name, _ in literals),
        tuple(span for _, span in literals),
    )


def _classifier_alias(
    node: Node,
    kind: Literal["class", "interface", "mixin", "enum", "extension", "extension_type", "typedef"],
    name_node: Node | None,
    source: _Source,
) -> str | None:
    if kind != "typedef":
        return None
    position = next((i for i, child in enumerate(node.named_children) if child == name_node), -1)
    alias_node = next(
        (
            child
            for child in node.named_children[position + 1 :]
            if child.type in {"function_type", "type_identifier", "generic_type"}
        ),
        None,
    )
    return source.text(alias_node) if alias_node is not None else None


def _classifier_modifiers(node: Node, name_node: Node | None, source: _Source) -> tuple[str, ...]:
    prefix = (
        source.data[node.start_byte : name_node.start_byte].decode("utf-8", "replace")
        if name_node is not None
        else _prefix(node, source)
    )
    return tuple(
        word
        for word in ("abstract", "base", "final", "interface", "sealed", "mixin")
        if re.search(rf"\b{word}\b", prefix)
    )


def _member_declaration(node: Node, source: _Source) -> list[Member]:
    constructor = next(
        (
            child
            for child in node.named_children
            if child.type
            in {
                "constructor_signature",
                "constant_constructor_signature",
                "redirecting_factory_constructor_signature",
            }
        ),
        None,
    )
    if constructor is not None:
        name_nodes = [child for child in constructor.named_children if child.type == "identifier"]
        name = (
            ".".join(source.text(item) for item in name_nodes)
            or _first_identifier(constructor, source)
            or ""
        )
        params = _parameters(_parameter_list(constructor), source)
        initializers = _named(node, "initializers")
        redirects = _redirect(node, source)
        return [
            Member(
                name,
                "constructor",
                _member_span(node, None, source),
                visibility=_visibility(name),
                parameters=params,
                constructor_initializers=tuple(
                    source.text(item) for item in initializers.named_children
                )
                if initializers
                else (),
                redirect=redirects,
                factory=constructor.type
                in {
                    "factory_constructor_signature",
                    "redirecting_factory_constructor_signature",
                },
                constant=source.text(node).lstrip().startswith("const"),
            )
        ]
    signature = next(
        (
            child
            for child in node.named_children
            if child.type in {"function_signature", "getter_signature", "setter_signature"}
        ),
        None,
    )
    if signature is not None:
        return [_member_method(node, None, source)]
    return _variables(node, source, "field")


def _member_method(node: Node, body: Node | None, source: _Source) -> Member:
    inner = node.named_children[0] if node.named_children else node
    signature = _named(inner, "function_signature") or inner
    factory = inner.type == "factory_constructor_signature"
    constructor = factory or inner.type in {
        "constructor_signature",
        "constant_constructor_signature",
        "redirecting_factory_constructor_signature",
    }
    getter = inner.type == "getter_signature"
    setter = inner.type == "setter_signature"
    operator = inner.type == "operator_signature"
    name_node = _named(signature, "name") or _named(inner, "name")
    if constructor:
        name_nodes = [item for item in inner.named_children if item.type == "identifier"]
        name = ".".join(source.text(item) for item in name_nodes)
    else:
        name = source.text(name_node) if name_node is not None else _operator_name(inner, source)
    kind: Literal["method", "getter", "setter", "operator", "constructor"] = (
        "constructor"
        if constructor
        else "getter"
        if getter
        else "setter"
        if setter
        else "operator"
        if operator
        else "method"
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
        static="static" in modifiers,
        abstract=body is None or "abstract" in modifiers,
        parameters=params,
        factory=factory,
        redirect=_redirect(node, source),
    )


def _member_span(node: Node, body: Node | None, source: _Source) -> Span:
    start = node.start_byte
    parent = node.parent
    if parent is not None:
        siblings = parent.named_children
        position = next((index for index, item in enumerate(siblings) if item == node), -1)
        while position > 0 and siblings[position - 1].type in {
            "annotation",
            "documentation_comment",
            "metadata",
        }:
            position -= 1
            start = siblings[position].start_byte
    end = body.end_byte if body is not None else node.end_byte
    return _span_bytes(source, start, end)


def _parameter_list(node: Node) -> Node | None:
    return _named(node, "parameters") or _named(node, "formal_parameter_list")


def _redirect(node: Node, source: _Source) -> str | None:
    redirect = next(
        (
            child
            for child in node.named_children
            if child.type in {"redirection", "redirecting_factory_constructor_signature"}
        ),
        None,
    )
    if redirect is None:
        return None
    raw = source.text(redirect)
    marker = "=" if redirect.type == "redirecting_factory_constructor_signature" else ":"
    return raw.split(marker, 1)[1].strip() if marker in raw else raw


def _operator_name(node: Node, source: _Source) -> str:
    operator = next(
        (
            child
            for child in node.named_children
            if child.type in {"binary_operator", "unary_operator"}
        ),
        None,
    )
    if operator is not None:
        return f"operator{source.text(operator)}"
    token = next((child for child in node.children if child.type in {"[]", "[]="}), None)
    return f"operator{source.text(token)}" if token is not None else "operator"


def _top_level_accessor(node: Node, source: _Source) -> Definition:
    name_node = _named(node, "name")
    name = source.text(name_node) if name_node is not None else ""
    kind: Literal["getter", "setter"] = "getter" if node.type == "getter_signature" else "setter"
    return Definition(
        name,
        kind,
        source.span(node),
        _visibility(name),
        return_type=_return_type(node, name_node, source),
        parameters=_parameters(_parameter_list(node), source),
    )


def _function(node: Node, source: _Source) -> Definition:
    signature = _named(node, "function_signature") or node
    name_node = _named(signature, "name")
    name = source.text(name_node) if name_node is not None else ""
    return_type = _return_type(signature, name_node, source)
    return Definition(
        name,
        "function",
        source.span(node),
        _visibility(name),
        parameters=_parameters(_parameter_list(signature), source),
        return_type=return_type,
    )


def _return_type(signature: Node, name_node: Node | None, source: _Source) -> str | None:
    if name_node is None:
        return None
    annotation = _annotation_before(signature, name_node, source)
    if annotation is not None:
        annotation = re.sub(r"\s+(?:get|set)\s*$", "", annotation)
        if annotation == "set":
            return None
    return annotation


def _parameters(node: Node | None, source: _Source) -> tuple[Parameter, ...]:
    if node is None:
        return ()
    result: list[Parameter] = []
    for group in node.named_children:
        if group.type == "formal_parameter":
            result.append(_parameter(group, "positional", source))
        elif group.type == "optional_formal_parameters":
            kind: Literal["positional", "named"] = (
                "named" if source.text(group).lstrip().startswith("{") else "positional"
            )
            result.extend(
                _parameter(item, kind, source) for item in _named_all(group, "formal_parameter")
            )
    return tuple(result)


def _parameter(node: Node, kind: Literal["positional", "named"], source: _Source) -> Parameter:
    field = next(
        (
            item
            for item in _walk(node)
            if item.type in {"constructor_param", "field_formal_parameter"}
        ),
        None,
    )
    super_formal = any(
        item.type in {"super_formal_parameter", "super_parameter"} for item in _walk(node)
    )
    ids = [item for item in node.named_children if item.type in {"identifier", "type_identifier"}]
    name_node = (
        ids[-1] if ids else next((item for item in _walk(node) if item.type == "identifier"), None)
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
    default = None
    for index, child in enumerate(node.children[:-1]):
        if child.type in {"=", ":"}:
            default = source.text(node.children[index + 1])
            break
    if default is None and node.parent is not None:
        siblings = node.parent.named_children
        position = next((index for index, item in enumerate(siblings) if item == node), -1)
        if position >= 0 and position + 1 < len(siblings):
            following = siblings[position + 1]
            if b"=" in source.data[node.end_byte : following.start_byte]:
                default = source.text(following)
    if default is None:
        candidate = next(
            (item for item in node.named_children if item.type == "default_formal_parameter"), None
        )
        if candidate is not None:
            default = next(
                (source.text(item) for item in candidate.named_children if item.type not in {""}),
                None,
            )
    before = source.data[node.parent.start_byte : node.start_byte] if node.parent else b""
    required = b"required" in before.rsplit(b",", 1)[-1]
    optional = kind == "named" and not required
    if node.parent is not None and node.parent.type == "optional_formal_parameters":
        optional = source.text(node.parent).lstrip().startswith("[") or optional
    nullable_or_dynamic = annotation is None or annotation.endswith("?") or annotation == "dynamic"
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


@overload
def _variables(node: Node, source: _Source, kind: Literal["field"]) -> list[Member]: ...


@overload
def _variables(node: Node, source: _Source, kind: Literal["variable"]) -> list[Definition]: ...


def _variables(
    node: Node, source: _Source, kind: Literal["field", "variable"]
) -> list[Member] | list[Definition]:
    """Read declaration names and exact annotation/initializer for each comma item."""
    list_node = _variable_list_node(node)
    if list_node is None:
        return []
    items = list_node.named_children if list_node.type.endswith("list") else (list_node,)
    if kind == "field":
        return _field_members(node, items, source)
    return _top_level_variables(node, items, source)


def _variable_list_node(node: Node) -> Node | None:
    declaration_types = {
        "initialized_identifier_list",
        "static_final_declaration_list",
        "initialized_variable_definition",
        "initialized_identifier",
    }
    return (
        node
        if node.type in declaration_types
        else next((item for item in node.named_children if item.type in declaration_types), None)
    )


def _field_members(node: Node, items: Sequence[Node], source: _Source) -> list[Member]:
    declaration_text = source.text(node)
    members: list[Member] = []
    for item in items:
        name_node = next(
            (child for child in item.named_children if child.type == "identifier"), None
        )
        if name_node is None:
            continue
        value = _initializer(item, source)
        name = source.text(name_node)
        members.append(
            Member(
                name,
                "field",
                source.span(item),
                annotation=_annotation_before(node, name_node, source),
                visibility=_visibility(name),
                static="static" in declaration_text,
                initializer=value,
                literal=value,
                constant="const" in declaration_text,
                final="final" in declaration_text,
                late="late" in declaration_text,
            )
        )
    return members


def _top_level_variables(node: Node, items: Sequence[Node], source: _Source) -> list[Definition]:
    declaration_text = _declaration_text(node, source)
    definitions: list[Definition] = []
    for item in items:
        name_node = next(
            (child for child in item.named_children if child.type == "identifier"), None
        )
        if name_node is None:
            continue
        name = source.text(name_node)
        value = _initializer(item, source)
        definitions.append(
            Definition(
                name,
                "variable",
                source.span(item),
                _visibility(name),
                return_type=_annotation_before(node, name_node, source),
                initializer=value,
                literal=value,
                constant="const" in declaration_text,
                final="final" in declaration_text,
                late="late" in declaration_text,
            )
        )
    return definitions


def _initializer(node: Node, source: _Source) -> str | None:
    equal = next((index for index, child in enumerate(node.children) if child.type == "="), None)
    return (
        source.text(node.children[equal + 1])
        if equal is not None and equal + 1 < len(node.children)
        else None
    )


def _declaration_text(node: Node, source: _Source) -> str:
    if node.parent is None:
        return source.text(node)
    siblings = node.parent.named_children
    position = next((index for index, item in enumerate(siblings) if item == node), -1)
    modifiers: list[str] = []
    for sibling in reversed(siblings[:position]):
        if sibling.type in {"const_builtin", "final_builtin", "late_builtin", "static_builtin"}:
            modifiers.append(source.text(sibling))
            continue
        if sibling.type in {"type_identifier", "type_name", "generic_type", "nullable_type"}:
            continue
        break
    return " ".join(reversed(modifiers)) or source.text(node)


def _unsupported_concerns(root: Node, source: _Source) -> tuple[Concern, ...]:
    return tuple(
        Concern(
            "unsupported_declaration",
            "Mixin on-constraints are not modeled by this parser.",
            source.span(node),
        )
        for node in _walk(root)
        if node.type == "mixin_declaration" and any(child.type == "on" for child in node.children)
    )


def _prefix(node: Node, source: _Source) -> str:
    if node.parent is None:
        return ""
    siblings = node.parent.named_children
    position = next((index for index, item in enumerate(siblings) if item == node), -1)
    start = siblings[position - 1].end_byte if position > 0 else node.parent.start_byte
    return source.data[start : node.start_byte].decode("utf-8", "replace")


def _visibility(name: str) -> Literal["public", "private"]:
    return "private" if name.startswith("_") else "public"


def _sites(
    root: Node,
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
        if candidate.type in {"function_signature", "method_signature"}
        if (body := _callable_body(candidate)) is not None
        if (name := _callable_decl_name(candidate)) is not None
    )
    scopes = tuple(
        (node, _scope_name(node, source, callables))
        for node in _walk(root)
        if node.type in {"function_body", "function_expression_body", "block"}
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
        parameter_nodes = [item for item in _ancestors(node) if item.type == "formal_parameter"]
        parameter_node = parameter_nodes[-1] if parameter_nodes else None
        if node.type == "formal_parameter":
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


def _inside_function_expression(node: Node) -> bool:
    return any(parent.type == "function_expression" for parent in _ancestors(node))


def _typed_receiver_names(
    root: Node, source: _Source, definitions: tuple[Definition, ...]
) -> frozenset[str]:
    names = {
        member.name
        for definition in definitions
        for member in definition.members
        if member.kind == "field" and member.annotation is not None
    }
    names.update(
        definition.name
        for definition in definitions
        if definition.kind in {"class", "interface", "mixin", "enum", "extension_type"}
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
        if node.type == "local_variable_declaration":
            for definition in _walk(node):
                if definition.type != "initialized_variable_definition":
                    continue
                name = _named(definition, "name")
                if name is not None and _variable_annotation(definition, name, source) is not None:
                    names.add(source.text(name))
        elif node.type == "formal_parameter":
            parameter = _parameter(node, "positional", source)
            if parameter.annotation is not None:
                names.add(parameter.name)
    return frozenset(names)


def _callable_decl_name(node: Node) -> Node | None:
    name = _named(node, "name")
    if name is not None:
        return name
    signature = next(
        (child for child in node.named_children if child.type == "function_signature"),
        None,
    )
    return _named(signature, "name") if signature is not None else None


def _scope_name(
    node: Node,
    source: _Source,
    callables: tuple[tuple[Node, str], ...],
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
    node: Node,
    source: _Source,
    scopes: tuple[tuple[Node, str | None], ...],
) -> tuple[str | None, Span | None, int] | None:
    ancestors = tuple(_ancestors(node))
    if any(item.type == "formal_parameter" for item in ancestors):
        return None
    callable_node = next(
        (
            item
            for item in ancestors
            if item.type
            in {
                "function_signature",
                "function_expression",
                "constructor_signature",
                "constant_constructor_signature",
                "factory_constructor_signature",
                "redirecting_factory_constructor_signature",
            }
        ),
        None,
    )
    if callable_node is None:
        return None
    return _callable_context_for(callable_node, source, scopes)


def _callable_context(
    node: Node,
    source: _Source,
    scopes: tuple[tuple[Node, str | None], ...],
) -> tuple[str | None, Span | None, int] | None:
    signatures = {
        "function_signature",
        "method_signature",
        "constructor_signature",
        "constant_constructor_signature",
        "factory_constructor_signature",
        "redirecting_factory_constructor_signature",
        "getter_signature",
        "setter_signature",
    }
    callable_node = next((item for item in _ancestors(node) if item.type in signatures), None)
    if callable_node is None:
        callable_node = next(
            (
                child
                for ancestor in _ancestors(node)
                for child in ancestor.named_children
                if child.type in signatures
                and child.start_byte <= node.start_byte
                and node.end_byte <= ancestor.end_byte
            ),
            None,
        )
    return (
        _callable_context_for(callable_node, source, scopes) if callable_node is not None else None
    )


def _callable_context_for(
    callable_node: Node,
    source: _Source,
    scopes: tuple[tuple[Node, str | None], ...],
) -> tuple[str | None, Span | None, int]:
    owner = callable_node
    if owner.parent is not None and owner.parent.type == "method_signature":
        owner = owner.parent
    body = _callable_body(owner)
    scope_name = _callable_name(callable_node, source)
    if callable_node.type in {
        "constructor_signature",
        "constant_constructor_signature",
        "factory_constructor_signature",
        "redirecting_factory_constructor_signature",
    }:
        names = tuple(
            source.text(child)
            for child in callable_node.named_children
            if child.type == "identifier"
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


def _callable_body(owner: Node) -> Node | None:
    if owner.type == "function_expression":
        return next(
            (child for child in owner.named_children if child.type == "function_expression_body"),
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
        if sibling.type in {"function_body", "function_expression_body"}:
            return sibling
        if sibling.type in {"function_signature", "method_signature", "function_expression"}:
            break
    return None


def _binding_sites(
    node: Node,
    source: _Source,
    context: tuple[str | None, Span | None, int],
    root: Node,
) -> tuple[Site, ...]:
    scope, scope_span, scope_depth = context
    if node.type == "local_variable_declaration":
        return tuple(
            Site(
                "binding",
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
            if child.type == "initialized_variable_definition"
            if (name := _named(child, "name")) is not None
        )
    if node.type != "formal_parameter":
        return ()
    if any(parent.type == "formal_parameter" for parent in _ancestors(node)):
        return ()
    parameter = _parameter(node, "positional", source)
    sites = [
        Site(
            "binding",
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
        kind: Literal["field_formal", "super_formal"] = (
            "field_formal" if parameter.field_formal else "super_formal"
        )
        sites.append(
            Site(
                kind,
                source.text(node),
                source.span(node),
                parameter.name,
                use="type",
                scope=scope,
                scope_span=scope_span,
                scope_depth=scope_depth,
            )
        )
    return tuple(sites)


def _local_initializer(node: Node, source: _Source) -> str | None:
    value = _named(node, "value")
    if value is None:
        return None
    selectors = _named_all(node, "selector")
    return source.text(value) + "".join(source.text(item) for item in selectors)


def _canonical_local_initializer(root: Node, node: Node, source: _Source) -> str | None:
    value = _named(node, "value")
    if value is None:
        return None
    selectors = _named_all(node, "selector")
    end = selectors[-1].end_byte if selectors else value.end_byte
    return _canonical_range(root, source, value.start_byte, end)


def _canonical_range(root: Node, source: _Source, start: int, end: int) -> str:
    tokens = list(_source_tokens(root, start, end))
    output = ""
    previous_word = False
    for token in tokens:
        value = source.text(token)
        if value == ",":
            output = output.rstrip() + ", "
            previous_word = False
        elif value in {")", "]", "}", ".", "?.", "?..", "..", "?[]", "!.", "?["}:
            output = output.rstrip() + value
            prefix = output[:-1].rstrip()
            if value in {")", "]", "}"} and prefix.endswith(","):
                output = prefix[:-1].rstrip() + value
            previous_word = value in {
                ")",
                "]",
                "}",
            }
        elif value in {"(", "[", "{", ".", "?.", "?..", "..", "!.", "?["}:
            output = output.rstrip() + value
            previous_word = False
        elif value in {
            "=",
            "=>",
            "+",
            "-",
            "*",
            "/",
            "~/",
            "%",
            "??",
            "&&",
            "||",
            "==",
            "!=",
            "<",
            ">",
            "<=",
            ">=",
            "??=",
        }:
            if value in {"<", ">"} and any(
                parent.type == "type_arguments" for parent in _ancestors(token)
            ):
                output = output.rstrip() + value
                previous_word = value == ">"
            else:
                output = output.rstrip() + f" {value} "
                previous_word = False
        else:
            word = bool(value) and (value[0].isalnum() or value[0] in "_$\"'")
            if previous_word and word:
                output += " "
            output += value
            previous_word = word
    return output.strip()


def _source_tokens(node: Node, start: int, end: int) -> Iterator[Node]:
    if node.end_byte <= start or node.start_byte >= end:
        return
    if node.type in {"comment", "documentation_comment"}:
        return
    if node.type == "string_literal":
        yield node
        return
    if not node.children:
        if node.type not in {"comment", "documentation_comment"}:
            yield node
        return
    for child in node.children:
        if child.start_byte >= end:
            break
        yield from _source_tokens(child, start, end)


def _expression_site(
    node: Node,
    source: _Source,
    context: tuple[str | None, Span | None, int],
    root: Node,
) -> Site | None:
    scope, scope_span, scope_depth = context
    if node.type in {"new_expression", "const_object_expression"}:
        return _creation(node, source, scope, scope_span, scope_depth, root)
    if node.type in {"assignment_expression", "compound_assignment_expression"}:
        left, right = _named(node, "left"), _named(node, "right")
        name, receiver, computed = _member_parts(left, source) if left else (None, None, False)
        return Site(
            "assignment",
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
    if node.type == "arguments":
        return _call_site(node, source, scope, scope_span, scope_depth, root)
    return None


def _reference_sites(
    node: Node,
    source: _Source,
    context: tuple[str | None, Span | None, int],
    receiver_names: frozenset[str],
    prefixes: frozenset[str],
) -> tuple[Site, ...]:
    scope, scope_span, scope_depth = context
    if node.type in {"type_identifier", "generic_type", "function_type"}:
        if node.parent is None or node.parent.type in {"type_parameters", "type_parameter"}:
            return ()
        name, receiver, computed = _member_parts(node, source)
        return (
            Site(
                _type_site_kind(node),
                source.text(node),
                source.span(node),
                name,
                receiver,
                use="type",
                computed=computed,
                scope=scope,
                scope_span=scope_span,
                scope_depth=scope_depth,
            ),
        )
    if node.type != "identifier" or _is_declaration_name(node):
        return ()
    if _is_member_receiver(node):
        name = source.text(node)
        if name in receiver_names and name not in prefixes and _receiver_needs_site(node):
            return (
                Site(
                    "reference",
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
                "reference",
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
            "reference",
            source.text(node),
            source.span(node),
            source.text(node),
            use=_reference_use(node, source),
            scope=scope,
            scope_span=scope_span,
            scope_depth=scope_depth,
        ),
    )


def _ancestors(node: Node) -> Iterator[Node]:
    parent = node.parent
    while parent is not None:
        yield parent
        parent = parent.parent


def _inside_directive(node: Node) -> bool:
    return any(
        parent.type in {"import_or_export", "library_name", "part_directive", "part_of_directive"}
        for parent in _ancestors(node)
    )


def _type_site_kind(
    node: Node,
) -> Literal["type", "extends", "implements", "with"]:
    for parent in _ancestors(node):
        if parent.type == "interfaces":
            return "implements"
        if parent.type == "mixins":
            return "with"
        if parent.type == "superclass":
            return "extends"
        if parent.type in {"class_body", "program"}:
            break
    return "type"


def _is_call_selector(node: Node) -> bool:
    selector = node.parent.parent if node.parent is not None else None
    if selector is None or selector.type != "selector" or selector.parent is None:
        return False
    siblings = selector.parent.named_children
    position = next((index for index, item in enumerate(siblings) if item == selector), -1)
    return any(
        item.type == "selector" and _named(item, "argument_part") is not None
        for item in siblings[position + 1 :]
    )


def _is_member_receiver(node: Node) -> bool:
    parent = node.parent
    if parent is None:
        return False
    siblings = parent.named_children
    position = next((index for index, item in enumerate(siblings) if item == node), -1)
    return position >= 0 and any(
        item.type == "selector"
        and any(child.type == "unconditional_assignable_selector" for child in item.named_children)
        for item in siblings[position + 1 :]
    )


def _receiver_needs_site(node: Node) -> bool:
    parent = node.parent
    if parent is None:
        return False
    siblings = parent.named_children
    position = next((index for index, item in enumerate(siblings) if item == node), -1)
    selectors = tuple(item for item in siblings[position + 1 :] if item.type == "selector")
    if any(
        _named(item, "argument_part") is not None or _selector_has_index(item) for item in selectors
    ):
        return True
    return any(
        any(child.type == "unconditional_assignable_selector" for child in item.named_children)
        for item in selectors
    )


def _selector_has_index(node: Node) -> bool:
    selector = next(
        (item for item in node.named_children if item.type == "unconditional_assignable_selector"),
        None,
    )
    return selector is not None and _named(selector, "index_selector") is not None


def _is_call_callee(node: Node) -> bool:
    parent = node.parent
    if parent is None:
        return False
    siblings = parent.named_children
    position = next((index for index, item in enumerate(siblings) if item == node), -1)
    return position >= 0 and any(
        item.type == "selector" and _named(item, "argument_part") is not None
        for item in siblings[position + 1 :]
    )


def _callable_name(node: Node, source: _Source) -> str | None:
    for parent in (node, *_ancestors(node)):
        if parent.type in {
            "function_signature",
            "method_signature",
            "method_declaration",
            "function_declaration",
            "getter_signature",
            "setter_signature",
            "function_expression",
        }:
            name = _named(parent, "name")
            if name is not None:
                return source.text(name)
        if (
            parent.type in {"function_body", "function_expression_body"}
            and parent.parent is not None
        ):
            siblings = parent.parent.named_children
            index = next((i for i, item in enumerate(siblings) if item == parent), -1)
            for signature in reversed(siblings[:index]):
                if signature.type in {"function_signature", "method_signature"}:
                    name = _named(signature, "name")
                    if name is not None:
                        return source.text(name)
    return None


def _creation(
    node: Node,
    source: _Source,
    scope: str | None,
    scope_span: Span | None,
    scope_depth: int,
    root: Node,
) -> Site:
    type_node = next(
        (
            child
            for child in node.named_children
            if child.type
            in {
                "type_identifier",
                "type_name",
                "generic_type",
                "qualified_type",
            }
        ),
        None,
    )
    args = _named(node, "arguments")
    arguments = tuple(source.text(item) for item in _named_all(args, "argument")) if args else ()
    name = None
    if type_node is not None:
        suffix = tuple(
            source.text(child)
            for child in node.named_children
            if child.type == "identifier" and child.start_byte > type_node.end_byte
        )
        name = ".".join((source.text(type_node), *suffix))
    return Site(
        "creation",
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
    node: Node,
    source: _Source,
    scope: str | None,
    scope_span: Span | None,
    scope_depth: int,
    root: Node,
) -> Site | None:
    parent = node.parent
    if parent is None or parent.type != "argument_part":
        return None
    selector = parent.parent
    if selector is None or selector.type != "selector":
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
        if earlier.type not in {
            "identifier",
            "type_identifier",
            "selector",
            "assignable_expression",
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
    arguments = tuple(source.text(item) for item in _named_all(node, "argument"))
    return Site(
        "call",
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
    if "." in value:
        receiver, name = value.rsplit(".", 1)
        return name or None, receiver or None, "[" in receiver
    return value.rsplit(" ", 1)[-1] or None, None, "[" in value


def _member_parts(node: Node | None, source: _Source) -> tuple[str | None, str | None, bool]:
    if node is None:
        return None, None, False
    text = source.text(node)
    if "." in text:
        receiver, name = text.rsplit(".", 1)
        return name, receiver, "[" in receiver
    return text, None, "[" in text


def _member_reference(
    node: Node, source: _Source
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
        if earlier.type not in {"identifier", "type_identifier", "selector"}:
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
            if ancestor.type not in {"assignment_expression", "compound_assignment_expression"}:
                continue
            left = _named(ancestor, "left")
            if left is not None and left.start_byte <= node.start_byte < left.end_byte:
                _, receiver, _ = _member_parts(left, source)
                break
    name = source.text(node)
    end = outer_selector.end_byte
    expression = source.data[start:end].decode("utf-8", "replace")
    return name, receiver, "[" in (receiver or ""), expression, _span_bytes(source, start, end)


def _assignment_use(node: Node, source: _Source) -> Literal["write", "read_write"]:
    left = _named(node, "left")
    right = _named(node, "right")
    if left is None or right is None:
        return "write"
    operator = source.data[left.end_byte : right.start_byte].strip()
    return "write" if operator == b"=" else "read_write"


def _reference_use(node: Node, source: _Source) -> Literal["read", "write", "read_write", "value"]:
    for parent in _ancestors(node):
        if parent.type in {"assignment_expression", "compound_assignment_expression"}:
            left = _named(parent, "left")
            if left is not None and left.start_byte <= node.start_byte < left.end_byte:
                return _assignment_use(parent, source)
            break
        if parent.type in {"function_body", "block", "expression_statement"}:
            break
    return "read"


def _is_declaration_name(node: Node) -> bool:
    parent = node.parent
    return parent is not None and (
        parent.child_by_field_name("name") == node
        or parent.type
        in {
            "type_identifier",
            "enum_constant",
            "library_name",
            "initialized_identifier",
        }
        or parent.type == "constructor_param"
        or parent.type == "super_formal_parameter"
    )


def _is_type_context(node: Node) -> bool:
    return any(
        parent.type
        in {
            "type_identifier",
            "type_annotation",
            "type_parameters",
            "type_parameter",
            "type_alias",
            "function_type",
            "generic_type",
            "nullable_type",
            "superclass",
            "interfaces",
            "mixins",
        }
        for parent in _ancestors(node)
    )


def _is_member_selector(node: Node) -> bool:
    parent = node.parent
    return parent is not None and parent.type == "unconditional_assignable_selector"


def _variable_annotation(node: Node, name: Node, source: _Source) -> str | None:
    return _annotation_before(node, name, source)


def _annotation_before(node: Node, name: Node, source: _Source) -> str | None:
    value = source.data[node.start_byte : name.start_byte].decode("utf-8", "replace")
    value = re.sub(
        r"^\s*(?:(?:static|const|final|late|external|covariant|required|var)\s+)*",
        "",
        value,
    ).strip()
    return value or None
