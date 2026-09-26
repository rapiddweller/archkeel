# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Conservative deterministic AST scanner for the Python architecture profile."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from collections.abc import Set as AbstractSet
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, TypeAlias

from archkeel.ir.codec import InsideContractMount
from archkeel.ir.model import (
    ArchitectureContract,
    ContractComponent,
    ContractDeclarations,
    EvidenceClass,
    in_scope,
    stable_id,
)
from archkeel.ir.profiles import PYTHON, Profile

from .bindings import collect_bindings
from .calls import collect_calls
from .constructs import collect_constructs
from .contexts import collect_contexts, private_attribute_limits
from .dependencies import (
    aggregate_edges,
    component_scope_observations,
    cycle_sections,
    declared_path_observations,
    module_records,
    package_records,
    transitive_path_records,
)
from .imports import collect_imports, resolve_reexports, strip_internal_reexport_facts
from .records import RawEvidence, RawRecord, classified
from .references import collect_references
from .resolve import build_symbol_index
from .source import file_evidence, parse_sources, stable_direct_module_bindings
from .symbols import collect_symbols
from .typing_signals import collect_typing_signals
from .violations import (
    boundary_type_limits,
    exports_by_module,
    facade_signature_types,
    profile_failures,
    rule_subject_failures,
    rule_violations,
)

# AD-2: coverage mixes counts with RawRecord failures, which RawJson cannot hold.
CoveragePayload: TypeAlias = dict[str, Any]


@dataclass
class ScanResult:
    source_digest: str
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


def iter_source_paths(root: Path, *, roots: tuple[str, ...]) -> tuple[Path, ...]:
    return tuple(
        sorted(
            path
            for source_root in (root / source for source in roots)
            if source_root.is_dir()
            for path in source_root.rglob("*.py")
            if "__pycache__" not in path.parts
        )
    )


def coverage_payload(
    *,
    paths: Sequence[Path],
    files_read: int,
    files_parsed: int,
    failures: Sequence[RawRecord],
    rule_failures: Sequence[RawRecord],
    calls: Sequence[RawRecord],
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
                key=lambda item: (item["data"]["file"], item["data"]["line"], item["kind"]),
            ),
            *sorted(rule_failures, key=lambda item: item["id"]),
        ],
        "calls_analyzed": calls_analyzed,
        "calls_resolved": calls_resolved,
        "calls_partially_resolved": calls_partially_resolved,
        "calls_unresolved": calls_unresolved,
        "call_resolution_percent": round(calls_resolved / calls_analyzed * 100, 2)
        if calls_analyzed
        else 0.0,
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


def _inside_rule_results(
    inside_contracts: Sequence[InsideContractMount],
    *,
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
) -> tuple[list[RawRecord], list[RawRecord], list[RawRecord], list[RawRecord], list[RawRecord]]:
    """Evaluate nested rules with the root scan's facts, limited to each parent's modules."""
    violations: list[RawRecord] = []
    unknowns: list[RawRecord] = []
    failures: list[RawRecord] = []
    assessments: list[RawRecord] = []
    allowances: list[RawRecord] = []
    all_modules = frozenset(module["data"]["qualified_name"] for module in modules)
    available_by_owner = {"": all_modules}
    mounts_by_parent = {mount.parent_id: mount for mount in inside_contracts}
    for mount in inside_contracts:
        available = available_by_owner.get(mount.owner_id, frozenset())
        scoped, source_modules, scope_failures = _inside_source_domain(
            mount.parent, mount.contract, modules, mount.parent_id, available
        )
        available_by_owner[mount.parent_id] = source_modules
        failures.extend(scope_failures)
        external_components = _inside_external_components(
            mount, mounts_by_parent, root_contract, scoped
        )
        results = _evaluate_inside_contract(
            mount.parent,
            scoped,
            source_modules,
            external_components=external_components,
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
        )
        violations.extend(results[0])
        unknowns.extend(results[1])
        failures.extend(results[2])
        allowances.extend(results[3])
    return (
        sorted(violations, key=lambda item: item["id"]),
        sorted(unknowns, key=lambda item: item["id"]),
        sorted(failures, key=lambda item: item["id"]),
        sorted(assessments, key=lambda item: item["id"]),
        sorted(allowances, key=lambda item: item["id"]),
    )


