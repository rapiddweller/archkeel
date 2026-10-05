# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Normalize recorded source facts into the shared graph; never infer Target intent."""

from __future__ import annotations

from dataclasses import replace
from pathlib import PurePosixPath
from typing import TypeVar, get_args

from archkeel.ir.architecture_graph import (
    ArchitectureGraph,
    Coverage,
    CoverageStatus,
    DefinitionBranchKind,
    DefinitionContext,
    DefinitionContextKind,
    Entity,
    EntityKind,
    ModifierKind,
    Parameter,
    ParameterKind,
    Relationship,
    RelationshipKind,
    Signature,
    Visibility,
    VisibilityBasis,
    VisibilityKind,
)
from archkeel.ir.facts import member_inventories
from archkeel.ir.model import JsonValue, Observation, Record, RecordData, stable_id
from archkeel.ir.profiles import PROFILES, profile_for

_Choice = TypeVar("_Choice", bound=str)
_KINDS: tuple[EntityKind, ...] = get_args(EntityKind)
_VISIBILITIES: tuple[VisibilityKind, ...] = get_args(VisibilityKind)
_BASES: tuple[VisibilityBasis, ...] = get_args(VisibilityBasis)
_PARAMETERS: tuple[ParameterKind, ...] = get_args(ParameterKind)
_MODIFIERS: tuple[ModifierKind, ...] = get_args(ModifierKind)
_CLASSIFIER_RELATIONSHIPS: tuple[RelationshipKind, ...] = ("inherits", "realizes")


def _choice(value: JsonValue, choices: tuple[_Choice, ...], default: _Choice) -> _Choice:
    if value is None:
        return default
    for choice in choices:
        if value == choice:
            return choice
    raise ValueError(f"invalid graph vocabulary value: {value!r}")


def _text(value: JsonValue) -> str | None:
    if value is None or isinstance(value, str):
        return value
    raise ValueError("source graph expected text")


def _texts(value: JsonValue) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, tuple) or any(not isinstance(item, str) for item in value):
        raise ValueError("source graph expected text array")
    return tuple(item for item in value if isinstance(item, str))


def _records(value: JsonValue) -> tuple[RecordData, ...]:
    if value is None:
        return ()
    if not isinstance(value, tuple) or any(not isinstance(item, RecordData) for item in value):
        raise ValueError("source graph expected record array")
    return tuple(item for item in value if isinstance(item, RecordData))


def _visibility(value: JsonValue, spelling: str | None = None) -> Visibility:
    if value is None:
        return Visibility(spelling=spelling)
    if not isinstance(value, RecordData):
        raise ValueError("source graph expected visibility record")
    return Visibility(
        _choice(value.get("kind"), _VISIBILITIES, "unknown"),
        _choice(value.get("basis"), _BASES, "unknown"),
        _text(value.get("spelling")),
    )


def _signature(data: RecordData) -> Signature:
    parameters: list[Parameter] = []
    for item in _records(data.get("parameters")):
        name: str = _text(item.get("name")) or ""
        if not name:
            raise ValueError("source parameter needs a name")
        kind = _choice(item.get("kind"), _PARAMETERS, "unknown")
        known = item.get("default_known")
        if known is not None and not isinstance(known, bool):
            raise ValueError("source default_known must be boolean")
        parameters.append(
            Parameter(
                name.lstrip("*") if kind in {"varargs", "kwargs"} else name,
                _text(item.get("annotation")),
                kind,
                _text(item.get("default")),
                known is True,
            )
        )
    return Signature(tuple(parameters), _text(data.get("returns")))


def _definition_contexts(value: JsonValue) -> tuple[DefinitionContext, ...]:
    result: list[DefinitionContext] = []
    for context in _records(value):
        kind = context.get("kind")
        branch = context.get("branch")
        if (
            {key for key, _ in context.entries} != {"kind", "branch", "evidence_ids"}
            or kind is None
            or branch is None
        ):
            raise ValueError("source definition context fields mismatch")
        result.append(
            DefinitionContext(
                _choice(kind, get_args(DefinitionContextKind), "if"),
                _choice(branch, get_args(DefinitionBranchKind), "body"),
                _texts(context.get("evidence_ids")),
            )
        )
    return tuple(result)


