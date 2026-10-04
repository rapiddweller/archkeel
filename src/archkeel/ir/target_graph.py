# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Compile independent contract intent into the shared graph, without source observations."""

from __future__ import annotations

from dataclasses import replace
from typing import Literal

from archkeel.ir.architecture_graph import (
    ArchitectureGraph,
    ComponentIntent,
    Entity,
    ExternalDependencyScopeRule,
    ModuleInventory,
    PublicAPIEntry,
    Relationship,
    RootLayoutRule,
    TargetDefinition,
)
from archkeel.ir.model import (
    ArchitectureContract,
    ContractComponent,
    InsideContractTree,
    RequiredComponent,
    public_api_id,
    stable_id,
)


def intent_graph(
    target: TargetDefinition,
    owners: tuple[Entity, ...],
    *,
    component_intents: tuple[ComponentIntent, ...] = (),
    module_inventories: tuple[ModuleInventory, ...] = (),
    layout_rules: tuple[RootLayoutRule, ...] = (),
    public_api: tuple[PublicAPIEntry, ...] = (),
    external_scopes: tuple[ExternalDependencyScopeRule, ...] = (),
) -> ArchitectureGraph:
    for entity in target.entities:
        if entity.kind == "component":
            raise ValueError("UML cannot redeclare an existing component owner")
        if entity.presence not in {"planned", "referenced"} or entity.record_ids:
            raise ValueError("UML entities need independent planned or referenced intent")
        if entity.presence == "planned" and not entity.responsibilities:
            raise ValueError("UML entities need a responsibility")
    if any(edge.record_ids for edge in target.relationships):
        raise ValueError("UML relationships cannot cite observed record IDs")
    if any(edge.kind == "requires" for edge in target.relationships):
        raise ValueError("dependency permissions belong in component requires")
    graph = ArchitectureGraph(
        "declared",
        (*owners, *target.entities),
        target.relationships,
        target_scopes=target.scopes,
        component_intents=component_intents,
        module_inventories=module_inventories,
        layout_rules=layout_rules,
        public_api=public_api,
        external_scopes=external_scopes,
    )
    graph.validate()
    return graph


def component_permissions(
    owner_id: str,
    requires: tuple[RequiredComponent, ...],
    targets: dict[str, str],
    provenance: tuple[str, ...],
    decided_by: Literal["architect", "agent"] | None,
) -> tuple[Relationship, ...]:
    seen: dict[RequiredComponent, int] = {}
    result: list[Relationship] = []
    for entry in sorted(
        (
            replace(
                item, through=tuple(sorted(item.through)), decided_by=item.decided_by or decided_by
            )
            for item in requires
        ),
        key=lambda item: (item.component, item.through, item.rationale, item.decided_by or ""),
    ):
        target = targets.get(entry.component)
        if target is None:
            raise ValueError("dependency permission target is unavailable")
        occurrence = seen.get(entry, 0)
        seen[entry] = occurrence + 1
        result.append(
            Relationship(
                stable_id(
                    "TARGET-REQUIRES",
                    owner_id,
                    target,
                    entry.through,
                    entry.rationale,
                    entry.decided_by,
                    occurrence,
                ),
                "requires",
                owner_id,
                target,
                provenance=tuple(sorted(provenance)),
                reason=entry.rationale,
                through=entry.through,
                decided_by=entry.decided_by,
            )
        )
    return tuple(result)


def _component_intent(component: ContractComponent) -> ComponentIntent:
    return ComponentIntent(
        component.id,
        component.role,
        tuple(sorted(component.packages)),
        component.exact_modules or (),
        component.namespace,
        None if component.public is None else tuple(sorted(component.public)),
        None if component.planned is None else tuple(sorted(component.planned)),
        tuple(sorted(component.forbidden_responsibilities)),
        component.decided_by,
        component.inside,
        label=component.label,
    )


