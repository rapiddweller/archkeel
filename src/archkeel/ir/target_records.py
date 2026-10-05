# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Project authenticated canonical Target records for Core and presentation."""

from dataclasses import replace

from archkeel.ir.architecture_graph import (
    ArchitectureGraph,
    ComponentIntent,
    ContractModuleTarget,
    Entity,
    ExternalDependencyScopeRule,
    ModuleInventory,
    Relationship,
    RootLayoutRule,
)
from archkeel.ir.codec import decode_json, parse_required_component, value_bytes
from archkeel.ir.graph_codec import (
    parse_component_intent,
    parse_external_scope,
    parse_layout_rule,
    parse_public_api_entry,
    parse_target,
)
from archkeel.ir.model import Observation, Record, RecordData, stable_id
from archkeel.ir.target_graph import component_permissions, intent_graph


def _inside_levels(declaration: Record) -> tuple[RecordData, ...]:
    levels = declaration.data.get("inside_levels", ())
    if not isinstance(levels, tuple):
        raise ValueError("UML inside levels must be an array")
    result: list[RecordData] = []
    seen: set[str] = set()
    for level in levels:
        if not isinstance(level, RecordData) or set(dict(level.entries)) != {
            "component_id",
            "owner_ids",
            "module_target_ids",
            "layout_rule_ids",
            "external_scope_ids",
        }:
            raise ValueError("UML inside level needs declaration references")
        owner_id = level.get("component_id")
        if not isinstance(owner_id, str) or owner_id in seen:
            raise ValueError("UML inside level needs a unique component")
        seen.add(owner_id)
        result.append(level)
    return tuple(result)


def _recorded_intent(
    owner: Record, parent_id: str | None, layout_rule_ids: tuple[str, ...]
) -> ComponentIntent:
    metadata = RecordData(
        (
            ("component_id", owner.id),
            ("parent_id", parent_id),
            ("label", owner.title),
            ("layout_rule_ids", layout_rule_ids),
            *((("layer", owner.data.get("layer")),) if owner.data.get("layer") is not None else ()),
            ("packages", owner.subjects),
            ("exact_modules", owner.data.get("exact_modules", ())),
            ("forbidden_responsibilities", owner.data.get("forbidden_responsibilities", ())),
            *(
                (key, owner.data.get(key))
                for key in ("role", "namespace", "public", "planned", "decided_by", "inside")
            ),
        )
    )
    return parse_component_intent(decode_json(value_bytes(metadata)))


def _recorded_owners(
    model: Observation, declaration: Record, levels: tuple[RecordData, ...]
) -> tuple[tuple[Entity, ...], tuple[ComponentIntent, ...]]:
    identifiers = declaration.data.get("owner_ids")
    if not isinstance(identifiers, tuple):
        raise ValueError("UML target needs authenticated owner IDs")
    records = {record.id: record for record in model.records("declarations") or ()}
    parents: dict[str, str] = {}
    layouts: dict[str, tuple[str, ...]] = {}
    for level in levels:
        parent_id = level.get("component_id")
        if not isinstance(parent_id, str) or parent_id not in identifiers:
            raise ValueError("UML inside level owner is unavailable")
        children = _declaration_records(
            records, level, "owner_ids", "inside_component_responsibility"
        )
        rules = _declaration_records(records, level, "layout_rule_ids", "root_layout")
        layouts[parent_id] = tuple(rule.id for rule in rules)
        for child in children:
            if child.id in parents or child.id not in identifiers:
                raise ValueError("UML inner component needs one parent")
            parents[child.id] = parent_id
    result: list[Entity] = []
    intents: list[ComponentIntent] = []
    seen: set[str] = set()
    for identifier in identifiers:
        if not isinstance(identifier, str) or identifier in seen:
            raise ValueError("UML owner IDs must be unique text")
        seen.add(identifier)
        owner = records.get(identifier)
        if (
            owner is None
            or owner.kind
            != (
                "inside_component_responsibility"
                if identifier in parents
                else "component_responsibility"
            )
            or owner.evidence_class.value != "DECLARED_RULE"
        ):
            raise ValueError("UML component owner is unavailable")
        namespace = owner.data.get("namespace")
        responsibilities = owner.data.get("responsibilities")
        if (namespace is not None and not isinstance(namespace, str)) or not isinstance(
            responsibilities, tuple
        ):
            raise ValueError("UML component owner is malformed")
        duties: list[str] = []
        for responsibility in responsibilities:
            if not isinstance(responsibility, str):
                raise ValueError("UML component responsibility must be text")
            duties.append(responsibility)
        result.append(
            Entity(
                owner.id,
                "component",
                namespace or owner.title,
                "architecture",
                presence="planned",
                responsibilities=tuple(duties),
                provenance=owner.provenance,
            )
        )
        intents.append(_recorded_intent(owner, parents.get(owner.id), layouts.get(owner.id, ())))
    return tuple(result), tuple(intents)