def _symbol(record: Record, language: str) -> Entity:
    data = record.data
    category = data.get("symbol_category", record.kind)
    kind = (
        _choice(category, _KINDS, "symbol")
        if category not in {"static_constant", "dynamic_binding"}
        else ("constant" if category == "static_constant" else "binding")
    )
    if kind == "class" and data.get("class_kind") in {"protocol", "enum"}:
        kind = "interface" if data.get("class_kind") == "protocol" else "enum"
    modifiers: list[ModifierKind] = []
    for key, modifier in (("async", "async"), ("frozen_object", "frozen")):
        if data.get(key) is True:
            modifiers.append(_choice(modifier, _MODIFIERS, "async"))
    if data.get("method_kind") in {"static", "class"}:
        modifiers.append("static" if data.get("method_kind") == "static" else "class")
    return Entity(
        record.id,
        kind,
        _text(data.get("qualified_name")) or "",
        language,
        visibility=_visibility(data.get("visibility_detail"), _text(data.get("name"))),
        signature=_signature(data) if kind in {"method", "function"} else None,
        annotation=_text(data.get("annotation")),
        modifiers=tuple(modifiers),
        presence="defined",
        evidence_ids=record.evidence_ids,
        record_ids=(record.id,),
        definition_contexts=_definition_contexts(data.get("definition_contexts")),
    )


def _attribute_entities(item: Record, entity: Entity, language: str) -> list[Entity]:
    fields = item.data.get("attribute_declarations", item.data.get("fields"))
    literals = _texts(item.data.get("enum_members")) if entity.kind == "enum" else ()
    result: list[Entity] = []
    for field in _records(fields):
        name = _text(field.get("name")) or ""
        static = field.get("static")
        if static is not None and not isinstance(static, bool):
            raise ValueError("attribute static modifier must be boolean")
        result.append(
            Entity(
                _text(field.get("definition_id")) or stable_id("ATTR", item.id, name),
                "enum_literal" if name in literals else "attribute",
                f"{entity.qualified_name}.{name}",
                language,
                parent_id=item.id,
                visibility=_visibility(field.get("visibility")),
                annotation=_text(field.get("annotation")),
                modifiers=("static",) if static is True and name not in literals else (),
                presence="defined",
                evidence_ids=_texts(field.get("evidence_ids")) or item.evidence_ids,
                record_ids=(item.id,),
                definition_contexts=entity.definition_contexts,
            )
        )
    return result


def _source_entities(observation: Observation, language: str) -> list[Entity]:
    modules = observation.records("modules") or ()
    records = {item.id: item for item in modules}
    packages = observation.records("packages") or ()
    package_ids = {_text(item.data.get("qualified_name")): item.id for item in packages}
    module_ids = {_text(item.data.get("qualified_name")): item.id for item in modules}
    entities = [
        Entity(
            item.id,
            "package",
            _text(item.data.get("qualified_name")) or "",
            language,
            presence="defined",
            evidence_ids=tuple(
                sorted(
                    set(item.evidence_ids).union(
                        *(records[fact].evidence_ids for fact in item.fact_ids if fact in records)
                    )
                )
            ),
            record_ids=(item.id,),
        )
        for item in packages
    ]
    for item in modules:
        module_name: str = _text(item.data.get("qualified_name")) or ""
        module_parent = (
            module_name
            if PurePosixPath(_text(item.data.get("file")) or "").name == "__init__.py"
            else module_name.rpartition(".")[0]
        )
        entities.append(
            Entity(
                item.id,
                "module",
                module_name,
                language,
                parent_id=package_ids.get(module_parent),
                presence="defined",
                evidence_ids=item.evidence_ids,
                record_ids=(item.id,),
                file_path=_text(item.data.get("file")),
            )
        )
    symbols = observation.records("symbols") or ()
    symbol_ids: dict[str, list[str]] = {}
    for item in symbols:
        name = _text(item.data.get("qualified_name")) or ""
        definitions: list[str] = symbol_ids.setdefault(name, [])
        definitions.append(item.id)
    for item in symbols:
        entity = _symbol(item, language)
        parents = symbol_ids.get(_text(item.data.get("parent")) or "", [])
        parent = _text(item.data.get("lexical_parent_id"))
        if parent is None:
            if len(parents) > 1:
                raise ValueError("ambiguous lexical parent needs a definition-site identity")
            parent = parents[0] if parents else module_ids.get(_text(item.data.get("module")))
        entities.append(replace(entity, parent_id=parent))
        entities.extend(_attribute_entities(item, entity, language))
    return entities


