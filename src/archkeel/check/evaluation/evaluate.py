# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Evaluate architecture rules and topology over immutable source facts."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from collections.abc import Set as AbstractSet
from dataclasses import dataclass, replace
from pathlib import Path
from types import MappingProxyType
from typing import Any, TypeAlias

from archkeel.ir.codec import InsideContractMount
from archkeel.ir.facts import (
    BuiltinTarget,
    ConstructCapability,
    ExternalPackageTarget,
    SourceFacts,
    UnresolvedTarget,
)
from archkeel.ir.facts_codec import (
    ProtocolError,
    RawEvidence,
    RawRecord,
    classified,
    raw_evidence,
    raw_record,
)
from archkeel.ir.facts_validation import validate_source_facts
from archkeel.ir.model import (
    ArchitectureContract,
    ContractComponent,
    ContractDeclarations,
    EvidenceClass,
    InterfaceBoundaryRule,
    in_scope,
    module_in_ownership,
    stable_id,
)
from archkeel.ir.profiles import Profile, profile_for
from archkeel.ir.type_shapes import TypeShapeIndex

from .imports import strip_internal_reexport_facts
from .rules import (
    boundary_type_limits,
    construct_capability_limits,
    exports_by_module,
    facade_signature_types,
    profile_failures,
    rule_subject_failures,
    rule_violations,
    symbol_limits,
)
from .state import evaluate_contexts
from .topology import (
    aggregate_edges,
    component_scope_observations,
    cycle_sections,
    declared_path_observations,
    module_records,
    package_records,
    transitive_path_records,
)

InsideRuleResults: TypeAlias = tuple[
    list[RawRecord],
    list[RawRecord],
    list[RawRecord],
    list[RawRecord],
    list[RawRecord],
    list[RawRecord],
]

# AD-2: coverage mixes counts with RawRecord failures, which RawJson cannot hold.
CoveragePayload: TypeAlias = dict[str, Any]


@dataclass
class ScanResult:
    source_digest: str
    type_shapes: TypeShapeIndex
    coverage: CoveragePayload
    evidence: list[RawEvidence]
    scope_observations: list[RawRecord]
    packages: list[RawRecord]
    modules: list[RawRecord]
    symbols: list[RawRecord]
    imports: list[RawRecord]
    dependency_edges: list[RawRecord]
    transitive_paths: list[RawRecord]
    path_observations: list[RawRecord]
    cycles: list[RawRecord]
    calls: list[RawRecord]
    references: list[RawRecord]
    bindings: list[RawRecord]
    typing_signals: list[RawRecord]
    constructs: list[RawRecord]
    contexts: list[RawRecord]
    context_evidence: list[RawRecord]
    violations: list[RawRecord]
    unknowns: list[RawRecord]


def coverage_payload(
    *,
    paths: Sequence[Path],
    files_read: int,
    files_parsed: int,
    failures: Sequence[RawRecord],
    rule_failures: Sequence[RawRecord],
    calls: Sequence[RawRecord],
    calls_measured: bool = True,
) -> CoveragePayload:
    """Summarize file discovery, rule and call-resolution coverage for one scan."""
    calls_analyzed = len(calls)
    calls_resolved = sum(1 for call in calls if call["data"]["status"] == "resolved")
    calls_partially_resolved = sum(
        1 for call in calls if call["data"]["status"] == "partially_resolved"
    )
    calls_unresolved = sum(1 for call in calls if call["data"]["status"] == "unresolved")
    return {
        "status": "FAIL" if failures or rule_failures or not paths else "PASS",
        "rules": "FAIL" if rule_failures else "PASS",
        "files_discovered": len(paths),
        "files_read": files_read,
        "files_parsed": files_parsed,
        "ast_coverage_percent": round((files_parsed / len(paths) * 100), 2) if paths else 0.0,
        "failures": [
            *sorted(
                failures,
                key=lambda item: (
                    item["data"].get("file", ""),
                    item["data"].get("line", 0),
                    item["kind"],
                ),
            ),
            *sorted(rule_failures, key=lambda item: item["id"]),
        ],
        "calls_analyzed": calls_analyzed if calls_measured else None,
        "calls_resolved": calls_resolved if calls_measured else None,
        "calls_partially_resolved": calls_partially_resolved if calls_measured else None,
        "calls_unresolved": calls_unresolved if calls_measured else None,
        "call_resolution_percent": (
            round(calls_resolved / calls_analyzed * 100, 2) if calls_analyzed else 0.0
        )
        if calls_measured
        else None,
    }


