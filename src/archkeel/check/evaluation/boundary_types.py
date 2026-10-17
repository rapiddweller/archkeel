# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Evaluate boundary types and public API signatures."""

from __future__ import annotations

import builtins
from collections import defaultdict
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, replace
from enum import StrEnum
from typing import Final, NamedTuple, TypeAlias

from archkeel.ir.facts import (
    SourceSymbolKind,
    parse_source_symbol_kind,
    MethodKind,
    PropertyOperation,
    PropertyOrigin,
    SymbolClassKind,
    parse_method_kind,
    parse_symbol_class_kind,
    property_binding,
)
from archkeel.ir.facts_codec import RawData as RecordData
from archkeel.ir.facts_codec import RawEvidence, RawRecord, classified
from archkeel.ir.model import (
    ArchitectureContract,
    BoundaryAliasBody,
    BoundaryTypeAllowance,
    BoundaryTypesRule,
    ComponentOwnership,
    EvidenceClass,
    ForbiddenDependencyRule,
    component_owns_module,
    facade_covers,
    in_scope,
    stable_id,
)
from archkeel.ir.profiles import Profile
from archkeel.ir.source_records import FRAMEWORK_BASES as _FRAMEWORK_BASES
from archkeel.ir.source_records import is_public_method_name as _is_public_method_name
from archkeel.ir.type_shapes import (
    LiteralKind,
    TypeApplication,
    TypeList,
    TypeLiteral,
    TypeMember,
    TypeName,
    TypeShape,
    TypeShapeIndex,
    TypeUnion,
    TypeUnpack,
    UnresolvedType,
)

from .rule_support import (
    DeclaredFacade,
    FacadeEntry,
    ReexportIndex,
    UncertainReexportOrigins,
    _forbidden_dependency_matches,
    _reexport_index,
    _rule_evaluation_receipt,
    exports_by_module,
)

_BROAD_BOUNDARY_TYPES: Final = ("object",)
_TYPED_MAPPING_UNION_VERSIONS: Final = frozenset(
    {"3.1.0", "3.2.0", "3.3.0", "3.4.0", "3.5.0", "3.6.0"}
)


def _is_broad_boundary_type(
    annotation: str,
    module: str,
    imports_by_binding: BindingIndex,
    classes_by_location: BindingIndex,
) -> bool:
    """Bare broad builtins only when their module binding is unshadowed."""
    return (
        annotation in _BROAD_BOUNDARY_TYPES
        and not _has_star_import(module, imports_by_binding)
        and (module, annotation) not in imports_by_binding
        and (module, annotation) not in classes_by_location
    )


_EXEMPT_CLASS_KINDS: Final = frozenset({SymbolClassKind.ENUM, SymbolClassKind.PYDANTIC_MODEL})


# Issue #9 names a builtin as an acceptable boundary type, and a builtin needs no import and
# defines no symbol of its own, so `resolve_named_type` returns nothing for one. The set comes
# from the running interpreter rather than a list kept here, the way `resolve.py` and `calls.py`
# already answer the same question, so one repository holds one answer to what a builtin is.
_BUILTIN_NAMES: Final = frozenset(dir(builtins))
# shortcut: quoted proof covers str/object; extend for another accepted builtin use case.
_QUOTED_BUILTIN_TYPE_ORIGINS: Final = frozenset({("builtins", "str"), ("builtins", "object")})


_BROAD_BOUNDARY_REASON: Final = "instead of a typed model"


# Why a position stayed undecided, in the order the limit record reports them (AD-67).
# `ambiguous_binding` (AD-74) sits next to `unresolved_name`: both are bare names that failed
# to resolve, but one failed because nothing defines it and the other because two records do --
# a reader who sees only the count needs the two kept apart to tell "unreadable annotation"
# from "this name is bound twice".
class _Cause(StrEnum):
    MISSING_ANNOTATION = "missing_annotation"
    INHERITED_SURFACE = "inherited_surface"
    FORWARD_REFERENCE = "forward_reference"
    DOTTED_NAME = "dotted_name"
    GENERIC = "generic"
    UNION = "union"
    AMBIGUOUS_BINDING = "ambiguous_binding"
    AMBIGUOUS_FACADE = "ambiguous_facade"
    UNRESOLVED = "unresolved_name"
    EXTERNAL = "external_type"
    NESTED_TYPE = "nested_type"
    OTHER = "other"


_UNDECIDABLE_KINDS: Final = tuple(str(reason) for reason in _Cause)


@dataclass(frozen=True, slots=True)
class _Position:
    """The one reading of an annotated position: the named types it resolves to, plus the
    `boundary_types` rule's verdict on them -- a violation reason, an undecidable kind, or
    neither.

    Neither is a decided pass. AD-63 answered all three with `None`, so a position the rule
    could not decide was indistinguishable from one it decided clean, and the rule's verdict
    read `no violation == probably fine` where the rest of the tool reads PASS, VIOLATION or
    UNKNOWN (AD-26). Naming the undecidable kind is what lets the rule report its own
    denominator instead of staying silent (AD-67).

    `resolved` is what `facade_types` (AD-65) reads off this same walk: a type reaches a
    component's boundary by being named in a signature, whether or not the rule's own
    exemptions (a builtin, an enum, an already-declared type) let it pass, so it is filled in
    on every branch that resolves a name and left empty on every branch that does not -- one
    walk of the annotation feeding both readers instead of each re-deriving it (AD-69's own
    Limit, closed for good).

    `named_origins` retains the bare name and alias chain, excluding expanded field types,
    so publication entry identity cannot include a component facade's nested fields (AD-131).
    """

    violation: str | None = None
    undecidable: _Cause | None = None
    unknown_context: str | None = None
    referenced_members_static: bool = True
    contains_callable: bool = False
    resolved: tuple[tuple[str, str], ...] = ()
    named_origins: tuple[tuple[str, str], ...] = ()
    path: tuple[str, ...] = ()
    nested_annotation: str | None = None
    violations: tuple[tuple[str, tuple[str, ...], str | None, int], ...] = ()
    mapping_occurrences: tuple[_MappingOccurrence, ...] = ()
    field_positions: tuple[_FieldPosition, ...] = ()
    field_declarations: tuple[tuple[str, ...], ...] = ()
    mapping_alternatives: tuple[_MappingAlternatives, ...] = ()
    exact_nested_map_chain: bool = False
    native_iterable_annotation: str | None = None
    bound_alias: _BoundAliasBody | None = None
    typed_mapping_union: _TypedMappingUnion | None = None
    typed_union_checked: bool = False

    def __post_init__(self) -> None:
        if self.undecidable is not None:
            builtins.object.__setattr__(self, "undecidable", _Cause(self.undecidable))


@dataclass(frozen=True, slots=True)
class _BoundAliasBody:
    binding: BoundaryAliasBody
    metadata_origin: tuple[str, str]
    import_bindings: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True, slots=True)
class _TypedMappingUnion:
    shape: str
    alias_body: BoundaryAliasBody | None = None
    key_alias_body: BoundaryAliasBody | None = None
    source_origins: tuple[tuple[str, str], ...] = ()
    import_bindings: tuple[tuple[str, str], ...] = ()


class _FieldPosition(NamedTuple):
    """Keep a leaf declaration tied to its member finding before deduplication."""

    finding: tuple[str, tuple[str, ...], str | None, int]
    annotation: str
    alias_free: bool = True


class _MappingOccurrence(NamedTuple):
    annotation: str
    depth: int
    path: tuple[str, ...] = ()
    alias_free: bool = True
    opaque_value_depth: int | None = None
    syntax_route: tuple[int, ...] | None = None
    literal_arm: str | None = None

    def legacy(self) -> _MappingOccurrence:
        return self._replace(syntax_route=None, literal_arm=None)


class _MappingAlternatives(NamedTuple):
    annotation: str
    occurrences: tuple[_MappingOccurrence, ...]


# A container whose declared element type is the whole of what actually crosses the boundary
# (AD-67). `dict`/`Dict` are absent because AD-58 already reports a `dict[...]` as broad, and
# mappings are broad records, not a way to bypass the dict rule with an abstract annotation.
_COLLECTION_CONTAINERS: Final = frozenset(
    {
        "list",
        "List",
        "set",
        "Set",
        "frozenset",
        "FrozenSet",
        "tuple",
        "Tuple",
        "Sequence",
        "MutableSequence",
        "Iterable",
        "Iterator",
        "Collection",
        "AbstractSet",
    }
)


def _split_type_parameters(inner: str) -> list[str] | None:
    """Split one subscript's parameters on its top-level commas.

    None when the brackets do not balance, which is how `Sequence[int] | list[str]` is told
    apart from a single subscript: both end in `]`, only one of them is one (AD-67).
    """
    parameters: list[str] = []
    current = ""
    depth = 0
    for character in inner:
        if character == "[":
            depth += 1
        elif character == "]":
            depth -= 1
            if depth < 0:
                return None
        if character == "," and depth == 0:
            parameters.append(current.strip())
            current = ""
        else:
            current += character
    if depth:
        return None
    parameters.append(current.strip())
    return parameters


def _typing_module_binding(module: str, binding: str, imports_by_binding: BindingIndex) -> bool:
    imported = imports_by_binding.get((module, binding))
    return (
        isinstance(imported, dict)
        and imported["target_module"] == "typing"
        and imported["symbol"] is None
    )


_PROVEN_MAPPINGS: Final = frozenset(
    {
        ("builtins", "dict"),
        ("typing", "Dict"),
        ("typing", "Mapping"),
        ("typing", "MutableMapping"),
        ("collections.abc", "Mapping"),
        ("collections.abc", "MutableMapping"),
    }
)


_PROVEN_SCALAR_LEAVES: Final = frozenset({("datetime", "datetime")})


def _proven_type_head(
    head: TypeShape,
    module: str,
    imports_by_binding: BindingIndex,
    classes_by_location: BindingIndex,
    origins: frozenset[tuple[str, str]],
) -> _Position | bool:
    """Prove a known origin without trusting a shadowed or ambiguous binding."""
    if isinstance(head, TypeName):
        binding, member = head.name, None
    elif isinstance(head, TypeMember) and isinstance(head.owner, TypeName):
        binding, member = head.owner.name, head.member
    else:
        return False
    key = (module, binding)
    if _has_star_import(module, imports_by_binding):
        return _Position(undecidable=_Cause.OTHER)
    if _binding_is_ambiguous(key, imports_by_binding, classes_by_location):
        return _Position(undecidable=_Cause.AMBIGUOUS_BINDING)
    if (
        member is None
        and ("builtins", binding) in origins
        and key not in imports_by_binding
        and key not in classes_by_location
    ):
        origin_module, origin_name = "builtins", binding
    else:
        imported = imports_by_binding.get(key)
        if not isinstance(imported, dict):
            return False
        target, symbol = imported["target_module"], imported["symbol"]
        if member is None:
            origin_module, origin_name = target, symbol
        else:
            # Import records cannot distinguish a dotted module from an alias to its root.
            if symbol is None and target == "collections.abc" and binding == "collections":
                return _Position(undecidable=_Cause.DOTTED_NAME)
            origin_module = f"{target}.{symbol}" if symbol else target
            origin_name = member
    if (origin_module, origin_name) not in origins:
        return False
    imported = imports_by_binding.get(key)
    if isinstance(imported, dict) and imported.get("source_binding_unique") is False:
        return _Position(undecidable=_Cause.AMBIGUOUS_BINDING)
    if (origin_module, origin_name) in classes_by_location:
        return _Position(undecidable=_Cause.AMBIGUOUS_BINDING)
    return True


def _mapping_parameters(
    annotation: str,
    module: str,
    imports_by_binding: BindingIndex,
    classes_by_location: BindingIndex,
    *,
    type_shapes: TypeShapeIndex,
) -> list[str] | _Position | None:
    expression = type_shapes.get(annotation)
    if not isinstance(expression, TypeApplication):
        return None
    proven = _proven_type_head(
        expression.head, module, imports_by_binding, classes_by_location, _PROVEN_MAPPINGS
    )
    if isinstance(proven, _Position):
        return proven
    if not proven:
        return None
    if not expression.tuple_arguments or len(expression.arguments) != 2:
        return _Position(undecidable=_Cause.GENERIC)
    if any(
        isinstance(arg, TypeUnpack)
        or (isinstance(arg, TypeLiteral) and arg.kind is LiteralKind.ELLIPSIS)
        for arg in expression.arguments
    ):
        return _Position(undecidable=_Cause.GENERIC)
    return [arg.text for arg in expression.arguments]


def _bare_type_verdict(
    annotation: str,
    module: str,
    imports_by_binding: BindingIndex,
    classes_by_location: BindingIndex,
    *,
    type_shapes: TypeShapeIndex,
) -> _Position | None:
    """Bare mappings are broad; a proven stdlib scalar is a leaf (AD-123, AD-132)."""
    expression = type_shapes.get(annotation)
    if not isinstance(expression, (TypeName, TypeMember)):
        return None
    proven = _proven_type_head(
        expression, module, imports_by_binding, classes_by_location, _PROVEN_MAPPINGS
    )
    if isinstance(proven, _Position):
        return proven
    if proven:
        return _Position(violation=_BROAD_BOUNDARY_REASON)
    scalar = _proven_type_head(
        expression, module, imports_by_binding, classes_by_location, _PROVEN_SCALAR_LEAVES
    )
    if isinstance(scalar, _Position):
        return scalar
    return _Position() if scalar else None


def _typing_wrapper_inner(
    annotation: str,
    module: str,
    imports_by_binding: BindingIndex,
    classes_by_location: BindingIndex,
    wrapper: str,
    *,
    type_shapes: TypeShapeIndex,
) -> str | tuple[str, ...] | None:
    """Return the type argument for a statically bound typing wrapper."""
    expression = type_shapes.get(annotation)
    if not isinstance(expression, TypeApplication):
        return None
    expected_modules = (
        ("typing", "typing_extensions") if wrapper in ("Required", "NotRequired") else ("typing",)
    )
    head = expression.head
    if isinstance(head, TypeName):
        key = (module, head.name)
        if _binding_is_ambiguous(key, imports_by_binding, classes_by_location):
            return None
        imported = imports_by_binding.get(key)
        if not isinstance(imported, dict) or imported["target_module"] not in expected_modules:
            return None
        if imported["symbol"] != wrapper:
            return None
    elif isinstance(head, TypeMember) and isinstance(head.owner, TypeName):
        key = (module, head.owner.name)
        if _binding_is_ambiguous(key, imports_by_binding, classes_by_location):
            return None
        imported = imports_by_binding.get(key)
        if (
            head.member != wrapper
            or not isinstance(imported, dict)
            or imported["target_module"] not in expected_modules
            or imported["symbol"] is not None
        ):
            return None
    else:
        return None
    parameters = expression.arguments
    if (
        wrapper in ("Required", "NotRequired")
        and not expression.tuple_arguments
        and len(parameters) == 1
    ):
        return parameters[0].text
    if wrapper == "Annotated" and len(parameters) >= 2:
        return parameters[0].text
    if wrapper == "Literal" and parameters:
        names: list[str] = []
        for value in parameters:
            if isinstance(value, TypeLiteral) and value.kind in {
                LiteralKind.STRING,
                LiteralKind.INTEGER,
                LiteralKind.BOOLEAN,
                LiteralKind.NONE,
            }:
                continue
            if isinstance(value, TypeName):
                names.append(value.name)
                continue
            if isinstance(value, TypeMember):
                names.append(value.text)
                continue
            return None
        return tuple(names)
    return None


def _collection_parameters(
    annotation: str,
    module: str,
    imports_by_binding: BindingIndex,
) -> list[str] | None:
    """The type parameters of `Container[...]` when the container is a known collection.

    None when the annotation is not exactly one such subscript, so dotted containers without a
    proven `typing` import, a union around one and a mapping all stay where they were. The
    `...` of `tuple[X, ...]` is an arity, not a type, and is dropped (AD-67).
    """
    head, bracket, rest = annotation.partition("[")
    if "." in head:
        binding = annotation.split(".", 1)[0]
        container = head[len(binding) + 1 :]
        if container not in _COLLECTION_CONTAINERS or not _typing_module_binding(
            module, binding, imports_by_binding
        ):
            return None
    else:
        container = head
        imported = imports_by_binding.get((module, container))
        if container not in _COLLECTION_CONTAINERS and (
            not isinstance(imported, dict)
            or imported["target_module"] != "typing"
            or imported["symbol"] not in _COLLECTION_CONTAINERS
        ):
            return None
        if isinstance(imported, dict) and imported["target_module"] == "typing":
            container = imported["symbol"] or container
    if not bracket or not rest.endswith("]") or container not in _COLLECTION_CONTAINERS:
        return None
    parameters = _split_type_parameters(rest[:-1])
    if parameters is None:
        return None
    return [parameter for parameter in parameters if parameter != "..."]


def _unresolvable_shape(annotation: str) -> _Cause:
    """Name why an annotation that is not one bare identifier cannot be decided (AD-67)."""
    head = annotation.split("[", 1)[0]
    if "." in head:
        return _Cause.DOTTED_NAME
    if "[" in annotation:
        return _Cause.GENERIC
    if "|" in annotation:
        return _Cause.UNION
    return _Cause.OTHER


def _union_parameters(
    annotation: str, module: str, imports_by_binding: BindingIndex, *, type_shapes: TypeShapeIndex
) -> list[str] | None:
    """Return members only for syntactically valid standard union annotations."""
    expression = type_shapes.get(annotation)
    if isinstance(expression, TypeUnion):
        return [expression.left.text, expression.right.text]
    if not isinstance(expression, TypeApplication):
        return None
    head = expression.head
    if isinstance(head, TypeName):
        name = head.name
        imported = imports_by_binding.get((module, name))
        if (
            not isinstance(imported, dict)
            or imported["target_module"] != "typing"
            or imported["symbol"] not in {"Union", "Optional"}
        ):
            return None
        name = imported["symbol"]
    elif isinstance(head, TypeMember) and isinstance(head.owner, TypeName):
        if not _typing_module_binding(module, head.owner.name, imports_by_binding):
            return None
        name = head.member
    else:
        return None
    if name not in {"Union", "Optional"}:
        return None
    members = expression.arguments
    if name == "Optional":
        return [members[0].text, "None"] if len(members) == 1 else None
    return [member.text for member in members] if len(members) >= 2 else None


class _AmbiguousBinding:
    """Sentinel for a `(module, name)` key more than one distinct binding claims.

    Nothing recorded says which import or which same-named class definition is the one Python
    actually binds -- that is `boundary_type_indexes`'s whole reason to exist -- so a key with
    more than one claimant maps here instead of to whichever claimant happened to arrive last.
    """

    __slots__ = ()


_AMBIGUOUS: Final = _AmbiguousBinding()


# `boundary_type_indexes`'s own return shape: a `(module, name)` key maps to one binding target,
# or to `_AMBIGUOUS` when distinct targets or definitions claim it.
class BindingIndex(dict[tuple[str, str], RecordData | _AmbiguousBinding]):
    """Bindings plus same-owner facade evidence kept internal to type resolution."""

    def __init__(self) -> None:
        super().__init__()
        self.owner_facade_type_states: dict[tuple[str, str, str], bool] = {}
        self.ownership_contracts: tuple[ArchitectureContract, ...] = ()
        self.module_bindings: BindingIndex | None = None
        self.source_modules: frozenset[str] = frozenset()


def _has_star_import(module: str, imports_by_binding: BindingIndex) -> bool:
    return (module, "*") in imports_by_binding


def _binding_is_ambiguous(
    key: tuple[str, str], imports_by_binding: BindingIndex, classes_by_location: BindingIndex
) -> bool:
    imported = imports_by_binding.get(key)
    local = classes_by_location.get(key)
    return (
        imported is _AMBIGUOUS
        or local is _AMBIGUOUS
        or (imported is not None and local is not None)
    )


def resolve_named_type(
    annotation: str,
    module: str,
    imports_by_binding: BindingIndex,
    classes_by_location: BindingIndex,
) -> tuple[str, str] | _AmbiguousBinding | None:
    """Resolve a bare annotation name to the module and name where it is actually defined.

    Reuses the same `binding`/`origin_definition` fields `imports` already carries for
    `interface_boundary` (AD-9), so a `from ir import ObservationResult` import lets an
    `ObservationResult` annotation resolve the way the import itself would. Only a single bare
    identifier is attempted, never a dotted name, a subscripted generic or a forward-reference
    string: those stay unresolved exactly as AD-58 left them. A builtin needs no import and
    defines no symbol of its own, so it still resolves to nothing here; what changed is that
    the caller no longer reads that nothing as silence but asks the interpreter whether the
    name is a builtin, and calls it a decided pass when it is (AD-67).

    Returns `_AMBIGUOUS` when the name has distinct bindings in `module` (imports to different
    targets, an import and a local class, or colliding local definitions), or when it resolves
    to a location two same-named class definitions both claim. The records carry no source order,
    so the caller must read that apart from an unresolved name rather than pick a claimant.
    """
    if not annotation.isidentifier():
        return None
    key = (module, annotation)
    if _binding_is_ambiguous(key, imports_by_binding, classes_by_location):
        return _AMBIGUOUS
    imported = imports_by_binding.get(key)
    class_entry = classes_by_location.get(key)
    if isinstance(imported, dict):
        origin = imported["origin_definition"]
        # A bare `import pkg as name` binds a module, not a name; nonsensical as a type.
        if imported["symbol"] is None or not origin:
            return None
        origin_module, _, origin_name = origin.rpartition(".")
        chain = imported["reexport_chain"] or [origin]
        for entry in chain:
            entry_module, _, entry_name = entry.rpartition(".")
            if _binding_is_ambiguous(
                (entry_module, entry_name), imports_by_binding, classes_by_location
            ):
                return _AMBIGUOUS
        return origin_module, origin_name
    if class_entry is not None:
        return module, annotation
    return None


def _binding_index(entries: Iterator[tuple[str, str, object, RecordData]]) -> BindingIndex:
    """Index a binding once, or mark distinct targets ambiguous regardless of input order.

    Repeating the same import target does not change a Python binding and keeps the first record.
    Separate class definitions carry separate identities even when their bodies are identical
    (AD-74).
    """
    index = BindingIndex()
    identities: dict[tuple[str, str], object] = {}
    for scope, name, identity, data in entries:
        key = (scope, name)
        if key not in index:
            index[key] = data
            identities[key] = identity
        elif identities[key] != identity:
            index[key] = _AMBIGUOUS
    return index


def boundary_type_indexes(
    symbols: Sequence[RawRecord],
    imports: Sequence[RawRecord],
    contract: ArchitectureContract | None = None,
    exports_by_module: dict[str, frozenset[str]] | None = None,
    uncertain_reexport_origins: UncertainReexportOrigins | None = None,
    ancestor_contracts: Sequence[ArchitectureContract] = (),
) -> tuple[BindingIndex, BindingIndex]:
    """Index `imports` by (module, local binding) and top-level classes by (module, name).

    Both are `resolve_named_type`'s own lookups, built once per call instead of once per
    function checked: `boundary_types` may inspect many facade functions below one `source`,
    and `public_api_exposed_types` every declared `public_api` entry.

    `symbols` and `imports` arrive sorted by each record's own content-hash id, not source
    order, so distinct definitions sharing a binding must not let arrival order decide which
    record wins. Repeating one import target is still one binding (AD-74).
    """
    imports_by_binding = _binding_index(
        (
            data["source_module"],
            data["binding"],
            (data["target_module"], data["symbol"]),
            data,
        )
        for data in (item["data"] for item in imports)
    )
    imports_by_binding.source_modules = frozenset(exports_by_module or {})
    uncertain_origins = uncertain_reexport_origins or {}
    for item in imports:
        data = item["data"]
        key = (data["source_module"], data["binding"])
        if key in imports_by_binding and f"{key[0]}.{key[1]}" in uncertain_origins:
            imports_by_binding[key] = _AMBIGUOUS
    classes_by_location = _binding_index(
        (data["module"], data["name"], item["id"], data)
        for item in symbols
        for data in [item["data"]]
        for kind in [parse_source_symbol_kind(item["kind"])]
        # A nested class is never what a module-level annotation's bare name resolves to.
        if (kind is SourceSymbolKind.CLASS and data.get("parent") is None)
        or kind in {SourceSymbolKind.TYPE_ALIAS, SourceSymbolKind.STATIC_CONSTANT, SourceSymbolKind.DYNAMIC_BINDING}
    )
    for item in symbols:
        data = item["data"]
        key = (data["module"], data["name"])
        if parse_source_symbol_kind(item["kind"]) is SourceSymbolKind.FUNCTION and (
            key in classes_by_location
            or key in imports_by_binding
            or data["name"] in _BUILTIN_NAMES
        ):
            classes_by_location[key] = _AMBIGUOUS
    ownership_contracts = ((contract,) if contract is not None else ()) + tuple(ancestor_contracts)
    imports_by_binding.ownership_contracts = ownership_contracts
    for owner_contract in ownership_contracts:
        _index_owner_facade_type_states(
            imports,
            imports_by_binding,
            owner_contract,
            exports_by_module or {},
            uncertain_reexport_origins or {},
        )
    return imports_by_binding, classes_by_location


