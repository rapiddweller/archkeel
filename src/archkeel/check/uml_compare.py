# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Compare independent UML intent with recorded facts and explicit inventory limits."""

from archkeel.ir.architecture_graph import (
    ArchitectureGraph,
    AssessmentAspect,
    AssessmentChange,
    AssessmentStatus,
    CompletenessMode,
    CoverageStatus,
    Entity,
    EntityCorrespondence,
    EntityKind,
    GraphAssessment,
    GraphComparison,
    OriginKind,
    ParameterKind,
    PresenceKind,
    Relationship,
    RelationshipKind,
    ResolutionKind,
    Signature,
    TargetScope,
    VisibilityBasis,
    VisibilityKind,
)
from archkeel.ir.facts import Language
from archkeel.ir.model import stable_id


def _result(
    subject: str,
    aspect: AssessmentAspect,
    status: AssessmentStatus,
    change: AssessmentChange,
    reason: str,
    facts: tuple[Entity | Relationship, ...] = (),
    scope_kinds: tuple[EntityKind | RelationshipKind, ...] = (),
) -> GraphAssessment:
    identities = tuple(sorted({item.id for item in facts}))
    return GraphAssessment(
        stable_id("UML-ASSESSMENT", subject, aspect, change, *scope_kinds, *identities),
        subject,
        aspect,
        status,
        change,
        reason,
        identities,
        tuple(sorted({key for item in facts for key in item.evidence_ids})),
        tuple(sorted({key for item in facts for key in item.record_ids})),
    )


def _matches(graph: ArchitectureGraph, wanted: Entity) -> tuple[Entity, ...]:
    namespace = wanted.kind in {EntityKind.MODULE, EntityKind.PACKAGE}
    type_only = {EntityKind.INTERFACE, EntityKind.TYPE_ALIAS}
    value_only = {
        EntityKind.METHOD,
        EntityKind.FUNCTION,
        EntityKind.ATTRIBUTE,
        EntityKind.CONSTANT,
        EntityKind.BINDING,
        EntityKind.ENUM_LITERAL,
    }
    # Classes, enums and opaque kinds can occupy both namespaces; never pick by kind alone.
    excluded = (
        value_only
        if wanted.language == Language.TYPESCRIPT and wanted.kind in type_only
        else type_only
        if wanted.language == Language.TYPESCRIPT and wanted.kind in value_only
        else ()
    )
    matches = tuple(
        item
        for item in graph.entities
        if item.qualified_name == wanted.qualified_name
        and item.language == wanted.language
        and (item.presence == PresenceKind.DEFINED or wanted.presence == PresenceKind.REFERENCED)
        and (
            item.kind == wanted.kind
            if namespace
            else item.kind not in {EntityKind.MODULE, EntityKind.PACKAGE}
        )
        and item.kind not in excluded
    )
    if wanted.kind == EntityKind.ENUM_LITERAL:
        # A physical field or value binding alone does not prove enum membership.
        return tuple(
            item for item in matches if item.kind not in {EntityKind.ATTRIBUTE, EntityKind.BINDING}
        )
    if wanted.kind in {EntityKind.ATTRIBUTE, EntityKind.BINDING} and any(
        item.kind == wanted.kind for item in matches
    ):
        # One annotated assignment can expose a field and a separate value-binding site.
        return tuple(
            item
            for item in matches
            if item.kind == wanted.kind
            or item.kind not in {EntityKind.ATTRIBUTE, EntityKind.BINDING}
        )
    return matches


def _scope(graph: ArchitectureGraph, wanted: Entity) -> tuple[Entity, ...]:
    if wanted.kind != EntityKind.COMPONENT:
        return _matches(graph, wanted)
    packages = tuple(
        item
        for item in graph.entities
        if item.kind == EntityKind.PACKAGE
        and item.presence == PresenceKind.DEFINED
        and item.qualified_name == wanted.qualified_name
    )
    return packages or tuple(
        item
        for item in graph.entities
        if item.kind == EntityKind.MODULE
        and item.presence == PresenceKind.DEFINED
        and item.qualified_name == wanted.qualified_name
    )


def _ancestors(entities: dict[str, Entity], identifier: str) -> set[str]:
    result: set[str] = set()
    while identifier in entities:
        result.add(identifier)
        parent = entities[identifier].parent_id
        if parent is None:
            break
        identifier = parent
    return result


