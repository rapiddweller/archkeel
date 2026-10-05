# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Public API, compatibility and interface-budget diagnostics."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import replace
from typing import Final

from archkeel.ir.baseline import KnownViolation
from archkeel.ir.codec import InsideContractMount
from archkeel.ir.measurements import NameBudgetKind
from archkeel.ir.model import (
    ArchitectureContract,
    CompatibilityShim,
    ContractComponent,
    ContractDeclarations,
    Diagnostic,
    InterfaceBoundaryRule,
    InterfaceBudgetResult,
    JsonValue,
    Observation,
    Record,
    RecordData,
    component_owns_module,
    facade_covers,
    in_scope,
    text_value,
)

from .diagnostics import _diagnostic


def _scanned_modules(observation: Observation) -> frozenset[str]:
    """Every module the scan actually read, by qualified name (shared with reference checks)."""
    return frozenset(
        module_name
        for record in observation.records("modules") or ()
        if isinstance((module_name := record.data.get("qualified_name")), str)
    )


def _literal_exports(observation: Observation) -> dict[str, frozenset[str]]:
    """Each scanned module's literal `__all__`, absent for a module that declares none.

    A module without `__all__` is not in the mapping at all, which is what lets a reader tell
    "this module states its surface and the name is not in it" from "this module states no
    surface", the distinction `symbols` alone cannot make for a constant or type alias.
    """
    return {
        module_name: frozenset(export for export in exports if isinstance(export, str))
        for record in observation.records("modules") or ()
        if isinstance((module_name := record.data.get("qualified_name")), str)
        and isinstance((exports := record.data.get("all_exports")), tuple)
        and exports
    }


def _entry_module(entry: str) -> str:
    return entry.partition(":")[0]


def _resolved_public_entries(
    contract: ArchitectureContract,
    known: tuple[KnownViolation, ...],
    observed: tuple[KnownViolation, ...],
    observation: Observation | None = None,
) -> tuple[tuple[str, str], ...]:
    """Return public entries proven to have lost their last importer by a 1.1 baseline.

    A role is before-evidence, not an inference from a diagnostic message.  The fingerprint's
    subjects add the imported symbol, while the role preserves source and target module
    direction.  Older baselines have no roles and therefore cannot suppress ``interface.unused``.
    """
    observed_by_fingerprint = {item.fingerprint: item for item in observed}
    resolved: set[tuple[str, str]] = set()
    public_by_component = {
        component.label: frozenset(component.public or ()) for component in contract.components
    }
    records_by_component = (
        _imports_by_target(contract, observation) if observation is not None else {}
    )
    facade_types = _facade_types(observation) if observation is not None else ()

    def add_if_unused(component: str, entry: str) -> None:
        if not _entry_used(entry, records_by_component.get(component, []), facade_types):
            resolved.add((component, entry))

    for item in known:
        if not item.roles or len(item.fingerprint.subjects) != 2:
            continue
        current = observed_by_fingerprint.get(item.fingerprint)
        if current is not None:
            continue
        gone_roles = set(item.roles)
        if len(gone_roles) != 1:
            continue
        subjects = frozenset(item.fingerprint.subjects)
        ((source_module, target_module),) = gone_roles
        if source_module not in subjects:
            continue
        target_component = contract.component_for(target_module)
        source_component = contract.component_for(source_module)
        if (
            target_component is None
            or source_component is None
            or source_component == target_component
        ):
            continue
        target_name = next((subject for subject in subjects if subject != source_module), None)
        if target_name is None or not (
            target_name == target_module or target_name.startswith(f"{target_module}.")
        ):
            continue
        public = public_by_component[target_component.label]
        if target_name == target_module and target_module in public:
            add_if_unused(target_component.label, target_module)
            continue
        symbol = target_name.removeprefix(f"{target_module}.")
        entry = f"{target_module}:{symbol}"
        if entry in public:
            add_if_unused(target_component.label, entry)
    return tuple(sorted(resolved))


def _entry_reached_by(entry: str, names: Iterable[JsonValue]) -> bool:
    """True when one of the dotted names reaches the entry.

    A `pkg.module:Name` entry is reached by exactly that name; a `pkg.module` entry by any
    name the module defines. Both ways an entry can be reached share this one match (AD-65),
    because an import's `reexport_chain` and a declared facade signature's `facade_types`
    carry the same dotted shape: neither can drift into a second reading of what an entry
    covers.
    """
    module, colon, name = entry.partition(":")
    target = f"{module}.{name}" if colon else ""
    return any(
        (item == target if colon else item.rpartition(".")[0] == module)
        for item in names
        if isinstance(item, str)
    )