def _analysis_limits(
    calls: Sequence[RawRecord], declarations: ContractDeclarations, namespace: str
) -> list[RawRecord]:
    """Build the two UNKNOWN records naming the scanner's structural analysis limits."""
    return [
        classified(
            item_id="UNKNOWN-PYTHON-DYNAMIC-CALLS",
            evidence_class=EvidenceClass.UNKNOWN,
            area="call_hierarchy",
            kind="dynamic_call_limit",
            title="Python dynamic behavior prevents a complete call graph",
            subjects=[namespace],
            data={
                "unresolved_calls": sum(
                    1 for call in calls if call["data"]["status"] == "unresolved"
                )
            },
        ),
        classified(
            item_id="UNKNOWN-CONTEXT-DATAFLOW",
            evidence_class=EvidenceClass.UNKNOWN,
            area="contexts_state",
            kind="context_alias_limit",
            title="Context read/write topology excludes unproven dynamic aliases",
            subjects=sorted(declarations.context_roots),
            data={
                "reason": (
                    "The scanner follows direct annotations, constructor bindings, "
                    "and self-field access only"
                )
            },
        ),
    ]


def api_surface_limits(
    declarations: ContractDeclarations,
    symbols: Sequence[RawRecord],
    module_all_exports: Mapping[str, AbstractSet[str]],
    reason: str,
) -> list[RawRecord]:
    """UNKNOWN records for a `public_api` name only `__all__` or a scanned symbol could settle.

    A module the scan never saw is `check`'s own `api_surface.missing`, and one that declares
    `__all__` is proven or disproven there too (AD-71): neither reaches here. What is left is a
    module with no `__all__`, where a name absent from `symbols` is not proof of absence - it
    may still be a constant or a type alias - so the analyzer records the gap as UNKNOWN rather
    than let a module's silence pass a typo (AD-72).
    """
    top_level = {
        (item["data"]["module"], item["data"]["name"])
        for item in symbols
        if item["data"]["parent"] is None
    }
    limits = []
    for entry in declarations.public_api:
        module, colon, name = entry.partition(":")
        if not colon or module not in module_all_exports:
            continue
        if module_all_exports[module] or (module, name) in top_level:
            continue
        limits.append(
            classified(
                item_id=stable_id("UNKNOWN-API-SURFACE", module, name),
                evidence_class=EvidenceClass.UNKNOWN,
                area="api_surface",
                kind="api_surface_limit",
                title="Public API name cannot be proven present or absent",
                subjects=[entry],
                data={"module": module, "name": name, "reason": reason},
            )
        )
    return limits


def _inside_mount_scope(
    mount: InsideContractMount,
    owner_levels: Sequence[ArchitectureContract],
    modules: Sequence[RawRecord],
    available: frozenset[str],
) -> tuple[ContractComponent, ArchitectureContract, frozenset[str], list[RawRecord]]:
    owner_contract = owner_levels[0] if owner_levels else None
    parent = _inside_parent_component(mount, owner_contract)
    return (
        parent,
        *_inside_source_domain(parent, mount.contract, modules, mount.parent_id, available),
    )


def _mount_facade_signature_types(
    symbols: Sequence[RawRecord],
    imports: Sequence[RawRecord],
    mount: InsideContractMount,
    scoped: ArchitectureContract,
    source_modules: frozenset[str],
    exports_by_module: dict[str, frozenset[str]],
    uncertain_reexport_origins: dict[str, frozenset[str]],
    owner_levels: Sequence[ArchitectureContract],
    *,
    type_shapes: TypeShapeIndex,
) -> list[RawRecord]:
    if not any(isinstance(rule, InterfaceBoundaryRule) for rule in scoped.rules):
        return list(symbols)
    return facade_signature_types(
        symbols,
        imports,
        scoped,
        exports_by_module,
        uncertain_reexport_origins,
        source_modules=source_modules,
        scope_id=mount.parent_id,
        ancestor_contracts=owner_levels,
        type_shapes=type_shapes,
    )


