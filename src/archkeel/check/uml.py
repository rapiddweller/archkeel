# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Authenticate declared graph inputs; only explicit UML intent adds an assessment."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, replace
from pathlib import Path

from archkeel.ir.architecture_graph import ArchitectureGraph, TargetDefinition
from archkeel.ir.codec import (
    InsideContractTree,
    decode_json,
    load_inside_contract_tree,
    parse_contract,
    parse_record,
    parse_required_component,
    value_bytes,
)
from archkeel.ir.model import (
    ARCHITECTURE_TARGET_KIND,
    RULE_KINDS,
    TARGET_GRAPH_RECORD_KINDS,
    UML_TARGET_KIND,
    ArchitectureContract,
    ContractComponent,
    Diagnostic,
    ExternalDependencyScopeRule,
    ObservationResult,
    Record,
    RootLayoutRule,
    Section,
    UmlEligibility,
    contract_relative_path,
    public_api_id,
    stable_id,
)
from archkeel.ir.target_graph import component_permissions, declared_tree_graph

from .declarations import project_rule_declaration


def _read_contract(root: Path, relative: str) -> tuple[bytes, str]:
    reference = contract_relative_path(relative)
    if reference is None:
        raise ValueError("unsafe UML contract path")
    candidate: Path = root / reference
    candidate = candidate.resolve()
    if not candidate.is_relative_to(root):
        raise ValueError("UML contract path escapes its declaration root")
    return candidate.read_bytes(), relative


def _physical_ids(
    contract: ArchitectureContract,
    path: str,
    known: dict[str, Record],
    parent_scope: str | None = None,
) -> tuple[list[str], list[str]]:
    modules = contract.declarations.modules if contract.declarations is not None else None
    module_ids: list[str] = []
    if modules is not None:
        if not modules:
            identity = stable_id("MODULE-TARGET-INVENTORY", parent_scope or path)
            record = known.get(identity)
            if (
                record is None
                or record.kind != "module_target"
                or record.evidence_class.value != "DECLARED_RULE"
                or record.subjects
                or record.provenance != (path,)
                or record.data.get("inventory") is not True
                or record.data.get("parent_id") != parent_scope
            ):
                raise ValueError("UML physical declaration differs from the authenticated contract")
            module_ids.append(identity)
        for module in modules:
            identity = stable_id("MODULE-TARGET", parent_scope or path, module.path)
            record = known.get(identity)
            if (
                record is None
                or record.kind != "module_target"
                or record.evidence_class.value != "DECLARED_RULE"
                or record.subjects != (module.path,)
                or record.provenance != (path,)
                or record.data.get("path") != module.path
                or record.data.get("responsibility") != module.responsibility
                or record.data.get("inventory") is not None
                or record.data.get("parent_id") != parent_scope
            ):
                raise ValueError("UML physical declaration differs from the authenticated contract")
            module_ids.append(identity)
    layout_ids: list[str] = []
    for rule in contract.rules:
        if not isinstance(rule, RootLayoutRule):
            continue
        record = known.get(rule.id)
        if (
            record is None
            or record.kind != "root_layout"
            or record.evidence_class.value != "DECLARED_RULE"
            or record.subjects != tuple(sorted((rule.root, *rule.allowed_children)))
            or record.provenance != tuple(sorted(rule.provenance))
            or record.data.get("root") != rule.root
            or record.data.get("allowed_children") != tuple(sorted(rule.allowed_children))
            or record.data.get("rationale") != rule.rationale
            or record.data.get("decided_by") != rule.decided_by
            or record.data.get("parent_id") != parent_scope
        ):
            raise ValueError("UML physical declaration differs from the authenticated contract")
        layout_ids.append(rule.id)
    return module_ids, layout_ids