def _site_relationship(
    record: Record, kind: RelationshipKind, source: str, targets: tuple[str, ...]
) -> Relationship:
    status = record.data.get("status")
    if status not in {"resolved", "partially_resolved", "unresolved"}:
        raise ValueError("source relationship needs a resolution status")
    resolved = status == "resolved" and len(targets) == 1
    count = record.data.get("candidate_count")
    if count is not None and (not isinstance(count, int) or isinstance(count, bool)):
        raise ValueError("source candidate_count must be integer")
    if count is not None and count < len(_texts(record.data.get("targets"))):
        raise ValueError("source candidate count is smaller than its listed targets")
    truncated = record.data.get("candidates_truncated")
    if truncated is not None and not isinstance(truncated, bool):
        raise ValueError("source candidates_truncated must be boolean")
    if status == "unresolved" and targets:
        raise ValueError("unresolved source relationship has candidates")
    return Relationship(
        record.id,
        kind,
        source,
        targets[0] if resolved else None,
        "resolved" if resolved else "partial" if status != "unresolved" else "unresolved",
        candidate_ids=() if resolved else targets,
        expression=_text(record.data.get("expression")),
        evidence_ids=record.evidence_ids,
        record_ids=(record.id,),
        # The source count names qualified targets, not their definition sites.
        candidate_count=None if truncated is True or count is None else len(targets),
        candidates_truncated=truncated is True,
        reason=_text(record.data.get("reason")),
    )


def _endpoint(
    name: str,
    record: Record,
    by_name: dict[str, list[Entity]],
    entities: list[Entity],
    language: str,
) -> tuple[str, ...]:
    known = by_name.get(name)
    if known:
        return tuple(item.id for item in known)
    referenced = Entity(
        stable_id("REFENTITY", language, name),
        "symbol",
        name,
        language,
        presence="referenced",
        evidence_ids=record.evidence_ids,
        record_ids=(record.id,),
    )
    entities.append(referenced)
    by_name[name] = [referenced]
    return (referenced.id,)


def _source_endpoint(
    record: Record,
    name: str,
    by_name: dict[str, list[Entity]],
    entities: list[Entity],
    language: str,
) -> tuple[str, ...]:
    identity = _text(record.data.get("source_definition_id"))
    if identity:
        if not any(entity.id == identity for entity in by_name.get(name, [])):
            raise ValueError("source definition does not match its recorded scope")
        return (identity,)
    if any(key == "source_definition_id" for key, _ in record.data.entries):
        # A missing declaration must not borrow another definition with the same name.
        source = Entity(
            stable_id("REFSCOPE", record.id),
            "symbol",
            name,
            language,
            presence="referenced",
            evidence_ids=record.evidence_ids,
            record_ids=(record.id,),
        )
        entities.append(source)
        return (source.id,)
    return _endpoint(name, record, by_name, entities, language)


def _value_bindings(
    record: Record,
    source: str,
    entities: list[Entity],
    by_name: dict[str, list[Entity]],
    language: str,
) -> tuple[tuple[Entity, str], ...]:
    sites = _records(record.data.get("result_bindings"))
    if not sites:
        return ()
    owner = next(item for item in entities if item.id == source)
    result: list[tuple[Entity, str]] = []
    for site in sites:
        if {key for key, _ in site.entries} != {
            "id",
            "name",
            "target_kind",
            "annotation",
            "initializer",
            "evidence_ids",
            "definition_contexts",
        } or not _texts(site.get("evidence_ids")):
            raise ValueError("static result binding fields or evidence mismatch")
        identity = _text(site.get("id")) or ""
        name = _text(site.get("name")) or ""
        initializer = _text(site.get("initializer")) or ""
        target_kind = _text(site.get("target_kind")) or ""
        if (
            not identity
            or not name
            or not initializer
            or target_kind not in {"name", "attribute", "subscript"}
        ):
            raise ValueError("invalid static result binding")
        previous = next((item for item in entities if item.id == identity), None)
        value = Entity(
            identity,
            "binding",
            f"{owner.qualified_name}.{name}",
            language,
            parent_id=source,
            annotation=_text(site.get("annotation")),
            presence="defined",
            evidence_ids=tuple(
                sorted(
                    set(record.evidence_ids)
                    | set(_texts(site.get("evidence_ids")))
                    | set(previous.evidence_ids if previous else ())
                )
            ),
            record_ids=tuple(
                sorted(set((record.id,)) | set(previous.record_ids if previous else ()))
            ),
            definition_contexts=_definition_contexts(site.get("definition_contexts")),
            initializer=initializer,
        )
        if previous:
            if (
                previous.kind != "binding"
                or previous.qualified_name != value.qualified_name
                or previous.initializer is not None
            ):
                raise ValueError("static result binding identity conflicts")
            entities[entities.index(previous)] = value
            by_name[value.qualified_name] = [
                value if item.id == identity else item for item in by_name[value.qualified_name]
            ]
        else:
            entities.append(value)
            values: list[Entity] = by_name.setdefault(value.qualified_name, [])
            values.append(value)
        result.append((value, target_kind))
    return tuple(result)


