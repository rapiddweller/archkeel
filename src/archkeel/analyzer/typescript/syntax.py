# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The single immutable lexical syntax port shared by TypeScript parsing and collection."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ReferenceForm(Enum):
    IMPORT = "import"
    REEXPORT = "reexport"
    IMPORT_EQUALS = "import_equals"
    DYNAMIC_IMPORT = "dynamic_import"
    IMPORT_TYPE = "import_type"
    REQUIRE = "require"


class DefinitionKind(Enum):
    CLASS = "class"
    INTERFACE = "interface"
    ENUM = "enum"
    METHOD = "method"
    FUNCTION = "function"
    TYPE_ALIAS = "type_alias"
    CONSTANT = "constant"


class Visibility(Enum):
    PUBLIC = "public"
    PROTECTED = "protected"
    PRIVATE = "private"


class BaseRelationship(Enum):
    INHERITS = "inherits"
    REALIZES = "realizes"


class SiteKind(Enum):
    CALL = "call"
    NEW = "new"
    REFERENCE = "reference"


class SiteUse(Enum):
    TYPE = "type"
    VALUE = "value"
    MEMBER = "member"


class ReceiverKind(Enum):
    NONE = "none"
    THIS = "this"
    OTHER = "other"


@dataclass(frozen=True, slots=True)
class Span:
    """A 1-based line and UTF-16 column, as the TypeScript compiler reports them."""

    line: int
    end_line: int
    column: int
    excerpt: str


@dataclass(frozen=True, slots=True)
class Reference:
    form: ReferenceForm
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
    visibility: Visibility | None
    static: bool
    literal: str | None = None
    decorator_sources: tuple[tuple[str, Span], ...] = ()


@dataclass(frozen=True, slots=True)
class Base:
    name: str
    relationship: BaseRelationship
    span: Span


@dataclass(frozen=True, slots=True)
class Definition:
    name: str
    kind: DefinitionKind
    span: Span
    parent: str | None
    visibility: Visibility | None
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
    decorator_sources: tuple[tuple[str, Span], ...] = ()


@dataclass(frozen=True, slots=True)
class Site:
    kind: SiteKind
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
    use: SiteUse = SiteUse.VALUE
    scope_ambiguous: bool = False
    scope_column: int | None = None
    receiver_kind: ReceiverKind = ReceiverKind.NONE


@dataclass(frozen=True, slots=True)
class ImportBinding:
    span: Span
    imported: str
    local: str
    namespace: bool = False
    type_only: bool = False


@dataclass(frozen=True, slots=True)
class StringComparison:
    """A written literal participating in lexical equality, with its known named owner."""

    span: Span
    scope: str | None


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
    string_comparisons: tuple[StringComparison, ...] = ()