def _inside_rule_results(
    inside_contracts: Sequence[InsideContractMount],
    *,
    type_shapes: TypeShapeIndex,
    construct_capabilities: tuple[ConstructCapability, ...],
    root_contract: ArchitectureContract | None = None,
    imports: Sequence[RawRecord],
    typing_signals: Sequence[RawRecord],
    constructs: Sequence[RawRecord],
    packages: Sequence[RawRecord],
    modules: Sequence[RawRecord],
    symbols: Sequence[RawRecord],
    blank_modules: frozenset[str],
    module_cycles: Sequence[RawRecord],
    profile: Profile,
    exports_by_module: dict[str, frozenset[str]],
    uncertain_reexport_origins: dict[str, frozenset[str]],
    scanned_modules: set[str],
    stable_bindings_by_module: dict[str, frozenset[str]],
    evidence: dict[str, RawEvidence],
    cycle_scan_roots: tuple[str, ...] = (),
    cycle_namespace: str = "",
) -> InsideRuleResults:
    """Evaluate nested rules with the root scan's facts, limited to each parent's modules."""
    violations: list[RawRecord] = []
    unknowns: list[RawRecord] = []
    failures: list[RawRecord] = []
    assessments: list[RawRecord] = []
    allowances: list[RawRecord] = []
    all_modules = frozenset(module["data"]["qualified_name"] for module in modules)
    available_by_owner = {"": all_modules}
    contract_by_owner = {"": root_contract} if root_contract is not None else {}
    mounts_by_parent = {mount.parent_id: mount for mount in inside_contracts}
    for mount in inside_contracts:
        available = available_by_owner.get(mount.owner_id, frozenset())
        owner_levels = _inside_owner_levels(mount, mounts_by_parent, contract_by_owner)
        parent, scoped, source_modules, scope_failures = _inside_mount_scope(
            mount, owner_levels, modules, available
        )
        available_by_owner[mount.parent_id] = source_modules
        contract_by_owner[mount.parent_id] = scoped
        failures.extend(scope_failures)
        results = _evaluate_inside_contract(
            parent,
            scoped,
            source_modules,
            ancestor_contracts=owner_levels,
            imports=imports,
            typing_signals=typing_signals,
            constructs=constructs,
            packages=packages,
            modules=modules,
            symbols=symbols,
            blank_modules=blank_modules,
            module_cycles=module_cycles,
            profile=profile,
            exports_by_module=exports_by_module,
            uncertain_reexport_origins=uncertain_reexport_origins,
            scanned_modules=scanned_modules,
            stable_bindings_by_module=stable_bindings_by_module,
            evidence=evidence,
            assessments=assessments,
            cycle_scan_roots=cycle_scan_roots,
            cycle_namespace=cycle_namespace,
            type_shapes=type_shapes,
            construct_capabilities=construct_capabilities,
        )
        if "symbols" not in profile.absent_sections:
            symbols = _mount_facade_signature_types(
                symbols,
                imports,
                mount,
                scoped,
                source_modules,
                exports_by_module,
                uncertain_reexport_origins,
                owner_levels,
                type_shapes=type_shapes,
            )
        violations.extend(results[0])
        unknowns.extend(results[1])
        failures.extend(results[2])
        allowances.extend(results[3])
    return _sort_inside_rule_results(
        violations, unknowns, failures, assessments, allowances, symbols
    )


def _sort_inside_rule_results(
    violations: list[RawRecord],
    unknowns: list[RawRecord],
    failures: list[RawRecord],
    assessments: list[RawRecord],
    allowances: list[RawRecord],
    symbols: Sequence[RawRecord],
) -> InsideRuleResults:
    """Keep nested result ordering stable across mounts."""
    return (
        sorted(violations, key=lambda item: item["id"]),
        sorted(unknowns, key=lambda item: item["id"]),
        sorted(failures, key=lambda item: item["id"]),
        sorted(assessments, key=lambda item: item["id"]),
        sorted(allowances, key=lambda item: item["id"]),
        list(symbols),
    )


def _inside_parent_component(
    mount: InsideContractMount,
    owner_contract: ArchitectureContract | None,
) -> ContractComponent:
    """Resolve a mount's owner from the already-clipped ancestor contract."""
    if owner_contract is not None:
        parent = next(
            (item for item in owner_contract.components if item.id == mount.parent.id), None
        )
        if parent is not None:
            return parent
    return replace(mount.parent, packages=()) if mount.owner_id else mount.parent


