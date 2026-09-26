# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Assemble the Dart profile's observation sections from its directive records (AD-97).

Every section the Python scan builds from imports and modules is built here by the same shared
functions, so a Dart edge, cycle or violation is the record a Python one would be. The sections
the profile cannot observe stay empty, and the contract items it cannot decide are coverage
failures, so a run over them is exit 2 instead of a PASS nobody earned.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from archkeel.ir.model import ArchitectureContract, ContractComponent, ContractDeclarations
from archkeel.ir.profiles import DART

from .dart_libraries import DartSources, read_dart_sources
from .dependencies import (
    aggregate_edges,
    component_scope_observations,
    cycle_sections,
    declared_path_observations,
    module_records,
    package_records,
    transitive_path_records,
)
from .imports import resolve_reexports, strip_internal_reexport_facts
from .records import RawRecord
from .scanner import (
    ScanResult,
    api_surface_limits,
    coverage_payload,
)
from .scanner import (
    _inside_rule_results as evaluate_inside_rule_results,
)
from .violations import (
    exports_by_module,
    profile_failures,
    rule_subject_failures,
    rule_violations,
    symbol_limits,
)


def _topology(sources: DartSources, namespace: str) -> tuple[list[RawRecord], ...]:
    """Edges, package and module facts, transitive paths and cycles, as the Python scan has."""
    module_names = {library.module for library in sources.libraries}
    module_edges, module_pairs = aggregate_edges(
        sources.imports, level="module", internal_modules=module_names, namespace=namespace
    )
    package_edges, package_pairs = aggregate_edges(
        sources.imports, level="package", internal_modules=module_names, namespace=namespace
    )
    packages = sorted({library.package for library in sources.libraries})
    modules = module_records(
        sources.libraries, module_names, module_pairs, [], sources.module_evidence
    )
    module_cycles, cycles = cycle_sections(
        modules=modules,
        packages=packages,
        module_edges=module_edges,
        module_edge_pairs=module_pairs,
        package_edges=package_edges,
        package_edge_pairs=package_pairs,
    )
    return (
        module_edges,
        package_edges,
        package_records(sources.libraries, packages, package_pairs),
        modules,
        transitive_path_records(packages, package_pairs),
        module_cycles,
        cycles,
    )


def _rule_failures(
    sources: DartSources,
    contract: ArchitectureContract,
    facade_exports: dict[str, frozenset[str]],
) -> list[RawRecord]:
    """Rules without subjects, then every contract item the profile refuses to decide."""
    # An unsupported rule is refused once, as unsupported, not a second time as subjectless.
    supported = [rule for rule in contract.rules if rule.kind not in DART.unsupported_rules]
    return [
        *rule_subject_failures(
            supported,
            {library.module for library in sources.libraries},
            imports=sources.imports,
            contract=contract,
            exports_by_module=facade_exports,
            sdk_libraries=DART.sdk_libraries,
        ),
        *profile_failures(contract, DART),
    ]


def _inside_results(
    inside_contracts: Sequence[tuple[ContractComponent, ArchitectureContract]],
    sources: DartSources,
    packages: Sequence[RawRecord],
    modules: Sequence[RawRecord],
    module_cycles: Sequence[RawRecord],
    facade_exports: dict[str, frozenset[str]],
    uncertain_reexport_origins: dict[str, frozenset[str]],
) -> tuple[list[RawRecord], list[RawRecord], list[RawRecord], list[RawRecord]]:
    """Evaluate nested Dart rules with the imports and topology collected in its one pass."""
    return evaluate_inside_rule_results(
        inside_contracts,
        imports=sources.imports,
        typing_signals=[],
        constructs=[],
        packages=packages,
        modules=modules,
        symbols=[],
        blank_modules=frozenset(sources.blank_modules),
        module_cycles=module_cycles,
        profile=DART,
        exports_by_module=facade_exports,
        uncertain_reexport_origins=uncertain_reexport_origins,
        scanned_modules={library.module for library in sources.libraries},
        stable_bindings_by_module={},
        evidence={item["id"]: item for item in sources.evidence},
    )


