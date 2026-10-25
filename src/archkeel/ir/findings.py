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

from .baseline import ViolationFingerprint, violation_fingerprint
from .facts import Evidence, Record
from .model import (
    CyclePath,
    CyclePathStep,
    Finding,
    FindingKind,
    GraphTopologyLevel,
    Observation,
    ReportLocation,
    int_value,
    text_value,
)
from .module_explore import ModuleExploreLevel, ModuleStatistic, hub_modules

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


def _violation_findings(
    observation: Observation,
    evidence: Mapping[str, Evidence],
    modules: Mapping[str, ModuleStatistic],
    remedy: str,
) -> list[Finding]:
    grouped: defaultdict[ViolationFingerprint, list[Record]] = defaultdict(list)
    for record in observation.records("violations") or ():
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
        )
        for fingerprint, records in grouped.items()
    )


def _edge_ends(edge: Record) -> tuple[str, str]:
    """Direction lives in the data: `subjects` are sorted, so they carry no order."""
    return text_value(edge.data.get("source")), text_value(edge.data.get("target"))


def _cycle_step(
    edge: Record, imports: Mapping[str, Record], evidence: Mapping[str, Evidence]
) -> CyclePathStep | None:
    if any(identity not in imports for identity in edge.fact_ids):
        return None
    sites = [imports[identity] for identity in edge.fact_ids]
    locations = evidence_locations(evidence, (key for site in sites for key in site.evidence_ids))
    source, target = _edge_ends(edge)
    # A missing count is no proof of type-checking-only, so it never sets the flag.
    runtime = int_value(edge.data.get("runtime_count"), default=1)
    return CyclePathStep(source, target, locations[0] if locations else None, runtime == 0)


def _cycle_path(
    cycle: Record,
    edges: Mapping[str, Record],
    imports: Mapping[str, Record],
    evidence: Mapping[str, Evidence],
) -> CyclePath | None:
    """AD-263: the shortest closed walk through the cycle, from its smallest member.

    BFS distances do not depend on the order a frontier is visited in, and every choice takes
    the smallest name, so one observation always yields one walk.
    """
    internal = [edges[identity] for identity in cycle.fact_ids if identity in edges]
    if len(internal) != len(cycle.fact_ids):
        return None
    ends = {_edge_ends(edge): edge for edge in internal}
    # ponytail: each member scans every edge; index by source if a huge SCC is slow.
    successors = {
        node: [target for source, target in ends if source == node] for node in cycle.subjects
    }
    predecessors = {
        node: [source for source, target in ends if target == node] for node in cycle.subjects
    }
    start = min(cycle.subjects)
    # Edges from each member back to the start, following the edges in reverse.
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
    length = 1 + min(back[target] for target in successors[start])
    steps: list[CyclePathStep] = []
    current = start
    for remaining in range(length, 0, -1):
        following = min(
            target for target in successors[current] if back.get(target) == remaining - 1
        )
        step = _cycle_step(ends[current, following], imports, evidence)
        if step is None:
            return None
        steps.append(step)
        current = following
    return CyclePath(tuple(steps), omitted_edges=len(internal) - length)


def _cycle_findings(
    observation: Observation,
    evidence: Mapping[str, Evidence],
    modules: Mapping[str, ModuleStatistic],
) -> list[Finding]:
    edges = {item.id: item for item in observation.records("dependency_edges") or ()}
    imports = {item.id: item for item in observation.records("imports") or ()}
    # AD-98: a module-level cycle rule already reports the whole SCC, so it is listed once.
    reported = {
        frozenset(item.subjects)
        for item in observation.records("violations") or ()
        if item.kind == _MODULE_CYCLE_VIOLATION
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
                    path=_cycle_path(record, edges, imports, evidence),
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
                    path=_cycle_path(record, edges, imports, evidence),
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


def findings(
    observation: Observation, levels: tuple[ModuleExploreLevel, ...], *, violation_remedy: str
) -> tuple[Finding, ...]:
    """Rank violations, then module and package cycles, then hubs; by size within a kind."""
    evidence = {item.id: item for item in observation.evidence}
    root = next((level for level in levels if level.parent_id is None), None)
    modules = {item.name: item for item in root.modules} if root is not None else {}
    return (
        *_violation_findings(observation, evidence, modules, violation_remedy),
        *_cycle_findings(observation, evidence, modules),
        *_hub_findings(levels, evidence),
    )