def _inside_owner_levels(
    mount: InsideContractMount,
    mounts_by_parent: dict[str, InsideContractMount],
    contract_by_owner: dict[str, ArchitectureContract],
) -> tuple[ArchitectureContract, ...]:
    """Return the current owner contract and its already-clipped ancestors, nearest first."""
    levels = []
    owner_id = mount.owner_id
    while True:
        if contract := contract_by_owner.get(owner_id):
            levels.append(contract)
        if not owner_id:
            if not mount.owner_id and not levels:
                levels.append(mount.parent_contract)
            break
        owner = mounts_by_parent.get(owner_id)
        if owner is None:
            break
        owner_id = owner.owner_id
    return tuple(levels)


def _inside_source_domain(
    parent: ContractComponent,
    declared: ArchitectureContract,
    modules: Sequence[RawRecord],
    parent_id: str,
    available_modules: frozenset[str],
) -> tuple[ArchitectureContract, frozenset[str], list[RawRecord]]:
    """Clip child ownership claims to the parent's physical packages and report what was cut."""
    roots = parent.packages
    exact_roots = parent.exact_modules or ()
    source_modules = frozenset(
        module["data"]["qualified_name"]
        for module in modules
        if module["data"]["qualified_name"] in available_modules
        and module_in_ownership(module["data"]["qualified_name"], roots, exact_roots)
    )
    components = []
    failures = []
    for component in declared.components:
        packages = tuple(
            package
            for package in component.packages
            if any(in_scope(package, root) for root in roots)
        )
        exact_modules = tuple(
            module
            for module in component.exact_modules or ()
            if module in exact_roots or any(in_scope(module, root) for root in roots)
        )
        outside = sorted(set(component.packages) - set(packages))
        outside_exact = sorted(set(component.exact_modules or ()) - set(exact_modules))
        if outside or outside_exact:
            claims = [*outside, *outside_exact]
            failures.append(
                classified(
                    item_id=stable_id("UNKNOWN-INSIDE-SOURCE-DOMAIN", parent_id, component.id),
                    evidence_class=EvidenceClass.UNKNOWN,
                    area="analysis_coverage",
                    kind="inside_source_domain_incomplete",
                    title=(f"{component.label} claims {', '.join(claims)} outside {parent.label}"),
                    subjects=[component.label, *claims],
                    rule_ids=[rule.id for rule in declared.rules],
                    data={
                        "parent_id": parent_id,
                        "packages": outside,
                        "exact_modules": outside_exact,
                    },
                )
            )
        components.append(
            replace(component, packages=packages, exact_modules=exact_modules or None)
        )
    return replace(declared, components=tuple(components)), source_modules, failures


