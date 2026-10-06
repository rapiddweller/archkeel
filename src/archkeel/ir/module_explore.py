# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Sparse module exploration from Core evidence; hints stay provisional."""

from collections import Counter, defaultdict
from dataclasses import dataclass, replace
from statistics import median
from typing import Literal

from .architecture_graph import (
    ArchitectureGraph,
    ArchitectureReport,
    AssessmentStatus,
    ComponentIntent,
    Coverage,
    Entity,
    GraphAssessment,
    Relationship,
    ReportFinding,
    RuleAssessment,
)
from .decisions import _rule_receipt_complete, rule_assessments
from .interfaces import component_owners, owner_of
from .levels import inside_levels
from .model import (
    ComponentOwnership,
    JsonValue,
    Observation,
    Record,
    in_scope,
    module_in_ownership,
    text_value,
)
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
    symbol_coverage: tuple[Coverage, ...]


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


def _rule_applies(
    declaration: Record | None,
    assessment: RuleAssessment,
    source: str,
    target: str,
    site: Record,
    site_findings: tuple[ReportFinding, ...],
    source_owners: set[str],
    target_owners: set[str],
    intents: dict[str, ComponentIntent],
    scope_ids: dict[str, str],
) -> bool:
    if declaration is None or assessment.kind not in {
        "complete_requires",
        "forbidden_dependency",
        "interface_boundary",
        "sibling_isolation",
    }:
        return False
    if (
        site.data.get("under_type_checking") is True
        and declaration.data.get("include_type_checking", True) is False
    ):
        return False
    if assessment.kind == "forbidden_dependency":
        allowed_sources = declaration.data.get("allowed_sources")
        if isinstance(allowed_sources, tuple) and site.data.get("source_module") in allowed_sources:
            return False
    parent_scope = text_value(declaration.data.get("parent_id")) or None
    if parent_scope is not None and parent_scope not in scope_ids:
        return False
    parent = scope_ids[parent_scope] if parent_scope is not None else None
    for source_id in source_owners:
        source_intent = intents[source_id]
        for target_id in target_owners:
            target_intent = intents[target_id]
            if (
                source_id == target_id
                or source_intent.parent_id != parent
                or target_intent.parent_id != parent
            ):
                continue
            if assessment.kind == "forbidden_dependency":
                source_selector = text_value(declaration.data.get("source"))
                target_selector = text_value(declaration.data.get("target"))
                source_match = module_in_ownership(source, (source_selector,), ()) or (
                    source_selector in {source_id, source_intent.label}
                )
                target_match = module_in_ownership(target, (target_selector,), ()) or (
                    target_selector in {target_id, target_intent.label}
                )
                if source_match and target_match:
                    return True
            elif assessment.kind == "interface_boundary":
                if target_intent.public is not None and not any(
                    item.kind == "forbidden_dependency" for item in site_findings
                ):
                    return True
            elif assessment.kind == "sibling_isolation":
                source_member = next(
                    (item for item in declaration.subjects if in_scope(source, item)), None
                )
                target_member = next(
                    (item for item in declaration.subjects if in_scope(target, item)), None
                )
                if (
                    source_member is not None
                    and target_member is not None
                    and source_member != target_member
                ):
                    return True
            else:
                return True
    return False


def _cells(
    model: Observation, report: ArchitectureReport, scope_ids: dict[str, str]
) -> tuple[ModuleImportCell, ...]:
    if report.observed is None:
        return ()
    modules = {
        item.id: item.qualified_name
        for item in report.observed.entities
        if item.kind == "module" and item.presence == "defined"
    }
    identities = {name: identity for identity, name in modules.items()}
    intents = (
        {item.component_id: item for item in report.target.component_intents}
        if report.target
        else {}
    )
    memberships = {
        identity: {item.component_id for item in report.memberships if identity in item.module_ids}
        for identity in modules
    }
    undecided = Counter(
        rule_id for item in model.records("unknowns") or () for rule_id in item.rule_ids
    )
    core_assessments = {
        item.id: item
        for item in rule_assessments(
            model,
            undecided_by_rule=undecided,
            complete=model.coverage.status == "PASS",
        )
    }
    declarations = {item.id: item for item in model.records("declarations") or ()}
    imports = {item.id: item for item in model.records("imports") or ()}
    weights = {
        (identities[source], identities[target]): count
        for source, target, count in module_edges(model)
        if source in identities and target in identities
    }
    sites: dict[tuple[str, str], list[Relationship]] = defaultdict(list)
    for edge in report.observed.relationships:
        if (
            edge.kind == "imports"
            and edge.source_id in modules
            and edge.target_id is not None
            and edge.target_id in modules
        ):
            sites[edge.source_id, edge.target_id].append(edge)
    return tuple(
        _import_cell(
            source,
            target,
            modules,
            weights,
            sites,
            model,
            report,
            core_assessments,
            declarations,
            imports,
            memberships,
            intents,
            scope_ids,
        )
        for source, target in sorted(set(weights) | set(sites))
    )