def _construction_sites(
    record: Record,
    source: str,
    bindings: tuple[tuple[Entity, str], ...],
    by_name: dict[str, list[Entity]],
) -> tuple[Relationship, ...]:
    construction = record.data.get("construction")
    if construction is None:
        return ()
    if not isinstance(construction, RecordData):
        raise ValueError("invalid construction record")
    status = construction.get("status")
    names = _texts(construction.get("targets"))
    truncated = construction.get("candidates_truncated")
    reason = _text(construction.get("reason"))
    if (
        {key for key, _ in construction.entries}
        != {"status", "targets", "candidates_truncated", "reason"}
        or status not in {"resolved", "partially_resolved"}
        or not names
        or not isinstance(truncated, bool)
        or not reason
    ):
        raise ValueError("invalid construction resolution")
    if not set(names) <= set(_texts(record.data.get("targets"))) or (
        status == "resolved"
        and (record.data.get("status") != "resolved" or truncated or len(names) != 1)
    ):
        raise ValueError("construction resolution conflicts with its call site")
    targets = tuple(
        sorted(
            {
                item.id
                for name in names
                for item in by_name.get(name, ())
                if item.kind in {"class", "interface", "enum"}
            }
        )
    )
    if not targets:
        raise ValueError("construction needs a recorded classifier candidate")
    resolved = status == "resolved" and len(targets) == 1 and not truncated
    relations: list[tuple[RelationshipKind, str, bool]] = [("creates", source, True)]
    relations.extend(
        ("instance_of", binding.id, target_kind == "name") for binding, target_kind in bindings
    )
    result: list[Relationship] = []
    for kind, caller, stored in relations:
        proven = resolved and stored
        result.append(
            Relationship(
                stable_id("CONSTRUCTION", record.id, kind, caller),
                kind,
                caller,
                targets[0] if proven else None,
                "resolved" if proven else "partial",
                candidate_ids=() if proven else targets,
                expression=_text(record.data.get("expression")),
                evidence_ids=record.evidence_ids,
                record_ids=(record.id,),
                candidate_count=None if truncated else len(targets),
                candidates_truncated=truncated,
                reason=reason if stored else "Storage is unproven; initializer type is a candidate",
            )
        )
    return tuple(result)


def _namespace_memberships(observation: Observation, entities: list[Entity]) -> list[Relationship]:
    result: list[Relationship] = []
    modules = {entity.id: entity for entity in entities if entity.kind == "module"}
    for group in observation.records("packages") or ():
        for member in group.fact_ids:
            if member not in modules:
                raise ValueError("namespace group refers to an unknown module")
            result.append(
                Relationship(
                    stable_id("MEMBERSHIP", group.id, member),
                    "owns",
                    group.id,
                    member,
                    "resolved",
                    evidence_ids=modules[member].evidence_ids,
                    record_ids=(group.id, member),
                    reason="membership in the recorded namespace group; not lexical containment",
                )
            )
    return result


def _declaration_endpoint(
    record: Record, kind: str, lexical_owner: str, by_name: dict[str, list[Entity]]
) -> str | None:
    keys = {"declaration_scope", "declaration_definition_id"}
    present = keys & {key for key, _ in record.data.entries}
    if not present:
        return None
    name = _text(record.data.get("declaration_scope"))
    identity = _text(record.data.get("declaration_definition_id"))
    if kind != "references" or present != keys or not name or not identity:
        raise ValueError("reference declaration needs a scope and definition identity")
    if not any(
        entity.id == identity
        and entity.kind in {"method", "function"}
        and entity.parent_id == lexical_owner
        for entity in by_name.get(name, [])
    ):
        raise ValueError("reference declaration does not match an operation")
    return identity