def _index_owner_facade_type_states(
    imports: Sequence[RawRecord],
    imports_by_binding: BindingIndex,
    contract: ArchitectureContract,
    exports_by_module: dict[str, frozenset[str]],
    uncertain_reexport_origins: UncertainReexportOrigins,
) -> None:
    proven: set[tuple[str, str, str]] = set()
    uncertain: set[tuple[str, str, str]] = set()
    for item in imports:
        data = item["data"]
        module, binding = data["source_module"], data["binding"]
        owner = contract.component_for(module)
        if (
            owner is None
            or not isinstance(binding, str)
            or not facade_covers(module, binding, owner, exports_by_module)
        ):
            continue
        qualified_binding = f"{module}.{binding}"
        for origin in uncertain_reexport_origins.get(qualified_binding, frozenset()):
            origin_module, separator, origin_name = origin.rpartition(".")
            if separator and contract.component_for(origin_module) == owner:
                uncertain.add((owner.id, origin_module, origin_name))
        origin_definition = data.get("origin_definition")
        if (
            data.get("reexport") is True
            and imports_by_binding.get((module, binding)) is not _AMBIGUOUS
            and isinstance(origin_definition, str)
        ):
            origin_module, separator, origin_name = origin_definition.rpartition(".")
            if separator and contract.component_for(origin_module) == owner:
                proven.add((owner.id, origin_module, origin_name))
    imports_by_binding.owner_facade_type_states.update({key: False for key in uncertain})
    imports_by_binding.owner_facade_type_states.update({key: True for key in proven})


def _typing_wrapper_verdict(
    annotation: str,
    module: str,
    contract: ArchitectureContract,
    exports_by_module: dict[str, frozenset[str]],
    imports_by_binding: BindingIndex,
    classes_by_location: BindingIndex,
    *,
    type_shapes: TypeShapeIndex,
    enter_collections: bool,
    enter_fields: bool,
    visited: frozenset[tuple[str, str]],
    aliases_seen: frozenset[tuple[str, str]],
) -> _Position | None:
    for wrapper in ("Required", "NotRequired", "Annotated", "Literal"):
        inner = _typing_wrapper_inner(
            annotation,
            module,
            imports_by_binding,
            classes_by_location,
            wrapper,
            type_shapes=type_shapes,
        )
        if wrapper == "Literal":
            if isinstance(inner, tuple):
                decided = [
                    (
                        name,
                        _enum_member_verdict(
                            name,
                            module,
                            contract,
                            exports_by_module,
                            imports_by_binding,
                            classes_by_location,
                            visited=visited,
                            aliases_seen=aliases_seen,
                            type_shapes=type_shapes,
                        )
                        or _boundary_type_verdict(
                            name,
                            module,
                            contract,
                            exports_by_module,
                            imports_by_binding,
                            classes_by_location,
                            enter_collections=enter_collections,
                            visited=visited,
                            enter_fields=enter_fields,
                            _aliases_seen=aliases_seen,
                            _require_static_constant=True,
                            type_shapes=type_shapes,
                        ),
                    )
                    for name in inner
                ]
                return _combine_position_verdicts(decided)
        elif isinstance(inner, str):
            return _boundary_type_verdict(
                inner,
                module,
                contract,
                exports_by_module,
                imports_by_binding,
                classes_by_location,
                enter_collections=enter_collections,
                visited=visited,
                enter_fields=enter_fields,
                _aliases_seen=aliases_seen,
                type_shapes=type_shapes,
            )
    return None


def _quoted_builtin_type(
    shape: TypeShape | None,
    module: str,
    imports: BindingIndex,
    classes: BindingIndex,
) -> bool:
    if isinstance(shape, TypeName):
        return (
            _proven_type_head(shape, module, imports, classes, _QUOTED_BUILTIN_TYPE_ORIGINS) is True
        )
    if isinstance(shape, TypeLiteral):
        return shape.kind is LiteralKind.NONE
    if isinstance(shape, TypeUnion):
        return _quoted_builtin_type(shape.left, module, imports, classes) and _quoted_builtin_type(
            shape.right, module, imports, classes
        )
    return False


def _boundary_type_verdict(
    annotation: str,
    module: str,
    contract: ArchitectureContract,
    exports_by_module: dict[str, frozenset[str]],
    imports_by_binding: BindingIndex,
    classes_by_location: BindingIndex,
    *,
    type_shapes: TypeShapeIndex,
    enter_collections: bool = True,
    visited: frozenset[tuple[str, str]] = frozenset(),
    enter_fields: bool = True,
    _aliases_seen: frozenset[tuple[str, str]] = frozenset(),
    _require_static_constant: bool = False,
    uncertain_bindings: Sequence[str] = (),
) -> _Position:
    """Read one annotation for boundary_types and facade_types (AD-58, AD-69).
    Broad or undeclared types violate; builtins, enums and declared types pass. Other shapes
    report why undecidable, with bounded collection and field descent (AD-67, AD-84).
    """
    if uncertain_bindings:
        scoped_classes = BindingIndex()
        for key in classes_by_location:
            scoped_classes[key] = classes_by_location[key]
        for name in uncertain_bindings:
            scoped_classes[module, name] = _AMBIGUOUS
        scoped_classes.module_bindings = classes_by_location
        if classes_by_location.module_bindings is not None:
            scoped_classes.module_bindings = classes_by_location.module_bindings
        classes_by_location = scoped_classes
    if not annotation:
        return _Position(undecidable=_Cause.MISSING_ANNOTATION)
    if annotation.startswith(("'", '"')):
        decoded = type_shapes.get(annotation)
        if decoded is not None and _quoted_builtin_type(
            decoded, module, imports_by_binding, classes_by_location
        ):
            quoted = _boundary_type_verdict(
                decoded.text,
                module,
                contract,
                exports_by_module,
                imports_by_binding,
                classes_by_location,
                type_shapes=type_shapes,
                enter_collections=enter_collections,
                visited=visited,
                enter_fields=enter_fields,
                _aliases_seen=_aliases_seen,
                _require_static_constant=_require_static_constant,
            )
            return _without_literal_mapping_arms(quoted)
        return _Position(undecidable=_Cause.FORWARD_REFERENCE)
    wrapped = _typing_wrapper_verdict(
        annotation,
        module,
        contract,
        exports_by_module,
        imports_by_binding,
        classes_by_location,
        enter_collections=enter_collections,
        enter_fields=enter_fields,
        visited=visited,
        aliases_seen=_aliases_seen,
        type_shapes=type_shapes,
    )
    if wrapped is not None:
        return _without_literal_mapping_arms(
            replace(wrapped, bound_alias=None, typed_mapping_union=None)
        )
    if _is_broad_boundary_type(annotation, module, imports_by_binding, classes_by_location):
        return _Position(violation=_BROAD_BOUNDARY_REASON)
    bare_type = _bare_type_verdict(
        annotation, module, imports_by_binding, classes_by_location, type_shapes=type_shapes
    )
    if bare_type is not None:
        return bare_type
    if not annotation.isidentifier():
        verdict = _annotation_shape_verdict(
            annotation,
            module,
            contract,
            exports_by_module,
            imports_by_binding,
            classes_by_location,
            enter_collections=enter_collections,
            visited=visited,
            enter_fields=enter_fields,
            _aliases_seen=_aliases_seen,
            type_shapes=type_shapes,
        )
        native_iterable = (
            not _aliases_seen
            and verdict.undecidable is None
            and _native_iterable_shape(
                annotation, module, imports_by_binding, classes_by_location, type_shapes
            )
        )
        return _Position(
            violation=verdict.violation,
            undecidable=verdict.undecidable,
            unknown_context=verdict.unknown_context,
            referenced_members_static=verdict.referenced_members_static,
            contains_callable=verdict.contains_callable,
            resolved=verdict.resolved,
            named_origins=verdict.named_origins,
            path=verdict.path,
            nested_annotation=verdict.nested_annotation,
            violations=verdict.violations,
            mapping_occurrences=verdict.mapping_occurrences,
            field_positions=verdict.field_positions,
            field_declarations=verdict.field_declarations,
            mapping_alternatives=verdict.mapping_alternatives,
            exact_nested_map_chain=verdict.exact_nested_map_chain,
            native_iterable_annotation=annotation if native_iterable else None,
            typed_mapping_union=verdict.typed_mapping_union,
            typed_union_checked=verdict.typed_union_checked,
        )
    verdict = _named_type_verdict(
        annotation,
        module,
        contract,
        exports_by_module,
        imports_by_binding,
        classes_by_location,
        enter_collections=enter_collections,
        enter_fields=enter_fields,
        visited=visited,
        aliases_seen=_aliases_seen,
        require_static_constant=_require_static_constant,
        type_shapes=type_shapes,
    )

    return _named_reference_position(
        annotation, module, verdict, imports_by_binding, classes_by_location, type_shapes
    )


def _enum_member_verdict(
    annotation: str,
    module: str,
    contract: ArchitectureContract,
    exports_by_module: dict[str, frozenset[str]],
    imports_by_binding: BindingIndex,
    classes_by_location: BindingIndex,
    *,
    type_shapes: TypeShapeIndex,
    visited: frozenset[tuple[str, str]],
    aliases_seen: frozenset[tuple[str, str]],
) -> _Position | None:
    expression = type_shapes.get(annotation)
    if not isinstance(expression, TypeMember) or not isinstance(expression.owner, TypeName):
        return None
    base = _boundary_type_verdict(
        expression.owner.name,
        module,
        contract,
        exports_by_module,
        imports_by_binding,
        classes_by_location,
        visited=visited,
        enter_fields=False,
        _aliases_seen=aliases_seen,
        type_shapes=type_shapes,
    )
    if base.violation is not None or base.undecidable is not None:
        return None
    enum_origin: tuple[str, str] | None = None
    for resolved in base.resolved:
        symbol = classes_by_location.get(resolved)
        if not isinstance(symbol, dict):
            return None
        if parse_symbol_class_kind(symbol.get("class_kind")) is SymbolClassKind.ENUM:
            if enum_origin is not None:
                return None
            enum_origin = resolved
            continue
        if parse_source_symbol_kind(symbol.get("record_kind")) is not SourceSymbolKind.TYPE_ALIAS:
            return None
        alias = symbol.get("alias")
        if not isinstance(alias, str):
            return None
        alias_expression = type_shapes.get(alias)
        if not isinstance(alias_expression, TypeName):
            return None
    if enum_origin is None:
        return None
    enum = classes_by_location.get(enum_origin)
    if not isinstance(enum, dict) or expression.member not in enum.get("enum_members", ()):
        return None
    return _Position(resolved=(enum_origin,))


def _bound_alias_application(
    shape: TypeShape,
    head: str,
    arity: int,
    module: str,
    imports: BindingIndex,
    classes: BindingIndex,
) -> tuple[TypeShape, ...] | None:
    if (
        not isinstance(shape, TypeApplication)
        or len(shape.arguments) != arity
        or shape.tuple_arguments != (arity > 1)
        or _proven_type_head(shape.head, module, imports, classes, frozenset({("builtins", head)}))
        is not True
    ):
        return None
    return shape.arguments


def _bound_alias_metadata(
    metadata: TypeName,
    module: str,
    alias_origin: tuple[str, str],
    contract: ArchitectureContract,
    exports: dict[str, frozenset[str]],
    imports: BindingIndex,
    classes: BindingIndex,
    type_shapes: TypeShapeIndex,
) -> tuple[tuple[str, str], tuple[tuple[str, str], ...]] | None:
    verdict = _named_type_verdict(
        metadata.name,
        module,
        contract,
        exports,
        imports,
        classes,
        type_shapes=type_shapes,
        enter_collections=False,
        enter_fields=False,
        visited=frozenset(),
        aliases_seen=frozenset({alias_origin}),
        require_static_constant=False,
    )
    if len(verdict.named_origins) != 1:
        return None
    resolved = verdict.named_origins[0]
    symbol = classes.get(resolved)
    imported = imports.get((module, metadata.name))
    if (
        not isinstance(symbol, dict)
        or parse_source_symbol_kind(symbol.get("symbol_category")) is not SourceSymbolKind.CLASS
        or symbol.get("source_binding_unique") is not True
        or (
            symbol.get("class_header_static") is not True
            and symbol.get("typed_dict_header_static") is not True
        )
        or symbol.get("generic_parameters")
        or (
            imported is not None
            and (
                not isinstance(imported, dict)
                or imported.get("source_binding_unique") is not True
                or len(imported["reexport_chain"] or ()) > 1
            )
        )
    ):
        return None
    import_bindings: tuple[tuple[str, str], ...] = (
        ((module, metadata.name),) if imported is not None else ()
    )
    if symbol.get("typed_dict_header_static") is True:
        import_bindings += tuple(
            binding
            for binding, provider in imports.items()
            if binding[0] == resolved[0]
            and isinstance(provider, dict)
            and provider.get("origin_definition")
            in {
                "typing.TypedDict",
                "typing_extensions.TypedDict",
                "typing",
                "typing_extensions",
            }
        )
    return resolved, import_bindings


def _bound_alias_body(
    alias: str,
    origin: tuple[str, str],
    contract: ArchitectureContract,
    exports: dict[str, frozenset[str]],
    imports: BindingIndex,
    classes: BindingIndex,
    type_shapes: TypeShapeIndex,
) -> _BoundAliasBody | None:
    module, name = origin
    shape = type_shapes.get(alias)
    if shape is None:
        return None
    outer = _bound_alias_application(shape, "tuple", 2, module, imports, classes)
    if outer is None or not isinstance(outer[0], TypeUnion):
        return None
    arms = (outer[0].left, outer[0].right)
    rendered: list[str] = []
    metadata_origin: tuple[str, str] | None = None
    metadata_imports: tuple[tuple[str, str], ...] = ()
    for arm in arms:
        pair = _bound_alias_application(arm, "tuple", 2, module, imports, classes)
        triple = _bound_alias_application(arm, "tuple", 3, module, imports, classes)
        arguments = pair or triple
        if arguments is None:
            return None
        native = _bound_alias_application(arguments[1], "list", 1, module, imports, classes)
        if (
            _proven_type_head(
                arguments[0], module, imports, classes, frozenset({("builtins", "str")})
            )
            is not True
            or native is None
            or _proven_type_head(
                native[0], module, imports, classes, frozenset({("builtins", "object")})
            )
            is not True
        ):
            return None
        if triple is None:
            rendered.append("tuple[str, list[object]]")
            continue
        metadata = triple[2]
        if metadata_origin is not None or not isinstance(metadata, TypeName):
            return None
        proven_metadata = _bound_alias_metadata(
            metadata, module, origin, contract, exports, imports, classes, type_shapes
        )
        if proven_metadata is None:
            return None
        metadata_origin, metadata_imports = proven_metadata
        resolved = metadata_origin
        rendered.append(f"tuple[str, list[object], {resolved[0]}.{resolved[1]}]")
    if metadata_origin is None or rendered.count("tuple[str, list[object]]") != 1:
        return None
    rows = _bound_alias_application(outer[1], "list", 1, module, imports, classes)
    mapping = (
        _bound_alias_application(rows[0], "dict", 2, module, imports, classes)
        if rows is not None
        else None
    )
    if mapping is None or any(
        _proven_type_head(leaf, module, imports, classes, frozenset({("builtins", builtin)}))
        is not True
        for leaf, builtin in zip(mapping, ("str", "object"), strict=True)
    ):
        return None
    return _BoundAliasBody(
        BoundaryAliasBody(
            f"{module}:{name}",
            f"tuple[{' | '.join(rendered)}, list[dict[str, object]]]",
        ),
        metadata_origin,
        metadata_imports,
    )


def _bound_root_mapping_union(
    typed: _TypedMappingUnion | None,
    resolved: tuple[str, str],
    symbol: RecordData,
    aliases_seen: frozenset[tuple[str, str]],
    visited: frozenset[tuple[str, str]],
) -> _TypedMappingUnion | None:
    if (
        typed is not None
        and typed.alias_body is None
        and not aliases_seen
        and not visited
        and symbol.get("source_binding_unique") is True
        and symbol.get("source_member_binding_static") is True
    ):
        typed = replace(
            typed,
            alias_body=BoundaryAliasBody(f"{resolved[0]}:{resolved[1]}", typed.shape),
            source_origins=(resolved, *typed.source_origins),
        )
    else:
        typed = None
    return typed


def _alias_binding_static(binding: RecordData | _AmbiguousBinding) -> bool:
    return (
        isinstance(binding, dict)
        and binding.get("source_binding_unique") is True
        and binding.get("source_member_binding_static") is True
    )


def _alias_mapping_occurrences(
    occurrences: tuple[_MappingOccurrence, ...],
) -> tuple[_MappingOccurrence, ...]:
    return tuple(
        _MappingOccurrence(
            occurrence.annotation,
            occurrence.depth,
            occurrence.path,
            alias_free=False,
            opaque_value_depth=occurrence.opaque_value_depth,
            syntax_route=occurrence.syntax_route,
        )
        for occurrence in occurrences
    )


def _type_alias_verdict(
    symbol: RecordData | _AmbiguousBinding | None,
    resolved: tuple[str, str],
    annotation: str,
    module: str,
    contract: ArchitectureContract,
    exports_by_module: dict[str, frozenset[str]],
    imports_by_binding: BindingIndex,
    classes_by_location: BindingIndex,
    *,
    type_shapes: TypeShapeIndex,
    enter_collections: bool,
    enter_fields: bool,
    visited: frozenset[tuple[str, str]],
    aliases_seen: frozenset[tuple[str, str]],
) -> _Position | None:
    if not isinstance(symbol, dict) or parse_source_symbol_kind(symbol.get("record_kind")) is not SourceSymbolKind.TYPE_ALIAS:
        return None
    reached: tuple[tuple[str, str], ...] = (resolved,)
    alias = symbol.get("alias")
    if not _alias_binding_static(symbol):
        return _Position(undecidable=_Cause.OTHER, resolved=reached, named_origins=reached)
    if resolved in aliases_seen or not isinstance(alias, str) or alias == annotation:
        return _Position(undecidable=_Cause.OTHER, resolved=reached, named_origins=reached)
    if classes_by_location.module_bindings is not None:
        classes_by_location = classes_by_location.module_bindings
    expanded = _boundary_type_verdict(
        alias,
        module,
        contract,
        exports_by_module,
        imports_by_binding,
        classes_by_location,
        enter_collections=enter_collections,
        enter_fields=enter_fields,
        visited=visited,
        _aliases_seen=aliases_seen | {resolved},
        type_shapes=type_shapes,
    )
    proof = (
        _bound_alias_body(
            alias,
            resolved,
            contract,
            exports_by_module,
            imports_by_binding,
            classes_by_location,
            type_shapes,
        )
        if not aliases_seen and not visited
        else None
    )
    typed = expanded.typed_mapping_union
    typed = _bound_root_mapping_union(typed, resolved, symbol, aliases_seen, visited)
    return _Position(
        bound_alias=proof,
        typed_mapping_union=typed,
        typed_union_checked=expanded.typed_union_checked,
        violation=expanded.violation,
        undecidable=expanded.undecidable,
        unknown_context=expanded.unknown_context,
        referenced_members_static=expanded.referenced_members_static,
        contains_callable=expanded.contains_callable,
        resolved=tuple(sorted({*reached, *expanded.resolved})),
        named_origins=tuple(sorted({*reached, *expanded.named_origins})),
        path=expanded.path,
        nested_annotation=expanded.nested_annotation,
        violations=expanded.violations,
        field_positions=expanded.field_positions,
        field_declarations=expanded.field_declarations,
        mapping_occurrences=_alias_mapping_occurrences(expanded.mapping_occurrences),
    )


def _unresolved_named_verdict(
    annotation: str,
    module: str,
    imports_by_binding: BindingIndex,
    classes_by_location: BindingIndex,
    require_static_constant: bool,
) -> _Position:
    if (
        annotation in _BUILTIN_NAMES
        and not _has_star_import(module, imports_by_binding)
        and (module, annotation) not in imports_by_binding
        and (module, annotation) not in classes_by_location
        and not require_static_constant
    ):
        return _Position()
    if require_static_constant:
        return _Position(undecidable=_Cause.OTHER)
    return _Position(undecidable=_Cause.UNRESOLVED)


def _is_static_literal_constant(symbol: RecordData | _AmbiguousBinding | None) -> bool:
    # A constant recorded without its value (AD-102) proves nothing; `.get` alone would read
    # the missing value as a `None` literal.
    return (
        isinstance(symbol, dict)
        and parse_source_symbol_kind(symbol.get("record_kind")) is SourceSymbolKind.STATIC_CONSTANT
        and "constant" in symbol
        and isinstance(symbol["constant"], (str, int, bool, type(None)))
    )


def _imported_alias_verdict(
    alias: _Position, module: str, annotation: str, imports_by_binding: BindingIndex
) -> _Position:
    imported = imports_by_binding.get((module, annotation))
    if imported is not None and not _alias_binding_static(imported):
        return _Position(
            undecidable=_Cause.OTHER,
            resolved=alias.named_origins,
            named_origins=alias.named_origins,
        )
    if isinstance(imported, dict) and len(imported["reexport_chain"] or ()) > 1:
        return replace(alias, bound_alias=None, typed_mapping_union=None)
    if imported is not None and alias.typed_mapping_union is not None:
        typed = alias.typed_mapping_union
        alias = replace(
            alias,
            typed_mapping_union=replace(
                typed, import_bindings=(*typed.import_bindings, (module, annotation))
            ),
        )
    if imported is not None and alias.bound_alias is not None:
        proof = alias.bound_alias
        return replace(
            alias,
            bound_alias=replace(
                proof, import_bindings=(*proof.import_bindings, (module, annotation))
            ),
        )
    return alias


def _named_type_verdict(
    annotation: str,
    module: str,
    contract: ArchitectureContract,
    exports_by_module: dict[str, frozenset[str]],
    imports_by_binding: BindingIndex,
    classes_by_location: BindingIndex,
    *,
    type_shapes: TypeShapeIndex,
    enter_collections: bool,
    enter_fields: bool,
    visited: frozenset[tuple[str, str]],
    aliases_seen: frozenset[tuple[str, str]],
    require_static_constant: bool,
) -> _Position:
    resolved = resolve_named_type(annotation, module, imports_by_binding, classes_by_location)
    if isinstance(resolved, _AmbiguousBinding):
        # Distinct records bind this name in `module`: Python picks whichever is textually last,
        # and nothing the scanner recorded says which that is, so the position is undecidable,
        # not a guess at either candidate (AD-74).
        return _Position(undecidable=_Cause.AMBIGUOUS_BINDING)
    if resolved is None:
        return _unresolved_named_verdict(
            annotation,
            module,
            imports_by_binding,
            classes_by_location,
            require_static_constant,
        )
    origin_module, origin_name = resolved
    reached: tuple[tuple[str, str], ...] = (resolved,)
    origin_symbol = classes_by_location.get(resolved)
    if require_static_constant:
        return (
            _Position()
            if _is_static_literal_constant(origin_symbol)
            else _Position(undecidable=_Cause.OTHER)
        )
    alias = _type_alias_verdict(
        origin_symbol,
        resolved,
        annotation,
        origin_module,
        contract,
        exports_by_module,
        imports_by_binding,
        classes_by_location,
        enter_collections=enter_collections,
        enter_fields=enter_fields,
        visited=visited,
        aliases_seen=aliases_seen,
        type_shapes=type_shapes,
    )
    if alias is not None:
        return _imported_alias_verdict(alias, module, annotation, imports_by_binding)
    class_kind: SymbolClassKind | None = None
    if isinstance(origin_symbol, dict):
        if parse_source_symbol_kind(origin_symbol.get("record_kind")) in {SourceSymbolKind.STATIC_CONSTANT, SourceSymbolKind.DYNAMIC_BINDING}:
            return _Position(undecidable=_Cause.OTHER, resolved=reached, named_origins=reached)
        # `resolve_named_type` ruled out an ambiguous location; the surviving class record carries
        # `class_kind` (AD-30).
        class_kind = parse_symbol_class_kind(origin_symbol["class_kind"])
    if class_kind is SymbolClassKind.ENUM:
        return _Position(resolved=reached, named_origins=reached)
    return _owned_type_verdict(
        origin_symbol,
        origin_module,
        origin_name,
        class_kind,
        reached,
        contract,
        exports_by_module,
        imports_by_binding,
        classes_by_location,
        visited,
        aliases_seen,
        type_shapes=type_shapes,
    )