def _facade_types(observation: Observation) -> tuple[str, ...]:
    """Every type a declared facade signature exposes, as the analyzer resolved it (AD-65).

    The analyzer writes `facade_types` on the facade function's own symbol record, using the
    resolution `boundary_types` (AD-63) already runs over the same annotations; reading it back
    here keeps one answer to "which type does this signature expose" instead of a second
    derivation that could disagree with the rule about the same position.
    """
    return tuple(
        name
        for record in observation.records("symbols") or ()
        if isinstance((types := record.data.get("facade_types")), tuple)
        for name in types
        if isinstance(name, str)
    )


def _scoped_facade_types(
    observation: Observation, scope_id: str, source_modules: frozenset[str]
) -> tuple[str, ...]:
    """Read positive facade type facts recorded for this exact source scope."""
    types: set[str] = set()
    for record in observation.records("symbols") or ():
        by_mount = record.data.get("facade_types_by_mount")
        if not isinstance(by_mount, RecordData):
            continue
        scoped_types = by_mount.get(scope_id)
        if not isinstance(scoped_types, RecordData):
            continue
        for module, values in scoped_types.entries:
            if module in source_modules and isinstance(values, tuple):
                types.update(value for value in values if isinstance(value, str))
    return tuple(sorted(types))


def _inherited_facade_candidates(
    observation: Observation,
    publishers: frozenset[str] | None = None,
    scope_id: str | None = None,
) -> tuple[str, ...]:
    """Candidate types exposed by unresolved inherited overloads, scoped to publishers."""
    candidates: set[str] = set()
    key = "facade_type_candidates_by_publisher"
    for record in observation.records("symbols") or ():
        data = record.data
        publisher_data = data.get(key)
        if scope_id is not None:
            by_mount = data.get("facade_type_candidates_by_mount")
            scoped = by_mount.get(scope_id) if isinstance(by_mount, RecordData) else None
            publisher_data = scoped if isinstance(scoped, RecordData) else None
        if not isinstance(publisher_data, RecordData):
            continue
        for publisher, values in publisher_data.entries:
            if publishers is not None and publisher not in publishers:
                continue
            if isinstance(values, tuple):
                candidates.update(value for value in values if isinstance(value, str))
    return tuple(sorted(candidates))


def _entry_used(entry: str, records: list[RecordData], facade_types: tuple[str, ...]) -> bool:
    """Match one public entry's usage the way `_interface_allows` walks reexport_chain.

    Deliberately looser than the analyzer's runtime check: no `__all__` gate and no
    underscore rejection, since a public entry naming a private or unexported name is
    a rule violation already reported elsewhere, not an unused-entry drift signal.

    AD-65 adds the second way an entry is reached: a declared facade signature that names the
    type exposes it to every consumer of that signature, whether or not an import names it.
    AD-97: an import whose used names the scan cannot see may reach any name of its module, so
    it keeps a `module:Name` entry from reading unused on no evidence.
    """
    if _entry_reached_by(entry, facade_types):
        return True
    module, colon, _ = entry.partition(":")
    for data in records:
        chain = data.get("reexport_chain")
        if _entry_reached_by(entry, chain if isinstance(chain, tuple) else ()):
            return True
        if data.get("target_module") == module and (
            not colon or data.get("symbols_known") is False
        ):
            return True
    return False


def _parent_reexport_proven(record: RecordData) -> bool:
    """Accept uncertain constant routes only when this publisher binding is unique."""
    chain = record.get("reexport_chain")
    origin = record.get("origin_definition")
    return record.get("reexport") is True or (
        record.get("source_binding_unique") is True
        and isinstance(origin, str)
        and isinstance(chain, tuple)
        and origin in chain
    )


def _facade_covers_import(
    module: str,
    symbol: str | None,
    component: ContractComponent,
    exports_by_module: dict[str, frozenset[str]],
) -> bool:
    """Match the concrete module or symbol imported through a declared facade."""
    if symbol is None:
        return component.public is not None and module in component.public
    return facade_covers(module, symbol, component, exports_by_module)