def _declaration_records(
    known: dict[str, Record], data: RecordData, field: str, kind: str
) -> tuple[Record, ...]:
    identifiers = data.get(field, ())
    if not isinstance(identifiers, tuple):
        raise ValueError("Target intent needs authenticated declaration IDs")
    records: list[Record] = []
    seen: set[str] = set()
    for identifier in identifiers:
        if not isinstance(identifier, str) or identifier in seen:
            raise ValueError("Target declaration IDs must be unique text")
        seen.add(identifier)
        record = known.get(identifier)
        if record is None or record.kind != kind or record.evidence_class.value != "DECLARED_RULE":
            raise ValueError("Target declaration is unavailable")
        records.append(record)
    return tuple(records)


def _module_inventory(module_records: tuple[Record, ...], owner_id: str | None) -> ModuleInventory:
    modules: list[ContractModuleTarget] = []
    first: Record = module_records[0]
    scope = first.data.get("parent_id")
    provenance = first.provenance
    for record in module_records:
        if record.data.get("parent_id") != scope or record.provenance != provenance:
            raise ValueError("UML module inventory mixes declaration levels")
        if record.data.get("inventory") is True:
            if len(module_records) != 1:
                raise ValueError("empty module inventory conflicts with declared files")
            continue
        path, responsibility = record.data.get("path"), record.data.get("responsibility")
        if not isinstance(path, str) or not isinstance(responsibility, str):
            raise ValueError("UML module target is malformed")
        modules.append(ContractModuleTarget(path, responsibility))
    if scope is not None and not isinstance(scope, str):
        raise ValueError("UML module inventory scope must be text")
    return ModuleInventory(
        stable_id("MODULE-TARGET-INVENTORY", *((scope,) if scope else provenance)),
        tuple(modules),
        provenance,
        owner_id,
    )


def _recorded_permissions(
    known: dict[str, Record], intents: tuple[ComponentIntent, ...]
) -> tuple[Relationship, ...]:
    labels: dict[str | None, dict[str, str]] = {}
    for intent in intents:
        names: dict[str, str] = labels.setdefault(intent.parent_id, {})
        label = known[intent.component_id].title
        if label in names:
            raise ValueError("dependency permission component label is ambiguous")
        names[label] = intent.component_id
    result: list[Relationship] = []
    for intent in intents:
        owner: Record = known[intent.component_id]
        raw = owner.data.get("requires", ())
        if not isinstance(raw, tuple):
            raise ValueError("dependency permissions must be an array")
        entries = tuple(parse_required_component(decode_json(value_bytes(entry))) for entry in raw)
        result.extend(
            component_permissions(
                intent.component_id,
                entries,
                labels[intent.parent_id],
                owner.provenance,
                intent.decided_by,
            )
        )
    return tuple(result)


def recorded_target_graph(model: Observation, declaration: Record) -> ArchitectureGraph:
    target = parse_target(decode_json(value_bytes(declaration.data.get("target"))))
    levels = _inside_levels(declaration)
    owners, intents = _recorded_owners(model, declaration, levels)
    known = {record.id: record for record in model.records("declarations") or ()}
    inventories: list[ModuleInventory] = []
    layouts: list[RootLayoutRule] = []
    external_scopes: list[ExternalDependencyScopeRule] = []
    for data in (declaration.data, *levels):
        owner_id = data.get("component_id")
        if owner_id is not None and not isinstance(owner_id, str):
            raise ValueError("UML inventory owner must be text")
        for record in _declaration_records(
            known, data, "external_scope_ids", "external_dependency_scope"
        ):
            wire = RecordData(
                (
                    ("id", record.id),
                    ("kind", record.kind),
                    ("provenance", record.provenance),
                    *(
                        (key, record.data.get(key, () if key == "exact_sources" else None))
                        for key in (
                            "dependency",
                            "allowed_sources",
                            "exact_sources",
                            "rationale",
                            "decided_by",
                        )
                    ),
                )
            )
            external_scopes.append(parse_external_scope(decode_json(value_bytes(wire))))
        modules = _declaration_records(known, data, "module_target_ids", "module_target")
        if modules:
            inventories.append(_module_inventory(modules, owner_id))
        for record in _declaration_records(known, data, "layout_rule_ids", "root_layout"):
            wire = RecordData(
                (
                    ("id", record.id),
                    ("kind", record.kind),
                    ("provenance", record.provenance),
                    *(
                        (key, record.data.get(key))
                        for key in ("root", "allowed_children", "rationale", "decided_by")
                    ),
                )
            )
            layouts.append(parse_layout_rule(decode_json(value_bytes(wire))))
    graph = intent_graph(
        target,
        owners,
        component_intents=intents,
        module_inventories=tuple(inventories),
        layout_rules=tuple(layouts),
        external_scopes=tuple(external_scopes),
        public_api=tuple(
            parse_public_api_entry(
                decode_json(
                    value_bytes(
                        RecordData(
                            (
                                ("id", record.id),
                                ("selector", record.data.get("qualified_name")),
                                ("provenance", record.provenance),
                            )
                        )
                    )
                )
            )
            for record in _declaration_records(
                known, declaration.data, "public_api_ids", "declared_public_api"
            )
        ),
    )
    graph = replace(
        graph, relationships=(*_recorded_permissions(known, intents), *graph.relationships)
    )
    graph.validate()
    return graph
