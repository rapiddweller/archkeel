# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Discover declared facade positions from source signatures and publication evidence."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence

from archkeel.ir.facts import (
    ContextManagerSignature,
    MethodKind,
    PropertyOperation,
    contextmanager_signature,
    parse_method_kind,
    property_binding,
)
from archkeel.ir.facts_codec import RawData as RecordData
from archkeel.ir.facts_codec import RawRecord, freeze_data
from archkeel.ir.model import ArchitectureContract, ContractComponent, facade_covers
from archkeel.ir.source_records import FRAMEWORK_BASES as _FRAMEWORK_BASES
from archkeel.ir.source_records import is_public_method_name as _is_public_method_name

from .rule_support import (
    DeclaredFacade,
    FacadeEntry,
    ReexportIndex,
    UncertainReexportOrigins,
    _reexport_index,
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
        if (
            "property_binding" in data
            and property_binding(data["property_binding"]).operation is not PropertyOperation.CREATE
        ):
            chains.add(name)
    return frozenset(
        chains | {name for name, group in grouped.items() if _ambiguous_method_group(group)}
    )


def _contextmanager_return(data: RecordData, position: str) -> ContextManagerSignature | None:
    if (
        position != "return"
        or data.get("symbol_category") != "function"
        or data.get("source_binding_unique") is not True
        or data.get("namespace_bound") is not True
        or "contextmanager_signature" not in data
    ):
        return None
    try:
        return contextmanager_signature(freeze_data(data["contextmanager_signature"]))
    except ValueError:
        return None


def _function_return(data: RecordData) -> str:
    proof = _contextmanager_return(data, "return")
    if proof is None:
        return data["returns"] or ""
    result = proof.effective_return
    return f"{result.wrapper}[{result.payload}]"


def _declared_function_signature(data: RecordData) -> bool:
    """A source signature does not assert future runtime member stability."""
    return (
        data.get("source_binding_unique") is True
        and data.get("namespace_bound") is True
        and (
            data.get("signature_decorators_proven") is True
            or _contextmanager_return(data, "return") is not None
        )
    )


def _source_local_function(data: RecordData) -> bool:
    parent = data.get("parent")
    return (
        data.get("namespace_bound") is False
        and data.get("source_binding_unique") is True
        and data.get("declared_in_all") is False
        and data.get("definition_contexts") == []
        and isinstance(parent, str)
        and isinstance(data.get("lexical_parent_id"), str)
        and data.get("qualified_name") == f"{parent}.{data['name']}"
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
    owners: dict[str, ContractComponent | None] | None = None,
) -> DeclaredFacade | None:
    """Retain all positions of a declared facade, including uncertain and inherited ones."""
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
            include_fields=include_fields,
            owners=owners,
        )
    if data.get("qualified_name") in property_chains and not (
        data.get("source_final_method_binding") is True
        and data.get("signature_decorators_proven") is True
    ):
        return None
    if data.get("overloaded") is True and data.get("overload_signature") is not True:
        return None
    if item["kind"] == "method" and data.get("symbol_category") == "method":
        return _declared_facade_method_positions(
            data,
            contract,
            exports_by_module,
            imports,
            uncertain_reexport_origins,
            reexports,
            owners=owners,
        )
    if item["kind"] != "function" or data.get("symbol_category") != "function":
        return None
    module, name = data["module"], data["name"]
    facade_entries: list[tuple[str, str, str, bool]] = []
    signature_uncertain = not _declared_function_signature(data)
    component = contract.component_for(module) if owners is None else owners[module]
    if (
        component is not None
        and facade_covers(module, name, component, exports_by_module)
        and (not _source_local_function(data) or f"{module}:{name}" in (component.public or ()))
    ):
        facade_entries.append((module, name, module, signature_uncertain))
    origin = data["qualified_name"]
    reexport_entries = _reexport_facade_entries(
        origin,
        contract,
        exports_by_module,
        imports,
        uncertain_reexport_origins or {},
        reexports,
        owners=owners,
    )
    facade_entries.extend(
        (module, name, resolution, uncertain or signature_uncertain)
        for module, name, resolution, uncertain in reexport_entries
    )
    if not facade_entries:
        return None
    facade_entries = sorted(set(facade_entries))
    facade_module, facade_name, resolution_module, _ = facade_entries[0]
    # Missing annotations remain in the rule's denominator (AD-67).
    positions = [
        (parameter["name"], parameter["annotation"] or "") for parameter in data["parameters"]
    ]
    positions.append(("return", _function_return(data)))
    qualified_name = f"{facade_module}.{facade_name}"
    return facade_module, qualified_name, positions, resolution_module, tuple(facade_entries)


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
    owners: dict[str, ContractComponent | None] | None = None,
) -> DeclaredFacade | None:
    base_roots = data["base_roots"] if "base_roots" in data else data["bases"]
    if not any(
        f"{data['qualified_name']}.{name}" in property_chains for name in data["class_members"]
    ) and not any(base not in _FRAMEWORK_BASES for base in base_roots):
        if not include_fields or not data.get("fields"):
            return None
    module, name = data["module"], data["name"]
    entries: list[FacadeEntry] = []
    owner = contract.component_for(module) if owners is None else owners[module]
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
            owners=owners,
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
    *,
    owners: dict[str, ContractComponent | None] | None = None,
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
    owner = contract.component_for(module) if owners is None else owners[module]
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
            owners=owners,
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