def _import_cell(
    source: str,
    target: str,
    modules: dict[str, str],
    weights: dict[tuple[str, str], int],
    sites: dict[tuple[str, str], list[Relationship]],
    model: Observation,
    report: ArchitectureReport,
    core_assessments: dict[str, RuleAssessment],
    declarations: dict[str, Record],
    imports: dict[str, Record],
    memberships: dict[str, set[str]],
    intents: dict[str, ComponentIntent],
    scope_ids: dict[str, str],
) -> ModuleImportCell:
    edges = sites[source, target]
    relationships = tuple(sorted(item.id for item in edges))
    references = set(relationships)
    findings = tuple(
        item for item in report.findings if references.intersection(item.graph_subject_ids)
    )
    graph_assessments = (
        tuple(
            item
            for item in report.comparison.assessments
            if references.intersection(item.observed_ids)
        )
        if report.comparison
        else ()
    )
    site_results: list[tuple[tuple[RuleAssessment, ...], frozenset[str], frozenset[str]]] = []
    for edge in edges:
        site_records = tuple(
            imports[identity] for identity in edge.record_ids if identity in imports
        )
        if not site_records or len(site_records) != len(edge.record_ids):
            site_results.append(((), frozenset(), frozenset()))
            continue
        for site in site_records:
            site_findings = tuple(item for item in findings if edge.id in item.graph_subject_ids)
            applicable = tuple(
                assessment
                for assessment in core_assessments.values()
                if (declaration := declarations.get(assessment.id)) is not None
                and _rule_applies(
                    declaration,
                    assessment,
                    modules[source],
                    modules[target],
                    site,
                    site_findings,
                    memberships[source],
                    memberships[target],
                    intents,
                    scope_ids,
                )
            )
            undecided_sites = frozenset(
                assessment.id
                for assessment in applicable
                if _site_undecided(model, assessment.id, site.id)
            )
            proven = frozenset(
                assessment.id
                for assessment in applicable
                if assessment.evaluation_proven
                and assessment.id not in undecided_sites
                and _cell_receipt_proven(
                    model,
                    assessment,
                    declarations[assessment.id],
                    modules[source],
                    modules[target],
                )
            )
            site_results.append((applicable, proven, undecided_sites))
    if source != target and weights.get((source, target)) != len(edges):
        site_results.append(((), frozenset(), frozenset()))
    status = _cell_status(findings, graph_assessments, site_results)
    reasons = _cell_reasons(findings, graph_assessments, site_results, core_assessments)
    evidence = (
        {identity for edge in edges for identity in edge.evidence_ids}
        | {identity for item in findings for identity in item.evidence_ids}
        | {identity for item in graph_assessments for identity in item.evidence_ids}
    )

    return ModuleImportCell(
        source,
        target,
        len(relationships) if source == target else weights.get((source, target)),
        relationships,
        tuple(sorted(evidence)),
        tuple(sorted(item.id for item in findings)),
        tuple(sorted(item.id for item in graph_assessments)),
        status,
        tuple(sorted(reasons)),
    )


def _cell_status(
    findings: tuple[ReportFinding, ...],
    graph_assessments: tuple[GraphAssessment, ...],
    site_results: list[tuple[tuple[RuleAssessment, ...], frozenset[str], frozenset[str]]],
) -> AssessmentStatus:
    evidence = findings + graph_assessments
    if any(item.status == "FAIL" for item in evidence):
        return "FAIL"
    if (
        any(item.status == "UNKNOWN" for item in evidence)
        or not site_results
        or any(
            not applicable or len(proven) != len(applicable)
            for applicable, proven, _ in site_results
        )
    ):
        return "UNKNOWN"
    return "PASS"


