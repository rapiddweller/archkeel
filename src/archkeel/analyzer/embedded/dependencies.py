# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Dependency edge, cycle, and declared-scope aggregation shared by every scanner profile."""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterable, Sequence

from archkeel.ir.model import ContractComponent, ContractPath, EvidenceClass, in_scope, stable_id

from .graph import condensation_ranks, strongly_connected_components, transitive_paths
from .records import RawRecord, classified
from .source import ScannedModule


def _top_level_scope(module: str) -> str | None:
    parts = module.split(".")
    return ".".join(parts[:2]) if len(parts) > 1 else None


def aggregate_edges(
    imports: Sequence[RawRecord], *, level: str, internal_modules: set[str], namespace: str
) -> tuple[list[RawRecord], list[tuple[str, str]]]:
    buckets: dict[tuple[str, str], list[str]] = defaultdict(list)
    type_checking_counts: Counter[tuple[str, str]] = Counter()
    for item in imports:
        data = item["data"]
        if level == "module":
            source = data["source_module"]
            target = data["target_module"]
            if target not in internal_modules or source == target:
                continue
        else:
            source = data["source_package"]
            target = data["target_package"]
            if not in_scope(target, namespace) or source == target:
                continue
        buckets[(source, target)].append(item["id"])
        if data["under_type_checking"]:
            type_checking_counts[(source, target)] += 1
    graph_edges = sorted(buckets)
    ranks = condensation_ranks({value for edge in graph_edges for value in edge}, graph_edges)
    edge_set = set(graph_edges)
    records = [
        classified(
            item_id=stable_id("EDGE", level, source, target),
            evidence_class=EvidenceClass.FACT,
            area=f"{level}_topology",
            kind=f"{level}_dependency",
            title=f"{source} → {target}",
            subjects=[source, target],
            fact_ids=sorted(buckets[(source, target)]),
            data={
                "level": level,
                "source": source,
                "target": target,
                "count": len(buckets[(source, target)]),
                "type_checking_count": type_checking_counts[(source, target)],
                "runtime_count": len(buckets[(source, target)])
                - type_checking_counts[(source, target)],
                "source_rank": ranks.get(source, 0),
                "target_rank": ranks.get(target, 0),
                "bidirectional": (target, source) in edge_set,
            },
        )
        for source, target in graph_edges
    ]
    return records, graph_edges


def package_records(
    parsed: Sequence[ScannedModule],
    packages: Sequence[str],
    package_edge_pairs: Sequence[tuple[str, str]],
) -> list[RawRecord]:
    """Build one FACT record per package with fan-in/out, rank and declared dependencies."""
    package_fan_in = Counter(target for source, target in package_edge_pairs)
    package_fan_out = Counter(source for source, target in package_edge_pairs)
    # condensation_ranks only depends on packages/package_edge_pairs, both loop-invariant here.
    ranks = condensation_ranks(packages, package_edge_pairs)
    return [
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
                "rank": ranks.get(package, 0),
                "dependencies": sorted(
                    target for source, target in package_edge_pairs if source == package
                ),
            },
        )
        for package in packages
    ]


def module_records(
    parsed: Sequence[ScannedModule],
    module_names: set[str],
    module_edge_pairs: Sequence[tuple[str, str]],
    symbols: Sequence[RawRecord],
    module_evidence: dict[str, str],
) -> list[RawRecord]:
    """Build one FACT record per module with fan-in/out, rank and its export set."""
    module_fan_in = Counter(target for source, target in module_edge_pairs)
    module_fan_out = Counter(source for source, target in module_edge_pairs)
    module_ranks = condensation_ranks(module_names, module_edge_pairs)
    symbols_by_module = Counter(item["data"]["module"] for item in symbols)

    return [
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
                "compatibility_logic_free": module.compatibility_logic_free,
            },
        )
        for module in parsed
    ]