def _owned_type_verdict(
    origin_symbol: RecordData | _AmbiguousBinding | None,
    origin_module: str,
    origin_name: str,
    class_kind: SymbolClassKind | None,
    reached: tuple[tuple[str, str], ...],
    contract: ArchitectureContract,
    exports_by_module: dict[str, frozenset[str]],
    imports_by_binding: BindingIndex,
    classes_by_location: BindingIndex,
    visited: frozenset[tuple[str, str]],
    aliases_seen: frozenset[tuple[str, str]],
    *,
    type_shapes: TypeShapeIndex,
) -> _Position:
    resolved = (origin_module, origin_name)
    origin_component = None
    for level in imports_by_binding.ownership_contracts or (contract,):
        claims = [
            component
            for component in level.components
            if component_owns_module(component, origin_module)
        ]
        if len(claims) > 1:
            return _Position(undecidable=_Cause.OTHER, resolved=reached, named_origins=(resolved,))
        if claims:
            origin_component = claims[0]
            break
    if origin_component is None:
        return _Position(undecidable=_Cause.EXTERNAL, resolved=reached, named_origins=(resolved,))
    owner_facade_proof = imports_by_binding.owner_facade_type_states.get(
        (origin_component.id, origin_module, origin_name)
    )
    directly_public = facade_covers(origin_module, origin_name, origin_component, exports_by_module)
    if not directly_public and (
        owner_facade_proof is False
        or (owner_facade_proof is True and not isinstance(origin_symbol, dict))
    ):
        return _Position(undecidable=_Cause.UNRESOLVED, resolved=reached, named_origins=(resolved,))
    if directly_public or owner_facade_proof is True:
        if resolved in visited:
            return _Position(resolved=reached, named_origins=(resolved,))
        fields = _declared_field_verdict(
            origin_symbol,
            origin_module,
            contract,
            exports_by_module,
            imports_by_binding,
            classes_by_location,
            visited=visited | {resolved},
            _aliases_seen=aliases_seen,
            type_shapes=type_shapes,
        )
        reached = tuple(sorted({*reached, *fields.resolved}))
        return _Position(
            violation=fields.violation,
            undecidable=fields.undecidable,
            unknown_context=fields.unknown_context,
            referenced_members_static=fields.referenced_members_static,
            contains_callable=fields.contains_callable,
            resolved=reached,
            named_origins=(resolved,),
            path=fields.path,
            nested_annotation=fields.nested_annotation,
            violations=fields.violations,
            mapping_occurrences=fields.mapping_occurrences,
            field_positions=fields.field_positions,
            field_declarations=fields.field_declarations,
            mapping_alternatives=fields.mapping_alternatives,
        )
    if class_kind in _EXEMPT_CLASS_KINDS:
        return _Position(resolved=reached, named_origins=(resolved,))
    return _Position(
        violation=f"which {origin_component.label} does not declare",
        resolved=reached,
        named_origins=(resolved,),
    )


def _callable_import_static(data: RecordData | _AmbiguousBinding | None) -> bool:
    return (
        isinstance(data, dict)
        and data.get("source_binding_unique") is True
        and data.get("source_member_binding_static") is True
        and data.get("module_level_import") is True
        and (data.get("ordinary_module") is True or data.get("ordinary_module") is False)
        and data.get("under_type_checking") is False
        and not data.get("reexport_candidate")
        and not data.get("reexport_candidates")
    )


def _callable_head_proven(
    head: TypeShape, module: str, imports: BindingIndex, classes: BindingIndex
) -> bool:
    if isinstance(head, TypeName):
        binding, member = head.name, None
    elif isinstance(head, TypeMember) and isinstance(head.owner, TypeName):
        binding, member = head.owner.name, head.member
    else:
        return False
    key = (module, binding)
    imported = imports.get(key)
    if (
        _has_star_import(module, imports)
        or _binding_is_ambiguous(key, imports, classes)
        or not _callable_import_static(imported)
        or not isinstance(imported, dict)
    ):
        return False
    origins = {("typing", "Callable"), ("collections.abc", "Callable")}
    if member is not None:
        target, symbol = imported["target_module"], imported["symbol"]
        if symbol is not None or (target == "collections.abc" and binding == "collections"):
            return False
        origin_module, origin_name = target, member
    else:
        origin_value = imported.get("origin_definition")
        if not isinstance(origin_value, str) or imported.get("origin_binding_unique") is not True:
            return False
        origin: str = origin_value
        origin_module, _, origin_name = origin.rpartition(".")
        chain = imported.get("reexport_chain", ())
        if (
            not chain
            or chain[-1] != origin
            or chain[0] != f"{imported['target_module']}.{imported['symbol']}"
        ):
            return False
        for index, alias in enumerate(chain[:-1]):
            alias_text: str = alias
            hop_module, _, hop_name = alias_text.rpartition(".")
            hop_key = (hop_module, hop_name)
            hop = imports.get(hop_key)
            if (
                _binding_is_ambiguous(hop_key, imports, classes)
                or not _callable_import_static(hop)
                or not isinstance(hop, dict)
                or hop.get("reexport") is not True
                or hop.get("origin_binding_unique") is not True
                or hop.get("origin_definition") != origin
                or list(hop.get("reexport_chain", ())) != chain[index + 1 :]
            ):
                return False
    provider_module: str = origin_module
    return (origin_module, origin_name) in origins and not any(
        origin_module == local or provider_module.startswith(f"{local}.")
        for local in imports.source_modules
    )


def _named_reference_position(
    annotation: str,
    module: str,
    verdict: _Position,
    imports: BindingIndex,
    classes: BindingIndex,
    shapes: TypeShapeIndex,
) -> _Position:
    root = shapes.get(annotation)
    binding = (
        root.name
        if isinstance(root, TypeName)
        else root.owner.name
        if isinstance(root, TypeMember) and isinstance(root.owner, TypeName)
        else None
    )
    source = imports.get((module, binding)) if binding is not None else None
    static = verdict.referenced_members_static
    for origin in verdict.named_origins:
        symbol = classes.get(origin)
        static &= (
            isinstance(symbol, dict)
            and symbol.get("source_binding_unique") is True
            and symbol.get("source_member_binding_static") is True
        )
    if source is not None:
        static &= (
            _callable_import_static(source)
            and isinstance(source, dict)
            and source.get("origin_binding_unique") is True
            and source.get("origin_member_binding_static") is not False
        )
        if isinstance(source, dict):
            for hop in source.get("reexport_chain", ()):
                hop_text: str = hop
                owner, _, name = hop_text.rpartition(".")
                peer = imports.get((owner, name))
                if peer is None and (owner, name) in verdict.named_origins:
                    continue
                if owner in imports.source_modules:
                    static &= (
                        _callable_import_static(peer)
                        and isinstance(peer, dict)
                        and peer.get("origin_binding_unique") is True
                    )
    late_unknown = verdict.contains_callable and not static and verdict.undecidable is None
    return replace(
        verdict,
        referenced_members_static=static,
        undecidable=_Cause.OTHER if late_unknown else verdict.undecidable,
        unknown_context=f"Callable reference {annotation}"
        if late_unknown
        else verdict.unknown_context,
    )


def _callable_leaf_position(route: str, annotation: str, verdict: _Position) -> _Position:
    findings = verdict.violations or (
        ((verdict.violation, verdict.path, verdict.nested_annotation or annotation, 0),)
        if verdict.violation is not None
        else ()
    )
    prefixed = tuple(
        (f"Callable {route}: {reason}", path, nested, depth)
        for reason, path, nested, depth in findings
    )
    return replace(
        verdict,
        violation=prefixed[0][0] if prefixed else None,
        violations=prefixed,
        unknown_context=(
            f"Callable {route}: {verdict.unknown_context or annotation}"
            if verdict.undecidable is not None
            else None
        ),
        mapping_occurrences=(),
        field_positions=(),
        field_declarations=(),
        mapping_alternatives=(),
        exact_nested_map_chain=False,
        native_iterable_annotation=None,
        bound_alias=None,
        typed_mapping_union=None,
        typed_union_checked=False,
    )


def _callable_signature_verdict(
    shape: TypeApplication,
    module: str,
    contract: ArchitectureContract,
    exports: dict[str, frozenset[str]],
    imports: BindingIndex,
    classes: BindingIndex,
    visited: frozenset[tuple[str, str]],
    enter_fields: bool,
    aliases_seen: frozenset[tuple[str, str]],
    type_shapes: TypeShapeIndex,
) -> _Position:
    if len(shape.arguments) != 2 or not isinstance(shape.arguments[0], TypeList):
        return _Position(undecidable=_Cause.GENERIC)
    parameters = [
        (f"argument[{index}]", element) for index, element in enumerate(shape.arguments[0].elements)
    ]
    parameters.append(("result", shape.arguments[1]))
    decided = []
    for route, parameter in parameters:
        verdict = (
            _Position()
            if isinstance(parameter, TypeLiteral) and parameter.kind is LiteralKind.NONE
            else _boundary_type_verdict(
                parameter.text,
                module,
                contract,
                exports,
                imports,
                classes,
                visited=visited,
                enter_fields=enter_fields,
                _aliases_seen=aliases_seen,
                type_shapes=type_shapes,
            )
        )
        if not verdict.referenced_members_static:
            verdict = replace(verdict, undecidable=verdict.undecidable or _Cause.OTHER)
        decided.append((parameter.text, _callable_leaf_position(route, parameter.text, verdict)))
    return replace(_combine_position_verdicts(decided), contains_callable=True)


def _union_annotation_verdict(
    annotation: str,
    parameters: list[str],
    module: str,
    contract: ArchitectureContract,
    exports: dict[str, frozenset[str]],
    imports: BindingIndex,
    classes: BindingIndex,
    visited: frozenset[tuple[str, str]],
    enter_fields: bool,
    aliases_seen: frozenset[tuple[str, str]],
    type_shapes: TypeShapeIndex,
) -> _Position:
    verdict = _combined_annotation_verdict(
        parameters,
        module,
        contract,
        exports,
        imports,
        classes,
        visited=visited,
        enter_fields=enter_fields,
        _aliases_seen=aliases_seen,
        type_shapes=type_shapes,
    )
    verdict = _literal_union_verdict(annotation, verdict, module, imports, classes, type_shapes)
    return _mapping_union_verdict(
        annotation,
        verdict,
        module,
        imports,
        classes,
        type_shapes,
        contract,
        exports,
        visited,
        aliases_seen,
    )


def _annotation_shape_verdict(
    annotation: str,
    module: str,
    contract: ArchitectureContract,
    exports_by_module: dict[str, frozenset[str]],
    imports_by_binding: BindingIndex,
    classes_by_location: BindingIndex,
    *,
    type_shapes: TypeShapeIndex,
    enter_collections: bool,
    visited: frozenset[tuple[str, str]],
    enter_fields: bool,
    _aliases_seen: frozenset[tuple[str, str]],
) -> _Position:
    shape = type_shapes.get(annotation)
    if isinstance(shape, TypeApplication) and _callable_head_proven(
        shape.head, module, imports_by_binding, classes_by_location
    ):
        return _callable_signature_verdict(
            shape,
            module,
            contract,
            exports_by_module,
            imports_by_binding,
            classes_by_location,
            visited,
            enter_fields,
            _aliases_seen,
            type_shapes,
        )
    mapping = _mapping_parameters(
        annotation, module, imports_by_binding, classes_by_location, type_shapes=type_shapes
    )
    if isinstance(mapping, _Position):
        return mapping
    if mapping is not None:
        return _mapping_container_verdict(
            annotation,
            mapping,
            module,
            contract,
            exports_by_module,
            imports_by_binding,
            classes_by_location,
            visited,
            enter_fields,
            _aliases_seen,
            type_shapes=type_shapes,
        )
    union = _union_parameters(annotation, module, imports_by_binding, type_shapes=type_shapes)
    if union is not None:
        return _union_annotation_verdict(
            annotation,
            union,
            module,
            contract,
            exports_by_module,
            imports_by_binding,
            classes_by_location,
            visited,
            enter_fields,
            _aliases_seen,
            type_shapes,
        )
    if enter_collections:
        entered = _collection_verdict(
            annotation,
            module,
            contract,
            exports_by_module,
            imports_by_binding,
            classes_by_location,
            visited=visited,
            enter_fields=enter_fields,
            _aliases_seen=_aliases_seen,
            type_shapes=type_shapes,
        )
        if entered is not None:
            return entered
    return _Position(undecidable=_unresolvable_shape(annotation))


def _without_literal_mapping_arms(verdict: _Position) -> _Position:
    return replace(
        verdict,
        mapping_occurrences=tuple(
            _MappingOccurrence(
                occurrence.annotation,
                occurrence.depth,
                occurrence.path,
                occurrence.alias_free,
                occurrence.opaque_value_depth,
                occurrence.syntax_route,
            )
            for occurrence in verdict.mapping_occurrences
        ),
    )


def _literal_type_head_proven(
    head: TypeShape,
    module: str,
    imports: BindingIndex,
    classes: BindingIndex,
    origins: frozenset[tuple[str, str]],
) -> bool:
    if _proven_type_head(head, module, imports, classes, origins) is not True:
        return False
    name = (
        head.name
        if isinstance(head, TypeName)
        else head.owner.name
        if (isinstance(head, TypeMember) and isinstance(head.owner, TypeName))
        else None
    )
    imported = imports.get((module, name)) if name is not None else None
    return (
        imported is None
        or isinstance(imported, dict)
        and imported.get("source_binding_unique") is True
    ) and _base_route_member_static(head, module, imports, classes)


def _literal_union_verdict(
    annotation: str,
    verdict: _Position,
    module: str,
    imports: BindingIndex,
    classes: BindingIndex,
    type_shapes: TypeShapeIndex,
) -> _Position:
    shape = type_shapes.get(annotation)
    if isinstance(shape, TypeApplication) and not _literal_type_head_proven(
        shape.head,
        module,
        imports,
        classes,
        frozenset({("typing", "Union"), ("typing", "Optional")}),
    ):
        return _without_literal_mapping_arms(verdict)
    return verdict


def _literal_root_mapping_arm(
    annotation: str,
    module: str,
    imports: BindingIndex,
    classes: BindingIndex,
    type_shapes: TypeShapeIndex,
) -> bool:
    shape = type_shapes.get(annotation)
    return (
        isinstance(shape, TypeApplication)
        and shape.tuple_arguments
        and len(shape.arguments) == 2
        and _literal_type_head_proven(
            shape.head, module, imports, classes, frozenset({("builtins", "dict")})
        )
        and _literal_type_head_proven(
            shape.arguments[0], module, imports, classes, frozenset({("builtins", "str")})
        )
    )


def _literal_list_mapping_arm(
    annotation: str,
    module: str,
    imports: BindingIndex,
    classes: BindingIndex,
    type_shapes: TypeShapeIndex,
) -> bool:
    shape = type_shapes.get(annotation)
    if (
        not isinstance(shape, TypeApplication)
        or shape.tuple_arguments
        or len(shape.arguments) != 1
        or not _literal_type_head_proven(
            shape.head, module, imports, classes, frozenset({("builtins", "list")})
        )
    ):
        return False
    element = shape.arguments[0]
    return (
        isinstance(element, TypeApplication)
        and _literal_root_mapping_arm(element.text, module, imports, classes, type_shapes)
        and _literal_type_head_proven(
            element.arguments[1],
            module,
            imports,
            classes,
            frozenset({("builtins", "str"), ("builtins", "object")}),
        )
    )


def _native_iterable_shape(
    annotation: str,
    module: str,
    imports: BindingIndex,
    classes: BindingIndex,
    type_shapes: TypeShapeIndex,
) -> bool:
    shape = type_shapes.get(annotation)
    if isinstance(shape, TypeUnion):
        if isinstance(shape.right, TypeLiteral) and shape.right.kind is LiteralKind.NONE:
            shape = shape.left
        elif isinstance(shape.left, TypeLiteral) and shape.left.kind is LiteralKind.NONE:
            shape = shape.right
        else:
            return False
    if (
        not isinstance(shape, TypeApplication)
        or shape.tuple_arguments
        or len(shape.arguments) != 1
        or not (
            isinstance(shape.head, TypeName)
            and shape.head.name == "Iterable"
            or isinstance(shape.head, TypeMember)
            and shape.head.member == "Iterable"
        )
        or _proven_type_head(
            shape.head,
            module,
            imports,
            classes,
            frozenset({("typing", "Iterable"), ("collections.abc", "Iterable")}),
        )
        is not True
    ):
        return False
    element = shape.arguments[0]
    return (
        isinstance(element, TypeName)
        and element.name == "object"
        and _proven_type_head(
            element, module, imports, classes, frozenset({("builtins", "object")})
        )
        is True
    )


def _opaque_mapping_value_depth(
    annotation: str,
    module: str,
    imports: BindingIndex,
    classes: BindingIndex,
    type_shapes: TypeShapeIndex,
) -> int | None:
    shape = type_shapes.get(annotation)
    depth = 1
    if isinstance(shape, TypeApplication):
        if (
            not isinstance(shape.head, TypeName)
            or shape.head.name != "list"
            or shape.tuple_arguments
            or len(shape.arguments) != 1
            or _proven_type_head(
                shape.head, module, imports, classes, frozenset({("builtins", "list")})
            )
            is not True
        ):
            return None
        shape = shape.arguments[0]
        depth = 2
    return (
        depth
        if isinstance(shape, TypeName)
        and shape.name == "object"
        and _is_broad_boundary_type("object", module, imports, classes)
        else None
    )


def _mapping_union_arms(
    annotation: str,
    module: str,
    imports: BindingIndex,
    classes: BindingIndex,
    type_shapes: TypeShapeIndex,
) -> list[str] | None:
    shape = type_shapes.get(annotation)
    if isinstance(shape, TypeLiteral) and shape.kind is LiteralKind.NONE:
        return []
    members = _union_parameters(annotation, module, imports, type_shapes=type_shapes)
    if members is not None:
        if (
            isinstance(shape, TypeApplication)
            and _proven_type_head(
                shape.head,
                module,
                imports,
                classes,
                frozenset({("typing", "Union"), ("typing", "Optional")}),
            )
            is not True
        ):
            return None
        arms: list[str] = []
        for member in members:
            nested = _mapping_union_arms(member, module, imports, classes, type_shapes)
            if nested is None:
                return None
            arms.extend(nested)
        return arms
    if not isinstance(shape, TypeApplication) or not isinstance(
        _mapping_parameters(annotation, module, imports, classes, type_shapes=type_shapes), list
    ):
        return None
    key, value = shape.arguments
    if (
        _proven_type_head(key, module, imports, classes, frozenset({("builtins", "str")}))
        is not True
    ):
        return None
    if (
        _proven_type_head(value, module, imports, classes, frozenset({("builtins", "str")}))
        is not True
        and _opaque_mapping_value_depth(value.text, module, imports, classes, type_shapes) is None
    ):
        return None
    return [annotation]


def _nullable_string_key(
    shape: TypeShape, module: str, imports: BindingIndex, classes: BindingIndex
) -> bool:
    return (
        isinstance(shape, TypeUnion)
        and _proven_type_head(
            shape.left, module, imports, classes, frozenset({("builtins", "str")})
        )
        is True
        and isinstance(shape.right, TypeLiteral)
        and shape.right.kind is LiteralKind.NONE
    )


def _typed_union_map_shapes(
    annotation: str,
    module: str,
    imports: BindingIndex,
    classes: BindingIndex,
    type_shapes: TypeShapeIndex,
) -> list[TypeApplication] | None:
    shape = type_shapes.get(annotation)
    if shape is None:
        return None
    pending = [shape]
    maps: list[TypeApplication] = []
    while pending:
        arm = pending.pop(0)
        if isinstance(arm, TypeUnion):
            pending[0:0] = [arm.left, arm.right]
            continue
        members = _union_parameters(arm.text, module, imports, type_shapes=type_shapes)
        if members is not None:
            if (
                not isinstance(arm, TypeApplication)
                or _proven_type_head(
                    arm.head,
                    module,
                    imports,
                    classes,
                    frozenset({("typing", "Union"), ("typing", "Optional")}),
                )
                is not True
            ):
                return None
            shapes = [type_shapes.get(member) for member in members]
            if any(member is None for member in shapes):
                return None
            pending[0:0] = [member for member in shapes if member is not None]
            continue
        if not isinstance(arm, TypeApplication) or not isinstance(
            _mapping_parameters(arm.text, module, imports, classes, type_shapes=type_shapes),
            list,
        ):
            return None
        maps.append(arm)
    return maps


def _nullable_key_alias_proof(
    key: TypeName,
    module: str,
    imports: BindingIndex,
    classes: BindingIndex,
    type_shapes: TypeShapeIndex,
    contract: ArchitectureContract,
    exports_by_module: dict[str, frozenset[str]],
    visited: frozenset[tuple[str, str]],
    aliases_seen: frozenset[tuple[str, str]],
) -> tuple[BoundaryAliasBody, tuple[str, str], tuple[tuple[str, str], ...]] | None:
    verdict = _named_type_verdict(
        key.name,
        module,
        contract,
        exports_by_module,
        imports,
        classes,
        type_shapes=type_shapes,
        enter_collections=False,
        enter_fields=False,
        visited=visited,
        aliases_seen=aliases_seen,
        require_static_constant=False,
    )
    if (
        verdict.undecidable is not None
        or verdict.violation is not None
        or verdict.violations
        or len(verdict.named_origins) != 1
    ):
        return None
    origin = verdict.named_origins[0]
    symbol = classes.get(origin)
    imported = imports.get((module, key.name))
    if (
        not isinstance(symbol, dict)
        or parse_source_symbol_kind(symbol.get("record_kind")) is not SourceSymbolKind.TYPE_ALIAS
        or symbol.get("source_binding_unique") is not True
        or symbol.get("source_member_binding_static") is not True
        or (
            imported is not None
            and (
                not isinstance(imported, dict)
                or imported.get("source_binding_unique") is not True
                or imported.get("source_member_binding_static") is not True
                or len(imported["reexport_chain"] or ()) > 1
            )
        )
    ):
        return None
    alias = symbol.get("alias")
    key_shape = type_shapes.get(alias) if isinstance(alias, str) else None
    if key_shape is None or not _nullable_string_key(key_shape, origin[0], imports, classes):
        return None
    return (
        BoundaryAliasBody(f"{origin[0]}:{origin[1]}", "str | None"),
        origin,
        ((module, key.name),) if imported is not None else (),
    )


def _typed_mapping_key_text(
    key: TypeShape, module: str, imports: BindingIndex, classes: BindingIndex
) -> str | None:
    if _proven_type_head(key, module, imports, classes, frozenset({("builtins", "str")})) is True:
        return "str"
    elif _nullable_string_key(key, module, imports, classes):
        return "str | None"
    elif (pair := _bound_alias_application(key, "tuple", 2, module, imports, classes)) is not None:
        if any(
            _proven_type_head(leaf, module, imports, classes, frozenset({("builtins", "int")}))
            is not True
            for leaf in pair
        ):
            return None
        return "tuple[int, int]"
    return None


def _typed_union_verdict_matches(arms: list[str], verdict: _Position) -> bool:
    mappings = verdict.mapping_occurrences
    return (
        verdict.undecidable is None
        and len(mappings) == len(arms)
        and all(
            occurrence.legacy() == _MappingOccurrence(arm, 0)
            for arm, occurrence in zip(arms, mappings, strict=True)
        )
        and verdict.violations
        == tuple(sorted((_BROAD_BOUNDARY_REASON, (), arm, 0) for arm in arms))
    )


def _typed_mapping_union_proof(
    annotation: str,
    verdict: _Position,
    module: str,
    imports: BindingIndex,
    classes: BindingIndex,
    type_shapes: TypeShapeIndex,
    contract: ArchitectureContract,
    exports_by_module: dict[str, frozenset[str]],
    visited: frozenset[tuple[str, str]],
    aliases_seen: frozenset[tuple[str, str]],
) -> _TypedMappingUnion | None:
    map_shapes = _typed_union_map_shapes(annotation, module, imports, classes, type_shapes)
    if map_shapes is None:
        return None
    arms: list[str] = []
    rendered: list[str] = []
    identities: list[tuple[tuple[str, str], str, str]] = []
    key_binding: BoundaryAliasBody | None = None
    source_origins: tuple[tuple[str, str], ...] = ()
    import_bindings: tuple[tuple[str, str], ...] = ()
    for arm in map_shapes:
        key, value = arm.arguments
        key_is_alias = False
        value_name = next(
            (
                name
                for name in ("str", "int", "float")
                if _proven_type_head(
                    value, module, imports, classes, frozenset({("builtins", name)})
                )
                is True
            ),
            None,
        )
        if value_name is None:
            return None
        key_text = _typed_mapping_key_text(key, module, imports, classes)
        if key_text is None and isinstance(key, TypeName) and key_binding is None:
            proof = _nullable_key_alias_proof(
                key,
                module,
                imports,
                classes,
                type_shapes,
                contract,
                exports_by_module,
                visited,
                aliases_seen,
            )
            if proof is None:
                return None
            key_binding, origin, import_bindings = proof
            key_is_alias = True
            source_origins = (origin,)
            key_text = f"{origin[0]}.{origin[1]}"
        if key_text is None:
            return None
        head_origin = next(
            origin
            for origin in _PROVEN_MAPPINGS
            if _proven_type_head(arm.head, module, imports, classes, frozenset({origin})) is True
        )
        identities.append((head_origin, "str | None" if key_is_alias else key_text, value_name))
        arms.append(arm.text)
        rendered.append(f"{arm.head.text}[{key_text}, {value.text}]")
    if (
        len(arms) < 2
        or len(set(identities)) != len(arms)
        or not _typed_union_verdict_matches(arms, verdict)
    ):
        return None
    return _TypedMappingUnion(
        " | ".join(rendered),
        key_alias_body=key_binding,
        source_origins=source_origins,
        import_bindings=import_bindings,
    )


