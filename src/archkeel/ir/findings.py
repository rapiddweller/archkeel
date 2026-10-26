# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Rank what a report opens with: violations, dependency cycles and hubs (AD-258).

Every threshold already exists: a violation is the contract's rule, a cycle is a cycle, a hub
is `module_explore.hub_modules`. The list is computed once here, so the terminal, the HTML and
the JSON cannot rank differently.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping
from typing import Final

from .architecture_graph import ArchitectureRuleKind, AssessmentStatus
from .baseline import ViolationFingerprint, violation_fingerprint
from .facts import Evidence, Record
from .model import (
    CyclePath,
    CyclePathStep,
    Finding,
    FindingKind,
    FindingsState,
    GraphTopologyLevel,
    Observation,
    ReportLocation,
    RunResult,
    int_value,
    text_value,
)
from .module_explore import ModuleExploreLevel, ModuleStatistic, hub_modules
from .trace import trace_valid_violations

# The record kinds that declare a component and that scope its modules (AD-263 component paths).
_COMPONENT_DECLARATION: Final = "component_responsibility"
_DECLARED_SCOPE: Final = "declared_component_scope_observation"
# AD-258: hubs are ranked across every level, then cut, so a large repository stays readable.
_HUBS_SHOWN: Final = 10
_MEMBERS_NAMED: Final = 3
# The kind of violation a module-level `no_component_cycles` rule records for one whole SCC (AD-98).
_MODULE_CYCLE_VIOLATION: Final = "module_cycle"


def evidence_locations(
    evidence: Mapping[str, Evidence], evidence_ids: Iterable[str]
) -> tuple[ReportLocation, ...]:
    """Cited source positions, ordered by file and line; the one place violations get them."""
    return tuple(
        sorted(
            {
                ReportLocation(evidence[identity].file, evidence[identity].line)
                for identity in evidence_ids
                if identity in evidence
            },
            key=lambda location: (location.path, location.line),
        )
    )


def _count(number: int, noun: str) -> str:
    return f"{number} {noun}" if number == 1 else f"{number} {noun}s"


def _components(subjects: Iterable[str], modules: Mapping[str, ModuleStatistic]) -> tuple[str, ...]:
    owners = {
        modules[name].component_id
        for name in subjects
        if name in modules and modules[name].component_id is not None
    }
    return tuple(sorted(owner for owner in owners if owner is not None))


def _cited_components(
    records: Iterable[Record],
    evidence: Mapping[str, Evidence],
    modules: Mapping[str, ModuleStatistic],
) -> tuple[str, ...]:
    """Owners of the modules a finding's evidence cites; subjects may be symbols, not modules."""
    module_files = {
        evidence[item.evidence_ids[0]].file: name
        for name, item in modules.items()
        if item.evidence_ids and item.evidence_ids[0] in evidence
    }
    cited = {
        module_files[evidence[key].file]
        for record in records
        for key in record.evidence_ids
        if key in evidence and evidence[key].file in module_files
    }
    return _components(cited, modules)


def _package_modules(packages: Iterable[str], modules: Mapping[str, ModuleStatistic]) -> list[str]:
    """The first module inside each package, so a package roll-up gets an owner and a link."""
    names: list[str] = sorted(modules)
    firsts: list[str] = []
    for package in packages:
        prefix = f"{package}."
        inside = [name for name in names if name[: len(prefix)] == prefix]
        firsts += inside[:1]
    return firsts


def _ranked(items: Iterable[Finding]) -> list[Finding]:
    return sorted(items, key=lambda item: (-item.size, item.subjects, item.rules))


def _violation_path(
    record: Record,
    owners: Mapping[str, str],
    imports: Mapping[str, Record],
    evidence: Mapping[str, Evidence],
) -> CyclePath | None:
    """Only a component cycle among the violations carries a path (AD-263)."""
    if record.kind != ArchitectureRuleKind.NO_COMPONENT_CYCLES:
        return None
    return _component_cycle_path(record, owners, imports, evidence)


