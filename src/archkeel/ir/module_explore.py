# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Sparse module exploration from Core evidence; hint candidates decide no policy."""

from collections import defaultdict
from dataclasses import dataclass, replace
from statistics import median
from typing import Literal

from .architecture_graph import ArchitectureReport, AssessmentStatus, Entity, Relationship
from .interfaces import component_owners, owner_of
from .levels import inside_levels
from .model import ComponentOwnership, JsonValue, Observation, Record
from .report_graph import architecture_report
from .structure import module_edges


@dataclass(frozen=True, slots=True)
class ModuleStatistic:
    id: str
    name: str
    path: str | None
    component_id: str | None
    candidate_ids: tuple[str, ...]
    ownership_status: AssessmentStatus
    ownership_reason: str
    symbols: int | None
    fan_in: int | None
    fan_out: int | None
    rank: int | None
    evidence_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ModuleImportCell:
    """The source row imports the target column; findings are distinct from permission."""

    source_id: str
    target_id: str
    import_sites: int | None
    relationship_ids: tuple[str, ...]
    evidence_ids: tuple[str, ...]
    finding_ids: tuple[str, ...]
    assessment_ids: tuple[str, ...]
    status: AssessmentStatus
    reasons: tuple[str, ...]
    permission: Literal["UNKNOWN"] = "UNKNOWN"
    permission_reason: str = (
        "ArchitectureReport has no authenticated per-module import permission receipt."
    )


@dataclass(frozen=True, slots=True)
class HintCandidate:
    kind: Literal["used_elsewhere", "hub", "heavy", "no_owner"]
    module_ids: tuple[str, ...]
    component_ids: tuple[str, ...]
    count: int
    relationship_ids: tuple[str, ...]
    evidence_ids: tuple[str, ...]
    question: str
    provisional: Literal[True] = True


@dataclass(frozen=True, slots=True)
class ModuleExploreLevel:
    parent_id: str | None
    component_ids: tuple[str, ...]
    modules: tuple[ModuleStatistic, ...]
    cells: tuple[ModuleImportCell, ...]
    import_status: AssessmentStatus
    import_reason: str
    uncertain_relationship_ids: tuple[str, ...] = ()
    hint_candidates: tuple[HintCandidate, ...] = ()


def _count(value: JsonValue) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


def _cells(model: Observation, report: ArchitectureReport) -> tuple[ModuleImportCell, ...]:
    if report.observed is None:
        return ()
    modules = {
        item.id: item.qualified_name
        for item in report.observed.entities
        if item.kind == "module" and item.presence == "defined"
    }
    identities = {name: identity for identity, name in modules.items()}
    weights = {
        (identities[source], identities[target]): count
        for source, target, count in module_edges(model)
        if source in identities and target in identities
    }
    sites: dict[tuple[str, str], list[Relationship]] = defaultdict(list)
    for edge in report.observed.relationships:
        if edge.kind == "imports" and edge.source_id in modules and edge.target_id in modules:
            assert edge.target_id is not None
            sites[edge.source_id, edge.target_id].append(edge)
    cells = []
    for source, target in sorted(set(weights) | set(sites)):
        relationships = tuple(sorted(item.id for item in sites[source, target]))
        references = set(relationships)
        findings = tuple(
            item for item in report.findings if references.intersection(item.graph_subject_ids)
        )
        assessments = (
            tuple(
                item
                for item in report.comparison.assessments
                if references.intersection(item.observed_ids)
            )
            if report.comparison
            else ()
        )
        failed = any(item.status == "FAIL" for item in findings) or any(
            item.status == "FAIL" for item in assessments
        )
        cells.append(
            ModuleImportCell(
                source,
                target,
                weights.get((source, target)),
                relationships,
                tuple(
                    sorted(
                        {
                            identity
                            for item in sites[source, target]
                            for identity in item.evidence_ids
                        }
                        | {identity for item in findings for identity in item.evidence_ids}
                        | {identity for item in assessments for identity in item.evidence_ids}
                    )
                ),
                tuple(sorted(item.id for item in findings)),
                tuple(sorted(item.id for item in assessments)),
                "FAIL" if failed else "UNKNOWN",
                tuple(
                    sorted(
                        {item.title for item in findings} | {item.reason for item in assessments}
                    )
                ),
            )
        )
    return tuple(cells)