def _mapping_union_verdict(
    annotation: str,
    verdict: _Position,
    module: str,
    imports: BindingIndex,
    classes: BindingIndex,
    type_shapes: TypeShapeIndex,
    contract: ArchitectureContract | None,
    exports_by_module: dict[str, frozenset[str]],
    visited: frozenset[tuple[str, str]],
    aliases_seen: frozenset[tuple[str, str]],
) -> _Position:
    arms = _mapping_union_arms(annotation, module, imports, classes, type_shapes)
    if contract is not None and contract.schema_version in _TYPED_MAPPING_UNION_VERSIONS:
        ordinary_compatible = (
            annotation in _OPAQUE_NATIVE_REASONS
            or _native_iterable_shape(annotation, module, imports, classes, type_shapes)
            or arms is not None
            and len(arms) == 1
            or _ordinary_nullable_mapping(
                annotation, verdict, module, imports, classes, type_shapes
            )
        )
        verdict = replace(verdict, typed_union_checked=not ordinary_compatible)
        proof = _typed_mapping_union_proof(
            annotation,
            verdict,
            module,
            imports,
            classes,
            type_shapes,
            contract,
            exports_by_module,
            visited,
            aliases_seen,
        )
        if proof is not None:
            return replace(verdict, typed_mapping_union=proof)
    mappings = verdict.mapping_occurrences
    if (
        arms is None
        or len(arms) < 2
        or verdict.undecidable is not None
        or len(mappings) != len(arms)
        or any(
            occurrence.annotation != arm
            or occurrence.depth != 0
            or occurrence.path
            or not occurrence.alias_free
            for arm, occurrence in zip(arms, mappings, strict=True)
        )
    ):
        return verdict
    native_depths = [
        occurrence.opaque_value_depth
        for occurrence in mappings
        if occurrence.opaque_value_depth is not None
    ]
    if len(native_depths) != 1:
        return verdict
    expected = [(_BROAD_BOUNDARY_REASON, (), arm, 0) for arm in arms]
    expected.append((f"holding object {_BROAD_BOUNDARY_REASON}", (), "object", native_depths[0]))
    if tuple(sorted(expected)) != verdict.violations:
        return verdict
    return replace(
        verdict,
        mapping_alternatives=(
            *verdict.mapping_alternatives,
            _MappingAlternatives(annotation, mappings),
        ),
        exact_nested_map_chain=False,
        native_iterable_annotation=None,
        bound_alias=None,
        typed_mapping_union=None,
    )


def _ordinary_nullable_mapping(
    annotation: str,
    verdict: _Position,
    module: str,
    imports: BindingIndex,
    classes: BindingIndex,
    type_shapes: TypeShapeIndex,
) -> bool:
    members = _union_parameters(annotation, module, imports, type_shapes=type_shapes)
    if members is None or len(members) != 2 or "None" not in members or members[0] == members[1]:
        return False
    shape = type_shapes.get(annotation)
    if (
        isinstance(shape, TypeApplication)
        and _proven_type_head(
            shape.head,
            module,
            imports,
            classes,
            frozenset({("typing", "Union"), ("typing", "Optional")}),
        )
        is not True
    ):
        return False
    mapping = members[1] if members[0] == "None" else members[0]
    return isinstance(
        _mapping_parameters(mapping, module, imports, classes, type_shapes=type_shapes), list
    ) and _typed_union_verdict_matches([mapping], verdict)


def _relocate_mapping_alternatives(
    groups: tuple[_MappingAlternatives, ...], depth: int, path: tuple[str, ...]
) -> tuple[_MappingAlternatives, ...]:
    return tuple(
        _MappingAlternatives(
            group.annotation,
            tuple(
                _MappingOccurrence(
                    occurrence.annotation,
                    occurrence.depth + depth,
                    (*path, *occurrence.path),
                    occurrence.alias_free,
                    occurrence.opaque_value_depth,
                    occurrence.syntax_route,
                    occurrence.literal_arm,
                )
                for occurrence in group.occurrences
            ),
        )
        for group in groups
    )


def _mapping_container_verdict(
    annotation: str,
    parameters: list[str],
    module: str,
    contract: ArchitectureContract,
    exports_by_module: dict[str, frozenset[str]],
    imports_by_binding: BindingIndex,
    classes_by_location: BindingIndex,
    visited: frozenset[tuple[str, str]],
    enter_fields: bool,
    aliases_seen: frozenset[tuple[str, str]],
    *,
    type_shapes: TypeShapeIndex,
) -> _Position:
    contents = _combined_annotation_verdict(
        parameters,
        module,
        contract,
        exports_by_module,
        imports_by_binding,
        classes_by_location,
        visited=visited,
        enter_fields=enter_fields,
        _aliases_seen=aliases_seen,
        type_shapes=type_shapes,
    )
    nested_map = _proven_nested_map_chain(
        parameters, module, imports_by_binding, classes_by_location, type_shapes
    )
    exact_nested_map_chain = (
        nested_map is not None
        and contents.undecidable is None
        and not contents.mapping_alternatives
        and len(contents.mapping_occurrences) == 1
        and contents.mapping_occurrences[0].annotation == nested_map
        and contents.mapping_occurrences[0].depth == 1
        and contents.mapping_occurrences[0].path == ()
        and contents.mapping_occurrences[0].alias_free
        and contents.mapping_occurrences[0].opaque_value_depth == 1
    )
    return _Position(
        violation=_BROAD_BOUNDARY_REASON,
        undecidable=contents.undecidable,
        unknown_context=contents.unknown_context,
        referenced_members_static=contents.referenced_members_static,
        contains_callable=contents.contains_callable,
        resolved=contents.resolved,
        path=contents.path,
        nested_annotation=contents.nested_annotation,
        violations=(
            (_BROAD_BOUNDARY_REASON, (), annotation, 0),
            *((name, path, nested, depth + 1) for name, path, nested, depth in contents.violations),
        ),
        field_positions=tuple(
            _FieldPosition((reason, path, nested, depth + 1), field.annotation, field.alias_free)
            for field in contents.field_positions
            for reason, path, nested, depth in (field.finding,)
        ),
        field_declarations=contents.field_declarations,
        mapping_alternatives=_relocate_mapping_alternatives(contents.mapping_alternatives, 1, ()),
        mapping_occurrences=_mapping_container_occurrences(
            annotation,
            parameters[1],
            contents.mapping_occurrences,
            module,
            imports_by_binding,
            classes_by_location,
            type_shapes,
        ),
        exact_nested_map_chain=exact_nested_map_chain,
    )


def _mapping_container_occurrences(
    annotation: str,
    value: str,
    nested: tuple[_MappingOccurrence, ...],
    module: str,
    imports: BindingIndex,
    classes: BindingIndex,
    type_shapes: TypeShapeIndex,
) -> tuple[_MappingOccurrence, ...]:
    return (
        _MappingOccurrence(
            annotation,
            0,
            opaque_value_depth=_opaque_mapping_value_depth(
                value, module, imports, classes, type_shapes
            ),
            syntax_route=(),
            literal_arm=annotation
            if _literal_root_mapping_arm(annotation, module, imports, classes, type_shapes)
            else None,
        ),
        *(
            _MappingOccurrence(
                occurrence.annotation,
                occurrence.depth + 1,
                occurrence.path,
                occurrence.alias_free,
                occurrence.opaque_value_depth,
                occurrence.syntax_route,
            )
            for occurrence in nested
        ),
    )


def _proven_nested_map_chain(
    parameters: list[str],
    module: str,
    imports: BindingIndex,
    classes: BindingIndex,
    type_shapes: TypeShapeIndex,
) -> str | None:
    """Return the inner map only for one proven map → list → map → object shape."""
    if len(parameters) != 2:
        return None
    outer_key = type_shapes.get(parameters[0])
    values = type_shapes.get(parameters[1])
    if (
        not isinstance(outer_key, TypeName)
        or outer_key.name != "str"
        or _proven_type_head(outer_key, module, imports, classes, frozenset({("builtins", "str")}))
        is not True
        or not isinstance(values, TypeApplication)
        or values.tuple_arguments
        or len(values.arguments) != 1
        or _proven_type_head(
            values.head, module, imports, classes, frozenset({("builtins", "list")})
        )
        is not True
    ):
        return None
    inner = values.arguments[0]
    inner_parameters = _mapping_parameters(
        inner.text, module, imports, classes, type_shapes=type_shapes
    )
    if not isinstance(inner_parameters, list) or len(inner_parameters) != 2:
        return None
    inner_key = type_shapes.get(inner_parameters[0])
    if (
        not isinstance(inner_key, TypeName)
        or inner_key.name != "str"
        or _proven_type_head(inner_key, module, imports, classes, frozenset({("builtins", "str")}))
        is not True
        or _opaque_mapping_value_depth(inner_parameters[1], module, imports, classes, type_shapes)
        != 1
    ):
        return None
    return inner.text


def _declared_field_verdict(
    origin_symbol: RecordData | _AmbiguousBinding | None,
    module: str,
    contract: ArchitectureContract,
    exports_by_module: dict[str, frozenset[str]],
    imports_by_binding: BindingIndex,
    classes_by_location: BindingIndex,
    *,
    type_shapes: TypeShapeIndex,
    visited: frozenset[tuple[str, str]],
    _aliases_seen: frozenset[tuple[str, str]],
) -> _Position:
    """Inspect all owned declared model fields, stopping recursive graphs by origin."""
    if not isinstance(origin_symbol, dict) or not origin_symbol.get("fields"):
        return _Position()
    if classes_by_location.module_bindings is not None:
        classes_by_location = classes_by_location.module_bindings
    binding_uncertainties: dict[str, list[str]] = (
        origin_symbol["annotation_binding_uncertainties"]
        if "annotation_binding_uncertainties" in origin_symbol
        else {}
    )
    field_verdicts: list[tuple[str, _Position]] = []
    for field in origin_symbol["fields"]:
        if not isinstance(field, dict) or not isinstance(field.get("name"), str):
            continue
        annotation = field.get("annotation") or ""
        verdict = _boundary_type_verdict(
            annotation,
            module,
            contract,
            exports_by_module,
            imports_by_binding,
            classes_by_location,
            visited=visited,
            enter_fields=False,
            _aliases_seen=_aliases_seen,
            uncertain_bindings=binding_uncertainties.get(field["name"], ()),
            type_shapes=type_shapes,
        )
        field_verdicts.append(
            (field["name"], _field_position_verdict(field["name"], annotation, verdict))
        )
    return _combine_position_verdicts(field_verdicts)


def _field_violations(
    field_name: str, field_annotation: str, verdict: _Position
) -> list[tuple[str, tuple[str, ...], str | None, int]]:
    violations: list[tuple[str, tuple[str, ...], str | None, int]] = []
    if verdict.violations:
        violations.extend(
            (
                reason,
                (field_name, *path),
                nested_annotation or field_annotation,
                depth,
            )
            for reason, path, nested_annotation, depth in verdict.violations
        )
    elif verdict.violation is not None:
        violations.append(
            (
                verdict.violation,
                (field_name, *verdict.path),
                verdict.nested_annotation or field_annotation,
                0,
            )
        )
    return violations


def _field_position_verdict(
    field_name: str, field_annotation: str, verdict: _Position
) -> _Position:
    violations = _field_violations(field_name, field_annotation, verdict)
    mapping_occurrences = tuple(
        _MappingOccurrence(
            occurrence.annotation,
            occurrence.depth,
            (field_name, *occurrence.path),
            occurrence.alias_free,
            occurrence.opaque_value_depth,
            occurrence.syntax_route,
        )
        for occurrence in verdict.mapping_occurrences
    )
    field_positions = [
        _FieldPosition(
            (reason, (field_name, *path), nested, depth), field.annotation, field.alias_free
        )
        for field in verdict.field_positions
        for reason, path, nested, depth in (field.finding,)
    ]
    covered = {field.finding for field in verdict.field_positions}
    for reason, path, nested, depth in violations:
        original = (reason, path[1:], nested, depth)
        if original in covered:
            continue
        field_positions.append(
            _FieldPosition(
                (reason, path, nested, depth),
                field_annotation,
                not (
                    verdict.undecidable is not None
                    and verdict.named_origins
                    and nested != field_annotation
                )
                and all(
                    occurrence.alias_free
                    for occurrence in verdict.mapping_occurrences
                    if (occurrence.path, occurrence.annotation, occurrence.depth)
                    == (path[1:], nested, depth)
                ),
            )
        )
    return _Position(
        violation=verdict.violation,
        undecidable=verdict.undecidable,
        unknown_context=verdict.unknown_context,
        referenced_members_static=verdict.referenced_members_static,
        contains_callable=verdict.contains_callable,
        resolved=verdict.resolved,
        path=(field_name, *verdict.path),
        nested_annotation=verdict.nested_annotation or field_annotation,
        violations=tuple(violations),
        mapping_occurrences=mapping_occurrences,
        field_positions=tuple(field_positions),
        # One field can produce several findings; clean and UNKNOWN fields still count.
        field_declarations=((field_name,),)
        + tuple((field_name, *path) for path in verdict.field_declarations),
        mapping_alternatives=_relocate_mapping_alternatives(
            verdict.mapping_alternatives, 0, (field_name,)
        ),
    )


def _collection_verdict(
    annotation: str,
    module: str,
    contract: ArchitectureContract,
    exports_by_module: dict[str, frozenset[str]],
    imports_by_binding: BindingIndex,
    classes_by_location: BindingIndex,
    *,
    type_shapes: TypeShapeIndex,
    visited: frozenset[tuple[str, str]] = frozenset(),
    enter_fields: bool = True,
    _aliases_seen: frozenset[tuple[str, str]] = frozenset(),
) -> _Position | None:
    """Decide `Container[Name]` from its parameters, or None when it is not one (AD-67).

    The refactoring hole this closes: `execute(context: InternalContext)` was reported and
    `execute(contexts: list[InternalContext])` was silent, because a generic's parameters were
    never inspected, so moving a parameter into a list dropped the check. The container's own
    element type is the whole of what crosses the boundary, so it is decided by exactly the
    `resolve_named_type` lookup the rule already runs on a bare name -- one level in, never a
    general descent into name resolution: a nested subscript, a dotted name, a forward
    reference and a type no component owns stay undecidable, and now say so.

    Member violations and UNKNOWNs both survive, so an exact allowance cannot hide uncertainty.
    `resolved` includes every parameter's named types for `facade_types` (AD-65).
    """
    parameters = _collection_parameters(annotation, module, imports_by_binding)
    if parameters is None:
        return None
    verdict = _combined_annotation_verdict(
        parameters,
        module,
        contract,
        exports_by_module,
        imports_by_binding,
        classes_by_location,
        visited=visited,
        enter_fields=enter_fields,
        _aliases_seen=_aliases_seen,
        type_shapes=type_shapes,
    )
    return _Position(
        violation=verdict.violation,
        undecidable=verdict.undecidable,
        unknown_context=verdict.unknown_context,
        referenced_members_static=verdict.referenced_members_static,
        contains_callable=verdict.contains_callable,
        resolved=verdict.resolved,
        path=verdict.path,
        nested_annotation=verdict.nested_annotation,
        violations=tuple(
            (reason, path, nested, depth + 1) for reason, path, nested, depth in verdict.violations
        ),
        field_positions=tuple(
            _FieldPosition((reason, path, nested, depth + 1), field.annotation, field.alias_free)
            for field in verdict.field_positions
            for reason, path, nested, depth in (field.finding,)
        ),
        field_declarations=verdict.field_declarations,
        mapping_alternatives=_relocate_mapping_alternatives(verdict.mapping_alternatives, 1, ()),
        mapping_occurrences=tuple(
            _MappingOccurrence(
                occurrence.annotation,
                occurrence.depth + 1,
                occurrence.path,
                occurrence.alias_free,
                occurrence.opaque_value_depth,
                occurrence.syntax_route,
                annotation
                if occurrence.depth == 0
                and occurrence.alias_free
                and occurrence.literal_arm is not None
                and _literal_list_mapping_arm(
                    annotation, module, imports_by_binding, classes_by_location, type_shapes
                )
                else None,
            )
            for occurrence in verdict.mapping_occurrences
        ),
    )


def _combined_annotation_verdict(
    parameters: list[str],
    module: str,
    contract: ArchitectureContract,
    exports_by_module: dict[str, frozenset[str]],
    imports_by_binding: BindingIndex,
    classes_by_location: BindingIndex,
    *,
    type_shapes: TypeShapeIndex,
    visited: frozenset[tuple[str, str]],
    enter_fields: bool,
    _aliases_seen: frozenset[tuple[str, str]] = frozenset(),
) -> _Position:
    decided = [
        (
            parameter,
            _Position()
            if parameter == "None"
            else _boundary_type_verdict(
                parameter,
                module,
                contract,
                exports_by_module,
                imports_by_binding,
                classes_by_location,
                enter_collections=True,
                visited=visited,
                enter_fields=enter_fields,
                _aliases_seen=_aliases_seen,
                type_shapes=type_shapes,
            ),
        )
        for parameter in parameters
    ]
    return _combine_position_verdicts(decided)


def _combine_position_verdicts(decided: list[tuple[str, _Position]]) -> _Position:
    reached = tuple(sorted({pair for _parameter, verdict in decided for pair in verdict.resolved}))
    violations = tuple(
        sorted(
            [
                violation
                for parameter, verdict in decided
                if verdict.violation is not None
                for violation in (
                    verdict.violations
                    or (
                        (
                            f"holding {parameter} {verdict.violation}",
                            verdict.path,
                            verdict.nested_annotation or parameter,
                            0,
                        ),
                    )
                )
            ],
            key=lambda item: (item[0], item[1], item[2] or "", item[3]),
        )
    )
    mapping_occurrences = tuple(
        _MappingOccurrence(
            occurrence.annotation,
            occurrence.depth,
            occurrence.path,
            occurrence.alias_free,
            occurrence.opaque_value_depth,
            (index, *occurrence.syntax_route) if occurrence.syntax_route is not None else None,
            occurrence.literal_arm,
        )
        for index, (_parameter, verdict) in enumerate(decided)
        for occurrence in verdict.mapping_occurrences
    )
    field_positions = tuple(field for _, verdict in decided for field in verdict.field_positions)
    field_declarations = tuple(
        path for _parameter, verdict in decided for path in verdict.field_declarations
    )
    mapping_alternatives = tuple(
        group for _parameter, verdict in decided for group in verdict.mapping_alternatives
    )
    origins = tuple(sorted({origin for _, child in decided for origin in child.named_origins}))
    combined = _Position(
        referenced_members_static=all(verdict.referenced_members_static for _, verdict in decided),
        contains_callable=any(verdict.contains_callable for _, verdict in decided),
        resolved=reached,
        violations=violations,
        mapping_occurrences=mapping_occurrences,
        field_positions=field_positions,
        field_declarations=field_declarations,
        mapping_alternatives=mapping_alternatives,
    )
    for _parameter, verdict in decided:
        if verdict.undecidable is not None:
            return replace(
                combined,
                violation=violations[0][0] if violations else None,
                undecidable=verdict.undecidable,
                unknown_context=verdict.unknown_context,
                named_origins=origins,
                path=verdict.path,
                nested_annotation=verdict.nested_annotation,
            )
    if violations:
        reason, path, nested_annotation, _ = violations[0]
        return replace(combined, violation=reason, path=path, nested_annotation=nested_annotation)
    return combined


def _ambiguous_method_group(methods: Sequence[RawRecord]) -> bool:
    if len(methods) < 2:
        return False
    for method in methods:
        data = method["data"]
        if (
            data.get("overloaded") is not True
            or data.get("signature_decorators_proven") is not True
        ):
            return True
    return False


def _property_chains(symbols: Sequence[RawRecord]) -> frozenset[str]:
    grouped: dict[str, list[RawRecord]] = defaultdict(list)
    chains: set[str] = set()
    for item in symbols:
        if parse_source_symbol_kind(item["kind"]) is not SourceSymbolKind.METHOD or not _is_public_method_name(item["data"]["name"]):
            continue
        data = item["data"]
        name = data["qualified_name"]
        group: list[RawRecord] = grouped[name]
        group.append(item)
        if (
            "property_binding" in data
            and property_binding(data["property_binding"]).operation is not PropertyOperation.CREATE
        ):
            chains.add(name)
    return frozenset(
        chains | {name for name, group in grouped.items() if _ambiguous_method_group(group)}
    )


def _declared_facade_positions(
    item: RawRecord,
    contract: ArchitectureContract,
    exports_by_module: dict[str, frozenset[str]],
    imports: Sequence[RawRecord] = (),
    uncertain_reexport_origins: UncertainReexportOrigins | None = None,
    reexports: ReexportIndex | None = None,
    property_chains: frozenset[str] = frozenset(),
    *,
    include_fields: bool = False,
) -> DeclaredFacade | None:
    """The (module, qualified name, annotated positions) for one declared facade callable.

    Methods count only when their declaring class is proven exported. A class's inherited
    surface starts as a placeholder; the shared local-chain proof may discharge it.
    No rule is consulted: facade membership is a fact about the contract and scan.
    """
    data = item["data"]
    kind = parse_source_symbol_kind(item["kind"])
    category = parse_source_symbol_kind(data.get("symbol_category"))
    if kind is SourceSymbolKind.CLASS and category is SourceSymbolKind.CLASS:
        return _declared_facade_inherited_positions(
            data,
            contract,
            exports_by_module,
            imports,
            uncertain_reexport_origins,
            reexports,
            property_chains,
            include_fields=include_fields,
        )
    if data.get("qualified_name") in property_chains and not (
        data.get("source_final_method_binding") is True
        and data.get("signature_decorators_proven") is True
    ):
        return None
    if data.get("overloaded") is True and data.get("overload_signature") is not True:
        return None
    method = kind is SourceSymbolKind.METHOD and category is SourceSymbolKind.METHOD
    if method:
        return _declared_facade_method_positions(
            data, contract, exports_by_module, imports, uncertain_reexport_origins, reexports
        )
    if kind is not SourceSymbolKind.FUNCTION or category is not SourceSymbolKind.FUNCTION:
        return None
    module, name = data["module"], data["name"]
    facade_entries: list[tuple[str, str, str, bool]] = []
    component = contract.component_for(module)
    if component is not None and facade_covers(module, name, component, exports_by_module):
        facade_entries.append((module, name, module, False))

    origin = data["qualified_name"]
    reexport_entries = _reexport_facade_entries(
        origin,
        contract,
        exports_by_module,
        imports,
        uncertain_reexport_origins or {},
        reexports,
    )
    facade_entries.extend(reexport_entries)
    if not facade_entries:
        return None
    facade_entries = sorted(set(facade_entries))
    facade_module, facade_name, resolution_module, _ = facade_entries[0]
    # An unannotated position carries an empty annotation rather than being dropped: it is a
    # position of the facade the rule cannot decide, and dropping it hid it from the rule's own
    # denominator (AD-67).
    positions = [
        (parameter["name"], parameter["annotation"] or "") for parameter in data["parameters"]
    ]
    positions.append(("return", data["returns"] or ""))
    return (
        facade_module,
        f"{facade_module}.{facade_name}",
        positions,
        resolution_module,
        tuple(facade_entries),
    )


def _declared_facade_inherited_positions(
    data: RecordData,
    contract: ArchitectureContract,
    exports_by_module: dict[str, frozenset[str]],
    imports: Sequence[RawRecord],
    uncertain_reexport_origins: UncertainReexportOrigins | None,
    reexports: ReexportIndex | None,
    property_chains: frozenset[str],
    *,
    include_fields: bool = False,
) -> DeclaredFacade | None:
    base_roots = data["base_roots"] if "base_roots" in data else data["bases"]
    if not any(
        f"{data['qualified_name']}.{name}" in property_chains for name in data["class_members"]
    ) and not any(base not in _FRAMEWORK_BASES for base in base_roots):
        if not include_fields or not data.get("fields"):
            return None
    module, name = data["module"], data["name"]
    entries: list[FacadeEntry] = []
    owner = contract.component_for(module)
    if owner is not None and facade_covers(module, name, owner, exports_by_module):
        entries.append((module, name, module, False))
    entries.extend(
        _reexport_facade_entries(
            data["qualified_name"],
            contract,
            exports_by_module,
            imports,
            uncertain_reexport_origins or {},
            reexports,
            member_surface=True,
        )
    )
    if not entries:
        return None
    entries = sorted(set(entries))
    facade_module, facade_name, _, _ = entries[0]
    return (
        facade_module,
        f"{facade_module}.{facade_name}.__inherited_methods__",
        [("inherited methods", "")],
        module,
        tuple(
            (entry_module, f"{entry_name}.__inherited_methods__", resolution, uncertain)
            for entry_module, entry_name, resolution, uncertain in entries
        ),
    )


def _declared_facade_method_positions(
    data: RecordData,
    contract: ArchitectureContract,
    exports_by_module: dict[str, frozenset[str]],
    imports: Sequence[RawRecord],
    uncertain_reexport_origins: UncertainReexportOrigins | None,
    reexports: ReexportIndex | None,
) -> DeclaredFacade | None:
    name = data["name"]
    if not _is_public_method_name(name):
        return None
    parent = data["parent"]
    if not isinstance(parent, str):
        return None
    module = data["module"]
    class_name = parent[len(module) + 1 :]
    entries: list[FacadeEntry] = []
    owner = contract.component_for(module)
    if owner is not None and facade_covers(module, class_name, owner, exports_by_module):
        entries.append((module, class_name, module, False))
    entries.extend(
        _reexport_facade_entries(
            parent,
            contract,
            exports_by_module,
            imports,
            uncertain_reexport_origins or {},
            reexports,
        )
    )
    entries = sorted(set(entries))
    if not entries:
        return None
    positions = _method_signature_positions(data)
    method_entries = [
        (facade_module, f"{facade_name}.{name}", resolution, uncertain)
        for facade_module, facade_name, resolution, uncertain in entries
    ]
    facade_module, facade_name, _, _ = method_entries[0]
    return (
        facade_module,
        f"{facade_module}.{facade_name}",
        positions,
        module,
        tuple(method_entries),
    )