def transitive_path_records(
    packages: Sequence[str], package_edge_pairs: Sequence[tuple[str, str]]
) -> list[RawRecord]:
    """Build one FACT record per transitive package path, sorted by id."""
    records = [
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
    return sorted(records, key=lambda item: item["id"])


def _cycle_records(
    *,
    level: str,
    nodes: Iterable[str],
    edges: Sequence[tuple[str, str]],
    edge_records: Sequence[RawRecord],
) -> list[RawRecord]:
    edge_by_pair = {(item["data"]["source"], item["data"]["target"]): item for item in edge_records}
    records: list[RawRecord] = []
    for component in strongly_connected_components(nodes, edges):
        self_loop = len(component) == 1 and (component[0], component[0]) in edge_by_pair
        if len(component) <= 1 and not self_loop:
            continue
        member_set = set(component)
        internal_edges = [
            edge_by_pair[(source, target)]
            for source, target in edges
            if source in member_set and target in member_set and (source, target) in edge_by_pair
        ]
        records.append(
            classified(
                item_id=stable_id("SCC", level, *component),
                evidence_class=EvidenceClass.FACT,
                area="cycles",
                kind=f"{level}_scc",
                title=f"{level.capitalize()} cycle with {len(component)} members",
                subjects=component,
                fact_ids=[item["id"] for item in internal_edges],
                data={
                    "level": level,
                    "members": component,
                    "internal_edges": [item["id"] for item in internal_edges],
                },
            )
        )
    return sorted(records, key=lambda item: item["id"])


def _backed_package_cycles(
    package_cycles: Sequence[RawRecord],
    module_cycles: Sequence[RawRecord],
    package_of: dict[str, str],
) -> list[RawRecord]:
    """Name, on each package SCC, the module SCCs that cross two or more of its packages.

    AD-98: a package is a module's first two dotted segments, so `a.x -> b.y` and `b.z -> a.w`
    close a package cycle that no module import cycle closes. Every package edge is real, but
    the cycle is the roll-up's: `backed_by` stays empty and the title says so. A module SCC
    inside one package never backs one.
    """
    records: list[RawRecord] = []
    for cycle in package_cycles:
        packages = set(cycle["data"]["members"])
        backed_by = sorted(
            module_cycle["id"]
            for module_cycle in module_cycles
            if len(packages & {package_of[member] for member in module_cycle["data"]["members"]})
            > 1
        )
        rollup = ", roll-up only: no module cycle crosses them"
        title = cycle["title"] if backed_by else f"{cycle['title']}{rollup}"
        records.append({**cycle, "title": title, "data": {**cycle["data"], "backed_by": backed_by}})
    return records


def cycle_sections(
    *,
    modules: Sequence[RawRecord],
    packages: Sequence[str],
    module_edges: Sequence[RawRecord],
    module_edge_pairs: Sequence[tuple[str, str]],
    package_edges: Sequence[RawRecord],
    package_edge_pairs: Sequence[tuple[str, str]],
) -> tuple[list[RawRecord], list[RawRecord]]:
    """Return the module SCC records, and every SCC record for the `cycles` section.

    The one way a profile builds SCC records (AD-98): a package SCC leaves here with its
    `backed_by` already named, so no scan can report one the report cannot label. The module
    SCCs come back on their own because the module-level cycle rule judges exactly these.
    """
    module_cycles = _cycle_records(
        level="module",
        nodes=[item["data"]["qualified_name"] for item in modules],
        edges=module_edge_pairs,
        edge_records=module_edges,
    )
    package_cycles = _backed_package_cycles(
        _cycle_records(
            level="package", nodes=packages, edges=package_edge_pairs, edge_records=package_edges
        ),
        module_cycles,
        {item["data"]["qualified_name"]: item["data"]["package"] for item in modules},
    )
    return module_cycles, sorted([*package_cycles, *module_cycles], key=lambda item: item["id"])


def declared_path_observations(
    paths: Sequence[ContractPath], package_edges: Sequence[RawRecord]
) -> list[RawRecord]:
    edges = {(item["data"]["source"], item["data"]["target"]): item for item in package_edges}
    records: list[RawRecord] = []
    for declared_path in paths:
        steps = declared_path.steps
        for index, (source, target) in enumerate(zip(steps, steps[1:], strict=False)):
            edge = edges.get((source, target))
            if edge is None:
                records.append(
                    classified(
                        item_id=stable_id("UNKNOWN-PATH", declared_path.id, index, source, target),
                        evidence_class=EvidenceClass.UNKNOWN,
                        area="read_write_paths",
                        kind="path_segment_not_statically_observed",
                        title=f"{source} → {target} lacks direct static import evidence",
                        subjects=[source, target],
                        rule_ids=[declared_path.id],
                        data={
                            "path_id": declared_path.id,
                            "source": source,
                            "target": target,
                            "status": "UNKNOWN",
                            "reason": (
                                "Missing static proof does not prove that the runtime path "
                                "is absent"
                            ),
                        },
                    )
                )
                continue
            records.append(
                classified(
                    item_id=stable_id("PATH-OBS", declared_path.id, index, edge["id"]),
                    evidence_class=EvidenceClass.FACT,
                    area="read_write_paths",
                    kind="observed_path_segment",
                    title=f"{source} → {target} is statically observed",
                    subjects=[source, target],
                    rule_ids=[declared_path.id],
                    fact_ids=[edge["id"]],
                    data={
                        "path_id": declared_path.id,
                        "source": source,
                        "target": target,
                        "status": "observed",
                        "direct_import_count": edge["data"]["count"],
                    },
                )
            )
    return sorted(records, key=lambda item: item["id"])


def component_scope_observations(
    *,
    components: Sequence[ContractComponent],
    modules: Sequence[RawRecord],
    module_edges: Sequence[RawRecord],
    coverage_failures: Sequence[RawRecord],
) -> list[RawRecord]:
    """Aggregate observed modules under accepted component prefixes.

    A prefix owns only its exact module and dot-delimited descendants. Coverage
    failures suppress absence-based assignment findings because the missing
    source may contain evidence that changes the result.
    """
    module_by_name = {item["data"]["qualified_name"]: item for item in modules}
    assigned_modules: set[str] = set()
    observations: list[RawRecord] = []
    coverage_complete = not coverage_failures

    for component in sorted(components, key=lambda item: item.id):
        record, matched_names = _declared_scope_record(
            component, module_by_name, module_edges, coverage_complete
        )
        assigned_modules.update(matched_names)
        observations.append(record)

    if coverage_failures:
        observations.append(_scope_coverage_unknown(coverage_failures))
        return sorted(observations, key=lambda item: item["id"])

    observations.extend(_unassigned_scope_records(module_by_name, assigned_modules))
    return sorted(observations, key=lambda item: item["id"])


def _declared_scope_record(
    component: ContractComponent,
    module_by_name: dict[str, RawRecord],
    module_edges: Sequence[RawRecord],
    coverage_complete: bool,
) -> tuple[RawRecord, list[str]]:
    """Build one component's DECLARED scope record and its matched module names."""
    scopes = sorted(component.packages)
    matched_names = sorted(
        name for name in module_by_name if any(in_scope(name, scope) for scope in scopes)
    )
    matched_set = set(matched_names)
    outgoing_edges = sorted(
        (
            edge
            for edge in module_edges
            if edge["data"]["source"] in matched_set and edge["data"]["target"] not in matched_set
        ),
        key=lambda item: item["id"],
    )
    outgoing_modules = sorted({edge["data"]["target"] for edge in outgoing_edges})
    outgoing_scopes = sorted(
        {scope for name in outgoing_modules if (scope := _top_level_scope(name)) is not None}
    )
    module_facts = [module_by_name[name] for name in matched_names]
    record = classified(
        item_id=stable_id("SCOPE", "declared_component", component.id),
        evidence_class=EvidenceClass.FACT,
        area="components",
        kind="declared_component_scope_observation",
        title=f"Observed source scope for {component.label}",
        subjects=scopes,
        evidence_ids=[evidence_id for item in module_facts for evidence_id in item["evidence_ids"]],
        rule_ids=[component.id],
        fact_ids=[
            *[item["id"] for item in module_facts],
            *[item["id"] for item in outgoing_edges],
        ],
        data={
            "component_id": component.id,
            "scopes": scopes,
            "scope_module_counts": [
                {
                    "scope": scope,
                    "observed_module_count": sum(
                        1 for name in matched_names if in_scope(name, scope)
                    ),
                }
                for scope in scopes
            ],
            "coverage_complete": coverage_complete,
            "module_count": len(matched_names) if coverage_complete else None,
            "observed_module_count": len(matched_names),
            "modules": matched_names,
            "files": sorted(module_by_name[name]["data"]["file"] for name in matched_names),
            "fan_out": len(outgoing_scopes) if coverage_complete else None,
            "outgoing_scopes": outgoing_scopes,
            "outgoing_modules": outgoing_modules,
        },
    )
    return record, matched_names


def _scope_coverage_unknown(coverage_failures: Sequence[RawRecord]) -> RawRecord:
    """Build the UNKNOWN record when source coverage failed before scope assignment."""
    return classified(
        item_id="UNKNOWN-COMPONENT-SCOPE-COVERAGE",
        evidence_class=EvidenceClass.UNKNOWN,
        area="components",
        kind="component_scope_assignment_incomplete",
        title="Component scope assignment cannot be completed safely",
        subjects=sorted(
            subject for failure in coverage_failures for subject in failure.get("subjects", [])
        ),
        data={
            "reason": "Source coverage failed; unassigned-scope conclusions are suppressed",
            "coverage_failure_ids": sorted(failure["id"] for failure in coverage_failures),
        },
    )


def _unassigned_scope_records(
    module_by_name: dict[str, RawRecord], assigned_modules: set[str]
) -> list[RawRecord]:
    """Build UNKNOWN records for modules under a top-level scope no component claims."""
    unassigned_by_scope: dict[str, list[str]] = defaultdict(list)
    for name in sorted(module_by_name):
        scope = _top_level_scope(name)
        if scope is not None and name not in assigned_modules:
            unassigned_by_scope[scope].append(name)

    records: list[RawRecord] = []
    for scope, names in sorted(unassigned_by_scope.items()):
        module_facts = [module_by_name[name] for name in names]
        scope_modules = sorted(name for name in module_by_name if in_scope(name, scope))
        records.append(
            classified(
                item_id=stable_id("UNKNOWN-SCOPE", scope),
                evidence_class=EvidenceClass.UNKNOWN,
                area="components",
                kind="unassigned_component_scope",
                title=f"Accepted component ownership is undecided for {scope}",
                subjects=[scope, *names],
                evidence_ids=[
                    evidence_id for item in module_facts for evidence_id in item["evidence_ids"]
                ],
                fact_ids=[item["id"] for item in module_facts],
                data={
                    "scope": scope,
                    "module_count": len(names),
                    "modules": names,
                    "files": sorted(module_by_name[name]["data"]["file"] for name in names),
                    "partially_assigned": any(name in assigned_modules for name in scope_modules),
                    "reason": "No accepted component declaration covers these observed modules",
                },
            )
        )
    return records