def _clip_contract(
    contract: ArchitectureContract,
    packages: tuple[str, ...],
    exact_modules: tuple[str, ...] = (),
) -> ArchitectureContract:
    """Keep component ownership inside its declared parent packages."""
    return replace(
        contract,
        components=tuple(
            replace(
                component,
                packages=tuple(
                    package
                    for package in component.packages
                    if any(in_scope(package, root) for root in packages)
                ),
                exact_modules=tuple(
                    module
                    for module in component.exact_modules or ()
                    if module in exact_modules or any(in_scope(module, root) for root in packages)
                )
                or None,
            )
            for component in contract.components
        ),
    )


def _reexport_owners(
    contract: ArchitectureContract, names: Iterable[JsonValue]
) -> dict[str, ContractComponent]:
    """Keep canonical route ownership identical for local and outside lifecycle imports."""
    owners: dict[str, ContractComponent] = {}
    for name in names:
        if not isinstance(name, str):
            continue
        owner = contract.component_for(name.rpartition(".")[0])
        if owner is not None:
            owners[name] = owner
    return owners


def _imports_by_target(
    contract: ArchitectureContract,
    observation: Observation,
    source_modules: frozenset[str] | None = None,
    published_parent_components: dict[str, tuple[ContractComponent, ...]] | None = None,
    exports_by_module: dict[str, frozenset[str]] | None = None,
) -> dict[str, list[RecordData]]:
    imports_by_target: dict[str, list[RecordData]] = {}
    for record in observation.records("imports") or ():
        source_module = record.data.get("source_module")
        target_module = record.data.get("target_module")
        if not isinstance(source_module, str) or not isinstance(target_module, str):
            continue
        if source_modules is not None and source_module not in source_modules:
            continue
        source = contract.component_for(source_module)
        target = contract.component_for(target_module)
        if source is None:
            parent_components = (published_parent_components or {}).get(source_module, ())
            binding = record.data.get("binding")
            if (
                source_modules is None
                or not isinstance(binding, str)
                or not any(
                    facade_covers(source_module, binding, component, exports_by_module or {})
                    for component in parent_components
                )
                or not _parent_reexport_proven(record.data)
            ):
                continue
        if target is None:
            if source is not None and source_modules is None:
                continue
            chain = record.data.get("reexport_chain")
            owners: dict[str, ContractComponent] = _reexport_owners(
                contract, chain if isinstance(chain, tuple) else ()
            )
            targets: dict[str, ContractComponent] = {
                owner.label: owner for owner in owners.values()
            }
            target_components = tuple(targets.values())
        else:
            target_components = (target,)
        for target_component in target_components:
            if source is not None and source == target_component:
                continue
            imports_by_target.setdefault(target_component.label, []).append(record.data)
    return imports_by_target


def _published_parent_components(
    mount: InsideContractMount,
    mounts_by_parent: dict[str, InsideContractMount],
    source_modules: frozenset[str],
) -> dict[str, tuple[ContractComponent, ...]]:
    """Return declared ancestor components physically present in this parent scope."""
    components: dict[str, set[ContractComponent]] = {}
    contracts = [mount.parent_contract]
    owner_id = mount.owner_id
    while owner_id:
        owner = mounts_by_parent.get(owner_id)
        if owner is None:
            break
        contracts.append(owner.parent_contract)
        owner_id = owner.owner_id
    for contract in contracts:
        for component in contract.components:
            for entry in component.public or ():
                module = entry.partition(":")[0]
                if module not in source_modules or contract.component_for(module) != component:
                    continue
                components.setdefault(module, set()).add(component)
    return {module: tuple(values) for module, values in components.items()}