def _external_scope_ids(
    contract: ArchitectureContract, known: dict[str, Record], parent_scope: str | None = None
) -> list[str]:
    ids: list[str] = []
    for rule in contract.rules:
        if not isinstance(rule, ExternalDependencyScopeRule):
            continue
        record = known.get(rule.id)
        if (
            record is None
            or record.kind != rule.kind
            or record.evidence_class.value != "DECLARED_RULE"
            or record.subjects
            != tuple(sorted((rule.dependency, *rule.allowed_sources, *rule.exact_sources)))
            or record.provenance != tuple(sorted(rule.provenance))
            or record.data.get("dependency") != rule.dependency
            or record.data.get("allowed_sources") != tuple(sorted(rule.allowed_sources))
            or record.data.get("exact_sources", ()) != tuple(sorted(rule.exact_sources))
            or record.data.get("rationale") != rule.rationale
            or record.data.get("decided_by") != rule.decided_by
            or record.data.get("parent_id") != parent_scope
        ):
            raise ValueError("external permission differs from the authenticated contract")
        ids.append(rule.id)
    return ids


def _permission_matches(
    component: ContractComponent, owner: Record, labels: dict[str, str]
) -> bool:
    raw = owner.data.get("requires", ())
    if not isinstance(raw, tuple):
        raise ValueError("dependency permissions must be an array")
    recorded = tuple(parse_required_component(decode_json(value_bytes(entry))) for entry in raw)
    return component_permissions(
        component.id, recorded, labels, component.provenance, component.decided_by
    ) == component_permissions(
        component.id, component.requires or (), labels, component.provenance, component.decided_by
    )


def _owner_ids(
    contract: ArchitectureContract, known: dict[str, Record], parent_scope: str | None = None
) -> list[str]:
    labels = {component.label: component.id for component in contract.components}
    for component in contract.components:
        owner = known.get(component.id)
        if (
            owner is None
            or owner.evidence_class.value != "DECLARED_RULE"
            or owner.kind
            != ("inside_component_responsibility" if parent_scope else "component_responsibility")
            or owner.data.get("parent_id") != parent_scope
            or owner.title != component.label
            or owner.data.get("namespace") != component.namespace
            or owner.data.get("responsibilities") != tuple(sorted(component.responsibilities))
            or owner.subjects != tuple(sorted(component.packages))
            or owner.data.get("role") != component.role.value
            or owner.data.get("layer") != component.layer
            or owner.data.get("public")
            != (None if component.public is None else tuple(sorted(component.public)))
            or owner.data.get("planned")
            != (None if component.planned is None else tuple(sorted(component.planned)))
            or owner.data.get("exact_modules", ()) != tuple(component.exact_modules or ())
            or owner.data.get("forbidden_responsibilities", ())
            != tuple(sorted(component.forbidden_responsibilities))
            or owner.data.get("decided_by") != component.decided_by
            or owner.data.get("inside") != component.inside
            or owner.provenance != tuple(sorted(component.provenance))
        ):
            raise ValueError(
                f"Target component owner differs from the authenticated contract: {component.id!r}"
            )
        if not _permission_matches(component, owner, labels):
            raise ValueError("dependency permission differs from the authenticated contract")
    return [component.id for component in contract.components]


def _public_api_ids(contract: ArchitectureContract, known: dict[str, Record]) -> list[str]:
    declarations = contract.declarations
    selectors = sorted(declarations.public_api) if declarations is not None else []
    expected = {public_api_id(selector) for selector in selectors}
    if any(
        record.id not in expected
        for record in known.values()
        if record.kind == "declared_public_api"
    ):
        raise ValueError("public API intent is absent from the authenticated contract")
    for selector in selectors:
        record = known.get(public_api_id(selector))
        if (
            record is None
            or record.kind != "declared_public_api"
            or record.evidence_class.value != "DECLARED_RULE"
            or record.title != selector
            or record.subjects != (selector,)
            or declarations is None
            or record.provenance != tuple(sorted(declarations.public_api_provenance))
            or record.data.get("qualified_name") != selector
            or record.data.get("parent_id") is not None
        ):
            raise ValueError("public API intent differs from the authenticated contract")
    return [public_api_id(selector) for selector in selectors]


