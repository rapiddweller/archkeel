# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Compare independent UML intent with recorded facts and explicit inventory limits."""

from archkeel.ir.architecture_graph import (
    ArchitectureGraph,
    AssessmentAspect,
    AssessmentChange,
    AssessmentStatus,
    Entity,
    EntityCorrespondence,
    EntityKind,
    GraphAssessment,
    GraphComparison,
    Relationship,
    RelationshipKind,
    Signature,
    TargetScope,
)
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
    namespace = wanted.kind in {"module", "package"}
    matches = tuple(
        item
        for item in graph.entities
        if item.qualified_name == wanted.qualified_name
        and item.language == wanted.language
        and (item.presence == "defined" or wanted.presence == "referenced")
        and (item.kind == wanted.kind if namespace else item.kind not in {"module", "package"})
    )
    if wanted.kind == "enum_literal":
        # A physical field or value binding alone does not prove enum membership.
        return tuple(item for item in matches if item.kind not in {"attribute", "binding"})
    if wanted.kind in {"attribute", "binding"} and any(
        item.kind == wanted.kind for item in matches
    ):
        # One annotated assignment can expose a field and a separate value-binding site.
        return tuple(
            item
            for item in matches
            if item.kind == wanted.kind or item.kind not in {"attribute", "binding"}
        )
    return matches


def _scope(graph: ArchitectureGraph, wanted: Entity) -> tuple[Entity, ...]:
    if wanted.kind != "component":
        return _matches(graph, wanted)
    packages = tuple(
        item
        for item in graph.entities
        if item.kind == "package"
        and item.presence == "defined"
        and item.qualified_name == wanted.qualified_name
    )
    return packages or tuple(
        item
        for item in graph.entities
        if item.kind == "module"
        and item.presence == "defined"
        and item.qualified_name == wanted.qualified_name
    )


def _ancestors(graph: ArchitectureGraph, identifier: str) -> set[str]:
    entities = {item.id: item for item in graph.entities}
    result: set[str] = set()
    while identifier in entities:
        result.add(identifier)
        parent = entities[identifier].parent_id
        if parent is None:
            break
        identifier = parent
    return result


def _complete(graph: ArchitectureGraph, scope: Entity, kind: EntityKind | RelationshipKind) -> bool:
    ancestors = _ancestors(graph, scope.id)
    entities = {item.id: item for item in graph.entities}
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
        if item.scope_id not in ancestors and _within(graph, scope, entities[item.scope_id])
    )
    return bool(covering) and all(item.status == "complete" for item in receipts)


def _absence(
    observed: ArchitectureGraph, target: ArchitectureGraph, wanted: Entity
) -> GraphAssessment:
    parents = {item.id: item for item in target.entities}
    parent = parents.get(wanted.parent_id) if wanted.parent_id is not None else None
    scopes = _scope(observed, parent) if parent is not None else ()
    complete = len(scopes) == 1 and _complete(observed, scopes[0], wanted.kind)
    return _result(
        wanted.id,
        "existence",
        "FAIL" if complete else "UNKNOWN",
        "missing" if complete else "unavailable",
        "Declared entity is absent from a complete inventory."
        if complete
        else "Entity is absent; complete inventory is not proven.",
        scopes,
    )


def _signature(expected: Signature, actual: Signature | None) -> tuple[AssessmentStatus, str]:
    if actual is None:
        return "UNKNOWN", "Operation signature was not recorded."
    if len(expected.parameters) != len(actual.parameters):
        return "FAIL", "Parameter count differs."
    unknown = False
    for wanted, found in zip(expected.parameters, actual.parameters, strict=True):
        if wanted.name != found.name:
            return "FAIL", "Parameter name or order differs."
        if wanted.annotation is not None and wanted.annotation != found.annotation:
            return "FAIL", "Parameter annotation differs."
        if wanted.kind != "unknown":
            if found.kind == "unknown":
                unknown = True
            elif wanted.kind != found.kind:
                return "FAIL", "Parameter kind differs."
        if wanted.default_known:
            if not found.default_known:
                unknown = True
            elif wanted.default != found.default:
                return "FAIL", "Unevaluated parameter default differs."
    if expected.returns is not None and expected.returns != actual.returns:
        return "FAIL", "Return annotation differs."
    return (
        ("UNKNOWN", "Parameter metadata is unavailable.")
        if unknown
        else ("PASS", "Declared signature matches recorded syntax.")
    )