def _method_signature_positions(data: RecordData) -> list[tuple[str, str]]:
    parameters = data["parameters"]
    receiver_parameter = data.get("receiver_parameter")
    if (
        parse_method_kind(data["method_kind"]) is not MethodKind.STATIC
        and isinstance(receiver_parameter, str)
        and parameters
        and parameters[0]["name"] == receiver_parameter
    ):
        parameters = parameters[1:]
    positions = [(parameter["name"], parameter["annotation"] or "") for parameter in parameters]
    if data["name"] != "__init__":
        positions.append(("return", data["returns"] or ""))
    return positions


def _reexport_facade_entries(
    origin: str,
    contract: ArchitectureContract,
    exports_by_module: dict[str, frozenset[str]],
    imports: Sequence[RawRecord],
    uncertain_reexport_origins: UncertainReexportOrigins,
    reexports: ReexportIndex | None = None,
    *,
    member_surface: bool = False,
) -> list[FacadeEntry]:
    """Match re-export facts while keeping uncertain bindings scoped to one entry."""
    indexed = reexports or _reexport_index(imports)
    by_origin, by_alias, ambiguous_bindings = indexed
    candidates: dict[str, RawRecord] = {
        imported["id"]: imported for imported in by_origin.get(origin, ())
    }
    for alias, origins in uncertain_reexport_origins.items():
        if origin in origins:
            candidates.update({item["id"]: item for item in by_alias.get(alias, ())})
    facade_entries: list[FacadeEntry] = []
    for imported in candidates.values():
        imported_data = imported["data"]
        binding_key = (imported_data.get("source_module"), imported_data.get("binding"))
        binding_name = f"{imported_data['source_module']}.{imported_data['binding']}"
        candidate_origins = uncertain_reexport_origins.get(binding_name, frozenset())
        own_uncertainty = origin in candidate_origins
        if not (imported_data.get("reexport") or own_uncertainty):
            continue
        chain = imported_data.get("reexport_chain", ())
        inherited_uncertainty = any(
            origin in uncertain_reexport_origins.get(alias, frozenset()) for alias in chain
        )
        entry_origin = imported_data.get("origin_definition")
        if entry_origin != origin and not own_uncertainty and not inherited_uncertainty:
            continue
        facade_module = imported_data["source_module"]
        binding = imported_data["binding"]
        resolution_module, _, _ = origin.rpartition(".")
        member_uncertainty = member_surface and (
            imported_data.get("source_member_binding_static") is False
            or imported_data.get("origin_member_binding_static") is False
            or any(
                item["data"].get("source_member_binding_static") is False
                for alias in chain
                for item in by_alias.get(alias, ())
            )
        )
        entry_uncertain = (
            own_uncertainty
            or binding_key in ambiguous_bindings
            or inherited_uncertainty
            or member_uncertainty
        )
        owner = contract.component_for(facade_module)
        if (
            owner is not None
            and isinstance(binding, str)
            and facade_covers(facade_module, binding, owner, exports_by_module)
        ):
            facade_entries.append((facade_module, binding, resolution_module, entry_uncertain))
    return facade_entries


def _facade_positions(
    item: RawRecord,
    rule: BoundaryTypesRule,
    contract: ArchitectureContract,
    exports_by_module: dict[str, frozenset[str]],
    imports: Sequence[RawRecord] = (),
    uncertain_reexport_origins: UncertainReexportOrigins | None = None,
    reexports: ReexportIndex | None = None,
    property_chains: frozenset[str] = frozenset(),
) -> (
    tuple[
        str,
        str,
        list[tuple[str, str]],
        str,
        bool,
        tuple[tuple[str, str, str, bool], ...],
    ]
    | None
):
    """The declared facade positions `rule` must check, or None when the function is out of
    scope or exempted (AD-49)."""
    found = _declared_facade_positions(
        item,
        contract,
        exports_by_module,
        imports,
        uncertain_reexport_origins,
        reexports,
        property_chains,
    )
    if found is None:
        return None
    candidates = [
        entry
        for entry in found[4]
        if in_scope(entry[0], rule.source)
        and not any(in_scope(entry[0], allowed) for allowed in rule.allowed_sources)
        and entry[0] not in rule.exact_sources
    ]
    if not candidates:
        return None
    facade_module, facade_name, resolution_module, entry_uncertain = sorted(
        candidates, key=lambda entry: (entry[3], entry[:3])
    )[0]
    return (
        facade_module,
        f"{facade_module}.{facade_name}",
        found[2],
        resolution_module,
        entry_uncertain,
        found[4],
    )


def facade_signature_types(
    symbols: Sequence[RawRecord],
    imports: Sequence[RawRecord],
    contract: ArchitectureContract,
    exports_by_module: dict[str, frozenset[str]],
    uncertain_reexport_origins: UncertainReexportOrigins | None = None,
    *,
    type_shapes: TypeShapeIndex,
    source_modules: frozenset[str] | None = None,
    scope_id: str | None = None,
    ancestor_contracts: Sequence[ArchitectureContract] = (),
) -> list[RawRecord]:
    """Record on every declared facade function the types its signature exposes (AD-65).

    A type a facade signature names reaches the component's boundary whether or not another
    component imports it, so `interface_boundary`'s unused-entry check needs the same answer
    `boundary_types` already computes: `_declared_facade_positions` for which functions are
    facade, `_boundary_type_verdict`'s own `resolved` field (AD-69) for what an annotation
    resolves to. That one resolution is published here, as a `facade_types` key on the
    function's own symbol record beside the annotations it resolves, so `check.validation`
    reads the answer off the observation instead of deriving a second one that could disagree
    (AD-2's open payload, AD-4's one channel out of the analyzer).

    The key carries dotted `module.Name` origins, the shape an import's `reexport_chain`
    already uses, and is written only when at least one position resolves: an unresolved
    annotation reaches nothing, so recording an empty list would claim the function was
    inspected without saying anything a reader may act on. No `boundary_types` rule needs to
    be declared for this -- every component that declares a facade gets the same record,
    because `resolved` fills in on its own walk regardless of the verdict built alongside it.
    """
    imports_by_binding, classes_by_location = boundary_type_indexes(
        symbols,
        imports,
        contract,
        exports_by_module,
        uncertain_reexport_origins or {},
        ancestor_contracts,
    )
    reexports = _reexport_index(imports)
    property_chains = _property_chains(symbols)
    classes_by_qualified_name = {
        item["data"]["qualified_name"]: item for item in symbols if parse_source_symbol_kind(item["kind"]) is SourceSymbolKind.CLASS
    }
    methods_by_parent: dict[str, list[RawRecord]] = defaultdict(list)
    for item in symbols:
        parent = item["data"]["parent"] if "parent" in item["data"] else None
        if parse_source_symbol_kind(item["kind"]) is SourceSymbolKind.METHOD and isinstance(parent, str):
            methods_by_parent[parent] = [*methods_by_parent[parent], item]
    if source_modules is not None:
        if scope_id is None:
            raise ValueError("nested facade evidence requires a mount identity")
        return _scoped_facade_signature_types(
            symbols,
            imports,
            contract,
            exports_by_module,
            uncertain_reexport_origins or {},
            source_modules,
            scope_id,
            ancestor_contracts,
            imports_by_binding,
            classes_by_location,
            reexports,
            classes_by_qualified_name,
            methods_by_parent,
            type_shapes=type_shapes,
        )
    recorded: list[RawRecord] = []
    for item in symbols:
        found = _declared_facade_positions(
            item,
            contract,
            exports_by_module,
            imports,
            uncertain_reexport_origins,
            reexports,
            property_chains,
            include_fields=True,
        )
        has_proven_facade = found is not None and any(not entry[3] for entry in found[4])
        names = (
            _resolved_position_types(
                found[3],
                found[2],
                contract,
                exports_by_module,
                imports_by_binding,
                classes_by_location,
                type_shapes=type_shapes,
            )
            if has_proven_facade and found is not None
            else []
        )
        if found is not None and parse_source_symbol_kind(item["kind"]) is SourceSymbolKind.CLASS:
            field_types, field_candidates = _declared_field_reach(
                item,
                imports,
                contract,
                exports_by_module,
                imports_by_binding,
                classes_by_location,
                has_proven_facade,
                type_shapes=type_shapes,
            )
            names = sorted(set(names) | set(field_types))
            if has_proven_facade:
                inherited_types, _, _ = _inherited_facade_types(
                    item,
                    symbols,
                    methods_by_parent,
                    contract,
                    exports_by_module,
                    imports_by_binding,
                    classes_by_location,
                    incoming_imports=imports,
                    type_shapes=type_shapes,
                )
                names = sorted(set(names) | set(inherited_types))
            candidates = _inherited_generic_candidate_types(
                item,
                classes_by_qualified_name,
                methods_by_parent,
                contract,
                exports_by_module,
                imports_by_binding,
                classes_by_location,
                type_shapes=type_shapes,
            )
            candidates = sorted(set(candidates) | set(field_candidates))
            if candidates:
                raw_candidates = (
                    item["data"]["facade_type_candidates_by_publisher"]
                    if "facade_type_candidates_by_publisher" in item["data"]
                    else {}
                )
                by_publisher = dict(raw_candidates)
                for publisher in found[4]:
                    by_publisher[publisher[0]] = sorted(
                        set(by_publisher[publisher[0]] if publisher[0] in by_publisher else ())
                        | set(candidates)
                    )
                item = {
                    **item,
                    "data": {**item["data"], "facade_type_candidates_by_publisher": by_publisher},
                }
        recorded.append(
            {**item, "data": {**item["data"], "facade_types": names}} if names else item
        )
    return recorded


def _scoped_facade_signature_types(
    symbols: Sequence[RawRecord],
    imports: Sequence[RawRecord],
    contract: ArchitectureContract,
    exports_by_module: dict[str, frozenset[str]],
    uncertain_reexport_origins: UncertainReexportOrigins,
    source_modules: frozenset[str],
    scope_id: str,
    ancestor_contracts: Sequence[ArchitectureContract],
    imports_by_binding: BindingIndex,
    classes_by_location: BindingIndex,
    reexports: ReexportIndex,
    classes_by_qualified_name: dict[str, RawRecord],
    methods_by_parent: dict[str, list[RawRecord]],
    *,
    type_shapes: TypeShapeIndex,
) -> list[RawRecord]:
    """Attach nested facade type evidence to its mount and physical publisher module."""
    property_chains = _property_chains(symbols)
    owners = (contract, *ancestor_contracts)
    recorded: list[RawRecord] = []
    for item in symbols:
        by_mount: dict[str, dict[str, list[str]]] = {}
        raw_types = (
            item["data"]["facade_types_by_mount"]
            if "facade_types_by_mount" in item["data"]
            else None
        )
        if isinstance(raw_types, dict):
            for mount_id, publisher_types in raw_types.items():
                if not isinstance(mount_id, str) or not isinstance(publisher_types, dict):
                    continue
                by_mount[mount_id] = {
                    module: [value for value in values if isinstance(value, str)]
                    for module, values in publisher_types.items()
                    if isinstance(module, str) and isinstance(values, list)
                }
        scoped_types = by_mount.get(scope_id, {})
        for owner in owners:
            found = _declared_facade_positions(
                item,
                owner,
                exports_by_module,
                imports,
                uncertain_reexport_origins,
                reexports,
                property_chains,
                include_fields=True,
            )
            if found is None:
                continue
            publishers = [entry for entry in found[4] if entry[0] in source_modules]
            if not publishers:
                continue
            has_proven_facade = any(not entry[3] for entry in publishers)
            names = (
                _resolved_position_types(
                    found[3],
                    found[2],
                    contract,
                    exports_by_module,
                    imports_by_binding,
                    classes_by_location,
                    type_shapes=type_shapes,
                )
                if has_proven_facade
                else []
            )
            if parse_source_symbol_kind(item["kind"]) is SourceSymbolKind.CLASS:
                field_types, field_candidates = _declared_field_reach(
                    item,
                    imports,
                    contract,
                    exports_by_module,
                    imports_by_binding,
                    classes_by_location,
                    has_proven_facade,
                    type_shapes=type_shapes,
                )
                names = sorted(set(names) | set(field_types))
                if has_proven_facade:
                    inherited_types, _, _ = _inherited_facade_types(
                        item,
                        symbols,
                        methods_by_parent,
                        contract,
                        exports_by_module,
                        imports_by_binding,
                        classes_by_location,
                        incoming_imports=imports,
                        type_shapes=type_shapes,
                    )
                    names = sorted(set(names) | set(inherited_types))
                candidates = _inherited_generic_candidate_types(
                    item,
                    classes_by_qualified_name,
                    methods_by_parent,
                    contract,
                    exports_by_module,
                    imports_by_binding,
                    classes_by_location,
                    type_shapes=type_shapes,
                )
                candidates = sorted(set(candidates) | set(field_candidates))
                if candidates:
                    raw_candidates = (
                        item["data"]["facade_type_candidates_by_mount"]
                        if "facade_type_candidates_by_mount" in item["data"]
                        else {}
                    )
                    all_candidates = dict(raw_candidates)
                    raw_scoped = all_candidates[scope_id] if scope_id in all_candidates else {}
                    scoped_candidates = dict(raw_scoped)
                    for publisher in publishers:
                        scoped_candidates[publisher[0]] = sorted(
                            set(
                                scoped_candidates[publisher[0]]
                                if publisher[0] in scoped_candidates
                                else ()
                            )
                            | set(candidates)
                        )
                    all_candidates[scope_id] = scoped_candidates
                    item = {
                        **item,
                        "data": {**item["data"], "facade_type_candidates_by_mount": all_candidates},
                    }
            if not names:
                continue
            for entry in publishers:
                if not entry[3]:
                    scoped_types[entry[0]] = sorted(
                        set(scoped_types.get(entry[0], ())) | set(names)
                    )
        if scoped_types:
            by_mount[scope_id] = scoped_types
        if not by_mount:
            recorded.append(item)
            continue
        recorded.append(
            {
                **item,
                "data": {**item["data"], "facade_types_by_mount": by_mount},
            }
        )
    return recorded


def _declared_field_binding_static(data: RecordData, name: str) -> bool:
    """Name reach requires one surviving field on a statically bound public class."""
    declarations = data.get("attribute_declarations", ())
    uncertainties: dict[str, object] = data.get("annotation_binding_uncertainties", {})
    return (
        data.get("source_binding_unique") is True
        and data.get("source_member_binding_static") is True
        and data.get("class_header_static") is True
        and data.get("class_body_control_flow") is False
        and sum(declaration["name"] == name for declaration in declarations) == 1
        and name not in data.get("class_members", ())
        and not uncertainties.get(name)
    )


def _declared_field_reach(
    item: RawRecord,
    imports: Sequence[RawRecord],
    contract: ArchitectureContract,
    exports: dict[str, frozenset[str]],
    bindings: BindingIndex,
    classes: BindingIndex,
    published: bool,
    *,
    type_shapes: TypeShapeIndex,
) -> tuple[list[str], list[str]]:
    """A proven field exposes names, independently of proving their alias bodies."""
    data = item["data"]
    module = data["module"]
    names: set[str] = set()
    candidates: set[str] = set()
    static_routes = {
        f"{owner}.{name}"
        for owner, name in bindings
        if _alias_binding_static(bindings[(owner, name)])
    }
    for field in data.get("fields", ()):
        annotation = field.get("annotation")
        if not annotation:
            continue
        verdict = _boundary_type_verdict(
            annotation,
            module,
            contract,
            exports,
            bindings,
            classes,
            enter_fields=False,
            type_shapes=type_shapes,
        )
        shape = type_shapes.get(annotation)
        origin = (
            resolve_named_type(shape.name, module, bindings, classes)
            if isinstance(shape, TypeName)
            else None
        )
        reached: set[str] = {f"{origin[0]}.{origin[1]}"} if isinstance(origin, tuple) else set()
        provider = classes.get(origin) if isinstance(origin, tuple) else None
        route = bindings.get((module, shape.name)) if isinstance(shape, TypeName) else None
        chain: list[str] = (route["reexport_chain"] or []) if isinstance(route, dict) else []
        chain_static = all(entry in static_routes or entry in reached for entry in chain)
        possible: set[str] = {f"{owner}.{name}" for owner, name in verdict.resolved}
        if isinstance(shape, TypeName):
            for imported in imports:
                binding = imported["data"]
                if binding["source_module"] == module and binding["binding"] == shape.name:
                    possible.update(binding.get("reexport_candidates", ()))
                    possible.update(binding.get("reexport_chain", ()))
        certain = (
            published
            and _declared_field_binding_static(data, field["name"])
            and isinstance(origin, tuple)
            and isinstance(provider, dict)
            and _alias_binding_static(provider)
            and (route is None or _alias_binding_static(route))
            and chain_static
            and shape is not None
            and _base_route_member_static(shape, module, bindings, classes)
            and verdict.undecidable not in {_Cause.AMBIGUOUS_BINDING, _Cause.UNRESOLVED}
        )
        if certain:
            names.update(reached)
        candidates.update(possible - (reached if certain else set()))
    return sorted(names), sorted(candidates)


def _resolved_position_types(
    module: str,
    positions: Sequence[tuple[str, str]],
    contract: ArchitectureContract,
    exports_by_module: dict[str, frozenset[str]],
    imports_by_binding: BindingIndex,
    classes_by_location: BindingIndex,
    *,
    type_shapes: TypeShapeIndex,
) -> list[str]:
    """The distinct types one function's annotated positions resolve to, dotted and sorted.

    Reads `resolved` off `_boundary_type_verdict`'s own walk of each annotation (AD-69) instead
    of building a second candidate list: both readers take the bare name, and both take the
    element of a known collection, because a type inside a `list[...]` crosses the boundary
    exactly as the bare one does. A second, hand-kept reading would let `boundary_types` judge
    `list[Payload]` while `interface_boundary` called the very entry it judged unused -- the
    drift AD-65 exists to remove, reappearing wherever a future annotation shape is taught to
    only one of the two.
    """
    names = {
        f"{origin_module}.{origin_name}"
        for _, annotation in positions
        for origin_module, origin_name in _boundary_type_verdict(
            annotation,
            module,
            contract,
            exports_by_module,
            imports_by_binding,
            classes_by_location,
            type_shapes=type_shapes,
        ).resolved
    }
    return sorted(names)


class _BoundMethod(NamedTuple):
    symbol: RawRecord
    owner: RecordData
    imports: BindingIndex
    classes: BindingIndex


class _PropertyMethods(NamedTuple):
    getter: _BoundMethod
    setter: _BoundMethod | None = None


_MethodSurface: TypeAlias = dict[str, tuple[_BoundMethod, ...] | _PropertyMethods]


def _apply_property_methods(
    data: RecordData,
    methods: Sequence[RawRecord],
    inherited: _MethodSurface,
    imports: BindingIndex,
    classes: BindingIndex,
) -> _MethodSurface | None:
    surface = {
        name: value for name, value in inherited.items() if name not in data["class_members"]
    }
    grouped: dict[str, list[RawRecord]] = defaultdict(list)
    for method in methods:
        declared: list[RawRecord] = grouped[method["data"]["name"]]
        declared.append(method)
    for name, group in grouped.items():
        if name not in data.get("property_members", ()):
            if _ambiguous_method_group(group):
                return None
            for item in group:
                method_data = item["data"]
                if method_data.get("signature_decorators_proven") is not True:
                    return None
            surface[name] = tuple(_BoundMethod(item, data, imports, classes) for item in group)
            continue
        if any("property_binding" not in item["data"] for item in group):
            return None
        local: dict[int, _PropertyMethods] = {}
        bindings = [
            (method, property_binding(method["data"]["property_binding"])) for method in group
        ]
        for method, binding in sorted(bindings, key=lambda item: item[1].line):
            method_data = method["data"]
            bound = _BoundMethod(method, data, imports, classes)
            if binding.operation is PropertyOperation.CREATE:
                if method_data.get("signature_decorators_proven") is not True:
                    return None
                selected = _PropertyMethods(bound)
            else:
                origin = (
                    inherited.get(name)
                    if binding.source is PropertyOrigin.BASE
                    else local.get(binding.source_line)
                )
                if not isinstance(origin, _PropertyMethods):
                    return None
                selected = (
                    _PropertyMethods(bound, origin.setter)
                    if binding.operation is PropertyOperation.GETTER
                    else _PropertyMethods(origin.getter, bound)
                )
            local[binding.line] = selected
            surface[name] = selected
    return surface


def _effective_method_surface(
    item: RawRecord,
    symbols: Sequence[RawRecord],
    methods_by_parent: dict[str, list[RawRecord]],
    contract: ArchitectureContract,
    exports: dict[str, frozenset[str]],
    imports: BindingIndex,
    classes: BindingIndex,
    *,
    type_shapes: TypeShapeIndex,
    incoming_imports: Sequence[RawRecord],
    visited: frozenset[str] = frozenset(),
) -> _MethodSurface | None:
    data = item["data"]
    qualified_name = data["qualified_name"]
    typed_dict = (
        not visited
        and data.get("typed_dict_header_static") is True
        and data["base_roots"] == ["typing.TypedDict"]
        and len(data["bases"]) == 1
        and not methods_by_parent.get(qualified_name)
        and isinstance(data.get("attribute_declarations"), list)
        and all(
            any(
                declaration["name"] == field["name"]
                and declaration["annotation"] == field["annotation"]
                for declaration in data["attribute_declarations"]
            )
            for field in data["fields"]
        )
    )
    if (
        qualified_name in visited
        or data["class_body_control_flow"]
        or not (data.get("class_header_static") is True or typed_dict)
        or data.get("source_binding_unique") is not True
        or data.get("source_member_binding_static") is not True
        or not _member_origin_static(qualified_name, incoming_imports)
    ):
        return None
    if typed_dict:
        root = type_shapes.get(data["bases"][0])
        if root is None or not _base_route_member_static(root, data["module"], imports, classes):
            return None
        # TypedDict publishes value fields; dict operations are not its declared callable API.
        return {}
    base, reason = _public_api_base(
        item,
        symbols,
        contract,
        exports,
        imports,
        classes,
        member_surface=True,
        type_shapes=type_shapes,
    )
    if reason is not None:
        return None
    inherited: _MethodSurface = {}
    if base is not None:
        base_symbol, base_imports, base_classes = base
        found = _effective_method_surface(
            base_symbol,
            symbols,
            methods_by_parent,
            contract,
            exports,
            base_imports,
            base_classes,
            type_shapes=type_shapes,
            incoming_imports=incoming_imports,
            visited=visited | {qualified_name},
        )
        if found is None:
            return None
        inherited = found
    return _apply_property_methods(
        data, methods_by_parent.get(qualified_name, ()), inherited, imports, classes
    )


def _inherited_facade_types(
    item: RawRecord,
    symbols: Sequence[RawRecord],
    methods_by_parent: dict[str, list[RawRecord]],
    contract: ArchitectureContract,
    exports_by_module: dict[str, frozenset[str]],
    imports_by_binding: BindingIndex,
    classes_by_location: BindingIndex,
    *,
    type_shapes: TypeShapeIndex,
    incoming_imports: Sequence[RawRecord],
) -> tuple[list[str], list[tuple[str, str, str, str, _Position]], bool]:
    surface = _effective_method_surface(
        item,
        symbols,
        methods_by_parent,
        contract,
        exports_by_module,
        imports_by_binding,
        classes_by_location,
        type_shapes=type_shapes,
        incoming_imports=incoming_imports,
    )
    if surface is None:
        return [], _declared_chain_positions(item, classes_by_location, methods_by_parent), False
    property_chains = _property_chains(methods_by_parent.get(item["data"]["qualified_name"], ()))
    names: set[str] = set()
    positions: list[tuple[str, str, str, str, _Position]] = []
    data = item["data"]
    if data.get("typed_dict_header_static") is True and data["base_roots"] == ["typing.TypedDict"]:
        for declaration in data["attribute_declarations"]:
            verdict = _boundary_type_verdict(
                declaration["annotation"],
                data["module"],
                contract,
                exports_by_module,
                imports_by_binding,
                classes_by_location,
                type_shapes=type_shapes,
            )
            positions.append(
                (
                    declaration["name"],
                    declaration["definition_id"],
                    declaration["name"],
                    declaration["annotation"],
                    verdict,
                )
            )
            names.update(f"{module}.{name}" for module, name in verdict.resolved)
    for name, members in surface.items():
        if not _is_public_method_name(name):
            continue
        property_methods = isinstance(members, _PropertyMethods)
        selected = (
            (members.getter, members.setter) if isinstance(members, _PropertyMethods) else members
        )
        for bound in selected:
            if bound is None or (
                bound.owner["qualified_name"] == item["data"]["qualified_name"]
                and (
                    not property_methods
                    or bound.symbol["data"]["qualified_name"] not in property_chains
                )
            ):
                continue
            method_names, method_positions = _bound_method_positions(
                bound, contract, exports_by_module, type_shapes=type_shapes
            )
            names.update(method_names)
            positions.extend(method_positions)
    return sorted(names), positions, True


def _surface_position_origin(
    owner: RawRecord, identity: str, symbols_by_id: dict[str, RawRecord]
) -> RawRecord:
    if identity in symbols_by_id:
        return symbols_by_id[identity]
    declaration = next(
        declaration
        for declaration in owner["data"]["attribute_declarations"]
        if declaration["definition_id"] == identity
    )
    return {
        **owner,
        "evidence_ids": sorted(set(owner["evidence_ids"]) | set(declaration["evidence_ids"])),
    }