def _unavailable_target_assessment(path: str, identity: str) -> Record:
    return parse_record(
        {
            "area": "uml",
            "subjects": [],
            "evidence_ids": [],
            "fact_ids": [],
            "provenance": [path],
            "id": stable_id("UML-UNKNOWN", path),
            "evidence_class": "UNKNOWN",
            "kind": "uml_assessment_unavailable",
            "title": "UML target assessment is unavailable",
            "rule_ids": [identity],
            "data": {
                "reason": "Core has not yet evaluated the UML entities, relationships or scopes.",
            },
        }
    )


def _authenticate_rules(tree: InsideContractTree, known: dict[str, Record]) -> None:
    expected = []
    for contract, parent in (
        (tree.root, None),
        *((mount.contract, mount.parent_id) for mount in tree.mounts),
    ):
        for rule in contract.rules:
            raw = project_rule_declaration(rule)
            if parent is not None:
                raw = {**raw, "data": {**raw["data"], "parent_id": parent}}
            expected.append(parse_record(raw))
    actual = tuple(
        item
        for item in known.values()
        if item.kind in RULE_KINDS and item.evidence_class.value == "DECLARED_RULE"
    )
    if {item.id for item in expected} != {item.id for item in actual} or any(
        known.get(item.id) != item for item in expected
    ):
        raise ValueError("governing rules differ from the authenticated contract")


def _target_definition(graph: ArchitectureGraph) -> TargetDefinition:
    return TargetDefinition(
        entities=tuple(entity for entity in graph.entities if entity.kind != "component"),
        relationships=tuple(edge for edge in graph.relationships if edge.kind != "requires"),
        scopes=graph.target_scopes,
        schema_version=graph.schema_version,
    )


def _target_records(
    tree: InsideContractTree, path: str, known: dict[str, Record]
) -> tuple[Record, Record | None] | None:
    contracts = (tree.root, *(mount.contract for mount in tree.mounts))
    targets = tuple(
        contract.declarations.uml
        for contract in contracts
        if contract.declarations is not None and contract.declarations.uml is not None
    )
    graph = declared_tree_graph(tree, root_path=path)
    api_ids = _public_api_ids(tree.root, known)
    if not targets and not (
        graph.entities
        or graph.module_inventories
        or graph.layout_rules
        or graph.public_api
        or graph.external_scopes
    ):
        _authenticate_rules(tree, known)
        return None
    owner_ids: list[str] = _owner_ids(tree.root, known)
    module_ids, layout_ids = _physical_ids(tree.root, path, known)
    external_ids = _external_scope_ids(tree.root, known)
    levels = []
    for mount in tree.mounts:
        inner_owners = _owner_ids(mount.contract, known, mount.parent_id)
        inner_modules, inner_layouts = _physical_ids(
            mount.contract, mount.path, known, mount.parent_id
        )
        owner_ids.extend(inner_owners)
        levels.append(
            {
                "component_id": mount.parent.id,
                "owner_ids": inner_owners,
                "module_target_ids": inner_modules,
                "layout_rule_ids": inner_layouts,
                "external_scope_ids": _external_scope_ids(mount.contract, known, mount.parent_id),
            }
        )
    _authenticate_rules(tree, known)
    target = _target_definition(graph)
    identity = stable_id("UML-TARGET" if targets else "ARCHITECTURE-TARGET", path)
    declaration = parse_record(
        {
            "area": "uml",
            "subjects": [],
            "evidence_ids": [],
            "fact_ids": [],
            "provenance": [path],
            "id": identity,
            "evidence_class": "DECLARED_RULE",
            "kind": UML_TARGET_KIND if targets else ARCHITECTURE_TARGET_KIND,
            "title": "Independent UML target" if targets else "Declared architecture target",
            "rule_ids": [],
            "data": {
                "target": json.loads(json.dumps(asdict(target))),
                "owner_ids": owner_ids,
                "module_target_ids": module_ids,
                "layout_rule_ids": layout_ids,
                "external_scope_ids": external_ids,
                "public_api_ids": api_ids,
                "inside_levels": levels,
                "rationale": (
                    "Independent UML intent defines required entities and relationships."
                    if targets
                    else (
                        "Existing declarations define graph intent; "
                        "their rules retain evaluation ownership."
                    )
                ),
            },
        }
    )
    if not targets:
        return declaration, None
    return declaration, _unavailable_target_assessment(path, identity)


