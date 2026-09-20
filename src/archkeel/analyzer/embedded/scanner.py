# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Conservative deterministic AST scanner for the Python architecture profile."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypeAlias

from archkeel.ir.model import (
    ArchitectureContract,
    ContractDeclarations,
    EvidenceClass,
)

from .bindings import collect_bindings
from .calls import collect_calls
from .constructs import collect_constructs
from .contexts import collect_contexts
from .dependencies import (
    aggregate_edges,
    component_scope_observations,
    cycle_records,
    declared_path_observations,
    module_records,
    package_records,
    transitive_path_records,
)
from .imports import collect_imports, resolve_reexports
from .records import RawEvidence, RawRecord, classified
from .references import collect_references
from .resolve import build_symbol_index
from .source import ParsedModule, add_evidence, parse_sources
from .symbols import collect_symbols
from .typing_signals import collect_typing_signals
from .violations import rule_subject_failures, rule_violations

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


def _coverage(
    *,
    paths: Sequence[Path],
    files_read: int,
    parsed: Sequence[ParsedModule],
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
        "files_parsed": len(parsed),
        "ast_coverage_percent": round((len(parsed) / len(paths) * 100), 2) if paths else 0.0,
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


def scan_repository(
    root: Path,
    contract: ArchitectureContract,
    *,
    source_paths: Sequence[Path] | None = None,
    roots: tuple[str, ...],
    namespace: str,
) -> ScanResult:
    """Scan production Python and return the deterministic observed model sections."""
    paths = (
        tuple(source_paths) if source_paths is not None else iter_source_paths(root, roots=roots)
    )
    paths = tuple(sorted(paths, key=lambda path: path.relative_to(root).as_posix()))
    parsed_sources = parse_sources(paths, root=root, namespace=namespace)
    parsed = parsed_sources.modules
    failures = parsed_sources.failures
    evidence: dict[str, RawEvidence] = {}

    module_names = {module.module for module in parsed}
    rule_failures = rule_subject_failures(contract.rules, module_names)
    module_evidence = {
        module.module: add_evidence(evidence, module, module.tree) for module in parsed
    }
    imports = collect_imports(parsed, module_names, evidence, namespace=namespace)

    # Exports exist only after the import loop, and re-exports must resolve before symbols.
    exports_by_module = {module.module: module.all_exports for module in parsed}
    resolve_reexports(imports, exports_by_module)

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
    scope_observations = component_scope_observations(
        components=contract.components,
        modules=module_facts,
        module_edges=module_edges,
        coverage_failures=failures,
    )

    transitive_records = transitive_path_records(packages, package_edge_pairs)
    cycles = sorted(
        [
            *cycle_records(
                level="package",
                nodes=packages,
                edges=package_edge_pairs,
                edge_records=package_edges,
            ),
            *cycle_records(
                level="module",
                nodes=module_names,
                edges=module_edge_pairs,
                edge_records=module_edges,
            ),
        ],
        key=lambda item: item["id"],
    )
    violations = rule_violations(
        imports=imports,
        typing_signals=typing_signals,
        constructs=constructs,
        modules=module_facts,
        symbols=symbols,
        blank_modules=frozenset(module.module for module in parsed if not module.source.strip()),
        contract=contract,
    )

    unknowns = [*_analysis_limits(calls, declarations, namespace), *failures, *rule_failures]

    coverage = _coverage(
        paths=paths,
        files_read=parsed_sources.files_read,
        parsed=parsed,
        failures=failures,
        rule_failures=rule_failures,
        calls=calls,
    )

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