def _complete(graph: ArchitectureGraph, scope: Entity, kind: EntityKind | RelationshipKind) -> bool:
    entities = {item.id: item for item in graph.entities}
    ancestors = _ancestors(entities, scope.id)
    relevant = tuple(
        item for item in graph.coverage if kind in (*item.entity_kinds, *item.relationship_kinds)
    )
    identifier: str | None = scope.id
    covering = tuple(item for item in relevant if item.scope_id == identifier)
    while not covering and identifier is not None:
        identifier = entities[identifier].parent_id
        covering = tuple(item for item in relevant if item.scope_id == identifier)
    receipts = covering + tuple(
        item
        for item in relevant
        if item.scope_id not in ancestors and _within(entities, scope, entities[item.scope_id])
    )
    return bool(covering) and all(item.status == CoverageStatus.COMPLETE for item in receipts)


def _absence(
    observed: ArchitectureGraph, target: ArchitectureGraph, wanted: Entity
) -> GraphAssessment:
    parents = {item.id: item for item in target.entities}
    parent = parents.get(wanted.parent_id) if wanted.parent_id is not None else None
    scopes = _scope(observed, parent) if parent is not None else ()
    complete = len(scopes) == 1 and _complete(observed, scopes[0], wanted.kind)
    return _result(
        wanted.id,
        AssessmentAspect.EXISTENCE,
        AssessmentStatus.FAIL if complete else AssessmentStatus.UNKNOWN,
        AssessmentChange.MISSING if complete else AssessmentChange.UNAVAILABLE,
        "Declared entity is absent from a complete inventory."
        if complete
        else "Entity is absent; complete inventory is not proven.",
        scopes,
    )


def _signature(expected: Signature, actual: Signature | None) -> tuple[AssessmentStatus, str]:
    if actual is None:
        return AssessmentStatus.UNKNOWN, "Operation signature was not recorded."
    if len(expected.parameters) != len(actual.parameters):
        return AssessmentStatus.FAIL, "Parameter count differs."
    unknown = False
    for wanted, found in zip(expected.parameters, actual.parameters, strict=True):
        if wanted.name != found.name:
            return AssessmentStatus.FAIL, "Parameter name or order differs."
        if wanted.annotation is not None and wanted.annotation != found.annotation:
            return AssessmentStatus.FAIL, "Parameter annotation differs."
        if wanted.kind != ParameterKind.UNKNOWN:
            if found.kind == ParameterKind.UNKNOWN:
                unknown = True
            elif wanted.kind != found.kind:
                return AssessmentStatus.FAIL, "Parameter kind differs."
        if wanted.default_known:
            if not found.default_known:
                unknown = True
            elif wanted.default != found.default:
                return AssessmentStatus.FAIL, "Unevaluated parameter default differs."
    if expected.returns is not None and expected.returns != actual.returns:
        return AssessmentStatus.FAIL, "Return annotation differs."
    return (
        (AssessmentStatus.UNKNOWN, "Parameter metadata is unavailable.")
        if unknown
        else (AssessmentStatus.PASS, "Declared signature matches recorded syntax.")
    )


def _containment(
    observed: ArchitectureGraph, target: ArchitectureGraph, wanted: Entity, actual: Entity
) -> tuple[GraphAssessment, ...]:
    parents = {item.id: item for item in target.entities}
    parent = parents.get(wanted.parent_id) if wanted.parent_id is not None else None
    if (
        parent is None
        or parent.kind == EntityKind.COMPONENT
        or (parent.kind == EntityKind.PACKAGE and wanted.kind != EntityKind.MODULE)
    ):
        return ()
    matches = _matches(observed, parent)
    if len(matches) != 1 or actual.parent_id is None:
        return (
            _result(
                wanted.id,
                AssessmentAspect.CONTAINMENT,
                AssessmentStatus.UNKNOWN,
                AssessmentChange.UNAVAILABLE,
                "Lexical parent cannot be identified.",
                (actual,),
            ),
        )
    equal = actual.parent_id == matches[0].id
    return (
        _result(
            wanted.id,
            AssessmentAspect.CONTAINMENT,
            AssessmentStatus.PASS if equal else AssessmentStatus.FAIL,
            AssessmentChange.MATCHED if equal else AssessmentChange.CHANGED,
            "Lexical parent matches." if equal else "Lexical parent differs.",
            (actual, *matches),
        ),
    )


