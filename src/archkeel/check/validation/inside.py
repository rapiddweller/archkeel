# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Nested contract validation diagnostics."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from archkeel.ir.codec import InsideContractMount, InsideContractTree
from archkeel.ir.model import (
    AllowedDependencyRule,
    ArchitectureContract,
    CompleteRequiresRule,
    ContractComponent,
    Diagnostic,
    ForbiddenDependencyRule,
    InterfaceBoundaryRule,
    Observation,
    RecordData,
    component_owns_module,
    in_scope,
    interface_covers_import,
    module_in_ownership,
)

from ..ports import ScanConfig
from .diagnostics import _diagnostic, _sorted
from .public_api import (
    _clip_contract,
    _entry_used,
    _facade_covers_import,
    _imports_by_target,
    _inherited_facade_candidates,
    _literal_exports,
    _planned_entry_diagnostics,
    _public_entry_diagnostics,
    _published_parent_components,
    _reexport_owners,
    _scanned_modules,
    _scoped_facade_types,
)
from .references import _inside_contract_tree, reference_diagnostics


def _forbidden_targets(
    contract: ArchitectureContract, component: ContractComponent
) -> list[tuple[str, str]]:
    """Each rule id and target the level above forbids a component, by any of its packages.

    The id travels with the target because the diagnostic exists to point at a decision, and
    a reader cannot find the decision from the target alone.
    """
    return [
        (rule.id, rule.target)
        for rule in contract.rules
        if isinstance(rule, ForbiddenDependencyRule)
        and module_in_ownership(rule.source, component.packages, component.exact_modules or ())
    ]


def _denied_by_absence(
    contract: ArchitectureContract, label: str, required: frozenset[str], target: str
) -> str | None:
    """The `complete_requires` rule refusing an edge the component never asked for (AD-32).

    Absence decides only where such a rule is in force, and only for a target another
    component owns: a target inside the component itself is no component edge at all, and one
    no component owns belongs to the external scope rules instead. Without this, a level whose
    pairs are decided by absence - which is how this repository decides them - would let its
    inside grant anything, because there is no `forbidden_dependency` left to contradict.
    """
    rule = next((item for item in contract.rules if isinstance(item, CompleteRequiresRule)), None)
    if rule is None:
        return None
    owner = contract.component_for(target)
    if owner is None or owner.label == label or owner.label in required:
        return None
    return rule.id


def _inside_source_domain_diagnostics(
    pointer: str, component: ContractComponent, inner: ArchitectureContract
) -> list[Diagnostic]:
    """Reject nested physical claims outside the component holding the inside."""
    diagnostics = [
        _diagnostic(
            "contract.invalid",
            pointer,
            package,
            f"The inside claims {package}, outside {component.label}'s physical packages.",
            "Keep every inside component package within the parent component's packages.",
        )
        for child in inner.components
        for package in child.packages
        if not any(in_scope(package, parent) for parent in component.packages)
    ]
    for child_index, child in enumerate(inner.components):
        diagnostics.extend(
            _diagnostic(
                "contract.invalid",
                f"{pointer}/components/{child_index}/exact_modules/{exact_index}",
                module,
                f"The inside claims {module}, outside {component.label}'s physical scope.",
                "Keep exact modules within the parent packages or equal to a parent exact module.",
            )
            for exact_index, module in enumerate(child.exact_modules or ())
            if module not in (component.exact_modules or ())
            and not any(in_scope(module, parent) for parent in component.packages)
        )
    return diagnostics


def _import_published_through_ancestors(
    source_module: str,
    target_module: str,
    symbol: str | None,
    mount: InsideContractMount,
    mounts_by_parent: dict[str, InsideContractMount],
    available_by_owner: dict[str, frozenset[str]],
    exports_by_module: dict[str, frozenset[str]],
) -> bool:
    """Require publication at every boundary crossed by an outside import."""
    ancestor = mount
    while True:
        local_modules = available_by_owner.get(ancestor.parent_id, frozenset())
        if source_module in local_modules:
            local_contract = _clip_contract(
                ancestor.contract,
                ancestor.parent.packages,
                ancestor.parent.exact_modules or (),
            )
            return (
                local_contract.component_for(source_module) is not None
                and local_contract.component_for(target_module) is not None
            )
        parent_mount = mounts_by_parent.get(ancestor.owner_id) if ancestor.owner_id else None
        parent_contract = (
            _clip_contract(
                ancestor.parent_contract,
                parent_mount.parent.packages,
                parent_mount.parent.exact_modules or (),
            )
            if parent_mount is not None
            else ancestor.parent_contract
        )
        parent_modules = available_by_owner.get(ancestor.owner_id, frozenset())
        if (
            target_module not in parent_modules
            or parent_contract.component_for(target_module) != ancestor.parent
            or not _facade_covers_import(target_module, symbol, ancestor.parent, exports_by_module)
        ):
            return False
        if not ancestor.owner_id:
            return source_module in available_by_owner.get("", frozenset()) and (
                ancestor.parent_contract.component_for(source_module) is not None
            )
        if parent_mount is None:
            return False
        ancestor = parent_mount


