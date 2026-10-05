# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Evaluate boundary types and public API signatures."""

from __future__ import annotations

import builtins
from collections import defaultdict
from collections.abc import Iterator, Sequence
from typing import Final, NamedTuple, TypeAlias

from archkeel.ir.facts_codec import RawData as RecordData
from archkeel.ir.facts_codec import RawEvidence, RawRecord, classified
from archkeel.ir.model import (
    ArchitectureContract,
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


_EXEMPT_CLASS_KINDS: Final = frozenset({"enum", "pydantic_model"})


# Issue #9 names a builtin as an acceptable boundary type, and a builtin needs no import and
# defines no symbol of its own, so `resolve_named_type` returns nothing for one. The set comes
# from the running interpreter rather than a list kept here, the way `resolve.py` and `calls.py`
# already answer the same question, so one repository holds one answer to what a builtin is.
_BUILTIN_NAMES: Final = frozenset(dir(builtins))


_BROAD_BOUNDARY_REASON: Final = "instead of a typed model"


# Why a position stayed undecided, in the order the limit record reports them (AD-67).
# `ambiguous_binding` (AD-74) sits next to `unresolved_name`: both are bare names that failed
# to resolve, but one failed because nothing defines it and the other because two records do --
# a reader who sees only the count needs the two kept apart to tell "unreadable annotation"
# from "this name is bound twice".
_UNDECIDABLE_KINDS: Final = (
    "missing_annotation",
    "inherited_surface",
    "forward_reference",
    "dotted_name",
    "generic",
    "union",
    "ambiguous_binding",
    "ambiguous_facade",
    "unresolved_name",
    "external_type",
    "nested_type",
    "other",
)


class _Position(NamedTuple):
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
    undecidable: str | None = None
    resolved: tuple[tuple[str, str], ...] = ()
    named_origins: tuple[tuple[str, str], ...] = ()
    path: tuple[str, ...] = ()
    nested_annotation: str | None = None
    violations: tuple[tuple[str, tuple[str, ...], str | None, int], ...] = ()
    mapping_occurrences: tuple[_MappingOccurrence, ...] = ()
    field_positions: tuple[_FieldPosition, ...] = ()
    field_declarations: tuple[tuple[str, ...], ...] = ()


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
        return _Position(undecidable="other")
    if _binding_is_ambiguous(key, imports_by_binding, classes_by_location):
        return _Position(undecidable="ambiguous_binding")
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
                return _Position(undecidable="dotted_name")
            origin_module = f"{target}.{symbol}" if symbol else target
            origin_name = member
    if (origin_module, origin_name) not in origins:
        return False
    imported = imports_by_binding.get(key)
    if isinstance(imported, dict) and imported.get("source_binding_unique") is False:
        return _Position(undecidable="ambiguous_binding")
    if (origin_module, origin_name) in classes_by_location:
        return _Position(undecidable="ambiguous_binding")
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
        return _Position(undecidable="generic")
    if any(
        isinstance(arg, TypeUnpack)
        or (isinstance(arg, TypeLiteral) and arg.kind is LiteralKind.ELLIPSIS)
        for arg in expression.arguments
    ):
        return _Position(undecidable="generic")
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


def _unresolvable_shape(annotation: str) -> str:
    """Name why an annotation that is not one bare identifier cannot be decided (AD-67)."""
    head = annotation.split("[", 1)[0]
    if "." in head:
        return "dotted_name"
    if "[" in annotation:
        return "generic"
    if "|" in annotation:
        return "union"
    return "other"


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
        # A nested class is never what a module-level annotation's bare name resolves to.
        if (item["kind"] == "class" and data.get("parent") is None)
        or item["kind"] in {"type_alias", "static_constant", "dynamic_binding"}
    )
    for item in symbols:
        data = item["data"]
        key = (data["module"], data["name"])
        if item["kind"] == "function" and (
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
        return _Position(undecidable="missing_annotation")
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
        return wrapped
    if _is_broad_boundary_type(annotation, module, imports_by_binding, classes_by_location):
        return _Position(violation=_BROAD_BOUNDARY_REASON)
    bare_type = _bare_type_verdict(
        annotation, module, imports_by_binding, classes_by_location, type_shapes=type_shapes
    )
    if bare_type is not None:
        return bare_type
    if annotation.startswith(("'", '"')):
        return _Position(undecidable="forward_reference")
    if not annotation.isidentifier():
        return _annotation_shape_verdict(
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
    return _named_type_verdict(
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
        if symbol.get("class_kind") == "enum":
            if enum_origin is not None:
                return None
            enum_origin = resolved
            continue
        if symbol.get("record_kind") != "type_alias":
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
    if not isinstance(symbol, dict) or symbol.get("record_kind") != "type_alias":
        return None
    reached: tuple[tuple[str, str], ...] = (resolved,)
    alias = symbol.get("alias")
    if resolved in aliases_seen or not isinstance(alias, str) or alias == annotation:
        return _Position(undecidable="other", resolved=reached, named_origins=reached)
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
    return _Position(
        violation=expanded.violation,
        undecidable=expanded.undecidable,
        resolved=tuple(sorted({*reached, *expanded.resolved})),
        named_origins=tuple(sorted({*reached, *expanded.named_origins})),
        path=expanded.path,
        nested_annotation=expanded.nested_annotation,
        violations=expanded.violations,
        field_positions=expanded.field_positions,
        field_declarations=expanded.field_declarations,
        mapping_occurrences=tuple(
            _MappingOccurrence(
                occurrence.annotation,
                occurrence.depth,
                occurrence.path,
                alias_free=False,
                opaque_value_depth=occurrence.opaque_value_depth,
            )
            for occurrence in expanded.mapping_occurrences
        ),
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
        return _Position(undecidable="other")
    return _Position(undecidable="unresolved_name")


def _is_static_literal_constant(symbol: RecordData | _AmbiguousBinding | None) -> bool:
    # A constant recorded without its value (AD-102) proves nothing; `.get` alone would read
    # the missing value as a `None` literal.
    return (
        isinstance(symbol, dict)
        and symbol.get("record_kind") == "static_constant"
        and "constant" in symbol
        and isinstance(symbol["constant"], (str, int, bool, type(None)))
    )


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
        return _Position(undecidable="ambiguous_binding")
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
            else _Position(undecidable="other")
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
        return alias
    if isinstance(origin_symbol, dict) and origin_symbol.get("record_kind") == "static_constant":
        return _Position(undecidable="other", resolved=reached, named_origins=reached)
    if isinstance(origin_symbol, dict) and origin_symbol.get("record_kind") == "dynamic_binding":
        return _Position(undecidable="other", resolved=reached, named_origins=reached)
    # `resolve_named_type` ruled out an ambiguous location; the surviving class record carries
    # `class_kind` (AD-30).
    class_kind = origin_symbol["class_kind"] if isinstance(origin_symbol, dict) else None
    if class_kind == "enum":
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
    class_kind: str | None,
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
            return _Position(undecidable="other", resolved=reached, named_origins=(resolved,))
        if claims:
            origin_component = claims[0]
            break
    if origin_component is None:
        return _Position(undecidable="external_type", resolved=reached, named_origins=(resolved,))
    owner_facade_proof = imports_by_binding.owner_facade_type_states.get(
        (origin_component.id, origin_module, origin_name)
    )
    directly_public = facade_covers(origin_module, origin_name, origin_component, exports_by_module)
    if not directly_public and (
        owner_facade_proof is False
        or (owner_facade_proof is True and not isinstance(origin_symbol, dict))
    ):
        return _Position(undecidable="unresolved_name", resolved=reached, named_origins=(resolved,))
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
            resolved=reached,
            named_origins=(resolved,),
            path=fields.path,
            nested_annotation=fields.nested_annotation,
            violations=fields.violations,
            mapping_occurrences=fields.mapping_occurrences,
            field_positions=fields.field_positions,
            field_declarations=fields.field_declarations,
        )
    if class_kind in _EXEMPT_CLASS_KINDS:
        return _Position(resolved=reached, named_origins=(resolved,))
    return _Position(
        violation=f"which {origin_component.label} does not declare",
        resolved=reached,
        named_origins=(resolved,),
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
    """Resolve standard unions and collections recursively; leave other shapes UNKNOWN."""
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
        return _combined_annotation_verdict(
            union,
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
    return _Position(
        violation=_BROAD_BOUNDARY_REASON,
        undecidable=contents.undecidable,
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
        mapping_occurrences=(
            _MappingOccurrence(
                annotation,
                0,
                opaque_value_depth=_opaque_mapping_value_depth(
                    parameters[1], module, imports_by_binding, classes_by_location, type_shapes
                ),
            ),
            *(
                _MappingOccurrence(
                    occurrence.annotation,
                    occurrence.depth + 1,
                    occurrence.path,
                    occurrence.alias_free,
                    occurrence.opaque_value_depth,
                )
                for occurrence in contents.mapping_occurrences
            ),
        ),
    )


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


def _field_position_verdict(
    field_name: str, field_annotation: str, verdict: _Position
) -> _Position:
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
    mapping_occurrences = tuple(
        _MappingOccurrence(
            occurrence.annotation,
            occurrence.depth,
            (field_name, *occurrence.path),
            occurrence.alias_free,
            occurrence.opaque_value_depth,
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
                all(
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
        resolved=verdict.resolved,
        path=(field_name, *verdict.path),
        nested_annotation=verdict.nested_annotation or field_annotation,
        violations=tuple(violations),
        mapping_occurrences=mapping_occurrences,
        field_positions=tuple(field_positions),
        # One field can produce several findings; clean and UNKNOWN fields still count.
        field_declarations=((field_name,),)
        + tuple((field_name, *path) for path in verdict.field_declarations),
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
        mapping_occurrences=tuple(
            _MappingOccurrence(
                occurrence.annotation,
                occurrence.depth + 1,
                occurrence.path,
                occurrence.alias_free,
                occurrence.opaque_value_depth,
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
        occurrence for _parameter, verdict in decided for occurrence in verdict.mapping_occurrences
    )
    field_positions = tuple(
        field for _parameter, verdict in decided for field in verdict.field_positions
    )
    field_declarations = tuple(
        path for _parameter, verdict in decided for path in verdict.field_declarations
    )
    for _parameter, verdict in decided:
        if verdict.undecidable is not None:
            return _Position(
                violation=violations[0][0] if violations else None,
                undecidable=verdict.undecidable,
                resolved=reached,
                path=verdict.path,
                nested_annotation=verdict.nested_annotation,
                violations=violations,
                mapping_occurrences=mapping_occurrences,
                field_positions=field_positions,
                field_declarations=field_declarations,
            )
    if violations:
        reason, path, nested_annotation, _ = violations[0]
        return _Position(
            violation=reason,
            resolved=reached,
            path=path,
            nested_annotation=nested_annotation,
            violations=violations,
            mapping_occurrences=mapping_occurrences,
            field_positions=field_positions,
            field_declarations=field_declarations,
        )
    return _Position(
        resolved=reached,
        mapping_occurrences=mapping_occurrences,
        field_positions=field_positions,
        field_declarations=field_declarations,
    )


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
        if item["kind"] != "method" or not _is_public_method_name(item["data"]["name"]):
            continue
        data = item["data"]
        name = data["qualified_name"]
        group: list[RawRecord] = grouped[name]
        group.append(item)
        if "property_binding" in data and data["property_binding"]["operation"] != "create":
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
) -> DeclaredFacade | None:
    """The (module, qualified name, annotated positions) for one declared facade callable.

    Methods count only when their declaring class is proven exported. A class's inherited
    surface starts as a placeholder; the shared local-chain proof may discharge it.
    No rule is consulted: facade membership is a fact about the contract and scan.
    """
    data = item["data"]
    if item["kind"] == "class" and data.get("symbol_category") == "class":
        return _declared_facade_inherited_positions(
            data,
            contract,
            exports_by_module,
            imports,
            uncertain_reexport_origins,
            reexports,
            property_chains,
        )
    if data.get("qualified_name") in property_chains and not (
        data.get("source_final_method_binding") is True
        and data.get("signature_decorators_proven") is True
    ):
        return None
    if data.get("overloaded") is True and data.get("overload_signature") is not True:
        return None
    method = item["kind"] == "method" and data.get("symbol_category") == "method"
    if method:
        return _declared_facade_method_positions(
            data, contract, exports_by_module, imports, uncertain_reexport_origins, reexports
        )
    if item["kind"] != "function" or data.get("symbol_category") != "function":
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
) -> DeclaredFacade | None:
    base_roots = data["base_roots"] if "base_roots" in data else data["bases"]
    if not any(
        f"{data['qualified_name']}.{name}" in property_chains for name in data["class_members"]
    ) and not any(base not in _FRAMEWORK_BASES for base in base_roots):
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
        data["method_kind"] != "static"
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
        item["data"]["qualified_name"]: item for item in symbols if item["kind"] == "class"
    }
    methods_by_parent: dict[str, list[RawRecord]] = defaultdict(list)
    for item in symbols:
        parent = item["data"]["parent"] if "parent" in item["data"] else None
        if item["kind"] == "method" and isinstance(parent, str):
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
        if found is not None and item["kind"] == "class":
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
            if item["kind"] == "class":
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
        for method in sorted(group, key=lambda item: item["data"]["property_binding"]["line"]):
            method_data = method["data"]
            binding = method_data["property_binding"]
            bound = _BoundMethod(method, data, imports, classes)
            if binding["operation"] == "create":
                if method_data.get("signature_decorators_proven") is not True:
                    return None
                selected = _PropertyMethods(bound)
            else:
                origin = (
                    inherited.get(name)
                    if binding["source"] == "base"
                    else local.get(binding["source_line"])
                )
                if not isinstance(origin, _PropertyMethods):
                    return None
                selected = (
                    _PropertyMethods(bound, origin.setter)
                    if binding["operation"] == "getter"
                    else _PropertyMethods(origin.getter, bound)
                )
            local[binding["line"]] = selected
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
    if (
        qualified_name in visited
        or data["class_body_control_flow"]
        or data.get("class_header_static") is not True
        or data.get("source_binding_unique") is not True
        or data.get("source_member_binding_static") is not True
        or not _member_origin_static(qualified_name, incoming_imports)
    ):
        return None
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
        or source_owner.get("symbol_category") != "class"
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
                _Position(undecidable="inherited_surface"),
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
                symbol.get("symbol_category") == "class"
                or symbol.get("record_kind") == "type_alias"
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
    if base_symbol is None or base_symbol["kind"] != "class":
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
            or argument_symbol.get("symbol_category") != "class"
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
                    symbol.get("symbol_category") == "class"
                    or symbol.get("record_kind") == "type_alias"
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
                symbol.get("symbol_category") == "class"
                or symbol.get("record_kind") == "type_alias"
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


def _boundary_type_allowance_fact(
    rule: BoundaryTypesRule,
    facade_module: str,
    record: RawRecord,
    root_broad_count: int,
    verdict: _Position,
) -> RawRecord | None:
    data = record["data"]
    path = data["path"] if "path" in data else None
    for allowance in rule.allowed_positions:
        expected_path = (
            f"{allowance.position}.{allowance.field_path}" if allowance.field_path else None
        )
        annotation = data["annotation"]
        direct_match = (
            not allowance.field_path
            and isinstance(annotation, str)
            and (
                (data["reason"] == _BROAD_BOUNDARY_REASON and "nested_annotation" in data)
                or data["reason"] == _OPAQUE_NATIVE_REASONS.get(annotation)
            )
            and data.get("container_depth", 0) == 0
            and root_broad_count == 1
        )
        if (
            data["qualified_name"] != allowance.qualified_name
            or data["position"] != allowance.position
            or path != expected_path
            or (not allowance.field_path and annotation != allowance.annotation)
            or allowance.annotation == "dict"
        ):
            continue
        if allowance.container_depth is not None:
            if not _opaque_mapping_value_allowance_matches(allowance, data, verdict):
                continue
            is_contained = True
        elif allowance.field_path:
            if not _nested_field_allowance_matches(allowance, data, verdict):
                continue
            is_contained = False
        else:
            if not direct_match and not _contained_mapping_allowance_matches(
                allowance, data, verdict.mapping_occurrences
            ):
                continue
            is_contained = not direct_match
        return _boundary_type_allowance_fact_record(
            rule, facade_module, record, allowance, is_contained
        )
    return None


def _nested_field_allowance_matches(
    allowance: BoundaryTypeAllowance, data: RecordData, verdict: _Position
) -> bool:
    if sum(".".join(path) == allowance.field_path for path in verdict.field_declarations) != 1:
        return False
    finding = (data["reason"], data.get("nested_annotation"), data.get("container_depth", 0))
    fields = tuple(
        field
        for field in verdict.field_positions
        if ".".join(field.finding[1]) == allowance.field_path
        and (field.finding[0], field.finding[2], field.finding[3]) == finding
    )
    if len(fields) != 1 or fields[0].annotation != allowance.annotation:
        return False
    if data.get("nested_annotation") == allowance.annotation:
        return True
    path = fields[0].finding[1]
    mappings = tuple(
        occurrence for occurrence in verdict.mapping_occurrences if occurrence.path == path
    )
    if not mappings or not fields[0].alias_free:
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
    mappings = tuple(
        occurrence for occurrence in verdict.mapping_occurrences if not occurrence.path
    )
    return (
        len(mappings) == 1
        and mappings[0].alias_free
        and mappings[0].opaque_value_depth is not None
        and mappings[0].depth + mappings[0].opaque_value_depth == depth
        # Findings deduplicate; the selector must not accept two equal opaque occurrences.
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


def _boundary_type_allowance_fact_record(
    rule: BoundaryTypesRule,
    facade_module: str,
    record: RawRecord,
    allowance: BoundaryTypeAllowance,
    is_contained: bool,
) -> RawRecord:
    data = record["data"]
    opaque = allowance.container_depth is not None or (
        not allowance.field_path and allowance.annotation in _OPAQUE_NATIVE_REASONS
    )
    if allowance.container_depth is not None:
        allowance_scope = "opaque mapping value "
    elif is_contained:
        allowance_scope = "unique contained mapping "
    else:
        allowance_scope = "nested " if allowance.field_path else ""
    return classified(
        item_id=stable_id(
            "TYPE",
            rule.id,
            record["id"],
            allowance.qualified_name,
            allowance.position,
            allowance.field_path,
            allowance.annotation,
            *((str(allowance.container_depth),) if allowance.container_depth is not None else ()),
        ),
        evidence_class=EvidenceClass.FACT,
        area="type_architecture",
        kind="boundary_type_allowance",
        title=(
            f"{allowance.qualified_name} has an exact {allowance_scope}"
            "boundary type allowance"
            + (
                f" for {data['nested_annotation']} at container depth {data['container_depth']}"
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
        evidence_ids=record["evidence_ids"],
        rule_ids=[rule.id],
        fact_ids=record["fact_ids"],
        provenance=list(rule.provenance) if opaque else None,
        data={
            "qualified_name": allowance.qualified_name,
            "position": allowance.position,
            "field_path": allowance.field_path,
            "annotation": allowance.annotation,
            **(
                {"nested_annotation": data["nested_annotation"]}
                if allowance.field_path and data.get("nested_annotation") != allowance.annotation
                else {}
            ),
            **({"accepted_opacity": True} if opaque else {}),
            **(
                {
                    "nested_annotation": data["nested_annotation"],
                    "container_depth": data["container_depth"],
                }
                if is_contained
                else {}
            ),
        },
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
    rules = [rule for rule in contract.rules if isinstance(rule, BoundaryTypesRule)]
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
        if item["kind"] == "method" and isinstance(parent, str):
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
            inherited_positions: list[tuple[str, str, str, str, _Position]] = []
            if item["kind"] == "class":
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
                    _Position(undecidable="ambiguous_facade")
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
                    )
                    if fact is None:
                        violations.append(record)
                    else:
                        allowance_facts.append(fact)
            if item["kind"] == "class":
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
                        origin_symbol=symbols_by_id[method_id],
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
                if origin_symbol is not None
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
        if origin_symbol is not None
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
                "reason": "ambiguous_facade",
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
        if item["kind"] == "method" and isinstance(parent, str):
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
        inherited_positions: list[tuple[str, str, str, str, _Position]] = []
        if item["kind"] == "class":
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
        undecidable_positions.extend(details)
        positions_out.extend(
            _boundary_type_position_record(rule, item, detail) for detail in details
        )
        if item["kind"] == "class":
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
                method_data = symbols_by_id[method_id]["data"]
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
                        rule, item, detail, origin_symbol=symbols_by_id[method_id]
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
) -> list[dict[str, object]]:
    if binding_uncertainties is None:
        binding_uncertainties = {}
    details: list[dict[str, object]] = []
    for position, annotation in positions:
        verdict = (
            _Position(undecidable="inherited_surface")
            if position == "inherited methods"
            else _Position(undecidable="ambiguous_facade")
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
        details.append(detail)
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
            if candidate["kind"] == "type_alias":
                alias = type_shapes.get(candidate["data"]["alias"])
                if not isinstance(alias, TypeName):
                    return None
                class_alias = True
                continue
            if selected is not None and selected is not candidate:
                return None
            selected = candidate
    if class_alias and (selected is None or selected["kind"] != "class"):
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
    if symbol["kind"] == "class":
        return _public_api_field_positions(
            symbol, symbols, contract, exports, imports, classes, type_shapes=type_shapes
        )
    if symbol["kind"] != "function":
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
                and position.undecidable != "external_type"
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
            verdict.undecidable == "ambiguous_binding",
            type_shapes=type_shapes,
        )
        if base is None or base["kind"] != "class":
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
                or argument_symbol.get("symbol_category") != "class"
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
            position.undecidable == "ambiguous_binding" and not position.named_origins
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
            kinds = {item["kind"] for item in candidates}
            if ambiguous or (
                "type_alias" in kinds and (position.undecidable is not None or "class" in kinds)
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
