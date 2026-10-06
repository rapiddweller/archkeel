# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Small presentation payloads from authenticated Core values."""

from collections import Counter, defaultdict
from dataclasses import asdict, replace
from pathlib import PurePosixPath

from archkeel.ir.architecture_graph import ArchitectureReport, Coverage
from archkeel.ir.architecture_projection import ArchitectureProjection
from archkeel.ir.model import Observation, RunResult, stable_id
from archkeel.ir.module_explore import ModuleExploreLevel, ModuleStatistic, module_exploration


def _reference_fields(item: dict[str, object], references: dict[str, int]) -> dict[str, object]:
    for field in ("evidence_ids", "relationship_ids", "finding_ids", "assessment_ids"):
        values = item.get(field)
        if isinstance(values, (tuple, list)):
            item[field] = [references.setdefault(value, len(references)) for value in values]
    reason = item.get("permission_reason")
    if isinstance(reason, str):
        item["permission_reason"] = references.setdefault(reason, len(references))
    return item


def _component_edges(level: ModuleExploreLevel) -> list[dict[str, object]]:
    owners = {item.id: item.component_id for item in level.modules}
    pairs: dict[tuple[str, str], list[int]] = defaultdict(list)
    for index, cell in enumerate(level.cells):
        source, target = owners.get(cell.source_id), owners.get(cell.target_id)
        if source is not None and target is not None and source != target:
            pairs[source, target].append(index)
    return [
        {
            "source_id": source,
            "target_id": target,
            "import_sites": sum(level.cells[index].import_sites or 0 for index in indices)
            if all(level.cells[index].import_sites is not None for index in indices)
            else None,
            "status": "FAIL"
            if any(level.cells[index].status == "FAIL" for index in indices)
            else "UNKNOWN",
        }
        for (source, target), indices in sorted(pairs.items())
    ]


def _level_payload(
    level: ModuleExploreLevel,
    references: dict[str, int],
    cells: dict[tuple[str, str], int],
    questions: list[dict[str, object]],
    assignments: dict[tuple[str, str | None, tuple[str, ...], str, str], int],
) -> dict[str, object]:
    question_ids = []
    for hint in level.hint_candidates:
        question_ids.append(len(questions))
        questions.append(_reference_fields(asdict(hint), references))
    return {
        "parent_id": level.parent_id,
        "component_ids": level.component_ids,
        "modules": [
            assignments.setdefault(
                (
                    item.id,
                    item.component_id,
                    item.candidate_ids,
                    item.ownership_status,
                    item.ownership_reason,
                ),
                len(assignments),
            )
            for item in level.modules
        ],
        "cells": [cells[item.source_id, item.target_id] for item in level.cells],
        "edges": _component_edges(level),
        "import_status": level.import_status,
        "import_reason": level.import_reason,
        "questions": question_ids,
    }


def _leaf_levels(
    report: ArchitectureReport, levels: tuple[ModuleExploreLevel, ...]
) -> tuple[ModuleExploreLevel, ...]:
    if report.target is None:
        return levels
    native = {level.parent_id: level for level in levels}
    memberships = {item.component_id: set(item.module_ids) for item in report.memberships}
    leaves = []
    for intent in report.target.component_intents:
        if intent.component_id in native:
            continue
        parent = native.get(intent.parent_id)
        if parent is None:
            continue
        selected = memberships.get(intent.component_id, set())
        leaves.append(
            replace(
                parent,
                parent_id=intent.component_id,
                component_ids=(),
                modules=tuple(item for item in parent.modules if item.id in selected),
                cells=tuple(
                    item
                    for item in parent.cells
                    if item.source_id in selected and item.target_id in selected
                ),
                hint_candidates=(),
            )
        )
    return (*levels, *leaves)