def _violation_findings(
    observation: Observation,
    violations: tuple[Record, ...],
    evidence: Mapping[str, Evidence],
    modules: Mapping[str, ModuleStatistic],
    imports: Mapping[str, Record],
    remedy: str,
) -> list[Finding]:
    # Labels come from the target graph, so they are read only when a component cycle needs them.
    owners = (
        _module_labels(observation)
        if any(item.kind == ArchitectureRuleKind.NO_COMPONENT_CYCLES for item in violations)
        else {}
    )
    grouped: defaultdict[ViolationFingerprint, list[Record]] = defaultdict(list)
    for record in violations:
        group: list[Record] = grouped[violation_fingerprint(record)]
        group.append(record)
    return _ranked(
        Finding(
            FindingKind.VIOLATION,
            fingerprint.rules,
            fingerprint.subjects,
            len(records),
            # One rule broken in both directions groups A->B with B->A; name neither direction.
            records[0].title
            if len({item.title for item in records}) == 1
            else f"{', '.join(fingerprint.rules)} between {' and '.join(fingerprint.subjects)}",
            f"{', '.join(fingerprint.rules)} is broken {_count(len(records), 'time')}. {remedy}",
            evidence_locations(evidence, (key for item in records for key in item.evidence_ids)),
            _components(fingerprint.subjects, modules)
            or _cited_components(records, evidence, modules),
            path=_violation_path(records[0], owners, imports, evidence),
        )
        for fingerprint, records in grouped.items()
    )


def _shortest_cycle(
    nodes: Iterable[str], pairs: Iterable[tuple[str, str]]
) -> tuple[tuple[str, str], ...]:
    """AD-263: the shortest closed walk through one strongly connected set of pairs.

    The walk starts at the smallest node and takes the smallest next node among the shortest
    continuations. BFS distances do not depend on the order a frontier is visited in, so the
    same pairs always give the same walk.
    """
    ends = sorted(set(pairs))
    members = sorted(nodes)
    if not members:
        return ()
    # ponytail: each member scans every pair; index by source if a huge SCC is slow.
    successors = {node: [target for source, target in ends if source == node] for node in members}
    predecessors = {node: [source for source, target in ends if target == node] for node in members}
    start = members[0]
    # Edges from each member back to the start, following the pairs in reverse.
    back = {start: 0}
    frontier = {start}
    distance = 0
    while frontier:
        distance += 1
        frontier = {
            previous for node in frontier for previous in predecessors[node] if previous not in back
        }
        for previous in frontier:
            back[previous] = distance
    closing = [back[target] for target in successors[start] if target in back]
    if not closing:
        # Pairs that do not close through the start name no cycle; the caller shows no path.
        return ()
    length = 1 + min(closing)
    walk: list[tuple[str, str]] = []
    current = start
    for remaining in range(length, 0, -1):
        following = min(
            target for target in successors[current] if back.get(target) == remaining - 1
        )
        walk.append((current, following))
        current = following
    return tuple(walk)


def _edge_ends(edge: Record) -> tuple[str, str]:
    """Direction lives in the data: `subjects` are sorted, so they carry no order."""
    return text_value(edge.data.get("source")), text_value(edge.data.get("target"))


def _step(
    source: str,
    target: str,
    sites: Iterable[Record],
    evidence: Mapping[str, Evidence],
    type_checking_only: bool,
) -> CyclePathStep:
    locations = evidence_locations(evidence, (key for site in sites for key in site.evidence_ids))
    return CyclePathStep(source, target, locations[0] if locations else None, type_checking_only)


def _module_cycle_path(
    cycle: Record,
    edges: Mapping[str, Record],
    imports: Mapping[str, Record],
    evidence: Mapping[str, Evidence],
) -> CyclePath | None:
    """A module or package cycle: its edge records are the pairs, each with its import sites."""
    internal = [edges[identity] for identity in cycle.fact_ids if identity in edges]
    if len(internal) != len(cycle.fact_ids):
        return None
    by_pair = {_edge_ends(edge): edge for edge in internal}
    walk = _shortest_cycle(cycle.subjects, by_pair.keys())
    if not walk:
        return None
    steps: list[CyclePathStep] = []
    for source, target in walk:
        edge = by_pair[source, target]
        if any(identity not in imports for identity in edge.fact_ids):
            return None
        # A missing count is no proof of type-checking-only, so it never sets the flag.
        runtime = int_value(edge.data.get("runtime_count"), default=1)
        sites = [imports[identity] for identity in edge.fact_ids]
        steps.append(_step(source, target, sites, evidence, runtime == 0))
    return CyclePath(tuple(steps), omitted_edges=len(by_pair) - len(walk))


def _module_labels(observation: Observation) -> dict[str, str]:
    """AD-263: each module's component label, read from the contract's own membership.

    A declared scope record names the modules a component owns under its id, and the
    declaration names that id with its label. The exploration level is no source here: it
    carries ids, and it is empty of owners when the observation has no authenticated target.
    """
    labels = {
        record.id: record.title
        for record in observation.records("declarations") or ()
        if record.kind == _COMPONENT_DECLARATION
    }
    owners: dict[str, str] = {}
    for record in observation.records("scope_observations") or ():
        component = text_value(record.data.get("component_id"))
        modules = record.data.get("modules")
        if (
            record.kind != _DECLARED_SCOPE
            or component not in labels
            or not isinstance(modules, tuple)
        ):
            continue
        for module in modules:
            if isinstance(module, str):
                owners[module] = labels[component]
    return owners