def _statistic(
    entity: Entity,
    record: Record,
    members: tuple[str, ...],
    candidates: tuple[str, ...],
    complete: bool,
) -> ModuleStatistic:
    owner = members[0] if len(members) == 1 and members == candidates else None
    return ModuleStatistic(
        entity.id,
        entity.qualified_name,
        entity.file_path,
        owner,
        candidates,
        "PASS" if owner is not None else "UNKNOWN",
        "Authenticated component membership."
        if owner is not None
        else "Several components claim this module at this level."
        if len(candidates) > 1
        else "No authenticated component membership at this level.",
        _count(record.data.get("symbol_count")),
        _count(record.data.get("fan_in")) if complete else None,
        _count(record.data.get("fan_out")) if complete else None,
        _count(record.data.get("rank")),
        tuple(sorted(entity.evidence_ids)),
    )


def module_exploration(model: Observation) -> tuple[ModuleExploreLevel, ...]:
    """Read authenticated memberships; existing Core ownership helpers explain gaps.

    Candidate hints are an unapproved review artifact. No production report consumes them.
    """
    report = architecture_report(model)
    if report.observed is None:
        return (
            ModuleExploreLevel(
                None,
                (),
                (),
                (),
                "UNKNOWN",
                report.unavailable or "Authenticated Target is unavailable.",
            ),
        )
    if report.target is None:
        records = {item.id: item for item in model.records("modules") or ()}
        return (
            ModuleExploreLevel(
                None,
                (),
                tuple(
                    _statistic(item, records[item.id], (), (), False)
                    for item in sorted(report.observed.entities, key=lambda item: item.id)
                    if item.kind == "module" and item.presence == "defined"
                ),
                _cells(model, report),
                "UNKNOWN",
                "Authenticated Target is unavailable.",
            ),
        )
    observed, target = report.observed, report.target
    intents = {item.component_id: item for item in target.component_intents}
    labels: dict[str, str] = {}

    def scope(identity: str) -> str:
        if identity not in labels:
            intent = intents[identity]
            label = intent.label or identity
            labels[identity] = f"{scope(intent.parent_id)}:{label}" if intent.parent_id else label
        return labels[identity]

    scope_ids = {scope(identity): identity for identity in intents}
    owners: dict[str | None, tuple[ComponentOwnership, ...]] = {None: component_owners(model)}
    for inside_level in inside_levels(model):
        owners[scope_ids[inside_level.parent]] = tuple(
            (f"{inside_level.parent}:{item.label}", item.packages, item.exact_modules)
            for item in inside_level.components
        )
    modules = tuple(
        item for item in observed.entities if item.kind == "module" and item.presence == "defined"
    )
    records = {item.id: item for item in model.records("modules") or ()}
    memberships = {item.component_id: set(item.module_ids) for item in report.memberships}
    covered = {
        item.scope_id
        for item in observed.coverage
        if "imports" in item.relationship_kinds and item.status == "complete"
    }
    complete = (
        model.coverage.status == "PASS"
        and model.records("imports") is not None
        and model.records("dependency_edges") is not None
        and bool(modules)
        and all(item.id in covered for item in modules)
        and not any(
            item.kind == "imports" and item.target_id is None for item in observed.relationships
        )
    )
    cells = _cells(model, report)
    complete = complete and all(
        cell.import_sites == len(cell.relationship_ids) and bool(cell.relationship_ids)
        for cell in cells
    )
    parents = (
        None,
        *sorted({item.parent_id for item in intents.values() if item.parent_id is not None}),
    )
    levels = []
    for parent in parents:
        groups = tuple(
            sorted(item.component_id for item in intents.values() if item.parent_id == parent)
        )
        selected = tuple(
            item for item in modules if parent is None or item.id in memberships.get(parent, set())
        )
        statistics = []
        for module in selected:
            members = tuple(
                identity for identity in groups if module.id in memberships.get(identity, set())
            )
            candidates = tuple(
                sorted(
                    scope_ids[label]
                    for candidate in owners.get(parent, ())
                    if (label := owner_of(module.qualified_name, (candidate,))) is not None
                )
            )
            statistics.append(_statistic(module, records[module.id], members, candidates, complete))
        order = {identity: index for index, identity in enumerate(groups)}
        ordered = tuple(
            sorted(
                statistics,
                key=lambda item: (
                    order.get(item.component_id, len(groups))
                    if item.component_id is not None
                    else len(groups),
                    item.rank is None,
                    item.rank or 0,
                    item.name,
                    item.id,
                ),
            )
        )
        selected_ids = {item.id for item in selected}
        level = ModuleExploreLevel(
            parent,
            groups,
            ordered,
            tuple(
                item
                for item in cells
                if item.source_id in selected_ids and item.target_id in selected_ids
            ),
            "PASS" if complete else "UNKNOWN",
            "Complete module import evidence."
            if complete
            else "Module/import coverage or resolved import-site evidence is incomplete.",
            tuple(
                sorted(
                    item.id
                    for item in observed.relationships
                    if item.kind == "imports"
                    and item.target_id is None
                    and item.source_id in selected_ids
                )
            ),
        )
        levels.append(level)
    root = next(level for level in levels if level.parent_id is None)
    return tuple(
        replace(
            level,
            hint_candidates=_hint_candidates(level, root, cells, model.coverage.status == "PASS"),
        )
        for level in levels
    )


