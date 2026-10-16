# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Immutable Dart syntax API and its closed semantic categories."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ParameterKind(StrEnum):
    POSITIONAL = "positional"
    NAMED = "named"


class Visibility(StrEnum):
    PUBLIC = "public"
    PRIVATE = "private"


class MemberKind(StrEnum):
    FIELD = "field"
    METHOD = "method"
    CONSTRUCTOR = "constructor"
    GETTER = "getter"
    SETTER = "setter"
    OPERATOR = "operator"


class DefinitionKind(StrEnum):
    CLASS = "class"
    INTERFACE = "interface"
    MIXIN = "mixin"
    ENUM = "enum"
    EXTENSION = "extension"
    EXTENSION_TYPE = "extension_type"
    TYPEDEF = "typedef"
    FUNCTION = "function"
    GETTER = "getter"
    SETTER = "setter"
    VARIABLE = "variable"


class DirectiveKind(StrEnum):
    LIBRARY = "library"
    IMPORT = "import"
    EXPORT = "export"
    PART = "part"
    PART_OF = "part_of"


class Combinator(StrEnum):
    SHOW = "show"
    HIDE = "hide"


class SiteKind(StrEnum):
    REFERENCE = "reference"
    CALL = "call"
    CREATION = "creation"
    TYPE = "type"
    EXTENDS = "extends"
    IMPLEMENTS = "implements"
    WITH = "with"
    FIELD_FORMAL = "field_formal"
    SUPER_FORMAL = "super_formal"
    BINDING = "binding"
    ASSIGNMENT = "assignment"


class SiteUse(StrEnum):
    TYPE = "type"
    READ = "read"
    WRITE = "write"
    READ_WRITE = "read_write"
    VALUE = "value"


class Modifier(StrEnum):
    ABSTRACT = "abstract"
    BASE = "base"
    FINAL = "final"
    INTERFACE = "interface"
    SEALED = "sealed"
    MIXIN = "mixin"


class ConcernKind(StrEnum):
    SYNTAX_ERROR = "syntax_error"
    INVALID_ENCODING = "invalid_encoding"
    LANGUAGE_VERSION_ERROR = "LanguageVersionError"
    UNSUPPORTED_DIRECTIVE = "unsupported_directive"
    UNSUPPORTED_SYNTAX = "unsupported_syntax"
    UNSUPPORTED_DECLARATION = "unsupported_declaration"


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
    kind: ParameterKind
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
    kind: MemberKind
    span: Span
    annotation: str | None = None
    return_type: str | None = None
    visibility: Visibility = Visibility.PUBLIC
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
    kind: DefinitionKind
    span: Span
    visibility: Visibility = Visibility.PUBLIC
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
    modifiers: tuple[Modifier, ...] = ()
    constant: bool = False
    final: bool = False
    late: bool = False
    enum_member_spans: tuple[Span, ...] = ()


@dataclass(frozen=True, slots=True)
class Directive:
    kind: DirectiveKind
    span: Span
    target: str | None = None
    prefix: str | None = None
    deferred: bool = False
    show: tuple[str, ...] = ()
    hide: tuple[str, ...] = ()
    combinators: tuple[tuple[Combinator, tuple[str, ...]], ...] = ()
    alternatives: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True, slots=True)
class Site:
    kind: SiteKind
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
    use: SiteUse = SiteUse.VALUE
    computed: bool = False
    shadowed_names: tuple[str, ...] = ()
    closure_scope: bool = False
    expression_source: str | None = None
    initializer_source: str | None = None


@dataclass(frozen=True, slots=True)
class Concern:
    kind: ConcernKind
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