def _component_pair(
    site: Record, owners: Mapping[str, str], members: frozenset[str]
) -> tuple[str, str] | None:
    source = owners.get(text_value(site.data.get("source_module")))
    target = owners.get(text_value(site.data.get("target_module")))
    if source is None or target is None or source == target:
        return None
    if source not in members or target not in members:
        return None
    return source, target


def _component_cycle_path(
    violation: Record,
    owners: Mapping[str, str],
    imports: Mapping[str, Record],
    evidence: Mapping[str, Evidence],
) -> CyclePath | None:
    """A component cycle: its pairs come from the cross-component import sites it cites."""
    if any(identity not in imports for identity in violation.fact_ids):
        return None
    members = frozenset(violation.subjects)
    cited = [imports[identity] for identity in violation.fact_ids]
    keyed = [
        (pair, site)
        for site in cited
        if (pair := _component_pair(site, owners, members)) is not None
    ]
    sites_by_pair = {pair: [site for key, site in keyed if key == pair] for pair, _ in keyed}
    walk = _shortest_cycle(members, sites_by_pair.keys())
    if not walk:
        return None
    steps = [
        _step(
            source,
            target,
            sites_by_pair[source, target],
            evidence,
            all(
                site.data.get("under_type_checking") is True
                for site in sites_by_pair[source, target]
            ),
        )
        for source, target in walk
    ]
    return CyclePath(tuple(steps), omitted_edges=len(sites_by_pair) - len(walk))


def _cycle_findings(
    observation: Observation,
    violations: tuple[Record, ...],
    evidence: Mapping[str, Evidence],
    modules: Mapping[str, ModuleStatistic],
    edges: Mapping[str, Record],
    imports: Mapping[str, Record],
) -> list[Finding]:
    # AD-98: a module-level cycle rule already reports the whole SCC, so it is listed once.
    reported = {
        frozenset(item.subjects) for item in violations if item.kind == _MODULE_CYCLE_VIOLATION
    }
    module_cycles: list[Finding] = []
    package_cycles: list[Finding] = []
    for record in observation.records("cycles") or ():
        members = record.subjects
        size = len(record.fact_ids)
        named = ", ".join(members[:_MEMBERS_NAMED])
        more = len(members) - _MEMBERS_NAMED
        who = f"{named} and {_count(more, 'other')}" if more > 0 else named
        sentence = f"{who} import each other through {_count(size, 'import edge')}."
        level = record.data.get("level")
        backed_by = record.data.get("backed_by")
        if level == GraphTopologyLevel.MODULE and frozenset(members) not in reported:
            locations = evidence_locations(
                evidence,
                (
                    key
                    for name in members[:_MEMBERS_NAMED]
                    if name in modules
                    for key in modules[name].evidence_ids[:1]
                ),
            )
            module_cycles.append(
                Finding(
                    FindingKind.MODULE_CYCLE,
                    (),
                    members,
                    size,
                    record.title,
                    sentence,
                    locations,
                    _components(members, modules),
                    path=_module_cycle_path(record, edges, imports, evidence),
                )
            )
        elif level == GraphTopologyLevel.PACKAGE and backed_by == ():
            # A package cycle that a module cycle backs is that module cycle; only the
            # roll-up adds a finding (AD-98).
            representatives = _package_modules(members, modules)
            package_cycles.append(
                Finding(
                    FindingKind.PACKAGE_CYCLE,
                    (),
                    members,
                    size,
                    record.title,
                    sentence,
                    evidence_locations(evidence, record.evidence_ids)[:_MEMBERS_NAMED]
                    or evidence_locations(
                        evidence,
                        (
                            key
                            for name in representatives[:_MEMBERS_NAMED]
                            for key in modules[name].evidence_ids[:1]
                        ),
                    ),
                    _components(representatives, modules),
                    path=_module_cycle_path(record, edges, imports, evidence),
                )
            )
    return [*_ranked(module_cycles), *_ranked(package_cycles)]