def _cell_reasons(
    findings: tuple[ReportFinding, ...],
    graph_assessments: tuple[GraphAssessment, ...],
    site_results: list[tuple[tuple[RuleAssessment, ...], frozenset[str], frozenset[str]]],
    core_assessments: dict[str, RuleAssessment],
) -> set[str]:
    reasons = {item.title for item in findings} | {item.reason for item in graph_assessments}
    uncovered = False
    for applicable, proven, undecided in site_results:
        if not applicable or len(proven) != len(applicable):
            uncovered = True
        if not applicable:
            continue
        for item in applicable:
            if item.id in proven:
                reasons.add(f"{item.id}: complete evaluator receipt covers this import.")
                continue
            reason = (
                core_assessments[item.id].reason
                if not item.evaluation_proven
                else "Core left this import site undecided."
                if item.id in undecided
                else "No complete evaluator receipt covers every import site."
            )
            reasons.add(f"{item.id}: {reason}")
    if uncovered:
        reasons.add("Complete evidence is missing for one or more import sites.")
    reasons.update(
        f"{identity}: {core_assessments[identity].reason}"
        for finding in findings
        if finding.status == "UNKNOWN"
        for identity in finding.rule_ids
        if identity in core_assessments
    )
    return reasons or {"No complete applicable import-rule assessment establishes this cell."}


def _cell_receipt_proven(
    model: Observation,
    assessment: RuleAssessment,
    declaration: Record,
    source: str,
    target: str,
) -> bool:
    subjects = {source} if assessment.kind == "forbidden_dependency" else {source, target}
    return any(
        record.kind == "rule_evaluation"
        and assessment.id in record.rule_ids
        and subjects <= set(record.subjects)
        and _rule_receipt_complete(declaration, record)
        for record in model.records("scope_observations") or ()
    )


def _site_undecided(model: Observation, rule_id: str, import_id: str) -> bool:
    return any(
        rule_id in item.rule_ids and (not item.fact_ids or import_id in item.fact_ids)
        for item in model.records("unknowns") or ()
    )


def _statistic(
    entity: Entity,
    record: Record,
    members: tuple[str, ...],
    candidates: tuple[str, ...],
    complete: bool,
    coverage: tuple[Coverage, ...],
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
        tuple(item for item in coverage if item.scope_id == entity.id and item.entity_kinds),
    )