def _syntax_details(wanted: Entity, actual: Entity) -> tuple[GraphAssessment, ...]:
    fields: tuple[tuple[AssessmentAspect, str | None, str | None, str], ...] = (
        (AssessmentAspect.ANNOTATION, wanted.annotation, actual.annotation, "Annotation"),
        (
            AssessmentAspect.INITIALIZER,
            wanted.initializer,
            actual.initializer,
            "Initializer syntax",
        ),
    )
    results = []
    for aspect, expected, value, label in fields:
        if expected is None:
            continue
        unknown = value is None
        equal = expected == value
        results.append(
            _result(
                wanted.id,
                aspect,
                AssessmentStatus.UNKNOWN
                if unknown
                else AssessmentStatus.PASS
                if equal
                else AssessmentStatus.FAIL,
                AssessmentChange.UNAVAILABLE
                if unknown
                else AssessmentChange.MATCHED
                if equal
                else AssessmentChange.CHANGED,
                f"{label} is unavailable."
                if unknown
                else f"{label} matches."
                if equal
                else f"{label} differs.",
                (actual,),
            )
        )
    return tuple(results)


def _details(wanted: Entity, actual: Entity) -> tuple[GraphAssessment, ...]:
    results: list[GraphAssessment] = []
    if wanted.signature is not None:
        status, reason = _signature(wanted.signature, actual.signature)
        results.append(
            _result(
                wanted.id,
                AssessmentAspect.SIGNATURE,
                status,
                AssessmentChange.MATCHED
                if status == AssessmentStatus.PASS
                else AssessmentChange.CHANGED
                if status == AssessmentStatus.FAIL
                else AssessmentChange.UNAVAILABLE,
                reason,
                (actual,),
            )
        )
    if wanted.visibility.kind != VisibilityKind.UNKNOWN:
        unknown = (
            actual.visibility.kind == VisibilityKind.UNKNOWN
            or actual.visibility.basis == VisibilityBasis.UNKNOWN
        )
        equal = (
            wanted.visibility.kind == actual.visibility.kind
            and (
                wanted.visibility.basis in {VisibilityBasis.UNKNOWN, VisibilityBasis.DECLARED}
                or wanted.visibility.basis == actual.visibility.basis
            )
            and (
                wanted.visibility.spelling is None
                or wanted.visibility.spelling == actual.visibility.spelling
            )
        )
        results.append(
            _result(
                wanted.id,
                AssessmentAspect.VISIBILITY,
                AssessmentStatus.UNKNOWN
                if unknown
                else AssessmentStatus.PASS
                if equal
                else AssessmentStatus.FAIL,
                AssessmentChange.UNAVAILABLE
                if unknown
                else AssessmentChange.MATCHED
                if equal
                else AssessmentChange.CHANGED,
                "Visibility is unavailable."
                if unknown
                else "Visibility matches."
                if equal
                else "Visibility or its basis differs.",
                (actual,),
            )
        )
    if wanted.modifiers:
        equal = set(wanted.modifiers) <= set(actual.modifiers)
        results.append(
            _result(
                wanted.id,
                AssessmentAspect.MODIFIERS,
                AssessmentStatus.PASS if equal else AssessmentStatus.UNKNOWN,
                AssessmentChange.MATCHED if equal else AssessmentChange.UNAVAILABLE,
                "Requested traits are recorded."
                if equal
                else "Requested traits are not proven; trait coverage is unavailable.",
                (actual,),
            )
        )
    results.extend(_syntax_details(wanted, actual))
    return tuple(results)


def _entity(
    observed: ArchitectureGraph, target: ArchitectureGraph, wanted: Entity
) -> tuple[GraphAssessment, ...]:
    if wanted.kind == EntityKind.COMPONENT:
        return ()
    matches = _matches(observed, wanted)
    if wanted.presence == PresenceKind.REFERENCED:
        if (
            wanted.signature is None
            and wanted.visibility.kind == VisibilityKind.UNKNOWN
            and wanted.annotation is None
            and not wanted.modifiers
            and wanted.initializer is None
        ):
            return ()
        if len(matches) == 1:
            return _details(wanted, matches[0])
        return (
            _result(
                wanted.id,
                AssessmentAspect.EXISTENCE,
                AssessmentStatus.UNKNOWN,
                AssessmentChange.AMBIGUOUS if matches else AssessmentChange.UNAVAILABLE,
                "Referenced endpoint metadata cannot be identified uniquely.",
                matches,
            ),
        )
    if not matches:
        return (_absence(observed, target, wanted),)
    if len(matches) > 1:
        return (
            _result(
                wanted.id,
                AssessmentAspect.EXISTENCE,
                AssessmentStatus.UNKNOWN,
                AssessmentChange.AMBIGUOUS,
                "Several definition sites share the declared identity.",
                matches,
            ),
        )
    actual = matches[0]
    if actual.definition_contexts:
        return (
            _result(
                wanted.id,
                AssessmentAspect.EXISTENCE,
                AssessmentStatus.UNKNOWN,
                AssessmentChange.UNAVAILABLE,
                "Definition is recorded under control flow; its namespace binding is not proven.",
                matches,
            ),
        )
    if actual.kind != wanted.kind:
        return (
            _result(
                wanted.id,
                AssessmentAspect.KIND,
                AssessmentStatus.FAIL,
                AssessmentChange.CHANGED,
                "Recorded entity kind differs.",
                matches,
            ),
        )
    return (
        _result(
            wanted.id,
            AssessmentAspect.EXISTENCE,
            AssessmentStatus.PASS,
            AssessmentChange.MATCHED,
            "Declared definition is recorded.",
            matches,
        ),
        *_containment(observed, target, wanted, actual),
        *_details(wanted, actual),
    )