def _relationships(
    observation: Observation, entities: list[Entity], language: str
) -> tuple[Relationship, ...]:
    by_name: dict[str, list[Entity]] = {}
    for entity in entities:
        if entity.kind != "package":
            definitions: list[Entity] = by_name.setdefault(entity.qualified_name, [])
            definitions.append(entity)

    result: list[Relationship] = []
    result.extend(_namespace_memberships(observation, entities))
    for section, kind in (("imports", "imports"), ("calls", "calls"), ("references", "references")):
        for record in observation.records(section) or ():
            source_name = (
                _text(record.data.get("source_scope" if kind != "imports" else "source_module"))
                or ""
            )
            sources = _source_endpoint(record, source_name, by_name, entities, language)
            if len(sources) != 1:
                raise ValueError("ambiguous source scope needs a definition-site identity")
            declaration = _declaration_endpoint(record, kind, sources[0], by_name)
            if declaration is not None:
                sources = (declaration,)
            if kind == "imports":
                target_name = _text(record.data.get("target_module")) or ""
                targets = _endpoint(target_name, record, by_name, entities, language)
                result.append(
                    Relationship(
                        record.id,
                        "imports",
                        sources[0],
                        targets[0] if len(targets) == 1 else None,
                        "resolved" if len(targets) == 1 else "partial",
                        candidate_ids=() if len(targets) == 1 else targets,
                        expression=target_name,
                        evidence_ids=record.evidence_ids,
                        record_ids=(record.id,),
                    )
                )
            else:
                target_ids: dict[str, None] = {}
                for name in _texts(record.data.get("targets")):
                    for target in _endpoint(name, record, by_name, entities, language):
                        target_ids[target] = None
                targets = tuple(target_ids)
                result.append(
                    _site_relationship(
                        record, "calls" if kind == "calls" else "references", sources[0], targets
                    )
                )
                if kind == "calls":
                    bindings = _value_bindings(record, sources[0], entities, by_name, language)
                    result.extend(_construction_sites(record, sources[0], bindings, by_name))
    for record in observation.records("symbols") or ():
        for base in _records(record.data.get("base_declarations")):
            if record.kind != "class" or base.get("relationship_kind") is None:
                raise ValueError("typed base needs a classifier source and relationship kind")
            base_kind = _choice(
                base.get("relationship_kind"), _CLASSIFIER_RELATIONSHIPS, "inherits"
            )
            base_targets = tuple(
                target
                for name in _texts(base.get("targets"))
                for target in _endpoint(name, record, by_name, entities, language)
            )
            site = replace(
                record,
                id=_text(base.get("id")) or "",
                data=base,
                evidence_ids=_texts(base.get("evidence_ids")),
            )
            edge = _site_relationship(site, base_kind, record.id, base_targets)
            result.append(replace(edge, record_ids=(record.id,)))
    return tuple(result)


def _section_coverage(
    observation: Observation,
    scope_id: str,
    section: str,
    entity_kinds: tuple[EntityKind, ...],
    relationships: tuple[RelationshipKind, ...],
    available: bool,
) -> Coverage:
    status: CoverageStatus = "complete"
    reason: str | None = None
    if not available:
        status, reason = "unavailable", "profile does not publish this section"
    elif observation.coverage.status != "PASS":
        status, reason = "partial", "source observation is incomplete"
    elif section == "symbols":
        status, reason = (
            "partial",
            "legacy profile does not certify an exhaustive lexical symbol inventory",
        )
    elif section == "references":
        status, reason = "partial", "reference collector omits unresolved and external symbol uses"
    return Coverage(scope_id, entity_kinds, relationships, status, reason)


def _partial_inventory_coverage(
    entity: Entity, value_modules: set[str | None], base_modules: set[str | None]
) -> tuple[Coverage, ...]:
    result: list[Coverage] = []
    result.append(
        Coverage(
            entity.id,
            ("binding",),
            status="partial" if entity.qualified_name in value_modules else "unavailable",
            reason="call-result assignments are recorded; other binding forms remain incomplete"
            if entity.qualified_name in value_modules
            else "bindings section measures unread names, not static instances",
        )
    )
    result.append(
        Coverage(
            entity.id,
            relationship_kinds=("inherits", "realizes"),
            status="partial" if entity.qualified_name in base_modules else "unavailable",
            reason="explicit bases are recorded; the classifier inventory is not exhaustive"
            if entity.qualified_name in base_modules
            else "legacy profile has no typed classifier relationship facts",
        )
    )
    result.append(
        Coverage(
            entity.id,
            relationship_kinds=("creates", "instance_of"),
            status="partial" if entity.qualified_name in value_modules else "unavailable",
            reason="constructor sites are recorded; result typing and inventory remain partial"
            if entity.qualified_name in value_modules
            else "adapter has no typed instance relationship facts",
        )
    )
    result.append(
        Coverage(
            entity.id,
            ("attribute", "enum_literal"),
            status="partial",
            reason="class-body declarations are recorded; instance assignments remain unmeasured",
        )
    )
    return tuple(result)