def _components_payload(
    report: ArchitectureReport,
    projection: ArchitectureProjection,
    modules: tuple[ModuleStatistic, ...],
    references: dict[str, int],
) -> list[dict[str, object]]:
    components = []
    indices = {item.id: index for index, item in enumerate(projection.components)}
    for component in projection.components:
        item = asdict(component)
        for field in (
            "modules",
            "role",
            "permissions",
            "finding_ids",
            "namespace",
            "selector_prefix",
            "packages",
            "exact_modules",
            "scope",
        ):
            del item[field]
        del item["reason"]
        item["reason_ref"] = references.setdefault(component.reason, len(references))
        item["provenance"] = [
            references.setdefault(identity, len(references)) for identity in component.provenance
        ]
        item["public"] = (
            [references.setdefault(selector, len(references)) for selector in component.public]
            if component.public is not None
            else None
        )
        item["used_by"] = [
            [indices[entry.component_id], entry.import_sites] for entry in component.used_by
        ]
        item["requires"] = [
            {
                **{field: value for field, value in asdict(entry).items() if field != "rationale"},
                "rationale_ref": references.setdefault(entry.rationale, len(references)),
                "target_id": indices[entry.target_id],
            }
            for entry in component.requires
        ]
        members = next(
            (
                entry.module_ids
                for entry in report.memberships
                if entry.component_id == component.id
            ),
            (),
        )
        statistics = [entry for entry in modules if entry.id in members]
        item |= {
            "observed_modules": len(statistics),
            "observed_symbols": sum(entry.symbols or 0 for entry in statistics)
            if all(entry.symbols is not None for entry in statistics)
            else None,
            "symbols_complete": bool(statistics)
            and all(
                entry.symbols is not None
                and entry.symbol_coverage
                and all(coverage.status == "complete" for coverage in entry.symbol_coverage)
                for entry in statistics
            ),
        }
        components.append(item)
    return components


def _declared_modules(report: ArchitectureReport) -> list[dict[str, object]]:
    if report.target is None:
        return []
    entities = {item.id: item for item in report.target.entities}
    children = Counter(item.parent_id for item in report.target.entities)
    module_ids = {item.id for item in report.target.entities if item.kind == "module"}
    modules: list[dict[str, object]] = []
    for entity in report.target.entities:
        if entity.kind != "module":
            continue
        parent = entities.get(entity.parent_id or "")
        while parent is not None and parent.kind != "component":
            parent = entities.get(parent.parent_id or "")
        if parent is not None:
            modules.append(
                dict(
                    id=entity.id,
                    name=entity.qualified_name,
                    path=entity.file_path,
                    component_id=parent.id,
                    declarations=children[entity.id],
                    responsibilities=entity.responsibilities,
                    provenance=entity.provenance,
                    relationships=[
                        asdict(item)
                        for item in report.target.relationships
                        if item.source_id == entity.id and item.target_id in module_ids
                    ],
                )
            )
    return modules


def _finding_payload(
    model: Observation,
    projection: ArchitectureProjection,
    references: dict[str, int],
) -> tuple[list[dict[str, object]], dict[str | None, set[str]]]:
    violations = model.records("violations") or ()
    evidence = {item.id: item for item in model.evidence}
    entries: list[dict[str, object]] = []
    for item in violations:
        locations = sorted(
            [
                (evidence[identity].file, evidence[identity].line)
                for identity in item.evidence_ids
                if identity in evidence and evidence[identity].file is not None
            ],
            key=lambda location: (location[0] or "", location[1] or -1),
        )
        path, line = locations[0] if locations else (None, None)
        entries.append(
            {
                "id": item.id,
                "rule_ids": item.rule_ids,
                "kind": item.kind,
                "title": item.title,
                "path": path,
                "line": line,
                "remedy_ref": references.setdefault(projection.violation_remedy, len(references)),
            }
        )

    violation_ids = {item.id for item in violations}
    selected_by_component = {
        component.id: violation_ids & set(component.finding_ids)
        for component in projection.components
    }
    children: dict[str, set[str]] = defaultdict(set)
    for component in projection.components:
        if component.parent_id is not None:
            children[component.parent_id] |= {component.id}

    def descendants(identity: str) -> set[str]:
        result = {identity}
        pending = [identity]
        while pending:
            child = pending.pop()
            for nested in children[child] - result:
                result |= {nested}
                pending.append(nested)
        return result

    level_findings: dict[str | None, set[str]] = {}
    for component in projection.components:
        level_findings[component.id] = {
            identity
            for nested in descendants(component.id)
            for identity in selected_by_component.get(nested, set())
        }
    level_findings[None] = {item.id for item in violations}
    return entries, level_findings