def _inside_imports_by_target(
    mount: InsideContractMount,
    scoped: ArchitectureContract,
    source_modules: frozenset[str],
    observation: Observation,
    mounts_by_parent: dict[str, InsideContractMount],
    available_by_owner: dict[str, frozenset[str]],
) -> dict[str, list[RecordData]]:
    """Collect local and ancestor-published uses of this mount's interfaces."""
    exports_by_module = _literal_exports(observation)
    imports_by_target: dict[str, list[RecordData]] = _imports_by_target(
        scoped,
        observation,
        source_modules,
        _published_parent_components(mount, mounts_by_parent, source_modules),
        exports_by_module,
    )
    for record in observation.records("imports") or ():
        source_module = record.data.get("source_module")
        target_module = record.data.get("target_module")
        symbol = record.data.get("symbol")
        if (
            not isinstance(source_module, str)
            or source_module in source_modules
            or not isinstance(target_module, str)
            or target_module not in source_modules
            or (symbol is not None and not isinstance(symbol, str))
        ):
            continue
        if not _import_published_through_ancestors(
            source_module,
            target_module,
            symbol,
            mount,
            mounts_by_parent,
            available_by_owner,
            exports_by_module,
        ):
            continue
        target = scoped.component_for(target_module)
        if target is None and any(
            component_owns_module(component, target_module) for component in scoped.components
        ):
            continue
        chain = record.data.get("reexport_chain")
        candidates = record.data.get("reexport_candidates")
        names = (
            tuple(name for name in chain if isinstance(name, str))
            if isinstance(chain, tuple)
            else ()
        )
        candidate_names = (
            tuple(name for name in candidates if isinstance(name, str))
            if isinstance(candidates, tuple)
            else ()
        )
        owners: dict[str, ContractComponent] = _reexport_owners(scoped, (*names, *candidate_names))
        targets: dict[str, ContractComponent] = (
            {target.label: target}
            if target is not None
            else {owner.label: owner for owner in owners.values()}
        )
        for target in targets.values():
            owned_names = tuple(name for name in names if owners.get(name) == target)
            owned_candidates = tuple(name for name in candidate_names if owners.get(name) == target)
            public_import = interface_covers_import(
                target_module, symbol, owned_names, target, exports_by_module
            )
            uncertain_import = interface_covers_import(
                target_module, symbol, owned_candidates, target, exports_by_module
            )
            planned_import = any(
                _entry_used(entry, [record.data], ()) for entry in target.planned or ()
            )
            # Candidate admission preserves UNKNOWN; _entry_used reads only the proven chain.
            if not public_import and not uncertain_import and not planned_import:
                continue
            target_records: list[RecordData] = imports_by_target.setdefault(target.label, [])
            target_records.append(record.data)
    return imports_by_target


def _inside_interface_lifecycle_diagnostics(
    mount: InsideContractMount,
    scoped: ArchitectureContract,
    source_modules: frozenset[str],
    observation: Observation,
    mounts_by_parent: dict[str, InsideContractMount],
    available_by_owner: dict[str, frozenset[str]],
) -> list[Diagnostic]:
    """Check public and planned entries against this mount's physical evidence."""
    imports_by_target = _inside_imports_by_target(
        mount, scoped, source_modules, observation, mounts_by_parent, available_by_owner
    )
    facade_types = _scoped_facade_types(observation, mount.parent_id, source_modules)
    facade_candidates = _inherited_facade_candidates(observation, source_modules, mount.parent_id)
    diagnostics = []
    for component_index, component in enumerate(scoped.components):
        records = imports_by_target.get(component.label, [])
        pointer_root = f"{mount.pointer}/components"
        if component.public is None and records:
            diagnostics.append(
                _diagnostic(
                    "interface.undeclared",
                    f"{pointer_root}/{component_index}",
                    component.label,
                    "The component receives cross-component imports but declares "
                    "no public interface.",
                    "Declare the used modules or names in public.",
                )
            )
        if component.public is not None:
            diagnostics.extend(
                _public_entry_diagnostics(
                    component_index,
                    component,
                    records,
                    source_modules,
                    facade_types,
                    frozenset(),
                    pointer_root,
                    facade_candidates,
                )
            )
        diagnostics.extend(
            _planned_entry_diagnostics(
                component_index,
                component,
                records,
                source_modules,
                facade_types,
                pointer_root,
            )
        )
    return diagnostics