def _unknowns(
    sources: DartSources,
    contract: ArchitectureContract,
    declarations: ContractDeclarations,
    facade_exports: dict[str, frozenset[str]],
    inside_unknowns: Sequence[RawRecord],
    rule_failures: Sequence[RawRecord],
) -> list[RawRecord]:
    """Collect profile-known and nested coverage UNKNOWNs without inferring missing symbols."""
    return [
        *symbol_limits(sources.imports, contract, facade_exports),
        *api_surface_limits(
            declarations,
            [],
            {library.module: frozenset() for library in sources.libraries},
            "The Dart profile records no declarations, so no name can be proven present or absent.",
        ),
        *sources.failures,
        *inside_unknowns,
        *rule_failures,
    ]


def _rule_results(
    sources: DartSources,
    contract: ArchitectureContract,
    inside_contracts: Sequence[tuple[ContractComponent, ArchitectureContract]],
    packages: Sequence[RawRecord],
    modules: Sequence[RawRecord],
    module_cycles: Sequence[RawRecord],
    facade_exports: dict[str, frozenset[str]],
    uncertain_reexport_origins: dict[str, frozenset[str]],
) -> tuple[list[RawRecord], list[RawRecord], list[RawRecord], list[RawRecord]]:
    """Evaluate root and nested declarations against one shared Dart scan."""
    violations, _ = rule_violations(
        imports=sources.imports,
        typing_signals=[],
        constructs=[],
        packages=packages,
        modules=modules,
        symbols=[],
        blank_modules=frozenset(sources.blank_modules),
        module_cycles=module_cycles,
        contract=contract,
        exports_by_module=facade_exports,
        profile=DART,
        uncertain_reexport_origins=uncertain_reexport_origins,
    )
    inside = _inside_results(
        inside_contracts,
        sources,
        packages,
        modules,
        module_cycles,
        facade_exports,
        uncertain_reexport_origins,
    )
    return (
        sorted([*violations, *inside[0]], key=lambda item: item["id"]),
        inside[1],
        inside[2],
        inside[3],
    )


def scan_dart_repository(
    root: Path,
    contract: ArchitectureContract,
    *,
    roots: tuple[str, ...],
    namespace: str,
    inside_contracts: Sequence[tuple[ContractComponent, ArchitectureContract]] = (),
) -> ScanResult:
    """Scan the Dart libraries of the scan roots into the shared observation sections."""
    sources = read_dart_sources(root, roots=roots, namespace=namespace)
    # An `export ... show` passes its names on exactly as a Python re-export does.
    uncertain_reexport_origins = resolve_reexports(sources.imports, {})
    module_edges, package_edges, packages, modules, transitive, module_cycles, cycles = _topology(
        sources, namespace
    )
    declarations = contract.declarations or ContractDeclarations()
    facade_exports = exports_by_module(modules)
    rule_failures = _rule_failures(sources, contract, facade_exports)
    violations, inside_unknowns, inside_failures, inside_assessments = _rule_results(
        sources,
        contract,
        inside_contracts,
        packages,
        modules,
        module_cycles,
        facade_exports,
        uncertain_reexport_origins,
    )
    rule_failures.extend(inside_failures)
    unknowns = _unknowns(
        sources, contract, declarations, facade_exports, inside_unknowns, rule_failures
    )
    strip_internal_reexport_facts(sources.imports)
    return ScanResult(
        source_digest=sources.source_digest,
        coverage=coverage_payload(
            paths=sources.paths,
            files_read=sources.files_read,
            files_parsed=sources.files_parsed,
            failures=sources.failures,
            rule_failures=rule_failures,
            calls=[],
        ),
        evidence=sources.evidence,
        scope_observations=component_scope_observations(
            components=contract.components,
            modules=modules,
            module_edges=module_edges,
            coverage_failures=[*sources.failures, *inside_failures],
        )
        + inside_assessments,
        packages=sorted(packages, key=lambda item: item["id"]),
        modules=sorted(modules, key=lambda item: item["id"]),
        symbols=[],
        imports=sources.imports,
        dependency_edges=sorted([*package_edges, *module_edges], key=lambda item: item["id"]),
        transitive_paths=transitive,
        path_observations=declared_path_observations(declarations.paths, package_edges),
        cycles=cycles,
        calls=[],
        references=[],
        bindings=[],
        typing_signals=[],
        constructs=[],
        contexts=[],
        context_evidence=[],
        violations=violations,
        unknowns=sorted(unknowns, key=lambda item: item["id"]),
    )
