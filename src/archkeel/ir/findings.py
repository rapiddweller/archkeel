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
from .model import Finding, FindingKind, GraphTopologyLevel, Observation, ReportLocation
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
            records[0].title,
            f"{', '.join(fingerprint.rules)} is broken {_count(len(records), 'time')}. {remedy}",
            evidence_locations(evidence, (key for item in records for key in item.evidence_ids)),
            _components(fingerprint.subjects, modules),
        )
        for fingerprint, records in grouped.items()
    )


def _cycle_findings(
    observation: Observation,
    evidence: Mapping[str, Evidence],
    modules: Mapping[str, ModuleStatistic],
) -> list[Finding]:
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
                )
            )
        elif level == GraphTopologyLevel.PACKAGE and backed_by == ():
            # A package cycle that a module cycle backs is that module cycle; only the
            # roll-up adds a finding (AD-98).
            package_cycles.append(
                Finding(
                    FindingKind.PACKAGE_CYCLE, (), members, size, record.title, sentence, (), ()
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
    return _ranked(hubs.values())[:_HUBS_SHOWN]


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