def _reexport_declaration_proven(
    data: RecordData, by_alias: dict[str, tuple[RawRecord, ...]]
) -> bool:
    chain = data.get("reexport_chain", ())
    if not chain or data.get("origin_definition") != chain[-1]:
        return False
    route = (f"{data['source_module']}.{data['binding']}", *chain)
    if len(set(route)) != len(route):
        return False
    for index, alias in enumerate(route[:-1]):
        hops = {
            item["id"]: item["data"]
            for item in by_alias.get(alias, ())
            if f"{item['data']['source_module']}.{item['data']['binding']}" == alias
            and item["data"].get("module_level_import") is True
        }
        if len(hops) != 1:
            return False
        [hop] = hops.values()
        if (
            hop.get("source_binding_unique") is not True
            or hop.get("origin_binding_unique") is not True
            or hop.get("origin_definition") != route[-1]
            or tuple(hop.get("reexport_chain", ())) != route[index + 1 :]
        ):
            return False
    return True


def _reexport_facade_entries(
    origin: str,
    contract: ArchitectureContract,
    exports_by_module: dict[str, frozenset[str]],
    imports: Sequence[RawRecord],
    uncertain_reexport_origins: UncertainReexportOrigins,
    reexports: ReexportIndex | None = None,
    *,
    owners: dict[str, ContractComponent | None] | None = None,
) -> list[FacadeEntry]:
    """Match re-export facts while keeping uncertain bindings scoped to one entry."""
    indexed = reexports or _reexport_index(imports, uncertain_reexport_origins)
    by_origin, by_alias, ambiguous_bindings = indexed
    candidates: dict[str, RawRecord] = {
        imported["id"]: imported for imported in by_origin.get(origin, ())
    }
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
        entry_uncertain = (
            own_uncertainty
            or binding_key in ambiguous_bindings
            or inherited_uncertainty
            or not _reexport_declaration_proven(imported_data, by_alias)
        )
        owner = contract.component_for(facade_module) if owners is None else owners[facade_module]
        if (
            owner is not None
            and isinstance(binding, str)
            and facade_covers(facade_module, binding, owner, exports_by_module)
        ):
            facade_entries.append((facade_module, binding, resolution_module, entry_uncertain))
    return facade_entries


def _facade_module_owners(
    contract: ArchitectureContract, symbols: Sequence[RawRecord], imports: Sequence[RawRecord]
) -> dict[str, ContractComponent | None]:
    modules: set[str] = {
        item["data"]["module"]
        for item in symbols
        if item["kind"] in {"function", "method", "class"}
    }
    modules.update(item["data"]["source_module"] for item in imports)
    return {module: contract.component_for(module) for module in modules}
