# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Normalize recorded source facts into the shared graph; never infer Target intent."""

from __future__ import annotations

from dataclasses import replace
from pathlib import PurePosixPath

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
    OriginKind,
    Parameter,
    ParameterKind,
    PresenceKind,
    Relationship,
    RelationshipKind,
    ResolutionKind,
    Signature,
    Visibility,
    VisibilityBasis,
    VisibilityKind,
)
from archkeel.ir.coverage import observation_complete
from archkeel.ir.facts import (
    SOURCE_SCRIPT_GLOBAL_KIND,
    InventoryStatus,
    MemberKind,
    MethodKind,
    SourceResolution,
    SourceSectionName,
    SymbolClassKind,
    member_inventories,
    parse_method_kind,
    parse_source_resolution,
    parse_symbol_class_kind,
)
from archkeel.ir.member_inventory import validated_member_inventory_proof
from archkeel.ir.model import (
    JsonValue,
    Observation,
    Record,
    RecordData,
    stable_id,
)
from archkeel.ir.profiles import PROFILES, UnmeasurableScalar, profile_for
from archkeel.ir.source_values import optional_text, record_array, text_array, vocabulary_text

_CLASSIFIER_RELATIONSHIPS = (
    RelationshipKind.INHERITS,
    RelationshipKind.REALIZES,
    RelationshipKind.MIXES_IN,
)


def _visibility(value: JsonValue, spelling: str | None = None) -> Visibility:
    if value is None:
        return Visibility(spelling=spelling)
    if not isinstance(value, RecordData):
        raise ValueError("source graph expected visibility record")
    return Visibility(
        VisibilityKind(vocabulary_text(value.get("kind"), default=VisibilityKind.UNKNOWN)),
        VisibilityBasis(vocabulary_text(value.get("basis"), default=VisibilityBasis.UNKNOWN)),
        optional_text(value.get("spelling")),
    )


def _signature(data: RecordData) -> Signature:
    parameters: list[Parameter] = []
    for item in record_array(data.get("parameters")):
        name: str = optional_text(item.get("name")) or ""
        if not name:
            raise ValueError("source parameter needs a name")
        kind = ParameterKind(vocabulary_text(item.get("kind"), default=ParameterKind.UNKNOWN))
        known = item.get("default_known")
        if known is not None and not isinstance(known, bool):
            raise ValueError("source default_known must be boolean")
        parameters.append(
            Parameter(
                name.lstrip("*") if kind in {ParameterKind.VARARGS, ParameterKind.KWARGS} else name,
                optional_text(item.get("annotation")),
                kind,
                optional_text(item.get("default")),
                known is True,
            )
        )
    return Signature(tuple(parameters), optional_text(data.get("returns")))


def _definition_contexts(value: JsonValue) -> tuple[DefinitionContext, ...]:
    result: list[DefinitionContext] = []
    for context in record_array(value):
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
                DefinitionContextKind(vocabulary_text(kind, default=DefinitionContextKind.IF)),
                DefinitionBranchKind(vocabulary_text(branch, default=DefinitionBranchKind.BODY)),
                text_array(context.get("evidence_ids")),
            )
        )
    return tuple(result)


def _classifier_kind(value: JsonValue) -> EntityKind | None:
    """Read known source classifiers without promoting unrelated or future graph tags."""
    classifier = parse_symbol_class_kind(value)
    if classifier is not None:
        return {
            SymbolClassKind.PROTOCOL: EntityKind.INTERFACE,
            SymbolClassKind.ENUM: EntityKind.ENUM,
        }.get(classifier)
    if not isinstance(value, str):
        return None
    try:
        kind = EntityKind(value)
    except ValueError:
        return None
    return kind if kind is EntityKind.MIXIN else None