def _append_targets(
    sections: tuple[Section, ...],
    projected: list[tuple[Record, Record | None]],
) -> tuple[Section, ...]:
    known = {record.id: record for section in sections for record in section.records}
    additions: dict[str, list[Record]] = {"declarations": [], "unknowns": []}
    for pair in projected:
        for name, record in zip(additions, pair, strict=True):
            if record is None:
                continue
            previous = known.get(record.id)
            if previous is not None and previous != record:
                raise ValueError("UML declaration identity conflicts with recorded content")
            if previous is None:
                records: list[Record] = additions[name]
                records.append(record)
                known[record.id] = record
    updated = tuple(
        replace(section, records=(*section.records, *additions.get(section.name, ())))
        for section in sections
    )
    present = {section.name for section in sections}
    return (
        *updated,
        *(
            Section(name, tuple(records))
            for name, records in additions.items()
            if name not in present and records
        ),
    )


def assemble_uml(result: ObservationResult, contract_root: Path, path: str) -> ObservationResult:
    model = result.observation
    if model is None or any(item.code == "contract.invalid" for item in result.diagnostics):
        return replace(result, uml_eligibility=UmlEligibility.BLOCKED)
    if any(item.kind == "inside_contract_incomplete" for item in model.coverage.failures):
        return replace(result, uml_eligibility=UmlEligibility.BLOCKED)
    known = {record.id: record for section in model.sections for record in section.records}
    recorded_targets = tuple(
        record for record in known.values() if record.kind in TARGET_GRAPH_RECORD_KINDS
    )
    if (
        model.contract.schema_version not in {"2.2.0", "2.3.0"}
        and not recorded_targets
        and not any(
            record.kind
            in {
                "component_responsibility",
                "inside_component_responsibility",
                "module_target",
                "root_layout",
                "declared_public_api",
            }
            for record in known.values()
        )
    ):
        return replace(result, uml_eligibility=UmlEligibility.BLOCKED)
    root = contract_root.resolve()

    pointer = "/"
    try:
        payload, identity = _read_contract(root, path)
        contract = parse_contract(decode_json(payload))
        tree = load_inside_contract_tree(
            path,
            contract,
            hashlib.sha256(payload).hexdigest(),
            identity,
            lambda relative: _read_contract(root, relative),
        )
        if any(
            item.declarations is not None and item.declarations.uml is not None
            for item in (tree.root, *(mount.contract for mount in tree.mounts))
        ):
            pointer = "/declarations/uml"
        if tree.digest != model.contract.digest or model.contract.path != path:
            raise ValueError("UML intent differs from the analyzer's authenticated contract")
        pair = _target_records(tree, path, known)
        projected = [pair] if pair is not None else []
        declared_ids = {declaration.id for declaration, _ in projected}
        if any(record.id not in declared_ids for record in recorded_targets):
            raise ValueError("UML intent is absent from the authenticated contract")
        sections = _append_targets(model.sections, projected)
    except (OSError, ValueError) as error:
        return replace(
            result,
            uml_eligibility=UmlEligibility.BLOCKED,
            diagnostics=(
                *result.diagnostics,
                Diagnostic(
                    "contract_invalid",
                    path,
                    f"Target intent cannot be established: {error}",
                    "Repair the contract input and repeat the observation.",
                    pointer,
                    "contract.invalid",
                ),
            ),
        )
    if not projected:
        return replace(result, uml_eligibility=UmlEligibility.BLOCKED)
    eligibility = (
        UmlEligibility.AUTHENTICATED_PARTIAL
        if result.uml_eligibility == UmlEligibility.VALIDATED_PARTIAL_SOURCE
        and result.partial_uml_diagnostics
        and result.diagnostics == result.partial_uml_diagnostics
        else UmlEligibility.BLOCKED
    )
    return replace(
        result, observation=replace(model, sections=sections), uml_eligibility=eligibility
    )