def declared_graph(
    contract: ArchitectureContract, *, contract_path: str = "architecture-contract.json"
) -> ArchitectureGraph:
    target = contract.declarations.uml if contract.declarations is not None else None
    entities = tuple(
        Entity(
            component.id,
            "component",
            component.namespace or component.label,
            "architecture",
            presence="planned",
            responsibilities=tuple(sorted(component.responsibilities)),
            provenance=tuple(sorted(component.provenance)),
        )
        for component in contract.components
    )
    labels = {component.label: component.id for component in contract.components}
    requirements = tuple(
        edge
        for component in contract.components
        for edge in component_permissions(
            component.id,
            component.requires or (),
            labels,
            component.provenance,
            component.decided_by,
        )
    )
    intents = tuple(_component_intent(component) for component in contract.components)
    modules = contract.declarations.modules if contract.declarations is not None else None
    inventories = (
        (
            ModuleInventory(
                stable_id("MODULE-TARGET-INVENTORY", contract_path), modules, (contract_path,)
            ),
        )
        if modules is not None
        else ()
    )
    graph = intent_graph(
        target or TargetDefinition(),
        entities,
        component_intents=intents,
        module_inventories=inventories,
        public_api=tuple(
            PublicAPIEntry(
                public_api_id(selector),
                selector,
                tuple(sorted(contract.declarations.public_api_provenance)),
            )
            for selector in sorted(contract.declarations.public_api)
        )
        if contract.declarations is not None
        else (),
        external_scopes=tuple(
            replace(
                rule,
                allowed_sources=tuple(sorted(rule.allowed_sources)),
                exact_sources=tuple(sorted(rule.exact_sources)),
                provenance=tuple(sorted(rule.provenance)),
            )
            for rule in contract.rules
            if isinstance(rule, ExternalDependencyScopeRule)
        ),
        layout_rules=tuple(
            replace(
                rule,
                allowed_children=tuple(sorted(rule.allowed_children)),
                provenance=tuple(sorted(rule.provenance)),
            )
            for rule in contract.rules
            if isinstance(rule, RootLayoutRule)
        ),
    )
    graph = replace(graph, relationships=(*requirements, *graph.relationships))
    graph.validate()
    return graph


def declared_tree_graph(tree: InsideContractTree, *, root_path: str) -> ArchitectureGraph:
    """Compile every authenticated declaration level without consulting source facts."""
    if tree.issues:
        raise ValueError("incomplete inside contract tree")
    root = declared_graph(tree.root, contract_path=root_path)
    entities = list(root.entities)
    relationships = list(root.relationships)
    scopes = list(root.target_scopes)
    intents = {item.component_id: item for item in root.component_intents}
    inventories = list(root.module_inventories)
    layouts = list(root.layout_rules)
    external_scopes = list(root.external_scopes)
    for mount in tree.mounts:
        inner = declared_graph(mount.contract, contract_path=mount.path)
        owner_id = mount.parent.id
        entities.extend(inner.entities)
        relationships.extend(inner.relationships)
        scopes.extend(inner.target_scopes)
        intents.update(
            (item.component_id, replace(item, parent_id=owner_id))
            for item in inner.component_intents
        )
        intents[owner_id] = replace(
            intents[owner_id], layout_rule_ids=tuple(rule.id for rule in inner.layout_rules)
        )
        inventories.extend(
            replace(
                item,
                id=stable_id("MODULE-TARGET-INVENTORY", mount.parent_id),
                component_id=owner_id,
            )
            for item in inner.module_inventories
        )
        layouts.extend(inner.layout_rules)
        external_scopes.extend(inner.external_scopes)
    graph = replace(
        root,
        entities=tuple(entity for entity in entities if entity.kind == "component")
        + tuple(entity for entity in entities if entity.kind != "component"),
        relationships=tuple(edge for edge in relationships if edge.kind == "requires")
        + tuple(edge for edge in relationships if edge.kind != "requires"),
        target_scopes=tuple(scopes),
        component_intents=tuple(intents.values()),
        module_inventories=tuple(inventories),
        layout_rules=tuple(layouts),
        external_scopes=tuple(external_scopes),
    )
    graph.validate()
    return graph


def scoped_target(target: TargetDefinition | None, prefix: str) -> TargetDefinition | None:
    if target is None:
        return None
    return replace(
        target,
        entities=tuple(
            replace(
                entity,
                id=f"{prefix}:{entity.id}",
                parent_id=f"{prefix}:{entity.parent_id}" if entity.parent_id else None,
            )
            for entity in target.entities
        ),
        relationships=tuple(
            replace(
                edge,
                id=f"{prefix}:{edge.id}",
                source_id=f"{prefix}:{edge.source_id}",
                target_id=f"{prefix}:{edge.target_id}" if edge.target_id else None,
            )
            for edge in target.relationships
        ),
        scopes=tuple(
            replace(scope, scope_id=f"{prefix}:{scope.scope_id}") for scope in target.scopes
        ),
    )