def _symbol(record: Record, language: str) -> Entity:
    data = record.data
    category = optional_text(data.get("symbol_category", record.kind))
    aliases = {"static_constant": EntityKind.CONSTANT, "dynamic_binding": EntityKind.BINDING}
    kind = aliases.get(category or "")
    if kind is None:
        kind = EntityKind(vocabulary_text(category, default=EntityKind.SYMBOL))
    if kind is EntityKind.CLASS:
        kind = _classifier_kind(optional_text(data.get("class_kind"))) or kind
    modifiers: list[ModifierKind] = []
    if data.get("mixin_capable") is True:
        modifiers.append(ModifierKind.MIXIN)
    for key, modifier in (("async", ModifierKind.ASYNC), ("frozen_object", ModifierKind.FROZEN)):
        if data.get(key) is True:
            modifiers.append(modifier)
    method_kind = parse_method_kind(data.get("method_kind"))
    if method_kind in (MethodKind.STATIC, MethodKind.CLASS):
        modifiers.append(
            ModifierKind.STATIC if method_kind is MethodKind.STATIC else ModifierKind.CLASS
        )
    return Entity(
        record.id,
        kind,
        optional_text(data.get("qualified_name")) or "",
        language,
        visibility=_visibility(data.get("visibility_detail"), optional_text(data.get("name"))),
        signature=(
            _signature(data)
            if kind in {EntityKind.METHOD, EntityKind.FUNCTION}
            and data.get("signature_complete") is not False
            else None
        ),
        annotation=optional_text(data.get("annotation")),
        modifiers=tuple(modifiers),
        presence=PresenceKind.DEFINED,
        evidence_ids=record.evidence_ids,
        record_ids=(record.id,),
        definition_contexts=_definition_contexts(data.get("definition_contexts")),
        initializer=optional_text(data.get("initializer")) if kind == EntityKind.BINDING else None,
    )


def _attribute_entities(item: Record, entity: Entity, language: str) -> list[Entity]:
    fields = item.data.get("attribute_declarations", item.data.get("fields"))
    literals = text_array(item.data.get("enum_members")) if entity.kind == EntityKind.ENUM else ()
    result: list[Entity] = []
    for field in record_array(fields):
        name = optional_text(field.get("name")) or ""
        static = field.get("static")
        if static is not None and not isinstance(static, bool):
            raise ValueError("attribute static modifier must be boolean")
        result.append(
            Entity(
                optional_text(field.get("definition_id")) or stable_id("ATTR", item.id, name),
                EntityKind.ENUM_LITERAL if name in literals else EntityKind.ATTRIBUTE,
                f"{entity.qualified_name}.{name}",
                language,
                parent_id=item.id,
                visibility=_visibility(field.get("visibility")),
                annotation=optional_text(field.get("annotation")),
                modifiers=(ModifierKind.STATIC,) if static is True and name not in literals else (),
                presence=PresenceKind.DEFINED,
                evidence_ids=text_array(field.get("evidence_ids")) or item.evidence_ids,
                record_ids=(item.id,),
                definition_contexts=entity.definition_contexts,
            )
        )
    return result