def _hub_finding(
    kind: FindingKind,
    item: ModuleStatistic,
    count: int,
    owners: Mapping[str, str | None],
    evidence: Mapping[str, Evidence],
) -> Finding:
    modules = _count(count, "module")
    if kind is FindingKind.FAN_IN_HUB:
        title = f"{item.name} is imported by {modules}"
        sentence = (
            f"{modules} import it; is this the intended shared kernel, or does it hold "
            "several responsibilities?"
        )
    else:
        title = f"{item.name} imports {modules}"
        sentence = f"It imports {modules}; does it coordinate several responsibilities?"
    owner = owners.get(item.name)
    return Finding(
        kind,
        (),
        (item.name,),
        count,
        title,
        sentence,
        evidence_locations(evidence, item.evidence_ids[:1]),
        (owner,) if owner is not None else (),
    )


def _hub_findings(
    levels: tuple[ModuleExploreLevel, ...], evidence: Mapping[str, Evidence]
) -> list[Finding]:
    root = next((level for level in levels if level.parent_id is None), None)
    if root is None:
        return []
    owners = {item.name: item.component_id for item in root.modules}
    hubs: dict[tuple[FindingKind, str], Finding] = {}
    for kind, fan_in in ((FindingKind.FAN_IN_HUB, True), (FindingKind.FAN_OUT_HUB, False)):
        for level in levels:
            for item, count in hub_modules(level, fan_in=fan_in):
                if (kind, item.name) not in hubs:
                    hubs[(kind, item.name)] = _hub_finding(kind, item, count, owners, evidence)
    # Review (#652): fan-in hubs stay ahead of fan-out hubs, as the kinds are ranked.
    ranked = [
        *_ranked(item for item in hubs.values() if item.kind is FindingKind.FAN_IN_HUB),
        *_ranked(item for item in hubs.values() if item.kind is FindingKind.FAN_OUT_HUB),
    ]
    return ranked[:_HUBS_SHOWN]


def _proven_violations(observation: Observation) -> tuple[Record, ...]:
    """AD-272: the violations with a complete trace, the predicate that fails a partial run."""
    try:
        return trace_valid_violations(observation)
    except ValueError:
        return ()


def _has_import_sites(finding: Finding) -> bool:
    return finding.path is not None and all(
        step.location is not None for step in finding.path.steps
    )


def findings(
    observation: Observation,
    levels: tuple[ModuleExploreLevel, ...],
    *,
    violation_remedy: str,
    complete: bool = True,
) -> tuple[Finding, ...]:
    """Rank violations, then module and package cycles, then hubs; by size within a kind.

    AD-272: an incomplete observation ranks what one piece of evidence proves, a violation with a
    complete trace and a cycle whose every step has an import site, and no hub: a missing import
    lowers a count, so it cannot prove one.
    """
    evidence = {item.id: item for item in observation.evidence}
    root = next((level for level in levels if level.parent_id is None), None)
    modules = {item.name: item for item in root.modules} if root is not None else {}
    edges = {item.id: item for item in observation.records("dependency_edges") or ()}
    imports = {item.id: item for item in observation.records("imports") or ()}
    violations = (
        observation.records("violations") or () if complete else _proven_violations(observation)
    )
    cycles = _cycle_findings(observation, violations, evidence, modules, edges, imports)
    return (
        *_violation_findings(observation, violations, evidence, modules, imports, violation_remedy),
        *(cycles if complete else [item for item in cycles if _has_import_sites(item)]),
        *(_hub_findings(levels, evidence) if complete else ()),
    )


def findings_state(result: RunResult) -> FindingsState:
    """The state of a report result, from fields the result already carries."""
    if result.report_filter is not None:
        return FindingsState.FILTERED
    if result.observation_complete is AssessmentStatus.PASS:
        return (
            FindingsState.COMPLETE if result.findings is not None else FindingsState.NONE_RECORDED
        )
    # An incomplete run never has an empty list: an empty list means measured empty.
    if result.findings:
        return FindingsState.PARTIAL
    return FindingsState.NO_OBSERVATION if result.coverage is None else FindingsState.NOT_RANKED


def findings_note(result: RunResult) -> str | None:
    """The one sentence that explains a missing or partial list; None where the list says it all."""
    state = findings_state(result)
    gaps = (
        f" ({_count(len(result.coverage.failures), 'coverage failure')})"
        if result.coverage is not None
        else ""
    )
    if state is FindingsState.PARTIAL:
        return f"Hubs are not ranked: the observation is incomplete{gaps}."
    if state is FindingsState.NOT_RANKED:
        return (
            f"Findings are not ranked: the observation is incomplete{gaps}. "
            "Nothing was found in the part that was observed. No absence is claimed."
        )
    if state is FindingsState.NO_OBSERVATION:
        return "Findings are not ranked: no observation was produced."
    if state is FindingsState.FILTERED:
        return "A filtered result lists no findings. Run report without a filter."
    if state is FindingsState.NONE_RECORDED:
        return "This result carries no ranked findings."
    return None