def _member_inventory_coverage(
    observation: Observation, entities: list[Entity]
) -> tuple[Coverage, ...]:
    result: list[Coverage] = []
    symbols = observation.records("symbols") or ()
    for item in symbols:
        for inventory in member_inventories(item.data.get("member_inventories")):
            kinds: tuple[EntityKind, ...] = (
                ("attribute", "enum_literal")
                if inventory.kind == "attribute" and item.data.get("class_kind") == "enum"
                else (inventory.kind,)
            )
            actual = {
                entity.id
                for entity in entities
                if entity.parent_id == item.id and entity.kind in kinds
            }
            if item.kind != "class" or actual != set(inventory.definition_ids):
                raise ValueError("member inventory identities disagree with their owner")
            complete = (
                inventory.status == "complete"
                and observation.coverage.status == "PASS"
                and "enum_literal" not in kinds
            )
            result.append(
                Coverage(
                    item.id,
                    kinds,
                    status="complete" if complete else "partial",
                    reason=None
                    if complete
                    else (
                        "only literal enum assignments are measured"
                        if "enum_literal" in kinds
                        else inventory.reason or "source observation is incomplete"
                    ),
                )
            )
    return tuple(result)


def _coverage(observation: Observation, entities: list[Entity]) -> tuple[Coverage, ...]:
    source_kinds: tuple[EntityKind, ...] = (
        "class",
        "interface",
        "enum",
        "method",
        "function",
        "type_alias",
        "constant",
    )
    sections: tuple[tuple[str, tuple[EntityKind, ...], tuple[RelationshipKind, ...]], ...] = (
        ("symbols", source_kinds, ()),
        ("imports", (), ("imports",)),
        ("calls", (), ("calls",)),
        ("references", (), ("references",)),
    )
    profile = profile_for(observation.analyzer.name)
    value_modules = {
        _text(item.data.get("source_module"))
        for item in observation.records("calls") or ()
        if item.data.get("result_bindings") is not None
    }
    symbols = observation.records("symbols") or ()
    base_modules = {
        _text(item.data.get("module"))
        for item in symbols
        if item.data.get("base_declarations") is not None
    }
    result: list[Coverage] = []
    result.extend(_member_inventory_coverage(observation, entities))
    for item in symbols:
        if item.data.get("base_declarations") is None:
            continue
        bases = _records(item.data.get("base_declarations"))
        complete = observation.coverage.status == "PASS" and all(
            base.get("status") == "resolved" for base in bases
        )
        result.append(
            Coverage(
                item.id,
                relationship_kinds=("inherits", "realizes"),
                status="complete" if complete else "partial",
                reason=None if complete else "a base binding or classifier kind is not proven",
            )
        )
    for entity in entities:
        if entity.kind == "package":
            result.append(
                Coverage(
                    entity.id,
                    relationship_kinds=("owns",),
                    status="complete" if observation.coverage.status == "PASS" else "partial",
                    reason=None
                    if observation.coverage.status == "PASS"
                    else "source observation is incomplete",
                )
            )
        if entity.kind != "module" or entity.presence != "defined":
            continue
        for section, entity_kinds, relationships in sections:
            available = observation.records(section) is not None and not (
                section == "calls" and "calls_unresolved" in profile.unmeasured
            )
            result.append(
                _section_coverage(
                    observation, entity.id, section, entity_kinds, relationships, available
                )
            )
        result.extend(_partial_inventory_coverage(entity, value_modules, base_modules))
    return tuple(result)


def observed_graph(observation: Observation) -> ArchitectureGraph:
    profile = profile_for(observation.analyzer.name)
    language = next(
        language for language, entry in PROFILES.items() if entry.analyzer == profile.analyzer
    )
    entities = _source_entities(observation, language)
    relationships = _relationships(observation, entities, language)
    graph = ArchitectureGraph(
        "observed",
        tuple(sorted(entities, key=lambda entity: entity.id)),
        tuple(sorted(relationships, key=lambda edge: edge.id)),
        _coverage(observation, entities),
        observation.evidence,
    )
    graph.validate()
    return graph