def _source_entities(observation: Observation, language: str) -> list[Entity]:
    modules = observation.records("modules") or ()
    records = {item.id: item for item in modules}
    packages = observation.records("packages") or ()
    package_ids = {optional_text(item.data.get("qualified_name")): item.id for item in packages}
    module_ids = {optional_text(item.data.get("qualified_name")): item.id for item in modules}
    entities = [
        Entity(
            item.id,
            EntityKind.PACKAGE,
            optional_text(item.data.get("qualified_name")) or "",
            language,
            presence=PresenceKind.DEFINED,
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
        module_name: str = optional_text(item.data.get("qualified_name")) or ""
        module_parent = (
            module_name
            if PurePosixPath(optional_text(item.data.get("file")) or "").name == "__init__.py"
            else module_name.rpartition(".")[0]
        )
        entities.append(
            Entity(
                item.id,
                EntityKind.MODULE,
                module_name,
                language,
                parent_id=package_ids.get(module_parent),
                presence=PresenceKind.DEFINED,
                evidence_ids=item.evidence_ids,
                record_ids=(item.id,),
                file_path=optional_text(item.data.get("file")),
            )
        )
    symbols = observation.records("symbols") or ()
    symbol_ids: dict[str, list[str]] = {}
    for item in symbols:
        name = optional_text(item.data.get("qualified_name")) or ""
        definitions: list[str] = symbol_ids.setdefault(name, [])
        definitions.append(item.id)
    for item in symbols:
        entity = _symbol(item, language)
        parents = symbol_ids.get(optional_text(item.data.get("parent")) or "", [])
        parent = optional_text(item.data.get("lexical_parent_id"))
        if parent is None:
            if len(parents) > 1:
                raise ValueError("ambiguous lexical parent needs a definition-site identity")
            parent = (
                parents[0] if parents else module_ids.get(optional_text(item.data.get("module")))
            )
        entities.append(replace(entity, parent_id=parent))
        entities.extend(_attribute_entities(item, entity, language))
    return entities


def _source_resolution(value: JsonValue, message: str) -> ResolutionKind:
    status = parse_source_resolution(value)
    if status is None:
        raise ValueError(message)
    return {
        SourceResolution.RESOLVED: ResolutionKind.RESOLVED,
        SourceResolution.PARTIALLY_RESOLVED: ResolutionKind.PARTIAL,
        SourceResolution.UNRESOLVED: ResolutionKind.UNRESOLVED,
    }[status]


def _site_relationship(
    record: Record, kind: RelationshipKind, source: str, targets: tuple[str, ...]
) -> Relationship:
    status = _source_resolution(
        record.data.get("status"), "source relationship needs a resolution status"
    )
    resolved = status == ResolutionKind.RESOLVED and len(targets) == 1
    count = record.data.get("candidate_count")
    if count is not None and (not isinstance(count, int) or isinstance(count, bool)):
        raise ValueError("source candidate_count must be integer")
    if count is not None and count < len(text_array(record.data.get("targets"))):
        raise ValueError("source candidate count is smaller than its listed targets")
    truncated = record.data.get("candidates_truncated")
    if truncated is not None and not isinstance(truncated, bool):
        raise ValueError("source candidates_truncated must be boolean")
    if status == ResolutionKind.UNRESOLVED and targets:
        raise ValueError("unresolved source relationship has candidates")
    return Relationship(
        record.id,
        kind,
        source,
        targets[0] if resolved else None,
        ResolutionKind.RESOLVED
        if resolved
        else ResolutionKind.PARTIAL
        if status != ResolutionKind.UNRESOLVED
        else ResolutionKind.UNRESOLVED,
        candidate_ids=() if resolved else targets,
        expression=optional_text(record.data.get("expression")),
        evidence_ids=record.evidence_ids,
        record_ids=(record.id,),
        # The source count names qualified targets, not their definition sites.
        candidate_count=None if truncated is True or count is None else len(targets),
        candidates_truncated=truncated is True,
        reason=optional_text(record.data.get("reason")),
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
        EntityKind.SYMBOL,
        name,
        language,
        presence=PresenceKind.REFERENCED,
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
    identity = optional_text(record.data.get("source_definition_id"))
    if identity:
        if not any(entity.id == identity for entity in by_name.get(name, [])):
            raise ValueError("source definition does not match its recorded scope")
        return (identity,)
    if any(key == "source_definition_id" for key, _ in record.data.entries):
        # A missing declaration must not borrow another definition with the same name.
        source = Entity(
            stable_id("REFSCOPE", record.id),
            EntityKind.SYMBOL,
            name,
            language,
            presence=PresenceKind.REFERENCED,
            evidence_ids=record.evidence_ids,
            record_ids=(record.id,),
        )
        entities.append(source)
        return (source.id,)
    return _endpoint(name, record, by_name, entities, language)


def _reconcile_result_binding(
    previous: Entity | None,
    owner: Entity,
    source: str,
    name: str,
    target_kind: str,
    annotation: str | None,
    definition_contexts: tuple[DefinitionContext, ...],
) -> tuple[str, str | None, tuple[DefinitionContext, ...]]:
    qualified_name = f"{owner.qualified_name}.{name}"
    if previous is not None:
        if (
            previous.kind != "binding"
            or previous.parent_id != source
            or previous.initializer is not None
        ):
            raise ValueError("static result binding identity conflicts")
        if target_kind == "name":
            if (
                not previous.qualified_name.startswith(f"{owner.qualified_name}.")
                or previous.qualified_name.rsplit(".", 1)[-1] != name
            ):
                raise ValueError("static result binding identity conflicts")
            qualified_name = previous.qualified_name
        elif previous.qualified_name != qualified_name:
            raise ValueError("static result binding identity conflicts")
        if (
            previous.annotation is not None
            and annotation is not None
            and previous.annotation != annotation
        ):
            raise ValueError("static result binding identity conflicts")
        if (
            previous.definition_contexts
            and definition_contexts
            and tuple((item.kind, item.branch) for item in previous.definition_contexts)
            != tuple((item.kind, item.branch) for item in definition_contexts)
        ):
            raise ValueError("static result binding identity conflicts")
        annotation = annotation if annotation is not None else previous.annotation
        if not definition_contexts:
            definition_contexts = previous.definition_contexts
    return qualified_name, annotation, definition_contexts


def _result_binding_identity(site: RecordData) -> tuple[str, str, str, str]:
    if {key for key, _ in site.entries} != {
        "id",
        "name",
        "target_kind",
        "annotation",
        "initializer",
        "evidence_ids",
        "definition_contexts",
    } or not text_array(site.get("evidence_ids")):
        raise ValueError("static result binding fields or evidence mismatch")
    identity = optional_text(site.get("id")) or ""
    name = optional_text(site.get("name")) or ""
    initializer = optional_text(site.get("initializer")) or ""
    target_kind = optional_text(site.get("target_kind")) or ""
    if (
        not identity
        or not name
        or not initializer
        or target_kind not in {"name", "attribute", "subscript"}
    ):
        raise ValueError("invalid static result binding")
    return identity, name, initializer, target_kind


def _value_bindings(
    record: Record,
    source: str,
    entities: list[Entity],
    by_name: dict[str, list[Entity]],
    positions: dict[str, int],
    language: str,
) -> tuple[tuple[Entity, str], ...]:
    sites = record_array(record.data.get("result_bindings"))
    if not sites:
        return ()
    owner = entities[positions[source]]
    result: list[tuple[Entity, str]] = []
    for site in sites:
        identity, name, initializer, target_kind = _result_binding_identity(site)
        previous_index = positions.get(identity)
        previous = entities[previous_index] if previous_index is not None else None
        annotation = optional_text(site.get("annotation"))
        definition_contexts = _definition_contexts(site.get("definition_contexts"))
        qualified_name, annotation, definition_contexts = _reconcile_result_binding(
            previous,
            owner,
            source,
            name,
            target_kind,
            annotation,
            definition_contexts,
        )
        value = Entity(
            identity,
            EntityKind.BINDING,
            qualified_name,
            language,
            parent_id=source,
            annotation=annotation,
            presence=PresenceKind.DEFINED,
            evidence_ids=tuple(
                sorted(
                    set(record.evidence_ids)
                    | set(text_array(site.get("evidence_ids")))
                    | set(previous.evidence_ids if previous else ())
                )
            ),
            record_ids=tuple(
                sorted(set((record.id,)) | set(previous.record_ids if previous else ()))
            ),
            definition_contexts=definition_contexts,
            initializer=initializer,
        )
        if previous_index is not None:
            entities[previous_index] = value
            by_name[value.qualified_name] = [
                value if item.id == identity else item for item in by_name[value.qualified_name]
            ]
        else:
            positions[identity] = len(entities)
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
    status = _source_resolution(construction.get("status"), "invalid construction resolution")
    names = text_array(construction.get("targets"))
    truncated = construction.get("candidates_truncated")
    reason = optional_text(construction.get("reason"))
    if (
        {key for key, _ in construction.entries}
        != {"status", "targets", "candidates_truncated", "reason"}
        or (status == ResolutionKind.UNRESOLVED) != (not names)
        or not isinstance(truncated, bool)
        or not reason
    ):
        raise ValueError("invalid construction resolution")
    if not set(names) <= set(text_array(record.data.get("targets"))) or (
        status == ResolutionKind.RESOLVED
        and (
            parse_source_resolution(record.data.get("status")) is not SourceResolution.RESOLVED
            or truncated
            or len(names) != 1
        )
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
    if status != ResolutionKind.UNRESOLVED and not targets:
        raise ValueError("construction needs a recorded classifier candidate")
    resolved = status == ResolutionKind.RESOLVED and len(targets) == 1 and not truncated
    relations: list[tuple[RelationshipKind, str, bool]] = [(RelationshipKind.CREATES, source, True)]
    relations.extend(
        (RelationshipKind.INSTANCE_OF, binding.id, target_kind == "name")
        for binding, target_kind in bindings
    )
    result: list[Relationship] = []
    for kind, caller, stored in relations:
        proven = resolved and stored
        unresolved = status == ResolutionKind.UNRESOLVED
        result.append(
            Relationship(
                stable_id("CONSTRUCTION", record.id, kind, caller),
                kind,
                caller,
                targets[0] if proven else None,
                ResolutionKind.RESOLVED
                if proven
                else ResolutionKind.UNRESOLVED
                if unresolved
                else ResolutionKind.PARTIAL,
                candidate_ids=() if proven or unresolved else targets,
                expression=optional_text(record.data.get("expression")),
                evidence_ids=record.evidence_ids,
                record_ids=(record.id,),
                candidate_count=None if unresolved or truncated else len(targets),
                candidates_truncated=truncated,
                reason=reason if stored else "Storage is unproven; initializer type is a candidate",
            )
        )
    return tuple(result)


def _namespace_memberships(observation: Observation, entities: list[Entity]) -> list[Relationship]:
    result: list[Relationship] = []
    modules = {entity.id: entity for entity in entities if entity.kind == EntityKind.MODULE}
    for group in observation.records("packages") or ():
        for member in group.fact_ids:
            if member not in modules:
                raise ValueError("namespace group refers to an unknown module")
            result.append(
                Relationship(
                    stable_id("MEMBERSHIP", group.id, member),
                    RelationshipKind.OWNS,
                    group.id,
                    member,
                    ResolutionKind.RESOLVED,
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
    name = optional_text(record.data.get("declaration_scope"))
    identity = optional_text(record.data.get("declaration_definition_id"))
    if kind != "references" or present != keys or not name or not identity:
        raise ValueError("reference declaration needs a scope and definition identity")
    if not any(
        entity.id == identity
        and entity.kind in {EntityKind.METHOD, EntityKind.FUNCTION}
        and entity.parent_id == lexical_owner
        for entity in by_name.get(name, [])
    ):
        raise ValueError("reference declaration does not match an operation")
    return identity


def _relationships(
    observation: Observation, entities: list[Entity], language: str
) -> tuple[Relationship, ...]:
    by_name: dict[str, list[Entity]] = {}
    positions: dict[str, int] = {}
    for index, entity in enumerate(entities):
        positions.setdefault(entity.id, index)
        if entity.kind != EntityKind.PACKAGE:
            definitions: list[Entity] = by_name.setdefault(entity.qualified_name, [])
            definitions.append(entity)

    result: list[Relationship] = []
    result.extend(_namespace_memberships(observation, entities))
    indexed_count = len(entities)
    for section, kind in (
        ("imports", RelationshipKind.IMPORTS),
        ("calls", RelationshipKind.CALLS),
        ("references", RelationshipKind.REFERENCES),
    ):
        for record in observation.records(section) or ():
            if section == "references" and record.kind == "source_role":
                continue
            source_name = (
                optional_text(
                    record.data.get(
                        "source_scope" if kind != RelationshipKind.IMPORTS else "source_module"
                    )
                )
                or ""
            )
            sources = _source_endpoint(record, source_name, by_name, entities, language)
            if len(sources) != 1:
                raise ValueError("ambiguous source scope needs a definition-site identity")
            declaration = _declaration_endpoint(record, kind, sources[0], by_name)
            if declaration is not None:
                sources = (declaration,)
            if kind == RelationshipKind.IMPORTS:
                target_name = optional_text(record.data.get("target_module")) or ""
                targets = _endpoint(target_name, record, by_name, entities, language)
                result.append(
                    Relationship(
                        record.id,
                        RelationshipKind.REFERENCES
                        if record.kind == SOURCE_SCRIPT_GLOBAL_KIND
                        else RelationshipKind.IMPORTS,
                        sources[0],
                        targets[0] if len(targets) == 1 else None,
                        ResolutionKind.RESOLVED if len(targets) == 1 else ResolutionKind.PARTIAL,
                        candidate_ids=() if len(targets) == 1 else targets,
                        expression=target_name,
                        evidence_ids=record.evidence_ids,
                        record_ids=(record.id,),
                    )
                )
            else:
                target_ids: dict[str, None] = {}
                for name in text_array(record.data.get("targets")):
                    for target in _endpoint(name, record, by_name, entities, language):
                        target_ids[target] = None
                targets = tuple(target_ids)
                result.append(_site_relationship(record, kind, sources[0], targets))
                if kind == RelationshipKind.CALLS:
                    for index in range(indexed_count, len(entities)):
                        positions.setdefault(entities[index].id, index)
                    bindings = _value_bindings(
                        record, sources[0], entities, by_name, positions, language
                    )
                    indexed_count = len(entities)
                    result.extend(_construction_sites(record, sources[0], bindings, by_name))
    result.extend(
        _classifier_relationships(observation.records("symbols") or (), by_name, entities, language)
    )
    return tuple(result)


def _classifier_relationships(
    records: tuple[Record, ...],
    by_name: dict[str, list[Entity]],
    entities: list[Entity],
    language: str,
) -> list[Relationship]:
    result: list[Relationship] = []
    for record in records:
        for base in record_array(record.data.get("base_declarations")):
            if record.kind != "class" or base.get("relationship_kind") is None:
                raise ValueError("typed base needs a classifier source and relationship kind")
            base_kind = RelationshipKind(
                vocabulary_text(base.get("relationship_kind"), default=RelationshipKind.INHERITS)
            )
            if base_kind not in _CLASSIFIER_RELATIONSHIPS:
                raise ValueError("invalid classifier relationship kind")
            base_targets = tuple(
                target
                for name in text_array(base.get("targets"))
                for target in _endpoint(name, record, by_name, entities, language)
            )
            site = replace(
                record,
                id=optional_text(base.get("id")) or "",
                data=base,
                evidence_ids=text_array(base.get("evidence_ids")),
            )
            edge = _site_relationship(site, base_kind, record.id, base_targets)
            result.append(replace(edge, record_ids=(record.id,)))
    return result


def _section_coverage(
    observation: Observation,
    scope_id: str,
    section: SourceSectionName,
    entity_kinds: tuple[EntityKind, ...],
    relationships: tuple[RelationshipKind, ...],
    available: bool,
) -> Coverage:
    status: CoverageStatus = CoverageStatus.COMPLETE
    reason: str | None = None
    if not available:
        status, reason = CoverageStatus.UNAVAILABLE, "profile does not publish this section"
    elif not observation_complete(observation.coverage):
        status, reason = CoverageStatus.PARTIAL, "source observation is incomplete"
    elif (
        section == SourceSectionName.CALLS
        and UnmeasurableScalar.CALLS_UNRESOLVED in profile_for(observation.analyzer.name).unmeasured
    ):
        status, reason = (
            CoverageStatus.PARTIAL,
            "observed call sites do not certify an exhaustive module call inventory",
        )
    elif section == SourceSectionName.SYMBOLS:
        status, reason = (
            CoverageStatus.PARTIAL,
            "symbol records do not certify an exhaustive module-level lexical inventory",
        )
    elif section == SourceSectionName.REFERENCES:
        status, reason = (
            CoverageStatus.PARTIAL,
            "reference collector omits unresolved and external symbol uses",
        )
    return Coverage(scope_id, entity_kinds, relationships, status, reason)


def _partial_inventory_coverage(
    entity: Entity, value_modules: set[str | None], base_modules: set[str | None]
) -> tuple[Coverage, ...]:
    result: list[Coverage] = []
    result.append(
        Coverage(
            entity.id,
            (EntityKind.BINDING,),
            status=CoverageStatus.PARTIAL
            if entity.qualified_name in value_modules
            else CoverageStatus.UNAVAILABLE,
            reason="call-result assignments are recorded; other binding forms remain incomplete"
            if entity.qualified_name in value_modules
            else "the source facts do not certify a complete static binding inventory",
        )
    )
    result.append(
        Coverage(
            entity.id,
            relationship_kinds=(
                RelationshipKind.INHERITS,
                RelationshipKind.REALIZES,
                RelationshipKind.MIXES_IN,
            ),
            status=CoverageStatus.PARTIAL
            if entity.qualified_name in base_modules
            else CoverageStatus.UNAVAILABLE,
            reason="explicit bases are recorded; the classifier inventory is not exhaustive"
            if entity.qualified_name in base_modules
            else "no typed classifier relationship facts were recorded",
        )
    )
    result.append(
        Coverage(
            entity.id,
            relationship_kinds=(RelationshipKind.CREATES, RelationshipKind.INSTANCE_OF),
            status=CoverageStatus.PARTIAL
            if entity.qualified_name in value_modules
            else CoverageStatus.UNAVAILABLE,
            reason="constructor sites are recorded; result typing and inventory remain partial"
            if entity.qualified_name in value_modules
            else "adapter has no typed instance relationship facts",
        )
    )
    result.append(
        Coverage(
            entity.id,
            (EntityKind.ATTRIBUTE, EntityKind.ENUM_LITERAL),
            status=CoverageStatus.PARTIAL,
            reason="class-body declarations are recorded; instance assignments remain unmeasured",
        )
    )
    return tuple(result)


def _member_inventory_coverage(
    observation: Observation, entities: list[Entity]
) -> tuple[Coverage, ...]:
    result: list[Coverage] = []
    members: dict[tuple[str, EntityKind], set[str]] = {}
    for entity in entities:
        if entity.parent_id is not None:
            members.setdefault((entity.parent_id, entity.kind), set()).add(entity.id)
    proof = validated_member_inventory_proof(observation)
    approved = set(proof.fact_ids) if proof is not None else set()
    symbols = observation.records("symbols") or ()
    for item in symbols:
        for inventory in member_inventories(item.data.get("member_inventories")):
            kinds: tuple[EntityKind, ...] = (
                (EntityKind.ATTRIBUTE, EntityKind.ENUM_LITERAL)
                if inventory.kind == MemberKind.ATTRIBUTE
                and parse_symbol_class_kind(item.data.get("class_kind")) is SymbolClassKind.ENUM
                else (EntityKind(inventory.kind),)
            )
            actual = {identity for kind in kinds for identity in members.get((item.id, kind), ())}
            if item.kind != "class" or actual != set(inventory.definition_ids):
                raise ValueError("member inventory identities disagree with their owner")
            complete = (
                inventory.status == InventoryStatus.COMPLETE
                and (observation_complete(observation.coverage) or item.id in approved)
                and (
                    "enum_literal" not in kinds
                    or observation.analyzer.name
                    in {
                        "archkeel-dart-analyzer",
                        "archkeel-typescript-imports",
                    }
                )
            )
            result.append(
                Coverage(
                    item.id,
                    kinds,
                    status=CoverageStatus.COMPLETE if complete else CoverageStatus.PARTIAL,
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
        EntityKind.CLASS,
        EntityKind.INTERFACE,
        EntityKind.ENUM,
        EntityKind.MIXIN,
        EntityKind.METHOD,
        EntityKind.FUNCTION,
        EntityKind.TYPE_ALIAS,
        EntityKind.CONSTANT,
        EntityKind.MACRO,
    )
    sections: tuple[
        tuple[SourceSectionName, tuple[EntityKind, ...], tuple[RelationshipKind, ...]], ...
    ] = (
        (SourceSectionName.SYMBOLS, source_kinds, ()),
        (SourceSectionName.IMPORTS, (), (RelationshipKind.IMPORTS,)),
        (SourceSectionName.CALLS, (), (RelationshipKind.CALLS,)),
        (SourceSectionName.REFERENCES, (), (RelationshipKind.REFERENCES,)),
    )
    profile = profile_for(observation.analyzer.name)
    value_modules = {
        optional_text(item.data.get("source_module"))
        for item in observation.records("calls") or ()
        if item.data.get("result_bindings") is not None
    }
    symbols = observation.records("symbols") or ()
    base_modules = {
        optional_text(item.data.get("module"))
        for item in symbols
        if item.data.get("base_declarations") is not None
    }
    result: list[Coverage] = []
    result.extend(_member_inventory_coverage(observation, entities))
    scan_complete = observation_complete(observation.coverage)
    for item in symbols:
        if item.data.get("base_declarations") is None:
            continue
        bases = record_array(item.data.get("base_declarations"))
        complete = scan_complete and all(
            parse_source_resolution(base.get("status")) is SourceResolution.RESOLVED
            for base in bases
        )
        result.append(
            Coverage(
                item.id,
                relationship_kinds=(
                    RelationshipKind.INHERITS,
                    RelationshipKind.REALIZES,
                    RelationshipKind.MIXES_IN,
                ),
                status=CoverageStatus.COMPLETE if complete else CoverageStatus.PARTIAL,
                reason=None if complete else "a base binding or classifier kind is not proven",
            )
        )
    for entity in entities:
        if entity.kind == EntityKind.PACKAGE:
            result.append(
                Coverage(
                    entity.id,
                    relationship_kinds=(RelationshipKind.OWNS,),
                    status=CoverageStatus.COMPLETE if scan_complete else CoverageStatus.PARTIAL,
                    reason=None if scan_complete else "source observation is incomplete",
                )
            )
        if entity.kind != EntityKind.MODULE or entity.presence != PresenceKind.DEFINED:
            continue
        for section, entity_kinds, relationships in sections:
            available = (
                section not in profile.absent_sections and observation.records(section) is not None
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
        OriginKind.OBSERVED,
        tuple(sorted(entities, key=lambda entity: entity.id)),
        tuple(sorted(relationships, key=lambda edge: edge.id)),
        _coverage(observation, entities),
        observation.evidence,
    )
    graph.validate()
    return graph
