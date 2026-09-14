# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Conservative deterministic AST scanner for the Python architecture profile."""

from __future__ import annotations

import ast
import hashlib
from collections import Counter, defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from archkeel.ir.model import (
    ArchitectureContract,
    ContractDeclarations,
    EvidenceClass,
    in_scope,
)

from .calls import CallCollector
from .contexts import collect_contexts
from .dependencies import (
    aggregate_edges,
    component_scope_observations,
    cycle_records,
    declared_path_observations,
)
from .graph import condensation_ranks, transitive_paths
from .imports import ImportCollector, literal_all_exports
from .records import RawEvidence, RawRecord, classified, stable_id
from .source import ParsedModule, add_evidence, module_for, package_for
from .symbols import collect_symbols
from .typing_signals import collect_typing_signals
from .violations import rule_scopes, rule_violations


@dataclass
class ScanResult:
    source_digest: str
    # AD-2: coverage mixes counts with RawRecord failures, which RawJson cannot hold.
    coverage: dict[str, Any]
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
    typing_signals: list[RawRecord]
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
    parsed: list[ParsedModule] = []
    failures: list[RawRecord] = []
    evidence: dict[str, RawEvidence] = {}
    read_count = 0
    digest = hashlib.sha256()
    for path in paths:
        rel = path.relative_to(root).as_posix()
        try:
            raw = path.read_bytes()
            read_count += 1
            digest.update(rel.encode("utf-8"))
            digest.update(b"\0")
            digest.update(raw)
            digest.update(b"\0")
            source = raw.decode("utf-8")
            tree = ast.parse(source, filename=rel)
            module_name = module_for(path, root=root, namespace=namespace)
        except (OSError, UnicodeDecodeError, SyntaxError, ValueError) as exc:
            if isinstance(exc, SyntaxError):
                line, message = exc.lineno or 1, exc.msg
            elif isinstance(exc, OSError):
                line, message = 1, exc.strerror or exc.__class__.__name__
            else:
                line, message = 1, exc.__class__.__name__
            failure_id = stable_id("COVERAGE", rel, line, exc.__class__.__name__, message)
            failures.append(
                classified(
                    item_id=failure_id,
                    evidence_class=EvidenceClass.UNKNOWN,
                    area="analysis_coverage",
                    kind=exc.__class__.__name__,
                    title=f"{rel}:{line} could not be analyzed",
                    subjects=[rel],
                    data={"file": rel, "line": line, "message": str(message)},
                )
            )
            continue
        parsed.append(
            ParsedModule(
                path=path,
                rel_path=rel,
                module=module_name,
                package=package_for(module_name),
                source=source,
                source_bytes=raw,
                lines=source.splitlines(),
                tree=tree,
            )
        )

    module_names = {module.module for module in parsed}
    rule_failures: list[RawRecord] = []
    for rule in contract.rules:
        scopes = rule_scopes(rule)
        matches = {
            side: sum(
                any(in_scope(module, scope) for scope in side_scopes) for module in module_names
            )
            for side, side_scopes in scopes.items()
        }
        missing = [side for side, count in matches.items() if count == 0]
        if missing:
            rule_failures.append(
                classified(
                    item_id=stable_id("UNKNOWN-RULE-SUBJECTS", rule.id),
                    evidence_class=EvidenceClass.UNKNOWN,
                    area="analysis_coverage",
                    kind="rule-without-subjects",
                    title=f"{rule.id}: no scanned modules for {', '.join(missing)}",
                    subjects=[scope for side in missing for scope in scopes[side]],
                    rule_ids=[rule.id],
                    data={
                        "missing": missing,
                        **{f"{side}_matches": count for side, count in matches.items()},
                    },
                )
            )
    module_evidence = {
        module.module: add_evidence(evidence, module, module.tree) for module in parsed
    }
    imports: list[RawRecord] = []
    for module in parsed:
        module.all_exports = literal_all_exports(module.tree)
        collector = ImportCollector(module, module_names, evidence, namespace=namespace)
        collector.visit(module.tree)
        imports.extend(collector.items)
    imports.sort(key=lambda item: item["id"])

    reexports: dict[str, str] = {}
    exports_by_module = {module.module: module.all_exports for module in parsed}
    for item in imports:
        data = item["data"]
        if not data["reexport"] or not data["symbol"]:
            continue
        reexports[f"{data['source_module']}.{data['binding']}"] = (
            f"{data['target_module']}.{data['symbol']}"
        )
    for item in imports:
        data = item["data"]
        if not data["symbol"]:
            data["reexport_chain"] = []
            data["origin_definition"] = None
            data["symbol_visibility"] = None
            data["declared_in_all"] = False
            continue
        current = f"{data['target_module']}.{data['symbol']}"
        chain = [current]
        seen = {current}
        while current in reexports and reexports[current] not in seen:
            current = reexports[current]
            seen.add(current)
            chain.append(current)
        data["reexport_chain"] = chain
        data["origin_definition"] = chain[-1]
        data["symbol_visibility"] = "private" if data["symbol"].startswith("_") else "public_name"
        data["declared_in_all"] = data["binding"] in exports_by_module.get(
            data["source_module"], set()
        )

    symbols, symbol_nodes, symbol_owners = collect_symbols(parsed, evidence)
    symbol_names = {item["data"]["qualified_name"] for item in symbols}
    by_tail: dict[str, list[str]] = defaultdict(list)
    for name in sorted(symbol_names):
        by_tail[name.rsplit(".", 1)[-1]].append(name)

    calls: list[RawRecord] = []
    symbol_evidence = {item["data"]["qualified_name"]: item["evidence_ids"] for item in symbols}
    for module in parsed:
        call_collector = CallCollector(module, symbol_names, by_tail, symbol_evidence, evidence)
        call_collector.visit(module.tree)
        calls.extend(call_collector.items)
    calls.sort(key=lambda item: item["id"])

    typing_signals = collect_typing_signals(parsed, calls, symbols, imports, evidence)
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
    package_fan_in = Counter(target for source, target in package_edge_pairs)
    package_fan_out = Counter(source for source, target in package_edge_pairs)
    package_records = [
        classified(
            item_id=stable_id("PKG", package),
            evidence_class=EvidenceClass.FACT,
            area="package_topology",
            kind="package",
            title=package,
            subjects=[package],
            fact_ids=sorted(
                stable_id("MOD", module.module) for module in parsed if module.package == package
            ),
            data={
                "qualified_name": package,
                "module_count": sum(1 for module in parsed if module.package == package),
                "fan_in": package_fan_in[package],
                "fan_out": package_fan_out[package],
                "rank": condensation_ranks(packages, package_edge_pairs).get(package, 0),
                "dependencies": sorted(
                    target for source, target in package_edge_pairs if source == package
                ),
            },
        )
        for package in packages
    ]

    module_fan_in = Counter(target for source, target in module_edge_pairs)
    module_fan_out = Counter(source for source, target in module_edge_pairs)
    module_ranks = condensation_ranks(module_names, module_edge_pairs)
    symbols_by_module = Counter(item["data"]["module"] for item in symbols)
    module_records = [
        classified(
            item_id=stable_id("MOD", module.module),
            evidence_class=EvidenceClass.FACT,
            area="module_topology",
            kind="module",
            title=module.module,
            subjects=[module.module, module.package],
            evidence_ids=[module_evidence[module.module]],
            data={
                "qualified_name": module.module,
                "package": module.package,
                "file": module.rel_path,
                "symbol_count": symbols_by_module[module.module],
                "fan_in": module_fan_in[module.module],
                "fan_out": module_fan_out[module.module],
                "rank": module_ranks.get(module.module, 0),
                "all_exports": sorted(module.all_exports),
            },
        )
        for module in parsed
    ]
    scope_observations = component_scope_observations(
        components=contract.components,
        modules=module_records,
        module_edges=module_edges,
        coverage_failures=failures,
    )

    transitive_records = [
        classified(
            item_id=stable_id("PATH", "package", *path),
            evidence_class=EvidenceClass.FACT,
            area="package_topology",
            kind="transitive_package_dependency",
            title=" → ".join(path),
            subjects=path,
            fact_ids=[
                stable_id("EDGE", "package", source, target)
                for source, target in zip(path, path[1:], strict=False)
            ],
            data={"level": "package", "source": path[0], "target": path[-1], "path": path},
        )
        for path in transitive_paths(packages, package_edge_pairs)
    ]
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
        modules=module_records,
        blank_modules=frozenset(module.module for module in parsed if not module.source.strip()),
        contract=contract,
    )

    unknowns = [
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
        *failures,
        *rule_failures,
    ]

    calls_analyzed = len(calls)
    calls_resolved = sum(1 for call in calls if call["data"]["status"] == "resolved")
    calls_partially_resolved = sum(
        1 for call in calls if call["data"]["status"] == "partially_resolved"
    )
    calls_unresolved = sum(1 for call in calls if call["data"]["status"] == "unresolved")
    coverage = {
        "status": "FAIL" if failures or rule_failures or not paths else "PASS",
        "rules": "FAIL" if rule_failures else "PASS",
        "files_discovered": len(paths),
        "files_read": read_count,
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

    return ScanResult(
        source_digest=digest.hexdigest(),
        coverage=coverage,
        evidence=sorted(evidence.values(), key=lambda item: item["id"]),
        scope_observations=scope_observations,
        packages=sorted(package_records, key=lambda item: item["id"]),
        modules=sorted(module_records, key=lambda item: item["id"]),
        symbols=symbols,
        imports=imports,
        dependency_edges=dependency_edges,
        transitive_paths=sorted(transitive_records, key=lambda item: item["id"]),
        path_observations=path_observations,
        cycles=cycles,
        calls=calls,
        typing_signals=typing_signals,
        contexts=contexts,
        context_evidence=context_evidence,
        violations=violations,
        unknowns=sorted(unknowns, key=lambda item: item["id"]),
    )