def _inside_source_domain(
    parent: ContractComponent,
    declared: ArchitectureContract,
    modules: Sequence[RawRecord],
    parent_id: str,
    available_modules: frozenset[str],
) -> tuple[ArchitectureContract, frozenset[str], list[RawRecord]]:
    """Clip child ownership claims to the parent's physical packages and report what was cut."""
    roots = parent.packages
    source_modules = frozenset(
        module["data"]["qualified_name"]
        for module in modules
        if module["data"]["qualified_name"] in available_modules
        and any(in_scope(module["data"]["qualified_name"], root) for root in roots)
    )
    components = []
    failures = []
    for component in declared.components:
        packages = tuple(
            package
            for package in component.packages
            if any(in_scope(package, root) for root in roots)
        )
        outside = sorted(set(component.packages) - set(packages))
        if outside:
            failures.append(
                classified(
                    item_id=stable_id("UNKNOWN-INSIDE-SOURCE-DOMAIN", parent_id, component.id),
                    evidence_class=EvidenceClass.UNKNOWN,
                    area="analysis_coverage",
                    kind="inside_source_domain_incomplete",
                    title=(f"{component.label} claims {', '.join(outside)} outside {parent.label}"),
                    subjects=[component.label, *outside],
                    rule_ids=[rule.id for rule in declared.rules],
                    data={"parent_id": parent_id, "packages": outside},
                )
            )
        components.append(replace(component, packages=packages))
    return replace(declared, components=tuple(components)), source_modules, failures


def _inside_external_components(
    mount: InsideContractMount,
    mounts_by_parent: dict[str, InsideContractMount],
    root_contract: ArchitectureContract | None,
    scoped: ArchitectureContract,
) -> tuple[ContractComponent, ...]:
    """Keep established sibling owners visible without promoting the parent's scope."""
    contracts = [mount.parent_contract]
    owner_id = mount.owner_id
    while owner_id:
        owner = mounts_by_parent.get(owner_id)
        if owner is None:
            break
        contracts.append(owner.parent_contract)
        owner_id = owner.owner_id
    if root_contract is not None and all(item is not root_contract for item in contracts):
        contracts.append(root_contract)

    occupied = [
        *mount.parent.packages,
        *(package for component in scoped.components for package in component.packages),
    ]
    selected: list[ContractComponent] = []
    for contract in contracts:
        for component in contract.components:
            if any(
                in_scope(package, root) or in_scope(root, package)
                for package in component.packages
                for root in occupied
            ):
                continue
            selected.append(component)
            occupied.extend(component.packages)
    return tuple(selected)


def _evaluate_inside_contract(
    parent: ContractComponent,
    scoped: ArchitectureContract,
    source_modules: frozenset[str],
    *,
    external_components: tuple[ContractComponent, ...],
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
    )
    failures.extend(profile_failures(scoped, profile))
    boundary_contract = replace(scoped, components=(*scoped.components, *external_components))
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
        assessment_facts=assessments,
        assessment_parent=parent.label,
        boundary_contract=boundary_contract,
    )
    unknowns = boundary_type_limits(
        symbols,
        imports,
        boundary_contract,
        exports_by_module,
        evidence,
        uncertain_reexport_origins,
        scanned_modules,
        stable_bindings_by_module,
        source_modules,
    )
    return violations, unknowns, failures, allowance_facts