def _evaluate_inside_contract(
    parent: ContractComponent,
    scoped: ArchitectureContract,
    source_modules: frozenset[str],
    *,
    type_shapes: TypeShapeIndex,
    construct_capabilities: tuple[ConstructCapability, ...],
    ancestor_contracts: Sequence[ArchitectureContract],
    imports: Sequence[RawRecord],
    typing_signals: Sequence[RawRecord],
    constructs: Sequence[RawRecord],
    packages: Sequence[RawRecord],
    modules: Sequence[RawRecord],
    symbols: Sequence[RawRecord],
    blank_modules: frozenset[str],
    module_cycles: Sequence[RawRecord],
    profile: Profile,
    exports_by_module: dict[str, frozenset[str]],
    uncertain_reexport_origins: dict[str, frozenset[str]],
    scanned_modules: set[str],
    stable_bindings_by_module: dict[str, frozenset[str]],
    evidence: dict[str, RawEvidence],
    assessments: list[RawRecord],
    cycle_scan_roots: tuple[str, ...],
    cycle_namespace: str,
) -> tuple[list[RawRecord], list[RawRecord], list[RawRecord], list[RawRecord]]:
    """Run shared evaluators for one clipped contract over one already-collected scan."""
    failures = rule_subject_failures(
        tuple(rule for rule in scoped.rules if rule.kind not in profile.unsupported_rules),
        set(source_modules),
        target_module_names={module["data"]["qualified_name"] for module in modules},
        symbols=symbols,
        imports=imports,
        contract=scoped,
        exports_by_module=exports_by_module,
        uncertain_reexport_origins=uncertain_reexport_origins,
        stable_bindings_by_module=stable_bindings_by_module,
        sdk_libraries=profile.sdk_libraries,
        source_modules=source_modules,
        type_shapes=type_shapes,
    )
    failures.extend(profile_failures(scoped, profile, construct_capabilities))
    violations, allowance_facts = rule_violations(
        imports=imports,
        typing_signals=typing_signals,
        constructs=constructs,
        packages=packages,
        modules=modules,
        symbols=symbols,
        blank_modules=blank_modules,
        module_cycles=module_cycles,
        contract=scoped,
        exports_by_module=exports_by_module,
        profile=profile,
        uncertain_reexport_origins=uncertain_reexport_origins,
        source_modules=source_modules,
        source_roots=parent.packages,
        source_exact_modules=parent.exact_modules or (),
        assessment_facts=assessments,
        assessment_parent=parent.label,
        ancestor_contracts=ancestor_contracts,
        cycle_scan_roots=cycle_scan_roots,
        cycle_namespace=cycle_namespace,
        type_shapes=type_shapes,
    )
    unknowns = (
        boundary_type_limits(
            symbols,
            imports,
            scoped,
            exports_by_module,
            evidence,
            uncertain_reexport_origins,
            scanned_modules,
            stable_bindings_by_module,
            source_modules,
            ancestor_contracts,
            type_shapes=type_shapes,
        )
        if "symbols" not in profile.absent_sections
        else []
    )
    unknowns.extend(symbol_limits(imports, scoped, exports_by_module, source_modules))
    unknowns.extend(construct_capability_limits(scoped, construct_capabilities, parent.label))
    return violations, unknowns, failures, allowance_facts