def _inside_parent_policy_diagnostics(mount: InsideContractMount) -> list[Diagnostic]:
    """Reject inside grants that contradict the parent component's rules."""
    parent = mount.parent
    denied = _forbidden_targets(mount.parent_contract, parent)
    required = frozenset(entry.component for entry in parent.requires or ())
    diagnostics = []
    for rule in mount.contract.rules:
        if not isinstance(rule, AllowedDependencyRule):
            continue
        blocked = [rule_id for rule_id, value in denied if in_scope(rule.target, value)]
        absent = _denied_by_absence(mount.parent_contract, parent.label, required, rule.target)
        if absent is not None:
            blocked.append(absent)
        if blocked:
            diagnostics.append(
                _diagnostic(
                    "inside.forbidden_import",
                    mount.pointer,
                    f"{mount.parent_id} -> {rule.target}",
                    f"The inside allows {rule.target}, which {', '.join(sorted(blocked))} "
                    f"forbids {mount.parent_id} at the level above.",
                    "Remove the grant inside, or decide the pair differently above.",
                )
            )
    return diagnostics


def inside_diagnostics(
    root: Path,
    contract: ArchitectureContract,
    config: ScanConfig,
    tree: InsideContractTree | None = None,
    observation: Observation | None = None,
) -> tuple[Diagnostic, ...]:
    """AD-20: validate mounted contracts against parent scope and repository evidence.

    Local public lists govern sibling imports; the mounted component's public list remains
    its outward interface. Parent restrictions apply; external-scope grants are not compared.
    """
    diagnostics: list[Diagnostic] = []
    loaded = tree or _inside_contract_tree(root, config.contract, contract)
    if loaded is None:
        return ()
    scanned_modules = _scanned_modules(observation) if observation is not None else frozenset()
    available_by_owner = {"": scanned_modules}
    mounts_by_parent = {mount.parent_id: mount for mount in loaded.mounts}
    for issue in loaded.issues:
        if issue.input_error is not None:
            error = issue.input_error
            diagnostics.append(
                _diagnostic(
                    "contract.invalid",
                    f"{issue.pointer}{error.pointer}",
                    error.subject,
                    f"The architecture contract cannot be validated: {error}",
                    "Correct the contract declaration at this location.",
                )
            )
        else:
            diagnostics.append(
                _diagnostic(
                    "contract.invalid",
                    issue.pointer,
                    issue.path,
                    f"The contract describing this inside cannot be loaded: {issue.reason}",
                    "Repair the repository-relative contract reference.",
                )
            )
    for mount in loaded.mounts:
        inner = mount.contract
        parent = mount.parent
        pointer = mount.pointer
        available = available_by_owner.get(mount.owner_id, frozenset())
        source_modules = frozenset(
            module
            for module in available
            if module_in_ownership(module, parent.packages, parent.exact_modules or ())
        )
        available_by_owner[mount.parent_id] = source_modules
        scoped = _clip_contract(inner, parent.packages, parent.exact_modules or ())
        for diagnostic in reference_diagnostics(root, config, inner):
            diagnostics.append(replace(diagnostic, pointer=f"{pointer}{diagnostic.pointer or ''}"))
        diagnostics.extend(_inside_source_domain_diagnostics(pointer, parent, inner))
        if observation is not None and any(
            isinstance(rule, InterfaceBoundaryRule) for rule in inner.rules
        ):
            diagnostics.extend(
                _inside_interface_lifecycle_diagnostics(
                    mount,
                    scoped,
                    source_modules,
                    observation,
                    mounts_by_parent,
                    available_by_owner,
                )
            )
        diagnostics.extend(_inside_parent_policy_diagnostics(mount))
    return _sorted(diagnostics)