def _relationship(
    observed: ArchitectureGraph, target: ArchitectureGraph, wanted: Relationship
) -> GraphAssessment:
    entities = {item.id: item for item in target.entities}
    sources = _matches(observed, entities[wanted.source_id])
    targets = _matches(observed, entities[wanted.target_id]) if wanted.target_id is not None else ()
    if len(sources) != 1 or len(targets) != 1:
        return _result(
            wanted.id,
            AssessmentAspect.RELATIONSHIP,
            AssessmentStatus.UNKNOWN,
            AssessmentChange.AMBIGUOUS,
            "Relationship endpoints cannot be identified uniquely.",
            (*sources, *targets),
        )
    if sources[0].definition_contexts or targets[0].definition_contexts:
        return _result(
            wanted.id,
            AssessmentAspect.RELATIONSHIP,
            AssessmentStatus.UNKNOWN,
            AssessmentChange.UNAVAILABLE,
            "A relationship endpoint is conditional; its namespace binding is not proven.",
            (*sources, *targets),
        )
    sites = tuple(
        item
        for item in observed.relationships
        if item.kind == wanted.kind and item.source_id == sources[0].id
    )
    matched = tuple(
        item
        for item in sites
        if item.target_id == targets[0].id
        and item.resolution in {ResolutionKind.RESOLVED, ResolutionKind.NOT_APPLICABLE}
    )
    if matched:
        return _result(
            wanted.id,
            AssessmentAspect.RELATIONSHIP,
            AssessmentStatus.PASS,
            AssessmentChange.MATCHED,
            "Directed relationship is recorded.",
            matched,
        )
    uncertain = tuple(
        item
        for item in sites
        if item.resolution in {ResolutionKind.PARTIAL, ResolutionKind.UNRESOLVED}
    )
    if uncertain:
        return _result(
            wanted.id,
            AssessmentAspect.RELATIONSHIP,
            AssessmentStatus.UNKNOWN,
            AssessmentChange.UNAVAILABLE,
            "Unresolved source sites may refer to this endpoint.",
            uncertain,
        )
    complete = _complete(observed, sources[0], wanted.kind)
    return _result(
        wanted.id,
        AssessmentAspect.RELATIONSHIP,
        AssessmentStatus.FAIL if complete else AssessmentStatus.UNKNOWN,
        AssessmentChange.MISSING if complete else AssessmentChange.UNAVAILABLE,
        "Relationship is absent from a complete resolved inventory."
        if complete
        else "Relationship coverage is unavailable or partial.",
        sources,
    )


def _within(entities: dict[str, Entity], scope: Entity, item: Entity) -> bool:
    if scope.kind in {EntityKind.PACKAGE, EntityKind.COMPONENT}:
        prefix: str = scope.qualified_name
        name: str = item.qualified_name
        return name.startswith(f"{prefix}.")
    return scope.id in _ancestors(entities, item.id)