def _declared_chain_positions(
    item: RawRecord,
    classes: BindingIndex,
    methods_by_parent: dict[str, list[RawRecord]],
) -> list[tuple[str, str, str, str, _Position]]:
    data = item["data"]
    owner = data["qualified_name"]
    source_owner = classes.get((data["module"], data["name"]))
    if (
        not isinstance(source_owner, dict)
        or parse_source_symbol_kind(source_owner.get("symbol_category")) is not SourceSymbolKind.CLASS
        or source_owner.get("qualified_name") != owner
    ):
        return []
    methods = methods_by_parent.get(owner, ())
    chains = _property_chains(methods)
    for method in methods:
        method_data = method["data"]
        if (
            method_data.get("source_final_method_binding") is True
            and method_data.get("signature_decorators_proven") is True
        ):
            chains -= {method_data["qualified_name"]}
    positions: list[tuple[str, str, str, str, _Position]] = []
    for method in methods:
        method_data = method["data"]
        if method_data["qualified_name"] not in chains or (
            method_data.get("overloaded") is True
            and method_data.get("overload_signature") is not True
        ):
            continue
        positions.extend(
            (
                method_data["name"],
                method["id"],
                position,
                annotation,
                _Position(undecidable=_Cause.INHERITED_SURFACE),
            )
            for position, annotation in _method_signature_positions(method_data)
        )
    return positions


def _bound_method_positions(
    bound: _BoundMethod,
    contract: ArchitectureContract,
    exports: dict[str, frozenset[str]],
    *,
    type_shapes: TypeShapeIndex,
) -> tuple[set[str], list[tuple[str, str, str, str, _Position]]]:
    names: set[str] = set()
    positions: list[tuple[str, str, str, str, _Position]] = []
    method = bound.symbol
    data = method["data"]
    if data.get("overloaded") is True and data.get("overload_signature") is not True:
        return names, positions
    uncertainties = data.get("annotation_binding_uncertainties", {})
    for position, annotation in _method_signature_positions(data):
        verdict = _boundary_type_verdict(
            annotation,
            bound.owner["module"],
            contract,
            exports,
            bound.imports,
            bound.classes,
            uncertain_bindings=uncertainties.get(position, ()),
            type_shapes=type_shapes,
        )
        positions.append((data["name"], method["id"], position, annotation, verdict))
        for origin in verdict.resolved:
            symbol = bound.classes.get(origin)
            if isinstance(symbol, dict) and (
                parse_source_symbol_kind(symbol.get("symbol_category")) is SourceSymbolKind.CLASS
                or parse_source_symbol_kind(symbol.get("record_kind")) is SourceSymbolKind.TYPE_ALIAS
            ):
                names.add(f"{origin[0]}.{origin[1]}")
    return names, positions


def _direct_generic_candidate_types(
    item: RawRecord,
    classes_by_qualified_name: dict[str, RawRecord],
    methods_by_parent: dict[str, list[RawRecord]],
    contract: ArchitectureContract,
    exports_by_module: dict[str, frozenset[str]],
    imports_by_binding: BindingIndex,
    classes_by_location: BindingIndex,
    *,
    type_shapes: TypeShapeIndex,
) -> list[str]:
    """Retain possible type usage from the existing bounded generic candidate proof."""
    data = item["data"]
    if "class_body_control_flow" in data and data["class_body_control_flow"] is True:
        return []
    roots = data["base_roots"] if "base_roots" in data else ()
    if not isinstance(roots, list) or any(not isinstance(root, str) for root in roots):
        return []
    non_framework_roots = [root for root in roots if root not in _FRAMEWORK_BASES]
    specs = data["generic_bases"] if "generic_bases" in data else None
    if len(non_framework_roots) != 1 or not isinstance(specs, list) or len(specs) != 1:
        return []
    spec = specs[0]
    if not isinstance(spec, dict):
        return []
    base_name = spec["base"] if "base" in spec else None
    arguments = spec["arguments"] if "arguments" in spec else None
    bare_arguments = spec["arguments_are_names"] if "arguments_are_names" in spec else None
    if (
        not isinstance(base_name, str)
        or not isinstance(arguments, list)
        or not isinstance(bare_arguments, list)
        or len(arguments) != len(bare_arguments)
        or any(argument is not True for argument in bare_arguments)
    ):
        return []
    resolved_base = resolve_named_type(
        base_name,
        data["module"],
        imports_by_binding,
        classes_by_location,
    )
    if not isinstance(resolved_base, tuple):
        return []
    base_module, base_class = resolved_base
    base_qualified_name = f"{base_module}.{base_class}"
    base_symbol = classes_by_qualified_name.get(base_qualified_name)
    if base_symbol is None or parse_source_symbol_kind(base_symbol["kind"]) is not SourceSymbolKind.CLASS:
        return []
    base_data = base_symbol["data"]
    parameters = base_data["generic_parameters"] if "generic_parameters" in base_data else None
    if (
        not isinstance(parameters, list)
        or not parameters
        or len(parameters) != len(arguments)
        or any(not isinstance(parameter, str) for parameter in parameters)
        or any(not isinstance(argument, str) for argument in arguments)
    ):
        return []
    base_members = base_data["class_members"] if "class_members" in base_data else ()
    base_parameter_rebound = any(parameter in base_members for parameter in parameters)
    base_binding_uncertain = base_parameter_rebound or (
        "class_body_control_flow" in base_data and base_data["class_body_control_flow"] is True
    )

    substitutions: list[tuple[str, tuple[str, str]]] = []
    for parameter, argument in zip(parameters, arguments, strict=True):
        resolved_argument = resolve_named_type(
            argument,
            data["module"],
            imports_by_binding,
            classes_by_location,
        )
        if not isinstance(resolved_argument, tuple):
            return []
        resolved_origin = resolved_argument
        argument_symbol = classes_by_location.get(resolved_origin)
        if (
            not isinstance(argument_symbol, dict)
            or parse_source_symbol_kind(argument_symbol.get("symbol_category")) is not SourceSymbolKind.CLASS
        ):
            return []
        substitutions.append((parameter, resolved_origin))

    substituted_imports, substituted_classes = _substituted_type_bindings(
        base_module, substitutions, imports_by_binding, classes_by_location
    )

    overrides = set(data.get("class_members", ())) | {
        method["data"]["name"] for method in methods_by_parent.get(data["qualified_name"], ())
    }
    field_overrides = overrides | {
        field["name"] for field in data.get("fields", ()) if isinstance(field.get("name"), str)
    }
    base_fields = base_data["fields"] if "fields" in base_data else ()
    candidates: set[str] = set()
    for method in methods_by_parent.get(base_qualified_name, ()):
        method_data = method["data"]
        binding_uncertainties: dict[str, list[str]] = (
            method_data["annotation_binding_uncertainties"]
            if "annotation_binding_uncertainties" in method_data
            else {}
        )
        name = method_data["name"]
        if (
            name[:1] == "_"
            or name in overrides
            or (
                method_data.get("overloaded") is True
                and method_data.get("overload_signature") is not True
            )
        ):
            continue
        for position, annotation in _method_signature_positions(method_data):
            verdict = _boundary_type_verdict(
                annotation,
                base_module,
                contract,
                exports_by_module,
                substituted_imports,
                substituted_classes,
                uncertain_bindings=(
                    () if base_binding_uncertain else binding_uncertainties.get(position, ())
                ),
                type_shapes=type_shapes,
            )
            for origin in verdict.resolved:
                symbol = substituted_classes.get(origin)
                if isinstance(symbol, dict) and (
                    parse_source_symbol_kind(symbol.get("symbol_category")) is SourceSymbolKind.CLASS
                    or parse_source_symbol_kind(symbol.get("record_kind")) is SourceSymbolKind.TYPE_ALIAS
                ):
                    candidates.add(f"{origin[0]}.{origin[1]}")

    candidate_annotations = [
        field["annotation"]
        for field in base_fields
        if isinstance(field["name"], str)
        and field["name"] not in field_overrides
        and isinstance(field["annotation"], str)
        and field["annotation"]
    ]
    if "__init__" not in overrides:
        candidate_annotations += [
            parameter["annotation"]
            for method in methods_by_parent.get(base_qualified_name, ())
            if method["data"]["name"] == "__init__"
            for parameters in [method["data"]["parameters"]]
            for receiver in [method["data"]["receiver_parameter"]]
            for parameter in (
                parameters[1:]
                if isinstance(receiver, str) and parameters and parameters[0]["name"] == receiver
                else parameters
            )
            if isinstance(parameter["annotation"], str) and parameter["annotation"]
        ]
    for annotation in candidate_annotations:
        verdict = _boundary_type_verdict(
            annotation,
            base_module,
            contract,
            exports_by_module,
            substituted_imports,
            substituted_classes,
            type_shapes=type_shapes,
        )
        for origin in verdict.resolved:
            symbol = substituted_classes.get(origin)
            if isinstance(symbol, dict) and (
                parse_source_symbol_kind(symbol.get("symbol_category")) is SourceSymbolKind.CLASS
                or parse_source_symbol_kind(symbol.get("record_kind")) is SourceSymbolKind.TYPE_ALIAS
            ):
                candidates.add(f"{origin[0]}.{origin[1]}")

    return sorted(candidates)


def _substituted_type_bindings(
    base_module: str,
    substitutions: Sequence[tuple[str, tuple[str, str]]],
    imports_by_binding: BindingIndex,
    classes_by_location: BindingIndex,
) -> tuple[BindingIndex, BindingIndex]:
    substituted_imports = BindingIndex()
    for key in imports_by_binding:
        substituted_imports[key] = imports_by_binding[key]
    substituted_imports.ownership_contracts = imports_by_binding.ownership_contracts
    substituted_imports.owner_facade_type_states = dict(imports_by_binding.owner_facade_type_states)
    substituted_classes = BindingIndex()
    for key in classes_by_location:
        substituted_classes[key] = classes_by_location[key]
    for parameter, (origin_module, origin_name) in substitutions:
        key = (base_module, parameter)
        # The verified TypeVar binding is replaced for this one signature walk only.
        if key in substituted_classes:
            del substituted_classes[key]
        dotted_origin = f"{origin_module}.{origin_name}"
        substituted_imports[key] = {
            "source_module": base_module,
            "binding": parameter,
            "target_module": origin_module,
            "symbol": origin_name,
            "origin_definition": dotted_origin,
            "reexport_chain": [dotted_origin],
        }

    return substituted_imports, substituted_classes


def _inherited_generic_candidate_types(
    item: RawRecord,
    classes_by_qualified_name: dict[str, RawRecord],
    methods_by_parent: dict[str, list[RawRecord]],
    contract: ArchitectureContract,
    exports_by_module: dict[str, frozenset[str]],
    imports_by_binding: BindingIndex,
    classes_by_location: BindingIndex,
    *,
    type_shapes: TypeShapeIndex,
) -> list[str]:
    """Collect signature types from each independently resolvable ambiguous direct base."""
    data = item["data"]
    roots = data.get("base_roots", data.get("bases", ()))
    specs = data.get("generic_bases")
    if not isinstance(roots, list) or not isinstance(specs, list):
        return []
    candidates: set[str] = set()
    for spec in specs:
        if not isinstance(spec, dict) or not isinstance(spec.get("base"), str):
            continue
        base = spec["base"]
        if base in _FRAMEWORK_BASES:
            continue
        candidate: RawRecord = {
            **item,
            "data": {
                **data,
                "base_roots": [base],
                "generic_bases": [spec],
                "class_body_control_flow": False,
                "class_members": (
                    []
                    if data.get("class_body_control_flow") is True
                    else data.get("class_members", ())
                ),
            },
        }
        signature_candidates = _direct_generic_candidate_types(
            candidate,
            classes_by_qualified_name,
            methods_by_parent,
            contract,
            exports_by_module,
            imports_by_binding,
            classes_by_location,
            type_shapes=type_shapes,
        )
        candidates.update(signature_candidates)
    return sorted(candidates)


_OPAQUE_NATIVE_REASONS: Final = {
    "object": _BROAD_BOUNDARY_REASON,
    "object | None": f"holding object {_BROAD_BOUNDARY_REASON}",
}


def _root_broad_count(records: Sequence[RawRecord]) -> int:
    return sum(
        (
            record["data"]["reason"] == _BROAD_BOUNDARY_REASON
            or record["data"]["reason"] == _OPAQUE_NATIVE_REASONS.get(record["data"]["annotation"])
        )
        and "container_depth" not in record["data"]
        for record in records
    )


def _bound_alias_source_records(
    proof: _BoundAliasBody | _TypedMappingUnion,
    source_symbols: Sequence[RawRecord],
    source_imports: Sequence[RawRecord],
) -> tuple[RawRecord, ...]:
    if isinstance(proof, _TypedMappingUnion):
        origins = set(proof.source_origins)
    else:
        origin: str = proof.binding.origin
        module, _, name = origin.partition(":")
        origins = {(module, name), proof.metadata_origin}
    return (
        *(
            item
            for item in source_symbols
            if (item["data"]["module"], item["data"]["name"]) in origins
        ),
        *(
            item
            for item in source_imports
            if (item["data"]["source_module"], item["data"]["binding"]) in proof.import_bindings
        ),
    )


def _direct_boundary_allowance_matches(
    allowance: BoundaryTypeAllowance, data: RecordData, root_broad_count: int
) -> bool:
    annotation = data["annotation"]
    return (
        not allowance.field_path
        and isinstance(annotation, str)
        and (
            (data["reason"] == _BROAD_BOUNDARY_REASON and "nested_annotation" in data)
            or data["reason"] == _OPAQUE_NATIVE_REASONS.get(annotation)
        )
        and data.get("container_depth", 0) == 0
        and root_broad_count == 1
    )


def _ordinary_mapping_allowance_match(
    allowance: BoundaryTypeAllowance, data: RecordData, verdict: _Position, direct_match: bool
) -> tuple[bool, bool, bool] | None:
    if (
        not allowance.field_path
        and verdict.undecidable is not None
        and verdict.named_origins
        and data.get("nested_annotation") != allowance.annotation
    ):
        return None
    if allowance.native_mapping:
        return (
            (bool(allowance.field_path), False, False)
            if _native_mapping_allowance_matches(allowance, data, verdict)
            else None
        )
    alternative = False
    native_iterable = False
    if allowance.mapping_depth is not None:
        if not _nested_mapping_allowance_matches(allowance, data, verdict):
            return None
        is_contained = True
    elif alternative := _alternative_mapping_allowance_matches(allowance, data, verdict):
        is_contained = allowance.container_depth is not None
    elif allowance.container_depth is not None:
        native_iterable = (
            verdict.native_iterable_annotation == allowance.annotation
            and not allowance.field_path
            and allowance.container_depth == 1
            and data.get("container_depth") == 1
            and verdict.violations
            == ((f"holding object {_BROAD_BOUNDARY_REASON}", (), "object", 1),)
        )
        if not native_iterable and not _opaque_mapping_value_allowance_matches(
            allowance, data, verdict
        ):
            return None
        is_contained = True
    elif allowance.field_path:
        if not _nested_field_allowance_matches(allowance, data, verdict):
            return None
        is_contained = False
    else:
        if not direct_match and not _contained_mapping_allowance_matches(
            allowance, data, verdict.mapping_occurrences
        ):
            return None
        is_contained = not direct_match
    return is_contained, alternative, native_iterable


def _typed_mapping_allowance_matches(
    allowance: BoundaryTypeAllowance,
    data: RecordData,
    verdict: _Position,
    typed: _TypedMappingUnion,
) -> bool:
    return (
        allowance.alias_body == typed.alias_body
        and allowance.key_alias_body == typed.key_alias_body
        and not allowance.field_path
        and allowance.container_depth is None
        and allowance.mapping_depth is None
        and data.get("container_depth", 0) == 0
        and data["reason"] == _BROAD_BOUNDARY_REASON
        and sum(
            occurrence.annotation == data.get("nested_annotation")
            for occurrence in verdict.mapping_occurrences
        )
        == 1
    )


def _native_mapping_allowance_matches(
    allowance: BoundaryTypeAllowance, data: RecordData, verdict: _Position
) -> bool:
    if allowance.annotation == "dict" and not allowance.field_path:
        return (
            data["reason"] == _BROAD_BOUNDARY_REASON
            and not verdict.named_origins
            and verdict.undecidable is None
            and data.get("container_depth", 0) == 0
        )
    reason = f"holding dict {_BROAD_BOUNDARY_REASON}"
    if (
        data["reason"] not in {reason, _BROAD_BOUNDARY_REASON}
        or data.get("nested_annotation") != "dict"
    ):
        return False
    if allowance.field_path:
        field = _matching_field_position(allowance, data, verdict)
        return (
            field is not None
            and field.alias_free
            and data.get("container_depth", 0) == (1 if allowance.annotation == "list[dict]" else 0)
        )
    return (
        allowance.annotation == "dict | None"
        and not verdict.named_origins
        and verdict.undecidable is None
        and verdict.violations == ((reason, (), "dict", 0),)
    )


def _literal_mapping_arm_allowance_matches(
    allowance: BoundaryTypeAllowance, data: RecordData, verdict: _Position
) -> bool:
    if allowance.container_depth is not None:
        candidates = tuple(
            occurrence
            for occurrence in verdict.mapping_occurrences
            if not occurrence.path
            and occurrence.literal_arm == allowance.literal_mapping_arm
            and occurrence.alias_free
            and occurrence.syntax_route is not None
            and occurrence.opaque_value_depth is not None
            and occurrence.depth + occurrence.opaque_value_depth == allowance.container_depth
        )
        reason = f"holding object {_BROAD_BOUNDARY_REASON}"
        return (
            len(candidates) == 1
            and data["reason"] == reason
            and data.get("nested_annotation") == "object"
            and data.get("container_depth") == allowance.container_depth
            and verdict.violations.count((reason, (), "object", allowance.container_depth)) == 1
        )
    if data["reason"] != _BROAD_BOUNDARY_REASON:
        return False
    contributors = tuple(
        occurrence
        for occurrence in verdict.mapping_occurrences
        if not occurrence.path
        and occurrence.annotation == data.get("nested_annotation")
        and occurrence.depth == data.get("container_depth", 0)
    )
    matching_findings = sum(
        reason == _BROAD_BOUNDARY_REASON
        and not path
        and annotation == data.get("nested_annotation")
        and depth == data.get("container_depth", 0)
        for reason, path, annotation, depth in verdict.violations
    )
    if len(contributors) != 1 or matching_findings != 1:
        return False
    selected = contributors[0]
    return (
        selected.alias_free
        and selected.syntax_route is not None
        and selected.literal_arm == allowance.literal_mapping_arm
        and selected.depth in {0, 1}
        and (
            selected.depth == 1
            or sum(
                not occurrence.path and occurrence.depth == 0
                for occurrence in verdict.mapping_occurrences
            )
            == 1
        )
    )


def _boundary_type_allowance_fact(
    rule: BoundaryTypesRule,
    facade_module: str,
    record: RawRecord,
    root_broad_count: int,
    verdict: _Position,
    source_symbols: Sequence[RawRecord] = (),
    source_imports: Sequence[RawRecord] = (),
) -> RawRecord | None:
    data = record["data"]
    path = data["path"] if "path" in data else None
    for allowance in rule.allowed_positions:
        expected_path = (
            f"{allowance.position}.{allowance.field_path}" if allowance.field_path else None
        )
        direct_match = _direct_boundary_allowance_matches(allowance, data, root_broad_count)
        if (
            data["qualified_name"] != allowance.qualified_name
            or data["position"] != allowance.position
            or path != expected_path
            or (not allowance.field_path and data["annotation"] != allowance.annotation)
            or (allowance.annotation == "dict" and not allowance.native_mapping)
        ):
            continue
        if allowance.literal_mapping_arm is not None:
            if not _literal_mapping_arm_allowance_matches(allowance, data, verdict):
                continue
            return _boundary_type_allowance_fact_record(
                rule, facade_module, record, allowance, True
            )
        typed = verdict.typed_mapping_union
        if typed is not None:
            if not _typed_mapping_allowance_matches(allowance, data, verdict, typed):
                continue
            return _boundary_type_allowance_fact_record(
                rule,
                facade_module,
                record,
                allowance,
                True,
                alternative=True,
                typed_union=True,
                source_records=_bound_alias_source_records(typed, source_symbols, source_imports),
            )
        if allowance.key_alias_body is not None or (
            not allowance.field_path
            and not allowance.native_mapping
            and verdict.typed_union_checked
            and not verdict.mapping_alternatives
        ):
            continue
        if allowance.alias_body is not None:
            if not _bound_alias_allowance_matches(allowance, data, verdict):
                continue
            proof = verdict.bound_alias
            if proof is None:
                continue
            return _boundary_type_allowance_fact_record(
                rule,
                facade_module,
                record,
                allowance,
                True,
                source_records=_bound_alias_source_records(proof, source_symbols, source_imports),
            )
        match = _ordinary_mapping_allowance_match(allowance, data, verdict, direct_match)
        if match is None:
            continue
        is_contained, alternative, native_iterable = match
        return _boundary_type_allowance_fact_record(
            rule,
            facade_module,
            record,
            allowance,
            is_contained,
            alternative=alternative,
            native_iterable=native_iterable,
        )
    return None


def _bound_alias_allowance_matches(
    allowance: BoundaryTypeAllowance, data: RecordData, verdict: _Position
) -> bool:
    proof = verdict.bound_alias
    if (
        proof is None
        or allowance.alias_body != proof.binding
        or allowance.field_path
        or allowance.mapping_depth is not None
        or allowance.container_depth not in (None, 3)
    ):
        return False
    mappings = tuple(item for item in verdict.mapping_occurrences if not item.path)
    expected = (
        *((f"holding object {_BROAD_BOUNDARY_REASON}", (), "object", 3),) * 3,
        (_BROAD_BOUNDARY_REASON, (), "dict[str, object]", 2),
    )
    # Findings deduplicate the union arms; permission must still bind all three source leaves.
    if tuple(item for item in verdict.violations if not item[1]) != expected or tuple(
        item.legacy() for item in mappings
    ) != (_MappingOccurrence("dict[str, object]", 2, alias_free=False, opaque_value_depth=1),):
        return False
    return (
        data["reason"],
        data.get("nested_annotation"),
        data.get("container_depth"),
    ) == (
        (f"holding object {_BROAD_BOUNDARY_REASON}", "object", 3)
        if allowance.container_depth == 3
        else (_BROAD_BOUNDARY_REASON, "dict[str, object]", 2)
    )


def _matching_field_position(
    allowance: BoundaryTypeAllowance, data: RecordData, verdict: _Position
) -> _FieldPosition | None:
    if sum(".".join(path) == allowance.field_path for path in verdict.field_declarations) != 1:
        return None
    finding = (data["reason"], data.get("nested_annotation"), data.get("container_depth", 0))
    fields = tuple(
        field
        for field in verdict.field_positions
        if ".".join(field.finding[1]) == allowance.field_path
        and (field.finding[0], field.finding[2], field.finding[3]) == finding
    )
    if len(fields) != 1 or fields[0].annotation != allowance.annotation:
        return None
    return fields[0]


def _alternative_mapping_allowance_matches(
    allowance: BoundaryTypeAllowance, data: RecordData, verdict: _Position
) -> bool:
    path: tuple[str, ...] = ()
    if allowance.field_path:
        field = _matching_field_position(allowance, data, verdict)
        if field is None or not field.alias_free:
            return False
        path = field.finding[1]
    groups = tuple(
        group
        for group in verdict.mapping_alternatives
        if group.annotation == allowance.annotation
        and all(occurrence.path == path for occurrence in group.occurrences)
    )
    if len(groups) != 1:
        return False
    mappings = tuple(
        occurrence for occurrence in verdict.mapping_occurrences if occurrence.path == path
    )
    if tuple(item.legacy() for item in groups[0].occurrences) != tuple(
        item.legacy() for item in mappings
    ):
        return False
    if allowance.container_depth is not None:
        return (
            data["reason"] == f"holding object {_BROAD_BOUNDARY_REASON}"
            and data.get("nested_annotation") == "object"
            and data.get("container_depth") == allowance.container_depth
            and sum(
                occurrence.opaque_value_depth is not None
                and occurrence.depth + occurrence.opaque_value_depth == allowance.container_depth
                for occurrence in mappings
            )
            == 1
            and verdict.violations.count(
                (data["reason"], path, "object", allowance.container_depth)
            )
            == 1
        )
    if data["reason"] != _BROAD_BOUNDARY_REASON:
        return False
    return (
        len(
            tuple(
                occurrence
                for occurrence in mappings
                if occurrence.annotation == data.get("nested_annotation")
                and occurrence.depth == data.get("container_depth", 0)
            )
        )
        == 1
    )


def _nested_field_allowance_matches(
    allowance: BoundaryTypeAllowance, data: RecordData, verdict: _Position
) -> bool:
    field = _matching_field_position(allowance, data, verdict)
    if field is None:
        return False
    if data.get("nested_annotation") == allowance.annotation:
        return True
    path = field.finding[1]
    mappings = tuple(
        occurrence for occurrence in verdict.mapping_occurrences if occurrence.path == path
    )
    if not mappings or not field.alias_free:
        return False
    outer_depth = min(occurrence.depth for occurrence in mappings)
    outer = tuple(occurrence for occurrence in mappings if occurrence.depth == outer_depth)
    return (
        len(outer) == 1
        and outer[0].annotation == data.get("nested_annotation")
        and outer[0].depth == data.get("container_depth", 0)
    )