def _containment(
    observed: ArchitectureGraph, target: ArchitectureGraph, wanted: Entity, actual: Entity
) -> tuple[GraphAssessment, ...]:
    parents = {item.id: item for item in target.entities}
    parent = parents.get(wanted.parent_id) if wanted.parent_id is not None else None
    if (
        parent is None
        or parent.kind == "component"
        or (parent.kind == "package" and wanted.kind != "module")
    ):
        return ()
    matches = _matches(observed, parent)
    if len(matches) != 1 or actual.parent_id is None:
        return (
            _result(
                wanted.id,
                "containment",
                "UNKNOWN",
                "unavailable",
                "Lexical parent cannot be identified.",
                (actual,),
            ),
        )
    equal = actual.parent_id == matches[0].id
    return (
        _result(
            wanted.id,
            "containment",
            "PASS" if equal else "FAIL",
            "matched" if equal else "changed",
            "Lexical parent matches." if equal else "Lexical parent differs.",
            (actual, *matches),
        ),
    )


def _syntax_details(wanted: Entity, actual: Entity) -> tuple[GraphAssessment, ...]:
    fields: tuple[tuple[AssessmentAspect, str | None, str | None, str], ...] = (
        ("annotation", wanted.annotation, actual.annotation, "Annotation"),
        ("initializer", wanted.initializer, actual.initializer, "Initializer syntax"),
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
                "UNKNOWN" if unknown else "PASS" if equal else "FAIL",
                "unavailable" if unknown else "matched" if equal else "changed",
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
                "signature",
                status,
                "matched" if status == "PASS" else "changed" if status == "FAIL" else "unavailable",
                reason,
                (actual,),
            )
        )
    if wanted.visibility.kind != "unknown":
        unknown = actual.visibility.kind == "unknown" or actual.visibility.basis == "unknown"
        equal = (
            wanted.visibility.kind == actual.visibility.kind
            and (
                wanted.visibility.basis in {"unknown", "declared"}
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
                "visibility",
                "UNKNOWN" if unknown else "PASS" if equal else "FAIL",
                "unavailable" if unknown else "matched" if equal else "changed",
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
                "modifiers",
                "PASS" if equal else "UNKNOWN",
                "matched" if equal else "unavailable",
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
    if wanted.kind == "component":
        return ()
    matches = _matches(observed, wanted)
    if wanted.presence == "referenced":
        if (
            wanted.signature is None
            and wanted.visibility.kind == "unknown"
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
                "existence",
                "UNKNOWN",
                "ambiguous" if matches else "unavailable",
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
                "existence",
                "UNKNOWN",
                "ambiguous",
                "Several definition sites share the declared identity.",
                matches,
            ),
        )
    actual = matches[0]
    if actual.definition_contexts:
        return (
            _result(
                wanted.id,
                "existence",
                "UNKNOWN",
                "unavailable",
                "Definition is recorded under control flow; its namespace binding is not proven.",
                matches,
            ),
        )
    if actual.kind != wanted.kind:
        return (
            _result(wanted.id, "kind", "FAIL", "changed", "Recorded entity kind differs.", matches),
        )
    return (
        _result(
            wanted.id, "existence", "PASS", "matched", "Declared definition is recorded.", matches
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
            "relationship",
            "UNKNOWN",
            "ambiguous",
            "Relationship endpoints cannot be identified uniquely.",
            (*sources, *targets),
        )
    if sources[0].definition_contexts or targets[0].definition_contexts:
        return _result(
            wanted.id,
            "relationship",
            "UNKNOWN",
            "unavailable",
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
        if item.target_id == targets[0].id and item.resolution in {"resolved", "not_applicable"}
    )
    if matched:
        return _result(
            wanted.id,
            "relationship",
            "PASS",
            "matched",
            "Directed relationship is recorded.",
            matched,
        )
    uncertain = tuple(item for item in sites if item.resolution in {"partial", "unresolved"})
    if uncertain:
        return _result(
            wanted.id,
            "relationship",
            "UNKNOWN",
            "unavailable",
            "Unresolved source sites may refer to this endpoint.",
            uncertain,
        )
    complete = _complete(observed, sources[0], wanted.kind)
    return _result(
        wanted.id,
        "relationship",
        "FAIL" if complete else "UNKNOWN",
        "missing" if complete else "unavailable",
        "Relationship is absent from a complete resolved inventory."
        if complete
        else "Relationship coverage is unavailable or partial.",
        sources,
    )


def _within(graph: ArchitectureGraph, scope: Entity, item: Entity) -> bool:
    if scope.kind in {"package", "component"}:
        prefix: str = scope.qualified_name
        name: str = item.qualified_name
        return name.startswith(f"{prefix}.")
    return scope.id in _ancestors(graph, item.id)


def _closed_relationship_assessments(
    observed: ArchitectureGraph, target: ArchitectureGraph, wanted: TargetScope, actual: Entity
) -> tuple[GraphAssessment, ...]:
    entities = {item.id: item for item in target.entities}
    scope = entities[wanted.scope_id]
    matches = (actual,)
    kinds = (*wanted.entity_kinds, *wanted.relationship_kinds)
    expected_edges = tuple(
        item for item in target.relationships if _within(target, scope, entities[item.source_id])
    )
    sites = tuple(
        item
        for item in observed.relationships
        if item.kind in wanted.relationship_kinds
        and _within(
            observed, actual, {entry.id: entry for entry in observed.entities}[item.source_id]
        )
    )
    extra_edges = tuple(
        item
        for item in sites
        if item.target_id is not None
        and item.resolution == "resolved"
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
                "completeness",
                "FAIL",
                "unexpected",
                "Closed scope contains an unlisted relationship.",
                (item,),
                kinds,
            )
            for item in extra_edges
        )
    complete = all(
        _complete(observed, actual, kind)
        for kind in (*wanted.entity_kinds, *wanted.relationship_kinds)
    ) and not any(item.resolution in {"partial", "unresolved"} for item in sites)
    return (
        _result(
            scope.id,
            "completeness",
            "PASS" if complete else "UNKNOWN",
            "matched" if complete else "unavailable",
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
    kinds = (*wanted.entity_kinds, *wanted.relationship_kinds)
    matches = _scope(observed, scope)
    if len(matches) != 1:
        return (
            _result(
                scope.id,
                "completeness",
                "UNKNOWN",
                "ambiguous",
                "Scope cannot be identified uniquely.",
                matches,
                kinds,
            ),
        )
    actual = matches[0]
    if wanted.mode == "open":
        return (
            _result(
                scope.id,
                "completeness",
                "PASS",
                "matched",
                "Open scope permits unlisted elements; listed intent is assessed separately.",
                matches,
                kinds,
            ),
        )
    declared = tuple(item for item in target.entities if _within(target, scope, item))
    extras = tuple(
        item
        for item in observed.entities
        if item.id != actual.id
        and item.presence == "defined"
        and item.kind in wanted.entity_kinds
        and _within(observed, actual, item)
        and not any(
            item.qualified_name == entry.qualified_name and item.kind == entry.kind
            for entry in declared
        )
    )
    if extras:
        return tuple(
            _result(
                scope.id,
                "completeness",
                "FAIL",
                "unexpected",
                "Closed scope contains an unlisted definition.",
                (item,),
                kinds,
            )
            for item in extras
        )
    return _closed_relationship_assessments(observed, target, wanted, actual)


def compare_graphs(observed: ArchitectureGraph, target: ArchitectureGraph) -> GraphComparison:
    if observed.origin != "observed" or target.origin != "declared":
        raise ValueError("comparison requires observed facts and independent declared intent")
    observed.validate()
    target.validate()
    assessments = tuple(
        [item for entity in target.entities for item in _entity(observed, target, entity)]
        + [
            _relationship(observed, target, edge)
            for edge in target.relationships
            if edge.kind != "requires"
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