def module_exploration(model: Observation) -> tuple[ModuleExploreLevel, ...]:
    """Read authenticated memberships; existing Core ownership helpers explain gaps.

    Hints stay provisional and do not establish policy.
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
                    _statistic(item, records[item.id], (), (), False, report.observed.coverage)
                    for item in sorted(report.observed.entities, key=lambda item: item.id)
                    if item.kind == "module" and item.presence == "defined"
                ),
                _cells(model, report, {}),
                "UNKNOWN",
                "Authenticated Target is unavailable.",
            ),
        )
    observed, target = report.observed, report.target
    intents = {item.component_id: item for item in target.component_intents}
    scope_ids, owners = _scope_owners(model, intents)
    modules = tuple(
        item for item in observed.entities if item.kind == "module" and item.presence == "defined"
    )
    records = {item.id: item for item in model.records("modules") or ()}
    memberships = {item.component_id: set(item.module_ids) for item in report.memberships}
    cells = _cells(model, report, scope_ids)
    complete = _imports_complete(model, observed, modules, cells)
    parents = (
        None,
        *sorted({item.parent_id for item in intents.values() if item.parent_id is not None}),
    )
    levels = []
    for parent in parents:
        groups = tuple(
            sorted(item.component_id for item in intents.values() if item.parent_id == parent)
        )
        level = _module_level(
            parent,
            groups,
            modules,
            memberships,
            records,
            scope_ids,
            owners,
            complete,
            observed,
            cells,
        )
        levels.append(level)
    root = next(level for level in levels if level.parent_id is None)
    return tuple(
        replace(
            level,
            hint_candidates=_hint_candidates(
                level, root, cells, intents, model.coverage.status == "PASS"
            ),
        )
        for level in levels
    )


def _hint_candidates(
    level: ModuleExploreLevel,
    root: ModuleExploreLevel,
    cells: tuple[ModuleImportCell, ...],
    intents: dict[str, ComponentIntent],
    inventory_complete: bool,
) -> tuple[HintCandidate, ...]:
    """Provisional question candidates preserve native ownership and coverage."""
    root_modules = {item.id: item for item in root.modules}
    incoming: dict[str, list[ModuleImportCell]] = defaultdict(list)
    for cell in cells:
        incoming[cell.target_id].append(cell)
    hints: list[HintCandidate] = []

    if level.import_status == "PASS":
        hints.extend(_used_elsewhere_hints(level, root_modules, incoming, intents))
        hubs = sorted(
            (item for item in level.modules if item.fan_in is not None and item.fan_in >= 10),
            key=lambda item: (-(item.fan_in or 0), item.name),
        )[:3]
        hints.extend(
            _hint(
                incoming,
                "hub",
                (item,),
                (),
                item.fan_in or 0,
                "Is this the intended shared kernel, or does it hold several responsibilities?",
            )
            for item in hubs
        )
    hints.extend(
        _hint(
            incoming,
            "heavy",
            (item,),
            (),
            item.symbols or 0,
            "Does this module have one responsibility, or several that grew together?",
        )
        for item in _heavy_modules(level, inventory_complete)
    )
    if inventory_complete:
        hints.extend(
            _hint(
                incoming,
                "no_owner",
                (item,),
                (),
                0,
                "Which component owns this module, or is it a namespace container?",
            )
            for item in sorted(level.modules, key=lambda item: item.name)
            if not item.candidate_ids and item.component_id is None
        )
    kind_order = {"used_elsewhere": 0, "hub": 1, "heavy": 2, "no_owner": 3}
    return tuple(
        sorted(
            hints,
            key=lambda item: (
                kind_order[item.kind],
                -item.count,
                item.component_ids,
                tuple(root_modules[identity].name for identity in item.module_ids),
            ),
        )
    )


def _used_elsewhere_hints(
    level: ModuleExploreLevel,
    root_modules: dict[str, ModuleStatistic],
    incoming: dict[str, list[ModuleImportCell]],
    intents: dict[str, ComponentIntent],
) -> tuple[HintCandidate, ...]:
    elsewhere: dict[tuple[str, str], list[ModuleStatistic]] = defaultdict(list)
    for module in level.modules:
        owner = root_modules[module.id].component_id
        users = {root_modules[cell.source_id].component_id for cell in incoming[module.id]}
        if owner is not None and len(users) == 1 and None not in users and owner not in users:
            user = next(iter(users))
            if user is not None:
                elsewhere[owner, user].append(module)
    hints = []
    for owner, user in sorted(elsewhere):
        group = tuple(sorted(elsewhere[owner, user], key=lambda item: item.name))
        names = ", ".join(item.name for item in group)
        sites = sum(cell.import_sites or 0 for item in group for cell in incoming[item.id])
        owner_name = intents[owner].label or owner
        user_name = intents[user].label or user
        question = (
            f"Does {names} belong to {user_name}, or is it {owner_name}'s intended "
            f"interface for {user_name}?"
            if len(group) == 1
            else f"Do {names} belong to {user_name}, or are they {owner_name}'s intended "
            f"interface for {user_name}?"
        )
        hints.append(
            _hint(
                incoming,
                "used_elsewhere",
                group,
                (owner, user),
                sites,
                question,
            )
        )
    return tuple(hints)


def _scope_owners(
    model: Observation, intents: dict[str, ComponentIntent]
) -> tuple[dict[str, str], dict[str | None, tuple[ComponentOwnership, ...]]]:
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
    return scope_ids, owners


def _module_level(
    parent: str | None,
    groups: tuple[str, ...],
    modules: tuple[Entity, ...],
    memberships: dict[str, set[str]],
    records: dict[str, Record],
    scope_ids: dict[str, str],
    owners: dict[str | None, tuple[ComponentOwnership, ...]],
    complete: bool,
    observed: ArchitectureGraph,
    cells: tuple[ModuleImportCell, ...],
) -> ModuleExploreLevel:
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
        statistics.append(
            _statistic(module, records[module.id], members, candidates, complete, observed.coverage)
        )
    ordered = _ordered_statistics(statistics, groups)
    selected_ids = {item.id for item in selected}
    return ModuleExploreLevel(
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


def _ordered_statistics(
    statistics: list[ModuleStatistic], groups: tuple[str, ...]
) -> tuple[ModuleStatistic, ...]:
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
    return ordered


def _hint(
    incoming: dict[str, list[ModuleImportCell]],
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


def _heavy_modules(
    level: ModuleExploreLevel, inventory_complete: bool
) -> tuple[ModuleStatistic, ...]:
    sizes = [item.symbols for item in level.modules if item.symbols is not None]
    symbols_complete = all(
        item.symbol_coverage and all(entry.status == "complete" for entry in item.symbol_coverage)
        for item in level.modules
    )
    if inventory_complete and symbols_complete and sizes and len(sizes) == len(level.modules):
        threshold = max(40, 3 * median(sizes))
        return tuple(
            sorted(
                (
                    item
                    for item in level.modules
                    if item.symbols is not None and item.symbols >= threshold
                ),
                key=lambda item: (-(item.symbols or 0), item.name),
            )[:3]
        )
    return ()


def _imports_complete(
    model: Observation,
    observed: ArchitectureGraph,
    modules: tuple[Entity, ...],
    cells: tuple[ModuleImportCell, ...],
) -> bool:
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
    return complete and all(
        cell.import_sites == len(cell.relationship_ids) and bool(cell.relationship_ids)
        for cell in cells
    )