def _opaque_mapping_value_allowance_matches(
    allowance: BoundaryTypeAllowance, data: RecordData, verdict: _Position
) -> bool:
    depth = allowance.container_depth
    reason = f"holding object {_BROAD_BOUNDARY_REASON}"
    if (
        data["reason"] != reason
        or data.get("nested_annotation") != "object"
        or data.get("container_depth") != depth
    ):
        return False
    path: tuple[str, ...] = ()
    if allowance.field_path:
        field = _matching_field_position(allowance, data, verdict)
        if field is None or not field.alias_free:
            return False
        path = field.finding[1]
    mappings = tuple(
        occurrence for occurrence in verdict.mapping_occurrences if occurrence.path == path
    )
    return (
        len(mappings) == 1
        and mappings[0].alias_free
        and mappings[0].opaque_value_depth is not None
        and mappings[0].depth + mappings[0].opaque_value_depth == depth
        # Findings deduplicate; the selector must not accept two equal opaque occurrences.
        and verdict.violations.count((reason, path, "object", depth)) == 1
    )


def _nested_mapping_allowance_matches(
    allowance: BoundaryTypeAllowance, data: RecordData, verdict: _Position
) -> bool:
    if not verdict.exact_nested_map_chain or verdict.undecidable is not None:
        return False
    mappings = verdict.mapping_occurrences
    if (
        len(mappings) != 2
        or mappings[0].depth != 0
        or mappings[0].annotation != allowance.annotation
        or mappings[0].path
        or not mappings[0].alias_free
        or mappings[1].depth != allowance.mapping_depth
        or mappings[1].path
        or not mappings[1].alias_free
        or mappings[1].opaque_value_depth != 1
    ):
        return False
    depth = allowance.container_depth
    if depth is None:
        return (
            data["reason"] == _BROAD_BOUNDARY_REASON
            and data.get("nested_annotation") == mappings[1].annotation
            and data.get("container_depth") == allowance.mapping_depth
            and verdict.violations.count(
                (_BROAD_BOUNDARY_REASON, (), mappings[1].annotation, allowance.mapping_depth)
            )
            == 1
        )
    reason = f"holding object {_BROAD_BOUNDARY_REASON}"
    return (
        data["reason"] == reason
        and data.get("nested_annotation") == "object"
        and data.get("container_depth") == depth
        and mappings[1].depth + mappings[1].opaque_value_depth == depth
        and verdict.violations.count((reason, (), "object", depth)) == 1
    )


def _contained_mapping_allowance_matches(
    allowance: BoundaryTypeAllowance,
    data: RecordData,
    mapping_occurrences: tuple[_MappingOccurrence, ...],
) -> bool:
    # Only parameterized mappings record `nested_annotation`; bare broad types stay unmatched.
    if (
        data["reason"] != _BROAD_BOUNDARY_REASON
        or "nested_annotation" not in data
        or data.get("container_depth", 0) <= 0
        or allowance.annotation != data["annotation"]
    ):
        return False
    contained = tuple(occurrence for occurrence in mapping_occurrences if not occurrence.path)
    return (
        len(contained) == 1
        and contained[0].annotation == data["nested_annotation"]
        and contained[0].depth == data["container_depth"]
        and contained[0].alias_free
    )


def _boundary_type_allowance_data(
    allowance: BoundaryTypeAllowance,
    data: RecordData,
    is_contained: bool,
    alternative: bool,
    opaque: bool,
    *,
    typed_union: bool = False,
) -> RecordData:
    map_depth = allowance.mapping_depth
    depth_data: RecordData = {}
    if is_contained:
        depth_data = {"container_depth": data.get("container_depth", 0)}
        if allowance.alias_body is not None and not alternative:
            depth_data = {"observed_container_depth": data["container_depth"]}
            if allowance.container_depth is not None:
                depth_data["container_depth"] = allowance.container_depth
        if typed_union or allowance.literal_mapping_arm is not None:
            depth_data = {"observed_container_depth": data.get("container_depth", 0)}
    return {
        "qualified_name": allowance.qualified_name,
        "position": allowance.position,
        "field_path": allowance.field_path,
        "annotation": allowance.annotation,
        **(
            {
                "source": data["source"],
                "module": data["module"],
                "alias_body": {
                    "origin": allowance.alias_body.origin,
                    "shape": allowance.alias_body.shape,
                },
            }
            if allowance.alias_body is not None
            else {}
        ),
        **(
            {
                "source": data["source"],
                "module": data["module"],
                "key_alias_body": {
                    "origin": allowance.key_alias_body.origin,
                    "shape": allowance.key_alias_body.shape,
                },
            }
            if allowance.key_alias_body is not None
            else {}
        ),
        **({"mapping_depth": map_depth} if map_depth is not None else {}),
        **(
            {"nested_annotation": data["nested_annotation"]}
            if (allowance.field_path or alternative)
            and data.get("nested_annotation") != allowance.annotation
            else {}
        ),
        **(
            {
                "literal_mapping_arm": allowance.literal_mapping_arm,
                "observed_container_depth": data.get("container_depth", 0),
            }
            if allowance.literal_mapping_arm is not None
            else {}
        ),
        **({"native_mapping": True} if allowance.native_mapping else {}),
        **({"accepted_opacity": True} if opaque else {}),
        **(
            {
                "nested_annotation": data["nested_annotation"],
                **depth_data,
            }
            if is_contained
            else {}
        ),
    }


def _boundary_type_allowance_id(
    rule: BoundaryTypesRule, record: RawRecord, allowance: BoundaryTypeAllowance
) -> str:
    return stable_id(
        "TYPE",
        rule.id,
        record["id"],
        allowance.qualified_name,
        allowance.position,
        allowance.field_path,
        allowance.annotation,
        *((allowance.literal_mapping_arm,) if allowance.literal_mapping_arm is not None else ()),
        *(("native_mapping",) if allowance.native_mapping else ()),
        *((str(allowance.container_depth),) if allowance.container_depth is not None else ()),
        *((str(allowance.mapping_depth),) if allowance.mapping_depth is not None else ()),
        *(
            (allowance.alias_body.origin, allowance.alias_body.shape)
            if allowance.alias_body is not None
            else ()
        ),
        *(
            (allowance.key_alias_body.origin, allowance.key_alias_body.shape)
            if allowance.key_alias_body is not None
            else ()
        ),
    )


def _boundary_type_allowance_fact_record(
    rule: BoundaryTypesRule,
    facade_module: str,
    record: RawRecord,
    allowance: BoundaryTypeAllowance,
    is_contained: bool,
    *,
    alternative: bool = False,
    native_iterable: bool = False,
    typed_union: bool = False,
    source_records: Sequence[RawRecord] = (),
) -> RawRecord:
    data = record["data"]
    opaque = (
        allowance.native_mapping
        or allowance.container_depth is not None
        or (not allowance.field_path and allowance.annotation in _OPAQUE_NATIVE_REASONS)
    )
    if allowance.native_mapping:
        allowance_scope = "native open mapping "
    elif allowance.literal_mapping_arm is not None:
        allowance_scope = "literal mapping arm "
    elif allowance.container_depth is not None:
        allowance_scope = "opaque iterable element " if native_iterable else "opaque mapping value "
    elif alternative:
        allowance_scope = "alternative mapping "
    elif is_contained:
        allowance_scope = "unique contained mapping "
    else:
        allowance_scope = "nested " if allowance.field_path else ""
    return classified(
        item_id=_boundary_type_allowance_id(rule, record, allowance),
        evidence_class=EvidenceClass.FACT,
        area="type_architecture",
        kind="boundary_type_allowance",
        title=(
            f"{allowance.qualified_name} has an exact {allowance_scope}"
            "boundary type allowance"
            + (
                f" for {data['nested_annotation']} "
                f"at container depth {data.get('container_depth', 0)}"
                if is_contained
                else ""
            )
            + (
                f" at {allowance.position}; accepted opacity, type closure remains unproven"
                if opaque
                else ""
            )
        ),
        subjects=[allowance.qualified_name, facade_module],
        evidence_ids=sorted(
            {
                *record["evidence_ids"],
                *(evidence_id for item in source_records for evidence_id in item["evidence_ids"]),
            }
        ),
        rule_ids=[rule.id],
        fact_ids=[*record["fact_ids"], *(item["id"] for item in source_records)],
        provenance=(
            list(rule.provenance)
            if opaque
            or allowance.alias_body is not None
            or allowance.key_alias_body is not None
            or allowance.literal_mapping_arm is not None
            else None
        ),
        data=_boundary_type_allowance_data(
            allowance, data, is_contained, alternative, opaque, typed_union=typed_union
        ),
    )


def _boundary_types_violations(
    symbols: Sequence[RawRecord],
    imports: Sequence[RawRecord],
    contract: ArchitectureContract,
    exports_by_module: dict[str, frozenset[str]],
    uncertain_reexport_origins: UncertainReexportOrigins,
    source_modules: frozenset[str] | None = None,
    ancestor_contracts: Sequence[ArchitectureContract] = (),
    *,
    type_shapes: TypeShapeIndex,
    assessment_facts: list[RawRecord] | None = None,
    assessment_scope: str = "root",
    unsupported_rules: frozenset[str] = frozenset(),
) -> tuple[list[RawRecord], list[RawRecord]]:
    """Evaluate boundary rules only for facade positions the contract explicitly promises."""
    rules = [
        rule
        for rule in contract.rules
        if isinstance(rule, BoundaryTypesRule) and rule.kind not in unsupported_rules
    ]
    if not rules:
        return [], []
    imports_by_binding, classes_by_location = boundary_type_indexes(
        symbols,
        imports,
        contract,
        exports_by_module,
        uncertain_reexport_origins,
        ancestor_contracts,
    )
    reexports = _reexport_index(imports)
    property_chains = _property_chains(symbols)
    methods_by_parent: dict[str, list[RawRecord]] = defaultdict(list)
    for item in symbols:
        parent = item["data"]["parent"]
        if parse_source_symbol_kind(item["kind"]) is SourceSymbolKind.METHOD and isinstance(parent, str):
            methods_by_parent[parent] = [*methods_by_parent[parent], item]
    symbols_by_id = {item["id"]: item for item in symbols}
    violations: list[RawRecord] = []
    allowance_facts: list[RawRecord] = []
    for rule in rules:
        evaluated: dict[str, RawRecord] = {}
        for item in symbols:
            found = _facade_positions(
                item,
                rule,
                contract,
                exports_by_module,
                imports,
                uncertain_reexport_origins,
                reexports,
                property_chains,
            )
            if found is None:
                continue
            facade_module, qualname, positions, resolution_module, ambiguous_facade, _ = found
            if source_modules is not None and facade_module not in source_modules:
                continue
            data = item["data"]
            kind = parse_source_symbol_kind(item["kind"])
            inherited_positions: list[tuple[str, str, str, str, _Position]] = []
            if kind is SourceSymbolKind.CLASS:
                _, inherited_positions, complete = _inherited_facade_types(
                    item,
                    symbols,
                    methods_by_parent,
                    contract,
                    exports_by_module,
                    imports_by_binding,
                    classes_by_location,
                    incoming_imports=imports,
                    type_shapes=type_shapes,
                )
                if complete and not ambiguous_facade:
                    positions = []
                    evaluated[item["id"]] = item
                if ambiguous_facade:
                    inherited_positions = []
            binding_uncertainties: dict[str, list[str]] = (
                data["annotation_binding_uncertainties"]
                if "annotation_binding_uncertainties" in data
                else {}
            )
            for position, annotation in positions:
                verdict = (
                    _Position(undecidable=_Cause.AMBIGUOUS_FACADE)
                    if ambiguous_facade
                    else _boundary_type_verdict(
                        annotation,
                        resolution_module,
                        contract,
                        exports_by_module,
                        imports_by_binding,
                        classes_by_location,
                        uncertain_bindings=binding_uncertainties.get(position, ()),
                        type_shapes=type_shapes,
                    )
                )
                evaluated[item["id"]] = item
                records = _boundary_type_violation_records(
                    rule,
                    item,
                    facade_module,
                    qualname,
                    position,
                    annotation,
                    verdict,
                )
                root_broad_count = _root_broad_count(records)
                for record in records:
                    fact = _boundary_type_allowance_fact(
                        rule,
                        facade_module,
                        record,
                        root_broad_count,
                        verdict,
                        symbols,
                        imports,
                    )
                    if fact is None:
                        violations.append(record)
                    else:
                        allowance_facts.append(fact)
            if kind is SourceSymbolKind.CLASS:
                for method_name, method_id, position, annotation, verdict in inherited_positions:
                    facade_qualname = qualname[: -len(".__inherited_methods__")]
                    inherited_qualname = f"{facade_qualname}.{method_name}"
                    records = _boundary_type_violation_records(
                        rule,
                        item,
                        facade_module,
                        inherited_qualname,
                        position,
                        annotation,
                        verdict,
                        identity_suffix=method_id,
                        origin_symbol=_surface_position_origin(item, method_id, symbols_by_id),
                        resolved_types=tuple(
                            f"{module}:{name}" for module, name in verdict.resolved
                        ),
                    )
                    root_broad_count = _root_broad_count(records)
                    for record in records:
                        fact = _boundary_type_allowance_fact(
                            rule,
                            facade_module,
                            record,
                            root_broad_count,
                            verdict,
                            symbols,
                            imports,
                        )
                        if fact is None:
                            violations.append(record)
                        else:
                            allowance_facts.append(fact)
        _record_boundary_evaluation(
            rule, evaluated, assessment_facts, assessment_scope, unsupported_rules
        )
    return sorted(violations, key=lambda item: item["id"]), sorted(
        allowance_facts, key=lambda item: item["id"]
    )


def _record_boundary_evaluation(
    rule: BoundaryTypesRule,
    evaluated: dict[str, RawRecord],
    assessment_facts: list[RawRecord] | None,
    scope: str,
    unsupported_rules: frozenset[str],
) -> None:
    if not evaluated or assessment_facts is None or rule.kind in unsupported_rules:
        return
    subjects = sorted(
        {
            subject
            for item in evaluated.values()
            for subject in (item["data"]["module"], item["data"]["qualified_name"])
        }
    )
    assessment_facts.append(
        _rule_evaluation_receipt(rule, scope, tuple(evaluated.values()), subjects=subjects)
    )


def _boundary_type_violation_records(
    rule: BoundaryTypesRule,
    item: RawRecord,
    facade_module: str,
    qualname: str,
    position: str,
    annotation: str,
    verdict: _Position,
    *,
    identity_suffix: str = "",
    resolved_types: tuple[str, ...] = (),
    origin_symbol: RawRecord | None = None,
) -> list[RawRecord]:
    if verdict.violation is None:
        return []
    verb = "returns" if position == "return" else f"takes {position} as"
    resolution_detail = f" (resolved types: {', '.join(resolved_types)})" if resolved_types else ""
    findings = sorted(
        set(
            verdict.violations or ((verdict.violation, verdict.path, verdict.nested_annotation, 0),)
        ),
        key=lambda finding: (finding[0], finding[1], finding[2] or "", finding[3]),
    )
    records: list[RawRecord] = []
    for reason, path, nested_annotation, depth in findings:
        path_data = ".".join((position, *path)) if path else None
        if path:
            identity_parts = (rule.id, item["id"], position, *path, nested_annotation or "", reason)
            if identity_suffix:
                identity_parts += (identity_suffix,)
        elif len(findings) > 1:
            identity_parts = (rule.id, item["id"], position, nested_annotation or "", reason)
            if identity_suffix:
                identity_parts += (identity_suffix,)
        else:
            identity_parts = (rule.id, item["id"], position)
            if identity_suffix:
                identity_parts += (identity_suffix,)
        # Depth only separates findings that are otherwise identical; a lone one keeps its id.
        if depth and len(findings) > 1:
            identity_parts += (str(depth),)
        nested_fields = " ".join(f"field {name}" for name in path)
        field_detail = f"{nested_fields} " if nested_fields else ""
        records.append(
            classified(
                item_id=stable_id("VIO", *identity_parts),
                evidence_class=EvidenceClass.VIOLATION,
                area="type_architecture",
                kind=rule.kind,
                title=f"{qualname} {verb} {annotation} {field_detail}{reason}{resolution_detail}",
                subjects=[qualname, facade_module],
                evidence_ids=sorted(
                    set(item["evidence_ids"])
                    | set(origin_symbol["evidence_ids"] if origin_symbol is not None else ())
                ),
                rule_ids=[rule.id],
                fact_ids=[item["id"], origin_symbol["id"]]
                if origin_symbol is not None and origin_symbol["id"] != item["id"]
                else [item["id"]],
                data={
                    "source": rule.source,
                    "qualified_name": qualname,
                    "module": facade_module,
                    "position": position,
                    "annotation": annotation,
                    "reason": reason,
                    **({"resolved_types": resolved_types} if resolved_types else {}),
                    **({"container_depth": depth} if depth else {}),
                    **({"path": path_data} if path_data else {}),
                    **({"nested_annotation": nested_annotation} if nested_annotation else {}),
                },
            )
        )
    return records


def _boundary_type_position_record(
    rule: BoundaryTypesRule,
    symbol: RawRecord,
    detail: RecordData,
    *,
    origin_symbol: RawRecord | None = None,
    unknown_context: str | None = None,
) -> RawRecord:
    module = detail["module"]
    qualified_name = detail["qualified_name"]
    position = detail["position"]
    reason = detail["reason"]
    occurrence = detail["occurrence"]
    path = detail.get("path")
    location = f" at {path}" if isinstance(path, str) else ""
    title = (
        f"{qualified_name} {position}: declared annotation {detail['annotation'] or '(missing)'}; "
        "effective binding UNKNOWN"
        if detail.get("signature_scope") == "declared"
        else f"{qualified_name} {position}: {reason}{location}"
        + (f"; {unknown_context}" if unknown_context else "")
    )
    return classified(
        item_id=stable_id(
            "UNKNOWN-BOUNDARY-TYPE-POSITION",
            rule.id,
            module,
            qualified_name,
            occurrence,
            position,
        ),
        evidence_class=EvidenceClass.UNKNOWN,
        area="type_architecture",
        kind="boundary_type_position",
        title=title,
        subjects=[rule.source, module, qualified_name],
        evidence_ids=sorted(
            set(symbol["evidence_ids"])
            | set(origin_symbol["evidence_ids"] if origin_symbol is not None else ())
        ),
        rule_ids=[rule.id],
        fact_ids=[symbol["id"], origin_symbol["id"]]
        if origin_symbol is not None and origin_symbol["id"] != symbol["id"]
        else [symbol["id"]],
        data=detail,
    )


def _boundary_type_limit_record(
    rule: BoundaryTypesRule,
    seen: int,
    undecidable_positions: list[dict[str, object]],
) -> RawRecord | None:
    if not seen:
        # No positions means no declared facade function; `rule-without-subjects` already says so.
        return None
    decided = seen - len(undecidable_positions)
    if decided == seen:
        return None
    counts = dict.fromkeys(_UNDECIDABLE_KINDS, 0)
    for detail in undecidable_positions:
        reason = detail["reason"]
        if isinstance(reason, str):
            counts[reason] += 1
    return classified(
        item_id=stable_id("UNKNOWN-BOUNDARY-TYPES", rule.id),
        evidence_class=EvidenceClass.UNKNOWN,
        area="type_architecture",
        kind="boundary_type_limit",
        title=f"{rule.id} decided {decided} of {seen} declared facade type positions",
        subjects=[rule.source],
        rule_ids=[rule.id],
        data={
            "positions": seen,
            "decided": decided,
            "undecided": len(undecidable_positions),
            **counts,
            "undecidable_positions": undecidable_positions,
        },
    )


def _symbol_source_location(
    symbol: RawRecord, evidence: dict[str, RawEvidence]
) -> tuple[str, int, int]:
    item = evidence[symbol["evidence_ids"][0]]
    return item["file"], item["line"], item["column"]


def _uncertain_facade_position_records(
    item: RawRecord,
    rule: BoundaryTypesRule,
    facade_entries: Sequence[FacadeEntry],
    positions: Sequence[tuple[str, str]],
    selected: tuple[str, str, str],
    occurrences: dict[tuple[str, str], int],
) -> list[tuple[dict[str, object], RawRecord]]:
    records: list[tuple[dict[str, object], RawRecord]] = []
    for module, name, resolution_module, uncertain in facade_entries:
        if (
            not uncertain
            or (module, name, resolution_module) == selected
            or not in_scope(module, rule.source)
            or any(in_scope(module, allowed) for allowed in rule.allowed_sources)
            or module in rule.exact_sources
        ):
            continue
        qualname = f"{module}.{name}"
        key = (module, qualname)
        occurrence = occurrences.get(key, 0)
        occurrences[key] = occurrence + 1
        for position, annotation in positions:
            detail: dict[str, object] = {
                "module": module,
                "qualified_name": qualname,
                "position": position,
                "annotation": annotation,
                "reason": _Cause.AMBIGUOUS_FACADE,
                "occurrence": occurrence,
            }
            records.append((detail, _boundary_type_position_record(rule, item, detail)))
    return records


def _unresolved_public_alias_routes(
    rule: BoundaryTypesRule,
    symbols: Sequence[RawRecord],
    imports: Sequence[RawRecord],
    contract: ArchitectureContract,
    exports_by_module: dict[str, frozenset[str]],
    uncertain_reexport_origins: UncertainReexportOrigins,
    scanned_modules: set[str],
    stable_bindings_by_module: dict[str, frozenset[str]],
    source_modules: frozenset[str] | None = None,
    *,
    type_shapes: TypeShapeIndex,
) -> list[RawRecord]:
    records: dict[str, RawRecord] = {}
    symbols_by_binding: dict[tuple[str, str], list[RawRecord]] = defaultdict(list)
    imports_by_binding: dict[tuple[str, str], list[RawRecord]] = defaultdict(list)
    for item in symbols:
        data = item["data"]
        if "parent" not in data or data["parent"] is None:
            symbols_by_binding[(data["module"], data["name"])].append(item)
    for item in imports:
        data = item["data"]
        if data.get("module_level_import") is True:
            imports_by_binding[(data["source_module"], data["binding"])].append(item)
    for item in imports:
        data = item["data"]
        module, binding = data["source_module"], data["binding"]
        if (
            (source_modules is not None and module not in source_modules)
            or not data["symbol"]
            or not in_scope(module, rule.source)
            or any(in_scope(module, allowed) for allowed in rule.allowed_sources)
            or module in rule.exact_sources
        ):
            continue
        owner = contract.component_for(module)
        if (
            owner is None
            or not isinstance(binding, str)
            or not facade_covers(module, binding, owner, exports_by_module)
        ):
            continue
        route = (f"{module}.{binding}", *data.get("reexport_chain", ()))
        unresolved = tuple(
            alias
            for alias in route
            if alias in uncertain_reexport_origins and not uncertain_reexport_origins[alias]
        )
        if not unresolved and not _public_alias_route_has_unproven_hop(
            route,
            symbols_by_binding,
            imports_by_binding,
            scanned_modules,
            stable_bindings_by_module,
            type_shapes=type_shapes,
        ):
            continue
        qualified_name = f"{module}.{binding}"
        record = classified(
            item_id=stable_id("UNKNOWN-BOUNDARY-TYPE-ROUTE", rule.id, qualified_name),
            evidence_class=EvidenceClass.UNKNOWN,
            area="type_architecture",
            kind="boundary_type_route",
            title=f"{rule.id} cannot resolve a declared facade alias route",
            subjects=[qualified_name, module],
            evidence_ids=item["evidence_ids"],
            rule_ids=[rule.id],
            fact_ids=[item["id"]],
            data={
                "module": module,
                "qualified_name": qualified_name,
                "reason": "unresolved_reexport_route",
                "route": list(route),
            },
        )
        records[record["id"]] = record
    return sorted(records.values(), key=lambda item: item["id"])


def _public_alias_route_has_unproven_hop(
    route: tuple[str, ...],
    symbols_by_binding: dict[tuple[str, str], list[RawRecord]],
    imports_by_binding: dict[tuple[str, str], list[RawRecord]],
    scanned_modules: set[str],
    stable_bindings_by_module: dict[str, frozenset[str]],
    *,
    type_shapes: TypeShapeIndex,
) -> bool:
    """A public alias is known only while each traversed binding has one proven definition."""
    if not route:
        return True
    module, separator, binding = route[0].rpartition(".")
    if (
        not separator
        or module not in scanned_modules
        or binding not in stable_bindings_by_module.get(module, frozenset())
    ):
        return True
    publisher = imports_by_binding.get((module, binding), [])
    for alias in route[1:]:
        alias_name: str = alias
        module, separator, name = alias_name.rpartition(".")
        if not separator:
            return True
        if module not in scanned_modules:
            return True
        definitions = symbols_by_binding.get((module, name), [])
        bindings = imports_by_binding.get((module, name), [])
        if definitions:
            if (
                alias == route[-1]
                and not bindings
                and _public_overload_origin_proven(definitions, publisher, route)
            ):
                return False
            if (
                len(definitions) != 1
                or bindings
                or name not in stable_bindings_by_module.get(module, frozenset())
            ):
                return True
            category = definitions[0]["kind"]
            if category == "type_alias":
                definition_data = definitions[0]["data"]
                if "alias" not in definition_data:
                    return True
                alias_expression_text: str = definition_data["alias"]
                expression = type_shapes.get(alias_expression_text)
                return not (
                    (isinstance(expression, TypeUnion)) or isinstance(expression, TypeApplication)
                )
            return category not in {"function", "class", "static_constant"}
        if len(bindings) != 1:
            return True
        binding_data = bindings[0]["data"]
        if not binding_data["reexport"]:
            return True
    return False