def _closed_relationship_assessments(
    observed: ArchitectureGraph, target: ArchitectureGraph, wanted: TargetScope, actual: Entity
) -> tuple[GraphAssessment, ...]:
    entities = {item.id: item for item in target.entities}
    observed_entities = {item.id: item for item in observed.entities}
    scope = entities[wanted.scope_id]
    matches = (actual,)
    kinds: tuple[EntityKind | RelationshipKind, ...] = (
        *wanted.entity_kinds,
        *wanted.relationship_kinds,
    )
    expected_edges = tuple(
        item for item in target.relationships if _within(entities, scope, entities[item.source_id])
    )
    sites = tuple(
        item
        for item in observed.relationships
        if item.kind in wanted.relationship_kinds
        and _within(observed_entities, actual, observed_entities[item.source_id])
    )
    extra_edges = tuple(
        item
        for item in sites
        if item.target_id is not None
        and item.resolution == ResolutionKind.RESOLVED
        and not any(
            item.kind == entry.kind
            and item.source_id
            in {found.id for found in _matches(observed, entities[entry.source_id])}
            and entry.target_id is not None
            and item.target_id
            in {found.id for found in _matches(observed, entities[entry.target_id])}
            for entry in expected_edges
        )
    )
    if extra_edges:
        return tuple(
            _result(
                scope.id,
                AssessmentAspect.COMPLETENESS,
                AssessmentStatus.FAIL,
                AssessmentChange.UNEXPECTED,
                "Closed scope contains an unlisted relationship.",
                (item,),
                kinds,
            )
            for item in extra_edges
        )
    complete = (
        all(_complete(observed, actual, kind) for kind in wanted.entity_kinds)
        and all(_complete(observed, actual, kind) for kind in wanted.relationship_kinds)
        and not any(
            item.resolution in {ResolutionKind.PARTIAL, ResolutionKind.UNRESOLVED} for item in sites
        )
    )
    return (
        _result(
            scope.id,
            AssessmentAspect.COMPLETENESS,
            AssessmentStatus.PASS if complete else AssessmentStatus.UNKNOWN,
            AssessmentChange.MATCHED if complete else AssessmentChange.UNAVAILABLE,
            "Closed scope inventory is covered."
            if complete
            else "Closed scope inventory or resolution is incomplete.",
            matches,
            kinds,
        ),
    )


def _scope_assessments(
    observed: ArchitectureGraph, target: ArchitectureGraph, wanted: TargetScope
) -> tuple[GraphAssessment, ...]:
    entities = {item.id: item for item in target.entities}
    scope = entities[wanted.scope_id]
    kinds: tuple[EntityKind | RelationshipKind, ...] = (
        *wanted.entity_kinds,
        *wanted.relationship_kinds,
    )
    matches = _scope(observed, scope)
    if len(matches) != 1:
        return (
            _result(
                scope.id,
                AssessmentAspect.COMPLETENESS,
                AssessmentStatus.UNKNOWN,
                AssessmentChange.AMBIGUOUS,
                "Scope cannot be identified uniquely.",
                matches,
                kinds,
            ),
        )
    actual = matches[0]
    if wanted.mode == CompletenessMode.OPEN:
        return (
            _result(
                scope.id,
                AssessmentAspect.COMPLETENESS,
                AssessmentStatus.PASS,
                AssessmentChange.MATCHED,
                "Open scope permits unlisted elements; listed intent is assessed separately.",
                matches,
                kinds,
            ),
        )
    observed_entities = {item.id: item for item in observed.entities}
    declared = tuple(item for item in target.entities if _within(entities, scope, item))
    extras = tuple(
        item
        for item in observed.entities
        if item.id != actual.id
        and item.presence == PresenceKind.DEFINED
        and item.kind in wanted.entity_kinds
        and _within(observed_entities, actual, item)
        and not any(
            item.qualified_name == entry.qualified_name and item.kind == entry.kind
            for entry in declared
        )
    )
    if extras:
        return tuple(
            _result(
                scope.id,
                AssessmentAspect.COMPLETENESS,
                AssessmentStatus.FAIL,
                AssessmentChange.UNEXPECTED,
                "Closed scope contains an unlisted definition.",
                (item,),
                kinds,
            )
            for item in extras
        )
    return _closed_relationship_assessments(observed, target, wanted, actual)


def compare_graphs(observed: ArchitectureGraph, target: ArchitectureGraph) -> GraphComparison:
    if observed.origin != OriginKind.OBSERVED or target.origin != OriginKind.DECLARED:
        raise ValueError("comparison requires observed facts and independent declared intent")
    observed.validate()
    target.validate()
    assessments = tuple(
        [item for entity in target.entities for item in _entity(observed, target, entity)]
        + [
            _relationship(observed, target, edge)
            for edge in target.relationships
            if edge.kind != RelationshipKind.REQUIRES
        ]
        + [
            item
            for scope in target.target_scopes
            for item in _scope_assessments(observed, target, scope)
        ]
    )
    correspondences = tuple(
        EntityCorrespondence(entity.id, tuple(sorted(item.id for item in matches)))
        for entity in target.entities
        if (matches := _scope(observed, entity))
    )
    comparison = GraphComparison.from_assessments(assessments, correspondences=correspondences)
    comparison.validate()
    return comparison