def evaluate_source(
    facts: SourceFacts,
    contract: ArchitectureContract,
    *,
    roots: tuple[str, ...],
    namespace: str,
    inside_contracts: Sequence[InsideContractMount] = (),
) -> ScanResult:
    """Evaluate a contract against one immutable collection without language parser access."""
    try:
        validate_source_facts(facts)
    except ValueError as error:
        raise ProtocolError(str(error)) from error
    for file in facts.files:
        if (
            not in_scope(file.module, namespace)
            or not in_scope(file.module, file.package)
            or not (in_scope(file.package, namespace) or in_scope(namespace, file.package))
        ):
            raise ProtocolError("selected source identity is outside the configured namespace")
    profile = profile_for(facts.profile)
    is_python = facts.profile == "archkeel-python-analyzer"
    required = (
        {
            "symbols",
            "imports",
            "calls",
            "references",
            "bindings",
            "typing_signals",
            "constructs",
            "unknowns",
        }
        if is_python
        else {"imports", "unknowns"}
    )
    if set(facts.capabilities.sections) != required:
        raise ProtocolError("source sections do not match the registered profile")
    sections = {
        section.name: [raw_record(record) for record in section.records]
        for section in facts.sections
    }
    parsed = facts.files
    paths = tuple(Path(path) for path in facts.coverage.selected_files)
    failures = [raw_record(record) for record in facts.coverage.gaps]
    source_unknowns = sections.get("unknowns", [])
    stable_bindings_by_module = {module.module: module.stable_bindings for module in parsed}
    evidence = {entry.id: raw_evidence(entry) for entry in facts.evidence}
    module_names = {module.module for module in parsed}
    module_evidence = {module.module: module.evidence_id for module in parsed}
    module_all_exports = {module.module: module.all_exports for module in parsed}
    uncertain_reexport_origins = {
        binding: frozenset(origins) for binding, origins in facts.uncertain_reexports
    }
    type_shapes = MappingProxyType(dict(facts.type_shapes))
    imports = sections.get("imports", [])
    unresolved_targets = {
        target.import_id: target for target in facts.imports if isinstance(target, UnresolvedTarget)
    }
    unresolved_imports = [item for item in imports if item["id"] in unresolved_targets]
    imports = [item for item in imports if item["id"] not in unresolved_targets]
    for item in unresolved_imports:
        unresolved = unresolved_targets[item["id"]]
        item["data"]["resolution"] = "unresolved"
        failures.append(
            classified(
                item_id=stable_id("UNKNOWN-IMPORT", item["id"]),
                evidence_class=EvidenceClass.UNKNOWN,
                area="analysis_coverage",
                kind="unresolved-import",
                title=unresolved.reason,
                subjects=item["subjects"],
                evidence_ids=item["evidence_ids"],
                fact_ids=[item["id"]],
                data={"source_module": item["data"]["source_module"], "reason": unresolved.reason},
            )
        )
    if facts.profile == "archkeel-typescript-imports":
        targets = {target.import_id: target for target in facts.imports}
        for item in imports:
            target = targets[item["id"]]
            if isinstance(target, ExternalPackageTarget):
                item["data"]["external_package"] = target.package
            elif isinstance(target, BuiltinTarget):
                item["data"]["builtin_target"] = True

    symbols = sections.get("symbols", [])
    calls = sections.get("calls", [])
    references = sections.get("references", [])
    bindings = sections.get("bindings", [])
    typing_signals = sections.get("typing_signals", [])
    constructs = sections.get("constructs", [])
    declarations = contract.declarations or ContractDeclarations()
    contexts, context_evidence, used_evidence = (
        evaluate_contexts(
            facts.state,
            symbols,
            imports,
            calls,
            declarations.context_roots,
            facts.candidate_evidence,
        )
        if is_python
        else ([], [], ())
    )
    evidence.update((entry.id, raw_evidence(entry)) for entry in used_evidence)

    module_edges, module_edge_pairs = aggregate_edges(
        imports, level="module", internal_modules=module_names, namespace=namespace
    )
    package_edges, package_edge_pairs = aggregate_edges(
        imports, level="package", internal_modules=module_names, namespace=namespace
    )
    dependency_edges = sorted([*package_edges, *module_edges], key=lambda item: item["id"])
    path_observations = declared_path_observations(declarations.paths, package_edges)

    packages = sorted({module.package for module in parsed})
    package_facts = package_records(parsed, packages, package_edge_pairs)
    module_facts = module_records(parsed, module_names, module_edge_pairs, symbols, module_evidence)
    if "symbols" in profile.absent_sections:
        for module in module_facts:
            module["data"]["symbol_count"] = None
    # boundary_types reads the declared facade, not a naming convention (AD-63): a rule whose
    # source matches a scanned module can still have zero functions to check, so
    # rule_subject_failures needs symbols and the contract to see that, not module_names alone
    # (issue #56). Computed here, after module_facts exists, and handed to rule_violations too,
    # so the two share one answer to "what does __all__ narrow" instead of two computations.
    facade_exports = exports_by_module(module_facts)
    # AD-65: a type a declared facade signature names reaches the boundary without any import,
    # so the resolution boundary_types already runs is recorded on the facade function itself
    # and travels to validate's unused-entry check in the observation, not in a second copy.
    if "symbols" not in profile.absent_sections:
        symbols = facade_signature_types(
            symbols,
            imports,
            contract,
            facade_exports,
            uncertain_reexport_origins,
            type_shapes=type_shapes,
        )
    rule_failures = rule_subject_failures(
        tuple(rule for rule in contract.rules if rule.kind not in profile.unsupported_rules),
        module_names,
        symbols=symbols,
        imports=imports,
        contract=contract,
        exports_by_module=facade_exports,
        uncertain_reexport_origins=uncertain_reexport_origins,
        stable_bindings_by_module=stable_bindings_by_module,
        type_shapes=type_shapes,
        sdk_libraries=profile.sdk_libraries
        | frozenset(target.name for target in facts.imports if isinstance(target, BuiltinTarget)),
    )
    rule_failures.extend(profile_failures(contract, profile, facts.capabilities.constructs))
    scope_observations = component_scope_observations(
        components=contract.components,
        modules=module_facts,
        module_edges=module_edges,
        coverage_failures=failures,
    )

    transitive_records = transitive_path_records(packages, package_edge_pairs)
    module_cycles, cycles = cycle_sections(
        modules=module_facts,
        packages=packages,
        module_edges=module_edges,
        module_edge_pairs=module_edge_pairs,
        package_edges=package_edges,
        package_edge_pairs=package_edge_pairs,
    )
    blank_modules = frozenset(module.module for module in parsed if module.blank)
    violations, boundary_allowances = rule_violations(
        imports=imports,
        typing_signals=typing_signals,
        constructs=constructs,
        packages=package_facts,
        modules=module_facts,
        symbols=symbols,
        blank_modules=blank_modules,
        # AD-98: a module-level cycle rule judges the SCCs this report measures, not a copy.
        module_cycles=module_cycles,
        contract=contract,
        exports_by_module=facade_exports,
        profile=profile,
        uncertain_reexport_origins=uncertain_reexport_origins,
        assessment_facts=scope_observations,
        assessment_parent="root",
        cycle_scan_roots=roots if facts.coverage.full_scope and not failures else (),
        cycle_namespace=namespace,
        type_shapes=type_shapes,
    )
    (
        inside_violations,
        inside_unknowns,
        inside_failures,
        inside_assessments,
        inside_allowances,
        symbols,
    ) = _inside_rule_results(
        inside_contracts,
        construct_capabilities=facts.capabilities.constructs,
        root_contract=contract,
        imports=imports,
        typing_signals=typing_signals,
        constructs=constructs,
        packages=package_facts,
        modules=module_facts,
        symbols=symbols,
        blank_modules=blank_modules,
        module_cycles=module_cycles,
        profile=profile,
        exports_by_module=facade_exports,
        uncertain_reexport_origins=uncertain_reexport_origins,
        scanned_modules=module_names,
        stable_bindings_by_module=stable_bindings_by_module,
        evidence=evidence,
        cycle_scan_roots=roots if facts.coverage.full_scope and not failures else (),
        cycle_namespace=namespace,
        type_shapes=type_shapes,
    )
    violations = sorted([*violations, *inside_violations], key=lambda item: item["id"])
    rule_failures = sorted([*rule_failures, *inside_failures], key=lambda item: item["id"])
    scope_observations = sorted(
        [*scope_observations, *inside_assessments], key=lambda item: item["id"]
    )
    typing_signals = sorted(
        [*typing_signals, *boundary_allowances, *inside_allowances], key=lambda item: item["id"]
    )

    unknowns = [
        *(_analysis_limits(calls, declarations, namespace) if is_python else []),
        *source_unknowns,
        *symbol_limits(imports, contract, facade_exports),
        *construct_capability_limits(contract, facts.capabilities.constructs, "root"),
        # AD-67: a boundary position the rule could not decide is reported, not silent. It
        # joins the two structural limits above and never `coverage.failures`, because it
        # says how much of a facade was decided, not that the scan was incomplete.
        *(
            boundary_type_limits(
                symbols,
                imports,
                contract,
                facade_exports,
                evidence,
                uncertain_reexport_origins,
                module_names,
                stable_bindings_by_module,
                type_shapes=type_shapes,
            )
            if "symbols" not in profile.absent_sections
            else []
        ),
        *api_surface_limits(
            declarations,
            symbols,
            module_all_exports,
            "The module declares no __all__ and the scan records no class or function of this "
            "name.",
        ),
        *inside_unknowns,
        *failures,
        *rule_failures,
    ]

    coverage = coverage_payload(
        paths=paths,
        files_read=facts.coverage.files_read,
        files_parsed=facts.coverage.files_parsed,
        failures=failures,
        rule_failures=rule_failures,
        calls=calls,
        calls_measured="calls_unresolved" not in profile.unmeasured,
    )

    strip_internal_reexport_facts(imports)
    return ScanResult(
        type_shapes=type_shapes,
        source_digest=facts.source.source_digest,
        coverage=coverage,
        evidence=sorted(evidence.values(), key=lambda item: item["id"]),
        scope_observations=scope_observations,
        packages=sorted(package_facts, key=lambda item: item["id"]),
        modules=sorted(module_facts, key=lambda item: item["id"]),
        symbols=symbols,
        imports=sorted([*imports, *unresolved_imports], key=lambda item: item["id"]),
        dependency_edges=dependency_edges,
        transitive_paths=sorted(transitive_records, key=lambda item: item["id"]),
        path_observations=path_observations,
        cycles=cycles,
        calls=calls,
        references=references,
        bindings=bindings,
        typing_signals=typing_signals,
        constructs=constructs,
        contexts=contexts,
        context_evidence=context_evidence,
        violations=violations,
        unknowns=sorted(
            {item["id"]: item for item in unknowns}.values(), key=lambda item: item["id"]
        ),
    )