def _hint_candidates(
    level: ModuleExploreLevel,
    root: ModuleExploreLevel,
    cells: tuple[ModuleImportCell, ...],
    inventory_complete: bool,
) -> tuple[HintCandidate, ...]:
    """Mockup thresholds for human calibration, deliberately outside production defaults."""
    root_modules = {item.id: item for item in root.modules}
    incoming: dict[str, list[ModuleImportCell]] = defaultdict(list)
    for cell in cells:
        incoming[cell.target_id].append(cell)
    hints = []

    def hint(
        kind: Literal["used_elsewhere", "hub", "heavy", "no_owner"],
        modules: tuple[ModuleStatistic, ...],
        components: tuple[str, ...],
        count: int,
        question: str,
    ) -> HintCandidate:
        sites = tuple(cell for module in modules for cell in incoming[module.id])
        return HintCandidate(
            kind,
            tuple(item.id for item in modules),
            components,
            count,
            tuple(sorted({identity for cell in sites for identity in cell.relationship_ids})),
            tuple(
                sorted(
                    {identity for cell in sites for identity in cell.evidence_ids}
                    | {identity for module in modules for identity in module.evidence_ids}
                )
            ),
            question,
        )

    if level.import_status == "PASS":
        elsewhere: dict[tuple[str, str], list[ModuleStatistic]] = defaultdict(list)
        for module in level.modules:
            owner = root_modules[module.id].component_id
            users = {root_modules[cell.source_id].component_id for cell in incoming[module.id]}
            if owner is not None and len(users) == 1 and None not in users and owner not in users:
                user = next(iter(users))
                assert user is not None
                elsewhere[owner, user].append(module)
        for pair, candidates in sorted(elsewhere.items()):
            group = tuple(sorted(candidates, key=lambda item: item.name))
            hints.append(
                hint(
                    "used_elsewhere",
                    group,
                    pair,
                    sum(cell.import_sites or 0 for item in group for cell in incoming[item.id]),
                    "Do these modules belong to their only consumer, or are they the "
                    "owner's intended interface for it?",
                )
            )
        hubs = sorted(
            (item for item in level.modules if item.fan_in is not None and item.fan_in >= 10),
            key=lambda item: (-(item.fan_in or 0), item.name),
        )[:3]
        hints.extend(
            hint(
                "hub",
                (item,),
                (),
                item.fan_in or 0,
                "Is this the intended shared kernel, or does it hold several responsibilities?",
            )
            for item in hubs
        )
    sizes = [item.symbols for item in level.modules if item.symbols is not None]
    if inventory_complete and sizes and len(sizes) == len(level.modules):
        threshold = max(40, 3 * median(sizes))
        heavy = sorted(
            (
                item
                for item in level.modules
                if item.symbols is not None and item.symbols >= threshold
            ),
            key=lambda item: (-(item.symbols or 0), item.name),
        )[:3]
        hints.extend(
            hint(
                "heavy",
                (item,),
                (),
                item.symbols or 0,
                "Does this module have one responsibility, or several that grew together?",
            )
            for item in heavy
        )
    if inventory_complete:
        hints.extend(
            hint(
                "no_owner",
                (item,),
                (),
                0,
                "Which component owns this module, or is it a namespace container?",
            )
            for item in sorted(level.modules, key=lambda item: item.name)
            if not item.candidate_ids and item.component_id is None
        )
    return tuple(hints)