def _system_balance(
    balances: dict[str | None, dict[str, int | None]],
) -> dict[str, int | None]:
    fields = ("declared", "used", "allowed_unused", "undeclared")
    return {
        field: None
        if any(balance[field] is None for balance in balances.values())
        else sum(balance[field] or 0 for balance in balances.values())
        for field in fields
    }


def _level_balance(
    level: ModuleExploreLevel,
    report: ArchitectureReport,
    projection: ArchitectureProjection,
) -> tuple[dict[str, int | None], list[dict[str, str | None]]]:
    balance = next((item for item in projection.levels if item.parent_id == level.parent_id), None)
    if balance is None:
        if not projection.levels:
            return {
                "declared": None,
                "used": None,
                "allowed_unused": None,
                "undeclared": None,
            }, []
        return {"declared": 0, "used": 0, "allowed_unused": 0, "undeclared": 0}, []
    counts: dict[str, int | None] = {
        "declared": balance.declared,
        "used": balance.used,
        "allowed_unused": balance.unused,
        "undeclared": balance.undeclared,
    }
    if balance.unused is None or balance.undeclared is None:
        return counts, []
    if report.target is None:
        return counts, []
    component_ids = set(level.component_ids)
    declared = {
        (edge.source_id, edge.target_id)
        for edge in report.target.relationships
        if edge.kind == "requires"
        and edge.source_id in component_ids
        and edge.target_id is not None
    }
    declared |= {
        (component.id, permission.target_id)
        for component in projection.components
        if component.id in component_ids
        for permission in component.permissions
        if permission.status == "allowed"
    }
    owners = {item.id: item.component_id for item in level.modules}
    used: set[tuple[str, str]] = set()
    for cell in level.cells:
        source_owner = owners.get(cell.source_id)
        target_owner = owners.get(cell.target_id)
        if source_owner is not None and target_owner is not None and source_owner != target_owner:
            used |= {(source_owner, target_owner)}
    deviations: list[dict[str, str | None]] = [
        {
            "id": stable_id("atlas-deviation", level.parent_id, kind, source, target),
            "kind": kind,
            "source_id": source,
            "target_id": target,
            "level_id": level.parent_id,
        }
        for kind, pairs in (
            ("allowed_unused", sorted(declared - used)),
            ("undeclared", sorted(used - declared)),
        )
        for source, target in pairs
    ]
    return counts, deviations


def _cell_payload(
    root: ModuleExploreLevel,
    references: dict[str, int],
) -> tuple[list[list[object]], dict[tuple[str, str], int], dict[str, int]]:
    module_indices = {module.id: index for index, module in enumerate(root.modules)}
    cells: list[list[object]] = []
    for cell in root.cells:
        cells.append(
            [
                module_indices[cell.source_id],
                module_indices[cell.target_id],
                cell.import_sites,
                cell.status,
                [
                    references.setdefault(identity, len(references))
                    for identity in cell.evidence_ids
                ],
                [references.setdefault(identity, len(references)) for identity in cell.finding_ids],
                [references.setdefault(reason, len(references)) for reason in cell.reasons],
            ]
        )
    indices = {(item.source_id, item.target_id): index for index, item in enumerate(root.cells)}
    return cells, indices, module_indices


def _atlas_levels(
    exploration: tuple[ModuleExploreLevel, ...],
    report: ArchitectureReport,
    projection: ArchitectureProjection,
    model: Observation,
    references: dict[str, int],
    cell_indices: dict[tuple[str, str], int],
) -> tuple[
    list[dict[str, object]],
    list[dict[str, object]],
    dict[str | None, dict[str, int | None]],
    list[dict[str, str | None]],
    list[dict[str, object]],
    dict[tuple[str, str | None, tuple[str, ...], str, str], int],
]:
    questions: list[dict[str, object]] = []
    assignments: dict[tuple[str, str | None, tuple[str, ...], str, str], int] = {}
    levels = [
        _level_payload(level, references, cell_indices, questions, assignments)
        for level in exploration
    ]
    findings, level_findings = _finding_payload(model, projection, references)
    finding_indices = {item["id"]: index for index, item in enumerate(findings)}
    balances: dict[str | None, dict[str, int | None]] = {}
    deviations: list[dict[str, str | None]] = []
    level_deviations: dict[str | None, list[str]] = defaultdict(list)
    for level, payload in zip(exploration, levels, strict=True):
        payload["finding_ids"] = sorted(
            finding_indices[identity]
            for identity in level_findings.get(level.parent_id, set())
            if identity in finding_indices
        )
        balance, items = _level_balance(level, report, projection)
        payload["balance"] = balance
        balances[level.parent_id] = balance
        for item in items:
            identity = item["id"]
            if identity is not None:
                level_deviations[level.parent_id] += [identity]
            deviations.append(item)
        payload["deviation_ids"] = level_deviations[level.parent_id]
    return levels, findings, balances, deviations, questions, assignments