def _public_entry_diagnostics(
    index: int,
    component: ContractComponent,
    records: list[RecordData],
    modules: frozenset[str],
    facade_types: tuple[str, ...],
    resolved_public_entries: frozenset[tuple[str, str]],
    pointer_root: str = "/components",
    facade_candidates: tuple[str, ...] = (),
) -> list[Diagnostic]:
    """Split an unused `public` entry by whether its module was ever scanned (AD-56).

    A module the scan never saw does not exist yet, `interface.missing`, whether that is a typo
    or a facade a refactoring has not built; one the scan saw but nothing reaches is
    `interface.unused`, same as before -- unless a declared facade signature exposes the type
    it names, which reaches it without an import (AD-65). A `pkg.module:Name` entry is judged
    by its module alone: `symbols` records only classes and functions, so absence from it
    would misreport a constant or type alias as missing. A used entry is checked against
    neither, exactly as before.
    """
    diagnostics = []
    for item, entry in enumerate(component.public or ()):
        if _entry_used(entry, records, facade_types):
            continue
        if _entry_reached_by(entry, facade_candidates) or any(
            _entry_reached_by(entry, candidates if isinstance(candidates, tuple) else ())
            for data in records
            for candidates in (data.get("reexport_candidates"),)
        ):
            diagnostics.append(
                _diagnostic(
                    "interface.usage_unknown",
                    f"{pointer_root}/{index}/public/{item}",
                    entry,
                    "An unproven publication or inherited signature may expose this public entry.",
                    "Resolve the publication route or inherited bases before classifying "
                    "this entry as used or unused.",
                )
            )
            continue
        missing = _missing_public_entry(f"{pointer_root}/{index}/public/{item}", entry, modules)
        if missing is not None:
            diagnostics.append(missing)
        elif (component.label, entry) in resolved_public_entries:
            continue
        else:
            diagnostics.append(
                _diagnostic(
                    "interface.unused",
                    f"{pointer_root}/{index}/public/{item}",
                    entry,
                    "No cross-component import and no declared facade signature "
                    "reaches this public entry.",
                    "Remove the entry or confirm another component should use it.",
                )
            )
    return diagnostics


def _missing_public_entry(pointer: str, entry: str, modules: frozenset[str]) -> Diagnostic | None:
    if _entry_module(entry) in modules:
        return None
    return _diagnostic(
        "interface.missing",
        pointer,
        entry,
        "The public entry's module has not been scanned; it does not exist yet.",
        "Build the module, correct a typo, or move the entry to planned until it exists.",
    )


def _planned_entry_diagnostics(
    index: int,
    component: ContractComponent,
    records: list[RecordData],
    modules: frozenset[str],
    facade_types: tuple[str, ...],
    pointer_root: str = "/components",
) -> list[Diagnostic]:
    """Flag a built `planned` entry once code actually reaches it (AD-56, #79).

    A built but unused module is still target work. Promotion is needed only when an import or
    declared facade signature reaches the planned entry.
    """
    return [
        _diagnostic(
            "interface.planned_built",
            f"{pointer_root}/{index}/planned/{item}",
            entry,
            "The planned entry's module has been scanned; it is no longer planned.",
            "Move the entry to public and drop it from planned.",
        )
        for item, entry in enumerate(component.planned or ())
        if _entry_module(entry) in modules and _entry_used(entry, records, facade_types)
    ]


def _published_api_types(observation: Observation) -> dict[str, tuple[str, ...]]:
    """Each `declarations.public_api` entry mapped to the types its own signature exposes.

    Read off the `declared_public_api` records `public_api_exposed_types`
    (analyzer/embedded/violations.py, AD-70) already resolved -- `check` compares this published
    answer against the declared set instead of deriving a second one (AD-2's open payload, AD-4's
    one channel out of the analyzer).
    """
    types: dict[str, tuple[str, ...]] = {}
    for record in observation.records("declarations") or ():
        if record.kind != "declared_public_api":
            continue
        entry = text_value(record.data.get("qualified_name"))
        exposed = record.data.get("types")
        types[entry] = tuple(
            item
            for item in (exposed if isinstance(exposed, tuple) else ())
            if isinstance(item, str)
        )
    return types


def _public_api_entry_diagnostics(
    index: int,
    entry: str,
    modules: frozenset[str],
    exports: dict[str, frozenset[str]],
    exposed_types: dict[str, tuple[str, ...]],
    declared_api: frozenset[str],
) -> list[Diagnostic]:
    """One `declarations.public_api` entry's findings: existence (AD-66/AD-71) first, then
    AD-70's signature check once the entry is known to exist. Both read as `api_surface.missing`
    because either way a consumer was promised something this contract does not make good on.
    """
    module, _, name = entry.partition(":")
    pointer = f"/declarations/public_api/{index}"
    if module not in modules:
        return [
            _diagnostic(
                "api_surface.missing",
                pointer,
                entry,
                "The declared public API entry's module has not been scanned; "
                "it does not exist yet.",
                "Build the module, correct a typo, or remove the entry until it exists.",
            )
        ]
    if name and (exported := exports.get(module)) is not None and name not in exported:
        return [
            _diagnostic(
                "api_surface.missing",
                pointer,
                entry,
                "The module declares __all__ and the promised name is not in it.",
                "Export the name from the module, correct a typo, or remove the entry.",
            )
        ]
    return [
        _diagnostic(
            "api_surface.missing",
            pointer,
            entry,
            f"{entry} exposes {leaked.rpartition(':')[2]}, which declarations.public_api "
            "does not name.",
            f"Add {leaked} to declarations.public_api, or stop exposing it from this entry.",
        )
        for leaked in exposed_types.get(entry, ())
        if leaked not in declared_api
    ]