def _public_overload_origin_proven(
    definitions: Sequence[RawRecord], publisher: Sequence[RawRecord], route: tuple[str, ...]
) -> bool:
    if len(publisher) != 1 or len(definitions) < 3:
        return False
    imported = publisher[0]["data"]
    if (
        imported.get("reexport") is not True
        or imported.get("source_binding_unique") is not True
        or imported.get("origin_binding_unique") is not True
        or imported.get("origin_definition") != route[-1]
        or tuple(imported.get("reexport_chain", ())) != route[1:]
    ):
        return False
    implementation = []
    for item in definitions:
        data = item["data"]
        if data.get("overload_signature") is False:
            implementation.append(data)
    if len(implementation) != 1:
        return False
    implementation_data = implementation[0]
    if implementation_data.get("decorators") != []:
        return False
    for item in definitions:
        data = item["data"]
        if not (
            parse_source_symbol_kind(item["kind"]) is SourceSymbolKind.FUNCTION
            and data.get("overloaded") is True
            and (data.get("overload_signature") is True or data.get("overload_signature") is False)
            and "parent" in data
            and data["parent"] is None
            and data.get("namespace_bound") is True
            and data.get("definition_contexts") == []
            and (data.get("async") is True or data.get("async") is False)
            and data.get("async") is implementation_data.get("async")
        ):
            return False
    return True


def boundary_type_limits(
    symbols: Sequence[RawRecord],
    imports: Sequence[RawRecord],
    contract: ArchitectureContract,
    exports_by_module: dict[str, frozenset[str]],
    evidence: dict[str, RawEvidence],
    uncertain_reexport_origins: UncertainReexportOrigins,
    scanned_modules: set[str],
    stable_bindings_by_module: dict[str, frozenset[str]] | None = None,
    source_modules: frozenset[str] | None = None,
    ancestor_contracts: Sequence[ArchitectureContract] = (),
    *,
    type_shapes: TypeShapeIndex,
) -> list[RawRecord]:
    """Record undecidable facade positions as a non-gating UNKNOWN, preserving AD-67."""
    rules = [rule for rule in contract.rules if isinstance(rule, BoundaryTypesRule)]
    if not rules:
        return []
    imports_by_binding, classes_by_location = boundary_type_indexes(
        symbols,
        imports,
        contract,
        exports_by_module,
        uncertain_reexport_origins,
        ancestor_contracts,
    )
    # The origin symbol can live outside the rule's source package when a facade re-exports it.
    # `_boundary_rule_positions` selects the declared facade, so origin-module filtering here
    # would drop an unannotated facade position before it can become UNKNOWN.
    ordered_symbols = sorted(symbols, key=lambda item: _symbol_source_location(item, evidence))
    limits: list[RawRecord] = []
    positions_out: list[RawRecord] = []
    for rule in rules:
        seen, undecidable_positions, rule_positions = _boundary_rule_positions(
            rule,
            ordered_symbols,
            contract,
            exports_by_module,
            imports,
            imports_by_binding,
            classes_by_location,
            uncertain_reexport_origins,
            source_modules,
            type_shapes=type_shapes,
        )
        positions_out.extend(rule_positions)
        limit = _boundary_type_limit_record(rule, seen, undecidable_positions)
        if limit is not None:
            limits.append(limit)
        limits.extend(
            _unresolved_public_alias_routes(
                rule,
                symbols,
                imports,
                contract,
                exports_by_module,
                uncertain_reexport_origins,
                scanned_modules,
                stable_bindings_by_module or {},
                source_modules,
                type_shapes=type_shapes,
            )
        )
    return sorted([*positions_out, *limits], key=lambda item: item["id"])


def _boundary_rule_positions(
    rule: BoundaryTypesRule,
    ordered_symbols: Sequence[RawRecord],
    contract: ArchitectureContract,
    exports_by_module: dict[str, frozenset[str]],
    imports: Sequence[RawRecord],
    imports_by_binding: BindingIndex,
    classes_by_location: BindingIndex,
    uncertain_reexport_origins: UncertainReexportOrigins,
    source_modules: frozenset[str] | None,
    *,
    type_shapes: TypeShapeIndex,
) -> tuple[int, list[dict[str, object]], list[RawRecord]]:
    undecidable_positions: list[dict[str, object]] = []
    positions_out: list[RawRecord] = []
    occurrences: dict[tuple[str, str], int] = {}
    reexports = _reexport_index(imports)
    property_chains = _property_chains(ordered_symbols)
    methods_by_parent: dict[str, list[RawRecord]] = defaultdict(list)
    for item in ordered_symbols:
        parent = item["data"]["parent"]
        if parse_source_symbol_kind(item["kind"]) is SourceSymbolKind.METHOD and isinstance(parent, str):
            methods_by_parent[parent] = [*methods_by_parent[parent], item]
    symbols_by_id = {item["id"]: item for item in ordered_symbols}
    seen = 0
    for item in ordered_symbols:
        found = _facade_positions(
            item,
            rule,
            contract,
            exports_by_module,
            imports,
            uncertain_reexport_origins,
            reexports,
            property_chains,
        )
        if found is None:
            continue
        module, qualified_name, positions, resolution_module, ambiguous_facade, _ = found
        if source_modules is not None and module not in source_modules:
            continue
        callable_key = (module, qualified_name)
        occurrence = occurrences.get(callable_key, 0)
        occurrences[callable_key] = occurrence + 1
        data = item["data"]
        kind = parse_source_symbol_kind(item["kind"])
        inherited_positions: list[tuple[str, str, str, str, _Position]] = []
        if kind is SourceSymbolKind.CLASS:
            _, inherited_positions, complete = _inherited_facade_types(
                item,
                ordered_symbols,
                methods_by_parent,
                contract,
                exports_by_module,
                imports_by_binding,
                classes_by_location,
                incoming_imports=imports,
                type_shapes=type_shapes,
            )
            if complete and not ambiguous_facade:
                positions = []
            if ambiguous_facade:
                inherited_positions = _declared_chain_positions(
                    item, classes_by_location, methods_by_parent
                )
        details = _undecidable_declared_positions(
            module,
            qualified_name,
            positions,
            resolution_module,
            ambiguous_facade,
            contract,
            exports_by_module,
            imports_by_binding,
            classes_by_location,
            occurrence,
            data["annotation_binding_uncertainties"]
            if "annotation_binding_uncertainties" in data
            else {},
            data["annotation_scope"] if "annotation_scope" in data else None,
            type_shapes=type_shapes,
        )
        seen += len(positions)
        undecidable_positions.extend(detail for detail, _context in details)
        positions_out.extend(
            _boundary_type_position_record(rule, item, detail, unknown_context=context)
            for detail, context in details
        )
        if kind is SourceSymbolKind.CLASS:
            seen += len(inherited_positions)
            facade_qualname = qualified_name[: -len(".__inherited_methods__")]
            for inherited_index, (
                method_name,
                method_id,
                position,
                annotation,
                verdict,
            ) in enumerate(inherited_positions):
                if verdict.undecidable is None:
                    continue
                detail: dict[str, object] = {
                    "module": module,
                    "qualified_name": f"{facade_qualname}.{method_name}",
                    "position": position,
                    "annotation": annotation,
                    "reason": verdict.undecidable,
                    "occurrence": occurrence * 1000 + inherited_index,
                }
                if not complete or ambiguous_facade:
                    detail["signature_scope"] = "declared"
                origin = _surface_position_origin(item, method_id, symbols_by_id)
                method_data = origin["data"]
                uncertainties = (
                    method_data["annotation_binding_uncertainties"]
                    if "annotation_binding_uncertainties" in method_data
                    else {}
                )
                if position in uncertainties:
                    detail["annotation_bindings"] = uncertainties[position]
                    detail["annotation_scope"] = method_data["annotation_scope"]
                undecidable_positions.append(detail)
                positions_out.append(
                    _boundary_type_position_record(
                        rule,
                        item,
                        detail,
                        origin_symbol=origin,
                        unknown_context=verdict.unknown_context,
                    )
                )
        selected = _selected_facade(module, qualified_name, resolution_module)
        declared = _declared_facade_positions(
            item,
            contract,
            exports_by_module,
            imports,
            uncertain_reexport_origins,
            reexports,
            property_chains,
        )
        if declared is None:
            continue
        uncertain = _uncertain_facade_position_records(
            item, rule, declared[4], declared[2], selected, occurrences
        )
        for detail, record in uncertain:
            seen += 1
            undecidable_positions.append(detail)
            positions_out.append(record)
    return seen, undecidable_positions, positions_out


def _undecidable_declared_positions(
    module: str,
    qualified_name: str,
    positions: Sequence[tuple[str, str]],
    resolution_module: str,
    ambiguous_facade: bool,
    contract: ArchitectureContract,
    exports_by_module: dict[str, frozenset[str]],
    imports_by_binding: BindingIndex,
    classes_by_location: BindingIndex,
    occurrence: int,
    binding_uncertainties: dict[str, list[str]] | None = None,
    annotation_scope: str | None = None,
    *,
    type_shapes: TypeShapeIndex,
) -> list[tuple[dict[str, object], str | None]]:
    if binding_uncertainties is None:
        binding_uncertainties = {}
    details: list[tuple[dict[str, object], str | None]] = []
    for position, annotation in positions:
        verdict = (
            _Position(undecidable=_Cause.INHERITED_SURFACE)
            if position == "inherited methods"
            else _Position(undecidable=_Cause.AMBIGUOUS_FACADE)
            if ambiguous_facade
            else _boundary_type_verdict(
                annotation,
                resolution_module,
                contract,
                exports_by_module,
                imports_by_binding,
                classes_by_location,
                uncertain_bindings=binding_uncertainties.get(position, ()),
                type_shapes=type_shapes,
            )
        )
        reason = verdict.undecidable
        if reason is None:
            continue
        detail: dict[str, object] = {
            "module": module,
            "qualified_name": qualified_name,
            "position": position,
            "annotation": annotation,
            "reason": reason,
            "occurrence": occurrence,
        }
        if bindings := binding_uncertainties.get(position):
            detail["annotation_bindings"] = bindings
            detail["annotation_scope"] = annotation_scope
        if verdict.path:
            detail["path"] = ".".join((position, *verdict.path))
            detail["nested_annotation"] = verdict.nested_annotation or annotation
        details.append((detail, verdict.unknown_context))
    return details


def _selected_facade(
    module: str, qualified_name: str, resolution_module: str
) -> tuple[str, str, str]:
    prefix = f"{module}."
    selected_name = qualified_name.removeprefix(prefix)
    return module, selected_name, resolution_module


def _public_api_symbol(
    symbols: Sequence[RawRecord],
    module: str,
    name: str,
    origins: tuple[tuple[str, str], ...],
    ambiguous: bool,
    *,
    type_shapes: TypeShapeIndex,
) -> RawRecord | None:
    """The one top-level symbol a `module:name` public_api entry resolves to, if any."""
    if ambiguous:
        return None
    locations = ((module, name), *origins)
    selected: RawRecord | None = None
    class_alias = False
    for location in locations:
        candidates = [
            item
            for item in symbols
            if item["data"].get("module") == location[0]
            and item["data"].get("name") == location[1]
            and item["data"].get("parent") is None
        ]
        if len(candidates) > 1:
            return None
        if candidates:
            candidate = candidates[0]
            if parse_source_symbol_kind(candidate["kind"]) is SourceSymbolKind.TYPE_ALIAS:
                alias = type_shapes.get(candidate["data"]["alias"])
                if not isinstance(alias, TypeName):
                    return None
                class_alias = True
                continue
            if selected is not None and selected is not candidate:
                return None
            selected = candidate
    if class_alias and (selected is None or parse_source_symbol_kind(selected["kind"]) is not SourceSymbolKind.CLASS):
        return None
    return selected


def _public_api_positions(
    symbol: RawRecord,
    symbols: Sequence[RawRecord],
    contract: ArchitectureContract,
    exports: dict[str, frozenset[str]],
    imports: BindingIndex,
    classes: BindingIndex,
    *,
    type_shapes: TypeShapeIndex,
) -> tuple[list[_Position], list[tuple[RawRecord, str]]]:
    """A public function's signature or a class's declared and inherited fields."""
    data = symbol["data"]
    kind = parse_source_symbol_kind(symbol["kind"])
    if kind is SourceSymbolKind.CLASS:
        return _public_api_field_positions(
            symbol, symbols, contract, exports, imports, classes, type_shapes=type_shapes
        )
    if kind is not SourceSymbolKind.FUNCTION:
        return [], []
    annotations = [
        parameter["annotation"] for parameter in data["parameters"] if parameter["annotation"]
    ]
    if data["returns"]:
        annotations.append(data["returns"])
    return [
        _boundary_type_verdict(
            annotation, data["module"], contract, exports, imports, classes, type_shapes=type_shapes
        )
        for annotation in annotations
    ], []


def _public_api_field_positions(
    symbol: RawRecord,
    symbols: Sequence[RawRecord],
    contract: ArchitectureContract,
    exports: dict[str, frozenset[str]],
    imports: BindingIndex,
    classes: BindingIndex,
    *,
    type_shapes: TypeShapeIndex,
    overrides: frozenset[str] = frozenset(),
    visited: frozenset[tuple[str, str]] = frozenset(),
) -> tuple[list[_Position], list[tuple[RawRecord, str]]]:
    """Walk one proven base chain; sorted base records cannot prove multiple-base precedence."""
    data = symbol["data"]
    module = data["module"]
    origin = (module, data["name"])
    if origin in visited:
        return [], [(symbol, "inheritance_cycle")]
    fields = [field for field in data["fields"] if field["name"] not in overrides]
    positions = [
        _boundary_type_verdict(
            field["annotation"],
            module,
            contract,
            exports,
            imports,
            classes,
            type_shapes=type_shapes,
        )
        for field in fields
        if field["annotation"]
    ]
    limits: list[tuple[RawRecord, str]] = [
        (symbol, f"inherited_field:{reason}")
        for reason in sorted(
            {
                position.undecidable
                for position in positions
                if visited
                and position.undecidable is not None
                and position.undecidable != _Cause.EXTERNAL
            }
        )
    ]
    if data["class_body_control_flow"]:
        return positions, [(symbol, "class_body_control_flow")]
    base, reason = _public_api_base(
        symbol, symbols, contract, exports, imports, classes, type_shapes=type_shapes
    )
    if reason is not None:
        limits.append((symbol, reason))
    if base is None:
        return positions, limits
    base_symbol, base_imports, base_classes = base
    inherited, inherited_limits = _public_api_field_positions(
        base_symbol,
        symbols,
        contract,
        exports,
        base_imports,
        base_classes,
        overrides=overrides
        | frozenset(data["class_members"])
        | frozenset(field["name"] for field in data["fields"]),
        visited=visited | {origin},
        type_shapes=type_shapes,
    )
    return [*positions, *inherited], [*limits, *inherited_limits]


def _member_origin_static(origin: str, imports: Sequence[RawRecord]) -> bool:
    module, _, _ = origin.rpartition(".")
    for item in imports:
        imported = item["data"]
        if imported.get("source_member_binding_static") is True:
            continue
        if imported.get("origin_definition") == origin or origin in imported.get(
            "reexport_candidates", ()
        ):
            return False
        if imported["symbol"] is None and in_scope(module, imported["target_module"]):
            return False
    return True


def _base_route_member_static(
    root: TypeShape, module: str, imports: BindingIndex, classes: BindingIndex
) -> bool:
    name = (
        root.name
        if isinstance(root, TypeName)
        else root.owner.name
        if isinstance(root, TypeMember) and isinstance(root.owner, TypeName)
        else None
    )
    if name is None:
        return False
    binding = imports.get((module, name)) or classes.get((module, name))
    if not isinstance(binding, dict):
        return True
    if (
        binding.get("source_member_binding_static") is not True
        or binding.get("origin_member_binding_static") is False
    ):
        return False
    for alias in binding.get("reexport_chain", ()):
        alias_module, _, alias_name = alias.rpartition(".")
        imported = imports.get((alias_module, alias_name))
        if isinstance(imported, dict) and imported.get("source_member_binding_static") is not True:
            return False
    return True


def _public_api_base(
    symbol: RawRecord,
    symbols: Sequence[RawRecord],
    contract: ArchitectureContract,
    exports: dict[str, frozenset[str]],
    imports: BindingIndex,
    classes: BindingIndex,
    *,
    type_shapes: TypeShapeIndex,
    member_surface: bool = False,
) -> tuple[tuple[RawRecord, BindingIndex, BindingIndex] | None, str | None]:
    data = symbol["data"]
    module = data["module"]
    bases: list[tuple[str, TypeShape, RawRecord]] = []
    for annotation in data["bases"]:
        expression = type_shapes.get(annotation)
        if expression is None or (
            isinstance(expression, UnresolvedType) and not expression.valid_syntax
        ):
            return None, "unresolved_base"
        root = expression.head if isinstance(expression, TypeApplication) else expression
        base_name = root.text
        binding = imports.get((module, base_name)) or classes.get((module, base_name))
        if member_surface and not _base_route_member_static(root, module, imports, classes):
            return None, "unresolved_base"
        if (
            isinstance(root, TypeName)
            and isinstance(binding, dict)
            and binding.get("source_binding_unique") is False
        ):
            return None, "unresolved_base"
        verdict = _boundary_type_verdict(
            base_name,
            module,
            contract,
            exports,
            imports,
            classes,
            enter_fields=False,
            type_shapes=type_shapes,
        )
        if any(
            isinstance(origin_binding := classes.get(origin), dict)
            and origin_binding.get("source_binding_unique") is False
            for origin in verdict.named_origins
        ):
            return None, "unresolved_base"
        if (
            len(verdict.named_origins) == 1
            and ".".join(verdict.named_origins[0]) in _FRAMEWORK_BASES
        ):
            if ".".join(verdict.named_origins[0]) not in data["base_roots"]:
                return None, "unresolved_base"
            continue
        if base_name == "object" and "object" in data["base_roots"]:
            continue
        if not verdict.named_origins:
            return None, verdict.undecidable or "unresolved_base"
        base = _public_api_symbol(
            symbols,
            module,
            base_name,
            verdict.named_origins,
            verdict.undecidable == _Cause.AMBIGUOUS_BINDING,
            type_shapes=type_shapes,
        )
        if base is None or parse_source_symbol_kind(base["kind"]) is not SourceSymbolKind.CLASS:
            return None, f"unresolved_base:{base_name}"
        bases.append((base_name, expression, base))
    if len(bases) > 1:
        return None, "multiple_inheritance"
    if not bases:
        return None, None
    base_name, expression, base = bases[0]
    bindings = (imports, classes)
    if isinstance(expression, TypeApplication):
        substituted = _public_api_generic_bindings(
            base, expression, module, contract, exports, imports, classes, type_shapes=type_shapes
        )
        if substituted is None:
            return None, f"unresolved_generic_base:{base_name}"
        bindings = substituted
    return (base, *bindings), None


def _public_api_generic_bindings(
    base: RawRecord,
    expression: TypeApplication,
    module: str,
    contract: ArchitectureContract,
    exports: dict[str, frozenset[str]],
    imports: BindingIndex,
    classes: BindingIndex,
    *,
    type_shapes: TypeShapeIndex,
) -> tuple[BindingIndex, BindingIndex] | None:
    arguments = expression.arguments
    base_data = base["data"]
    parameters = base_data["generic_parameters"] if "generic_parameters" in base_data else ()
    if (
        len(parameters) != len(arguments)
        or not parameters
        or set(parameters) & set(base["data"]["class_members"])
    ):
        return None
    substitutions: list[tuple[str, tuple[str, str]]] = []
    for parameter, argument in zip(parameters, arguments, strict=True):
        if not isinstance(argument, TypeName):
            return None
        verdict = _boundary_type_verdict(
            argument.name,
            module,
            contract,
            exports,
            imports,
            classes,
            enter_fields=False,
            type_shapes=type_shapes,
        )
        if len(verdict.named_origins) == 1:
            resolved = verdict.named_origins[0]
            argument_symbol = classes.get(resolved)
            if (
                not isinstance(argument_symbol, dict)
                or parse_source_symbol_kind(argument_symbol.get("symbol_category")) is not SourceSymbolKind.CLASS
            ):
                return None
        elif (
            verdict.undecidable is None
            and argument.name in _BUILTIN_NAMES
            and (module, argument.name) not in imports
            and (module, argument.name) not in classes
        ):
            resolved = ("builtins", argument.name)
        else:
            return None
        substitutions.append((parameter, resolved))
    return _substituted_type_bindings(base["data"]["module"], substitutions, imports, classes)


def public_api_exposed_types(
    public_api: Sequence[str],
    symbols: Sequence[RawRecord],
    imports: Sequence[RawRecord],
    modules: Sequence[RawRecord],
    contract: ArchitectureContract,
    *,
    type_shapes: TypeShapeIndex,
    unknowns: list[RawRecord],
) -> dict[str, list[str]]:
    """Map public entries to exposed types not already declared, by origin (AD-70).

    Reuse boundary_types' resolution so facade aliases and nested types have one meaning.
    Unscanned external types are outside this package's publication promise. Validation
    consumes this result without resolving annotations again (AD-4).
    """
    if not public_api:
        return {}
    exports = exports_by_module(modules)
    imports_by_binding, classes_by_location = boundary_type_indexes(
        symbols, imports, contract, exports
    )
    scanned_modules = frozenset(item["data"]["qualified_name"] for item in modules)
    declared_positions = {
        entry: _boundary_type_verdict(
            declared_name,
            declared_module,
            contract,
            exports,
            imports_by_binding,
            classes_by_location,
            enter_fields=False,
            type_shapes=type_shapes,
        )
        for entry in public_api
        for declared_module, _, declared_name in [entry.partition(":")]
    }
    declared_origins = {
        pair for position in declared_positions.values() for pair in position.named_origins
    }
    types: dict[str, list[str]] = {}
    for entry in public_api:
        module, _, name = entry.partition(":")
        position = declared_positions[entry]
        ambiguous = (
            position.undecidable == _Cause.AMBIGUOUS_BINDING and not position.named_origins
        ) or _binding_is_ambiguous((module, name), imports_by_binding, classes_by_location)
        symbol = _public_api_symbol(
            symbols, module, name, position.named_origins, ambiguous, type_shapes=type_shapes
        )
        if symbol is None:
            locations = {(module, name), *position.resolved}
            candidates = [
                item
                for item in symbols
                if (item["data"]["module"], item["data"]["name"]) in locations
            ] + [
                item
                for item in imports
                if (item["data"]["source_module"], item["data"]["binding"]) == (module, name)
            ]
            kinds = {parse_source_symbol_kind(item["kind"]) for item in candidates}
            if ambiguous or (
                SourceSymbolKind.TYPE_ALIAS in kinds
                and (position.undecidable is not None or SourceSymbolKind.CLASS in kinds)
            ):
                reason = position.undecidable or "unproven_class_alias"
                unknowns.append(_public_api_limit(entry, reason, candidates))
            continue
        resolved: set[str] = set()
        positions, limits = _public_api_positions(
            symbol,
            symbols,
            contract,
            exports,
            imports_by_binding,
            classes_by_location,
            type_shapes=type_shapes,
        )
        unknowns.extend(_public_api_limit(entry, reason, [item]) for item, reason in limits)
        for verdict in positions:
            resolved.update(
                f"{origin_module}:{origin_name}"
                for origin_module, origin_name in verdict.resolved
                if origin_module in scanned_modules
                and (origin_module, origin_name) not in declared_origins
            )
        types[entry] = sorted(resolved)
    return types


def _public_api_limit(entry: str, reason: str, records: Sequence[RawRecord]) -> RawRecord:
    return classified(
        item_id=stable_id("UNKNOWN-API-SURFACE", entry, reason, *(item["id"] for item in records)),
        evidence_class=EvidenceClass.UNKNOWN,
        area="api_surface",
        kind="api_surface_limit",
        title=f"Public API fields cannot be fully resolved: {reason}",
        subjects=[entry],
        evidence_ids=sorted({evidence for item in records for evidence in item["evidence_ids"]}),
        fact_ids=[item["id"] for item in records],
        data={"module": entry.partition(":")[0], "name": entry.partition(":")[2], "reason": reason},
    )


def _boundary_rule_results(
    imports: Sequence[RawRecord],
    symbols: Sequence[RawRecord],
    contract: ArchitectureContract,
    components: tuple[ComponentOwnership, ...],
    exports_by_module: dict[str, frozenset[str]],
    uncertain_reexport_origins: UncertainReexportOrigins,
    source_modules: frozenset[str] | None,
    ancestor_contracts: Sequence[ArchitectureContract],
    profile: Profile,
    assessment_facts: list[RawRecord] | None,
    scope: str,
    *,
    type_shapes: TypeShapeIndex,
) -> tuple[
    list[tuple[ForbiddenDependencyRule, RawRecord]],
    frozenset[str],
    list[RawRecord],
    list[RawRecord],
]:
    matches = list(
        _forbidden_dependency_matches(imports, contract.rules, components, source_modules)
    )
    violations, allowances = _boundary_types_violations(
        symbols,
        imports,
        contract,
        exports_by_module,
        uncertain_reexport_origins,
        source_modules,
        ancestor_contracts,
        assessment_facts=assessment_facts,
        assessment_scope=scope,
        unsupported_rules=profile.unsupported_rules,
        type_shapes=type_shapes,
    )
    return matches, frozenset(item["id"] for _, item in matches), violations, allowances