def _modules_payload(
    root: ModuleExploreLevel,
    references: dict[str, int],
) -> tuple[list[dict[str, object]], list[list[dict[str, object]]]]:
    coverages: dict[tuple[Coverage, ...], int] = {}
    modules = []
    for module in root.modules:
        module_data = asdict(module)
        coverage = tuple(replace(entry, scope_id="") for entry in module.symbol_coverage)
        module_data["symbol_coverage"] = coverages.setdefault(coverage, len(coverages))
        for field in ("component_id", "candidate_ids", "ownership_status", "ownership_reason"):
            del module_data[field]
        modules.append(_reference_fields(module_data, references))
    symbol_coverages = [[asdict(entry) for entry in coverage] for coverage in coverages]
    return modules, symbol_coverages


def _rule_assessments_payload(
    result: RunResult,
    references: dict[str, int],
) -> list[list[object]]:
    return [
        [
            references.setdefault(item.id, len(references)),
            references.setdefault(item.kind, len(references)),
            item.status,
            item.count,
            item.undecided,
            references.setdefault(item.reason, len(references)),
            references.setdefault(item.scope, len(references)),
        ]
        for item in result.rule_assessments or ()
    ]


def atlas_payload(
    model: Observation,
    report: ArchitectureReport,
    projection: ArchitectureProjection,
    result: RunResult,
    *,
    repository: str,
    architecture_href: str,
) -> dict[str, object]:
    exploration = _leaf_levels(report, module_exploration(model))
    root = exploration[0]
    references: dict[str, int] = {}
    cells, indices, module_indices = _cell_payload(root, references)
    levels, findings, balances, deviations, questions, assignments = _atlas_levels(
        exploration, report, projection, model, references, indices
    )
    modules, symbol_coverages = _modules_payload(root, references)
    return {
        "repository": repository,
        "source": {
            "git_head": projection.source.git_head,
            "source_digest": projection.source.source_digest,
        },
        "declared_rules": result.declared_rules,
        "observation_complete": result.observation_complete,
        "rule_assessments": _rule_assessments_payload(result, references),
        "status": projection.status,
        "reason": projection.reason,
        "components": _components_payload(report, projection, root.modules, references),
        "modules": modules,
        "symbols_complete": bool(root.modules)
        and all(
            module.symbols is not None
            and module.symbol_coverage
            and all(entry.status == "complete" for entry in module.symbol_coverage)
            for module in root.modules
        ),
        "declared_modules": _declared_modules(report),
        "symbol_coverages": symbol_coverages,
        "assignments": [
            [
                module_indices[identity],
                references.setdefault(owner, len(references)) if owner is not None else None,
                [references.setdefault(candidate, len(references)) for candidate in candidates],
                status,
                references.setdefault(reason, len(references)),
            ]
            for identity, owner, candidates, status, reason in assignments
        ],
        "cells": cells,
        "cell_permission_reason_ref": references.setdefault(
            root.cells[0].permission_reason if root.cells else "", len(references)
        ),
        "levels": levels,
        "findings": findings,
        "balance": _system_balance(balances),
        "deviations": deviations,
        "questions": questions,
        "reference_ids": list(references),
        "unknowns": [
            {"reason": reason, "count": count}
            for reason, count in Counter(item.reason for item in projection.unknowns).most_common(5)
        ],
        "unknown_count": len(projection.unknowns),
        "detail_page": f"{PurePosixPath(architecture_href).stem}.detail.html",
        "unassigned_detail_href": "?component=unassigned",
        "architecture_href": architecture_href,
    }