def scan_repository(
    root: Path,
    contract: ArchitectureContract,
    *,
    source_paths: Sequence[Path] | None = None,
    roots: tuple[str, ...],
    namespace: str,
    inside_contracts: Sequence[InsideContractMount] = (),
) -> ScanResult:
    """Scan production Python and return the deterministic observed model sections."""
    paths = (
        tuple(source_paths) if source_paths is not None else iter_source_paths(root, roots=roots)
    )
    paths = tuple(sorted(paths, key=lambda path: path.relative_to(root).as_posix()))
    parsed_sources = parse_sources(paths, root=root, namespace=namespace)
    parsed = parsed_sources.modules
    failures = parsed_sources.failures
    stable_bindings_by_module = {
        module.module: stable_direct_module_bindings(module) for module in parsed
    }
    evidence: dict[str, RawEvidence] = {}

    module_names = {module.module for module in parsed}
    module_evidence = {
        module.module: file_evidence(evidence, module.rel_path, module.lines) for module in parsed
    }
    imports = collect_imports(parsed, module_names, evidence, namespace=namespace)

    # Exports exist only after the import loop, and re-exports must resolve before symbols.
    module_all_exports = {module.module: module.all_exports for module in parsed}
    uncertain_reexport_origins = resolve_reexports(imports, module_all_exports, parsed)

    symbols, symbol_nodes, symbol_owners = collect_symbols(parsed, evidence)
    symbol_index = build_symbol_index(symbols)
    calls = collect_calls(parsed, symbol_index, evidence)
    references = collect_references(parsed, symbol_index, evidence)
    bindings = collect_bindings(parsed, evidence)

    typing_signals = collect_typing_signals(parsed, calls, symbols, imports, evidence)
    constructs = collect_constructs(parsed, evidence)
    declarations = contract.declarations or ContractDeclarations()
    contexts, context_evidence = collect_contexts(
        parsed,
        symbols,
        symbol_nodes,
        symbol_owners,
        imports,
        calls,
        declarations.context_roots,
        evidence,
    )

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
    # boundary_types reads the declared facade, not a naming convention (AD-63): a rule whose
    # source matches a scanned module can still have zero functions to check, so
    # rule_subject_failures needs symbols and the contract to see that, not module_names alone
    # (issue #56). Computed here, after module_facts exists, and handed to rule_violations too,
    # so the two share one answer to "what does __all__ narrow" instead of two computations.
    facade_exports = exports_by_module(module_facts)
    # AD-65: a type a declared facade signature names reaches the boundary without any import,
    # so the resolution boundary_types already runs is recorded on the facade function itself
    # and travels to validate's unused-entry check in the observation, not in a second copy.
    symbols = facade_signature_types(
        symbols, imports, contract, facade_exports, uncertain_reexport_origins
    )
    rule_failures = rule_subject_failures(
        contract.rules,
        module_names,
        symbols=symbols,
        imports=imports,
        contract=contract,
        exports_by_module=facade_exports,
        uncertain_reexport_origins=uncertain_reexport_origins,
        stable_bindings_by_module=stable_bindings_by_module,
    )
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
    blank_modules = frozenset(module.module for module in parsed if not module.source.strip())
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
        profile=PYTHON,
        uncertain_reexport_origins=uncertain_reexport_origins,
    )
    (
        inside_violations,
        inside_unknowns,
        inside_failures,
        inside_assessments,
        inside_allowances,
    ) = _inside_rule_results(
        inside_contracts,
        root_contract=contract,
        imports=imports,
        typing_signals=typing_signals,
        constructs=constructs,
        packages=package_facts,
        modules=module_facts,
        symbols=symbols,
        blank_modules=blank_modules,
        module_cycles=module_cycles,
        profile=PYTHON,
        exports_by_module=facade_exports,
        uncertain_reexport_origins=uncertain_reexport_origins,
        scanned_modules=module_names,
        stable_bindings_by_module=stable_bindings_by_module,
        evidence=evidence,
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
        *_analysis_limits(calls, declarations, namespace),
        *private_attribute_limits(parsed, evidence),
        # AD-67: a boundary position the rule could not decide is reported, not silent. It
        # joins the two structural limits above and never `coverage.failures`, because it
        # says how much of a facade was decided, not that the scan was incomplete.
        *boundary_type_limits(
            symbols,
            imports,
            contract,
            facade_exports,
            evidence,
            uncertain_reexport_origins,
            module_names,
            stable_bindings_by_module,
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
        files_read=parsed_sources.files_read,
        files_parsed=len(parsed),
        failures=failures,
        rule_failures=rule_failures,
        calls=calls,
    )

    strip_internal_reexport_facts(imports)
    return ScanResult(
        source_digest=parsed_sources.source_digest,
        coverage=coverage,
        evidence=sorted(evidence.values(), key=lambda item: item["id"]),
        scope_observations=scope_observations,
        packages=sorted(package_facts, key=lambda item: item["id"]),
        modules=sorted(module_facts, key=lambda item: item["id"]),
        symbols=symbols,
        imports=imports,
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
        unknowns=sorted(unknowns, key=lambda item: item["id"]),
    )