def public_api_diagnostics(
    contract: ArchitectureContract, observation: Observation
) -> tuple[Diagnostic, ...]:
    """Flag a `declarations.public_api` entry whose module the scan never saw (AD-66/AD-71), or
    whose signature exposes a type the declarations never name (AD-70).

    `public_api` names the surface a consumer *outside* this package may rely on, the case
    AD-9's component `public` never covered, so there is no cross-component import to make an
    `interface.unused` twin possible here (see `_public_api_entry_diagnostics`). AD-70 adds a
    second, independent signal once an entry is known to exist: a declared function's parameter
    and return types, and a declared class's public attribute types, must themselves be
    named in `public_api` -- the generic form of the guard AD-58/AD-63 already hold a
    component's *internal* facade to, pointed here at the package's *external* one. The analyzer
    (`public_api_exposed_types`) resolves which types those are; this reads that answer rather
    than resolving annotations a second time.
    """
    declarations = contract.declarations or ContractDeclarations()
    modules = _scanned_modules(observation)
    exports = _literal_exports(observation)
    exposed_types = _published_api_types(observation)
    declared_api = frozenset(declarations.public_api)
    return tuple(
        diagnostic
        for index, entry in enumerate(declarations.public_api)
        for diagnostic in _public_api_entry_diagnostics(
            index, entry, modules, exports, exposed_types, declared_api
        )
    )


def _compatibility_import_diagnostics(
    shim: CompatibilityShim,
    pointer: str,
    all_exports: JsonValue,
    imports: tuple[Record, ...],
) -> tuple[Diagnostic, ...]:
    diagnostics: list[Diagnostic] = []
    imports_by_binding: dict[str, set[tuple[str, str | None]]] = {}
    for item in imports:
        binding = item.data.get("binding")
        target = item.data.get("target_module")
        if (
            item.data.get("source_module") == shim.module
            and isinstance(binding, str)
            and binding != "*"
            and isinstance(target, str)
        ):
            origin = item.data.get("origin_definition")
            if not isinstance(origin, str):
                origin = target if item.data.get("symbol") is None else None
            imports_by_binding.setdefault(binding, set()).add((target, origin))
    if not any(
        target == shim.target
        for imports_for_name in imports_by_binding.values()
        for target, _origin in imports_for_name
    ):
        diagnostics.append(
            _diagnostic(
                "compatibility.invalid",
                pointer,
                shim.module,
                "The compatibility module has no observed import of its declared target.",
                "Import the target module directly from the shim.",
            )
        )
    exported_names = (
        {name for name in all_exports if isinstance(name, str)}
        if isinstance(all_exports, tuple)
        else set()
    )
    for name in exported_names:
        imports_for_name = imports_by_binding.get(name, set())
        origins = {origin for _target, origin in imports_for_name}
        if (
            {target for target, _origin in imports_for_name} != {shim.target}
            or None in origins
            or len(origins) != 1
        ):
            diagnostics.append(
                _diagnostic(
                    "compatibility.invalid",
                    pointer,
                    shim.module,
                    "Every compatibility export must resolve only to the declared target.",
                    "Remove unrelated or ambiguous imports, or correct the declared target.",
                )
            )
            break
    if any(
        item.data.get("source_module") != shim.module
        and item.data.get("target_module") == shim.module
        for item in imports
    ):
        diagnostics.append(
            _diagnostic(
                "compatibility.invalid",
                pointer,
                shim.module,
                "Product code imports a compatibility module.",
                "Keep compatibility imports at the external boundary only.",
            )
        )
    return tuple(diagnostics)


def compatibility_diagnostics(
    contract: ArchitectureContract, observation: Observation
) -> tuple[Diagnostic, ...]:
    """Check declared shims from module and import facts already produced by the scan."""
    declarations = contract.declarations or ContractDeclarations()
    modules = {
        name: record.data
        for record in observation.records("modules") or ()
        if isinstance((name := record.data.get("qualified_name")), str)
    }
    imports = observation.records("imports") or ()
    diagnostics: list[Diagnostic] = []
    for index, shim in enumerate(declarations.compat):
        pointer = f"/declarations/compat/{index}"
        facts = modules.get(shim.module)
        if facts is None:
            diagnostics.append(
                _diagnostic(
                    "compatibility.invalid",
                    pointer,
                    shim.module,
                    "The declared compatibility module was not scanned.",
                    "Build the shim in the configured scan scope, or remove the declaration.",
                )
            )
            continue
        all_exports = facts.get("all_exports")
        if (
            facts.get("compatibility_logic_free") is not True
            or not isinstance(all_exports, tuple)
            or not all_exports
        ):
            diagnostics.append(
                _diagnostic(
                    "compatibility.invalid",
                    pointer,
                    shim.module,
                    "A compatibility module must contain only imports and a literal __all__.",
                    "Remove definitions and effectful statements, and declare a literal __all__.",
                )
            )
        if shim.target not in modules:
            diagnostics.append(
                _diagnostic(
                    "compatibility.invalid",
                    pointer,
                    shim.target,
                    "The declared compatibility target was not scanned.",
                    "Build the target module in the configured scan scope, or correct the "
                    "declaration.",
                )
            )
        diagnostics.extend(_compatibility_import_diagnostics(shim, pointer, all_exports, imports))
    return tuple(diagnostics)


def interface_diagnostics(
    contract: ArchitectureContract,
    observation: Observation,
    resolved_public_entries: frozenset[tuple[str, str]] = frozenset(),
) -> tuple[Diagnostic, ...]:
    """Require a declared interface for inbound imports and usage for declared entries.

    An entry is used when a cross-component import reaches it or when a declared facade
    signature exposes the type it names (AD-65): one notion of `public`, two ways of being
    reached.
    """
    if not any(isinstance(rule, InterfaceBoundaryRule) for rule in contract.rules):
        return ()
    imports_by_target = _imports_by_target(contract, observation)
    modules = _scanned_modules(observation)
    facade_types = _facade_types(observation)
    diagnostics = []
    for index, component in enumerate(contract.components):
        records = imports_by_target.get(component.label, [])
        facade_publishers = frozenset(
            module for module in modules if component_owns_module(component, module)
        )
        facade_candidates = _inherited_facade_candidates(observation, facade_publishers)
        if component.public is None:
            if records:
                diagnostics.append(
                    _diagnostic(
                        "interface.undeclared",
                        f"/components/{index}",
                        component.label,
                        "The component receives cross-component imports but declares "
                        "no public interface.",
                        "Declare the used modules or names in public.",
                    )
                )
        else:
            diagnostics.extend(
                _public_entry_diagnostics(
                    index,
                    component,
                    records,
                    modules,
                    facade_types,
                    resolved_public_entries,
                    facade_candidates=facade_candidates,
                )
            )
        diagnostics.extend(
            _planned_entry_diagnostics(index, component, records, modules, facade_types)
        )
    return tuple(diagnostics)


def interface_budget_diagnostics(
    results: tuple[InterfaceBudgetResult, ...], *, report_exceeded: bool
) -> tuple[Diagnostic, ...]:
    """AD-99: a budget over its target, or one the scan cannot count.

    A budget counts names, not which of them are too many, so an exceeded one lists them all.
    With a baseline its accepted names answer the target instead, the way AD-52 answers a
    violation, so only an uncountable budget is left to report there.
    """
    diagnostics = []
    for item in results:
        counted = (
            f"The {item.subject} {_BUDGET_NOUNS[item.budget]} counts "
            f"{'at least ' if item.uncounted else ''}{item.count} "
            f"{'name' if item.count == 1 else 'names'}"
        )
        if report_exceeded and item.over_target:
            diagnostics.append(
                _diagnostic(
                    "budget.exceeded",
                    item.pointer,
                    item.subject,
                    f"{counted}, {item.over_target} over max_names {item.max_names}: "
                    f"{', '.join(item.names)}.",
                    "Remove names until max_names holds; raising max_names widens the contract.",
                )
            )
        elif item.uncounted:
            diagnostics.append(
                _diagnostic(
                    "budget.unknown",
                    item.pointer,
                    item.subject,
                    f"{counted} against max_names {item.max_names}; not enumerated: "
                    f"{', '.join(item.uncounted)}.",
                    "Give the facade a literal __all__ or module:Name entries, and import the "
                    "used names explicitly.",
                )
            )
    return tuple(diagnostics)


_BUDGET_NOUNS: Final[dict[NameBudgetKind, str]] = {
    "facade_names": "facade",
    "coupling_names": "pair",
}
