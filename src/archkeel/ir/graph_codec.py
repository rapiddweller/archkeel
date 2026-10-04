# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Strict JSON codecs for shared graph values and independent Target intent."""

from __future__ import annotations

import json
from dataclasses import asdict
from typing import Literal, TypeGuard, TypeVar, get_args

from archkeel.ir.architecture_graph import (
    ArchitectureGraph,
    ArchitectureReport,
    AssessmentAspect,
    AssessmentChange,
    AssessmentStatus,
    CompletenessMode,
    ComponentIntent,
    ComponentMembership,
    ComponentRole,
    ContractModuleTarget,
    Coverage,
    CoverageStatus,
    DefinitionBranchKind,
    DefinitionContext,
    DefinitionContextKind,
    DependencyDecisionGap,
    Entity,
    EntityCorrespondence,
    EntityKind,
    ExternalDependencyScopeRule,
    GraphAssessment,
    GraphComparison,
    ModifierKind,
    ModuleInventory,
    OriginKind,
    Parameter,
    ParameterKind,
    PresenceKind,
    PublicAPIEntry,
    Relationship,
    RelationshipKind,
    ReportFinding,
    ResolutionKind,
    RootLayoutRule,
    Signature,
    TargetDefinition,
    TargetScope,
    Visibility,
    VisibilityBasis,
    VisibilityKind,
)
from archkeel.ir.facts import Evidence
from archkeel.ir.model import RawJson

_Choice = TypeVar("_Choice", bound=str)


def _object(value: RawJson) -> TypeGuard[dict[str, RawJson]]:
    return isinstance(value, dict) and all(isinstance(key, str) for key in value)


def _fields(
    value: RawJson, required: set[str], optional: set[str], label: str
) -> dict[str, RawJson]:
    if not _object(value):
        raise ValueError(f"{label} fields mismatch")
    keys = set(value)
    if not required <= keys or keys - required - optional:
        raise ValueError(f"{label} fields mismatch")
    return value


def _array(value: RawJson, label: str) -> tuple[RawJson, ...]:
    if not isinstance(value, list | tuple):
        raise ValueError(f"{label} must be an array")
    return tuple(value)


def _text(value: RawJson, label: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be non-empty text")
    text: str = value
    if not text.strip():
        raise ValueError(f"{label} must be non-empty text")
    return text


def _nullable(value: RawJson, label: str) -> str | None:
    return None if value is None else _text(value, label)


def _texts(value: RawJson, label: str) -> tuple[str, ...]:
    entries = tuple(_text(entry, label) for entry in _array(value, label))
    if len(set(entries)) != len(entries):
        raise ValueError(f"{label} must be unique")
    return entries


def _choice(value: RawJson, choices: tuple[_Choice, ...], label: str) -> _Choice:
    for choice in choices:
        if value == choice:
            return choice
    raise ValueError(f"{label} has an invalid vocabulary value")


def _boolean(value: RawJson, label: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{label} must be boolean")
    return value


def _integer(value: RawJson, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(f"{label} must be a non-negative integer")
    return value


def _visibility(value: RawJson) -> Visibility:
    item = _fields(value, set(), {"kind", "basis", "spelling"}, "visibility")
    return Visibility(
        _choice(item.get("kind", "unknown"), get_args(VisibilityKind), "visibility.kind"),
        _choice(item.get("basis", "unknown"), get_args(VisibilityBasis), "visibility.basis"),
        _nullable(item.get("spelling"), "visibility.spelling"),
    )


def _parameter(value: RawJson) -> Parameter:
    item = _fields(value, {"name"}, {"annotation", "kind", "default", "default_known"}, "parameter")
    default = item.get("default")
    if default is not None and not isinstance(default, str):
        raise ValueError("parameter.default must be text or null")
    return Parameter(
        _text(item["name"], "parameter.name"),
        _nullable(item.get("annotation"), "parameter.annotation"),
        _choice(item.get("kind", "unknown"), get_args(ParameterKind), "parameter.kind"),
        default,
        _boolean(item.get("default_known", False), "parameter.default_known"),
    )


def _signature(value: RawJson) -> Signature:
    item = _fields(value, set(), {"parameters", "returns"}, "signature")
    return Signature(
        tuple(_parameter(entry) for entry in _array(item.get("parameters", ()), "parameters")),
        _nullable(item.get("returns"), "signature.returns"),
    )


def parse_component_intent(value: RawJson) -> ComponentIntent:
    item = _fields(
        value,
        {"component_id", "role"},
        {
            "packages",
            "exact_modules",
            "namespace",
            "public",
            "planned",
            "forbidden_responsibilities",
            "decided_by",
            "inside",
            "parent_id",
            "label",
            "layout_rule_ids",
        },
        "component_intent",
    )
    public, planned, decider = item.get("public"), item.get("planned"), item.get("decided_by")
    deciders: tuple[Literal["architect", "agent"], ...] = ("architect", "agent")
    return ComponentIntent(
        component_id=_text(item["component_id"], "component_intent.component_id"),
        role=_choice(item["role"], tuple(ComponentRole), "component_intent.role"),
        packages=_texts(item.get("packages", ()), "component_intent.packages"),
        exact_modules=_texts(item.get("exact_modules", ()), "component_intent.exact_modules"),
        namespace=_nullable(item.get("namespace"), "component_intent.namespace"),
        public=None if public is None else _texts(public, "component_intent.public"),
        planned=None if planned is None else _texts(planned, "component_intent.planned"),
        forbidden_responsibilities=_texts(
            item.get("forbidden_responsibilities", ()),
            "component_intent.forbidden_responsibilities",
        ),
        decided_by=None
        if decider is None
        else _choice(decider, deciders, "component_intent.decided_by"),
        inside=_nullable(item.get("inside"), "component_intent.inside"),
        parent_id=_nullable(item.get("parent_id"), "component_intent.parent_id"),
        label=_nullable(item.get("label"), "component_intent.label"),
        layout_rule_ids=_texts(item.get("layout_rule_ids", ()), "component_intent.layout_rule_ids"),
    )


def parse_module_inventory(value: RawJson) -> ModuleInventory:
    item = _fields(value, {"id", "modules", "provenance"}, {"component_id"}, "module inventory")
    modules: list[ContractModuleTarget] = []
    for value in _array(item["modules"], "module inventory.modules"):
        module = _fields(value, {"path", "responsibility"}, set(), "module target")
        modules.append(
            ContractModuleTarget(
                _text(module["path"], "module target.path"),
                _text(module["responsibility"], "module target.responsibility"),
            )
        )
    return ModuleInventory(
        _text(item["id"], "module inventory.id"),
        tuple(modules),
        _texts(item["provenance"], "module inventory.provenance"),
        _nullable(item.get("component_id"), "module inventory.component_id"),
    )


def parse_public_api_entry(value: RawJson) -> PublicAPIEntry:
    item = _fields(value, {"id", "selector", "provenance"}, set(), "public API entry")
    return PublicAPIEntry(
        _text(item["id"], "public API entry.id"),
        _text(item["selector"], "public API entry.selector"),
        _texts(item["provenance"], "public API entry.provenance"),
    )


def parse_layout_rule(value: RawJson) -> RootLayoutRule:
    item = _fields(
        value,
        {"id", "kind", "root", "allowed_children", "rationale", "provenance", "decided_by"},
        set(),
        "layout rule",
    )
    deciders: tuple[Literal["architect", "agent"], ...] = ("architect", "agent")
    return RootLayoutRule(
        _text(item["id"], "layout rule.id"),
        _choice(item["kind"], ("root_layout",), "layout rule.kind"),
        _text(item["root"], "layout rule.root"),
        _texts(item["allowed_children"], "layout rule.allowed_children"),
        _text(item["rationale"], "layout rule.rationale"),
        _texts(item["provenance"], "layout rule.provenance"),
        _choice(item["decided_by"], deciders, "layout rule.decided_by"),
    )


def parse_external_scope(value: RawJson) -> ExternalDependencyScopeRule:
    item = _fields(
        value,
        {"id", "kind", "dependency", "allowed_sources", "rationale", "provenance", "decided_by"},
        {"exact_sources"},
        "external scope",
    )
    deciders: tuple[Literal["architect", "agent"], ...] = ("architect", "agent")
    return ExternalDependencyScopeRule(
        _text(item["id"], "external scope.id"),
        _choice(item["kind"], ("external_dependency_scope",), "external scope.kind"),
        _text(item["dependency"], "external scope.dependency"),
        _texts(item["allowed_sources"], "external scope.allowed_sources"),
        _text(item["rationale"], "external scope.rationale"),
        _texts(item["provenance"], "external scope.provenance"),
        _choice(item["decided_by"], deciders, "external scope.decided_by"),
        _texts(item.get("exact_sources", ()), "external scope.exact_sources"),
    )


def _definition_context(value: RawJson) -> DefinitionContext:
    item = _fields(value, {"kind", "branch", "evidence_ids"}, set(), "definition context")
    return DefinitionContext(
        _choice(item["kind"], get_args(DefinitionContextKind), "definition context.kind"),
        _choice(item["branch"], get_args(DefinitionBranchKind), "definition context.branch"),
        _texts(item["evidence_ids"], "definition context.evidence_ids"),
    )


def parse_entity(value: RawJson) -> Entity:
    item = _fields(
        value,
        {"id", "kind", "qualified_name", "language"},
        {
            "parent_id",
            "visibility",
            "signature",
            "annotation",
            "modifiers",
            "presence",
            "responsibilities",
            "evidence_ids",
            "provenance",
            "record_ids",
            "definition_contexts",
            "initializer",
            "file_path",
        },
        "entity",
    )
    signature = item.get("signature")
    return Entity(
        _text(item["id"], "entity.id"),
        _choice(item["kind"], get_args(EntityKind), "entity.kind"),
        _text(item["qualified_name"], "entity.qualified_name"),
        _text(item["language"], "entity.language"),
        _nullable(item.get("parent_id"), "entity.parent_id"),
        _visibility(item.get("visibility", {})),
        None if signature is None else _signature(signature),
        _nullable(item.get("annotation"), "entity.annotation"),
        tuple(
            _choice(entry, get_args(ModifierKind), "modifier")
            for entry in _texts(item.get("modifiers", ()), "modifiers")
        ),
        _choice(item.get("presence", "unspecified"), get_args(PresenceKind), "entity.presence"),
        _texts(item.get("responsibilities", ()), "entity.responsibilities"),
        _texts(item.get("evidence_ids", ()), "entity.evidence_ids"),
        _texts(item.get("provenance", ()), "entity.provenance"),
        _texts(item.get("record_ids", ()), "entity.record_ids"),
        tuple(
            _definition_context(entry)
            for entry in _array(item.get("definition_contexts", ()), "entity.definition_contexts")
        ),
        _nullable(item.get("initializer"), "entity.initializer"),
        _nullable(item.get("file_path"), "entity.file_path"),
    )


def parse_relationship(value: RawJson) -> Relationship:
    item = _fields(
        value,
        {"id", "kind", "source_id"},
        {
            "target_id",
            "resolution",
            "candidate_ids",
            "expression",
            "evidence_ids",
            "provenance",
            "record_ids",
            "candidate_count",
            "candidates_truncated",
            "reason",
            "through",
            "decided_by",
        },
        "relationship",
    )
    count = item.get("candidate_count")
    decider = item.get("decided_by")
    deciders: tuple[Literal["architect", "agent"], ...] = ("architect", "agent")
    return Relationship(
        _text(item["id"], "relationship.id"),
        _choice(item["kind"], get_args(RelationshipKind), "relationship.kind"),
        _text(item["source_id"], "relationship.source_id"),
        _nullable(item.get("target_id"), "relationship.target_id"),
        _choice(
            item.get("resolution", "not_applicable"),
            get_args(ResolutionKind),
            "relationship.resolution",
        ),
        _texts(item.get("candidate_ids", ()), "relationship.candidate_ids"),
        _nullable(item.get("expression"), "relationship.expression"),
        _texts(item.get("evidence_ids", ()), "relationship.evidence_ids"),
        _texts(item.get("provenance", ()), "relationship.provenance"),
        _texts(item.get("record_ids", ()), "relationship.record_ids"),
        None if count is None else _integer(count, "relationship.candidate_count"),
        _boolean(item.get("candidates_truncated", False), "relationship.candidates_truncated"),
        _nullable(item.get("reason"), "relationship.reason"),
        _texts(item.get("through", ()), "relationship.through"),
        None if decider is None else _choice(decider, deciders, "relationship.decided_by"),
    )


def _kinds(item: dict[str, RawJson]) -> tuple[tuple[EntityKind, ...], tuple[RelationshipKind, ...]]:
    return (
        tuple(
            _choice(entry, get_args(EntityKind), "entity kind")
            for entry in _texts(item.get("entity_kinds", ()), "entity_kinds")
        ),
        tuple(
            _choice(entry, get_args(RelationshipKind), "relationship kind")
            for entry in _texts(item.get("relationship_kinds", ()), "relationship_kinds")
        ),
    )


def _coverage(value: RawJson) -> Coverage:
    item = _fields(
        value, {"scope_id"}, {"entity_kinds", "relationship_kinds", "status", "reason"}, "coverage"
    )
    entity_kinds, relationship_kinds = _kinds(item)
    return Coverage(
        _text(item["scope_id"], "coverage.scope_id"),
        entity_kinds,
        relationship_kinds,
        _choice(item.get("status", "unavailable"), get_args(CoverageStatus), "coverage.status"),
        _nullable(item.get("reason"), "coverage.reason"),
    )


def _target_scope(value: RawJson) -> TargetScope:
    item = _fields(
        value,
        {"scope_id", "mode", "rationale", "provenance"},
        {"entity_kinds", "relationship_kinds"},
        "target scope",
    )
    entity_kinds, relationship_kinds = _kinds(item)
    return TargetScope(
        _text(item["scope_id"], "scope_id"),
        _choice(item["mode"], get_args(CompletenessMode), "mode"),
        _text(item["rationale"], "rationale"),
        _texts(item["provenance"], "provenance"),
        entity_kinds,
        relationship_kinds,
    )


def _evidence(value: RawJson) -> Evidence:
    item = _fields(
        value, {"id", "file", "line", "end_line", "column", "excerpt"}, set(), "evidence"
    )
    excerpt = item["excerpt"]
    if not isinstance(excerpt, str):
        raise ValueError("evidence.excerpt must be text")
    return Evidence(
        _text(item["id"], "evidence.id"),
        _text(item["file"], "evidence.file"),
        _integer(item["line"], "evidence.line"),
        _integer(item["end_line"], "evidence.end_line"),
        _integer(item["column"], "evidence.column"),
        excerpt,
    )


def parse_graph(value: RawJson) -> ArchitectureGraph:
    item = _fields(
        value,
        {"origin", "schema_version"},
        {
            "entities",
            "relationships",
            "coverage",
            "evidence",
            "target_scopes",
            "component_intents",
            "module_inventories",
            "layout_rules",
            "external_scopes",
            "public_api",
        },
        "graph",
    )
    if item["schema_version"] != "1.0.0":
        raise ValueError("unsupported graph schema_version")
    graph = ArchitectureGraph(
        _choice(item["origin"], get_args(OriginKind), "graph.origin"),
        tuple(parse_entity(entry) for entry in _array(item.get("entities", ()), "entities")),
        tuple(
            parse_relationship(entry)
            for entry in _array(item.get("relationships", ()), "relationships")
        ),
        tuple(_coverage(entry) for entry in _array(item.get("coverage", ()), "coverage")),
        tuple(_evidence(entry) for entry in _array(item.get("evidence", ()), "evidence")),
        target_scopes=tuple(
            _target_scope(entry) for entry in _array(item.get("target_scopes", ()), "target_scopes")
        ),
        component_intents=tuple(
            parse_component_intent(entry)
            for entry in _array(item.get("component_intents", ()), "component_intents")
        ),
        module_inventories=tuple(
            parse_module_inventory(entry)
            for entry in _array(item.get("module_inventories", ()), "module_inventories")
        ),
        layout_rules=tuple(
            parse_layout_rule(entry)
            for entry in _array(item.get("layout_rules", ()), "layout_rules")
        ),
        external_scopes=tuple(
            parse_external_scope(entry)
            for entry in _array(item.get("external_scopes", ()), "external_scopes")
        ),
        public_api=tuple(
            parse_public_api_entry(entry)
            for entry in _array(item.get("public_api", ()), "public_api")
        ),
    )
    graph.validate()
    return graph


def parse_target(value: RawJson) -> TargetDefinition:
    item = _fields(value, {"schema_version"}, {"entities", "relationships", "scopes"}, "uml")
    if item["schema_version"] != "1.0.0":
        raise ValueError("unsupported UML schema_version")
    return TargetDefinition(
        tuple(parse_entity(entry) for entry in _array(item.get("entities", ()), "entities")),
        tuple(
            parse_relationship(entry)
            for entry in _array(item.get("relationships", ()), "relationships")
        ),
        tuple(_target_scope(entry) for entry in _array(item.get("scopes", ()), "scopes")),
    )


def graph_bytes(graph: ArchitectureGraph) -> bytes:
    graph.validate()
    text: str = json.dumps(asdict(graph), sort_keys=True, ensure_ascii=False) + "\n"
    return text.encode()


def _assessment(value: RawJson) -> GraphAssessment:
    item = _fields(
        value,
        {"id", "subject_id", "aspect", "status", "change", "reason"},
        {"observed_ids", "evidence_ids", "fact_ids"},
        "assessment",
    )
    return GraphAssessment(
        _text(item["id"], "assessment.id"),
        _text(item["subject_id"], "assessment.subject_id"),
        _choice(item["aspect"], get_args(AssessmentAspect), "assessment.aspect"),
        _choice(item["status"], get_args(AssessmentStatus), "assessment.status"),
        _choice(item["change"], get_args(AssessmentChange), "assessment.change"),
        _text(item["reason"], "assessment.reason"),
        _texts(item.get("observed_ids", ()), "assessment.observed_ids"),
        _texts(item.get("evidence_ids", ()), "assessment.evidence_ids"),
        _texts(item.get("fact_ids", ()), "assessment.fact_ids"),
    )


def parse_comparison(value: RawJson) -> GraphComparison:
    item = _fields(
        value, {"status", "schema_version"}, {"assessments", "correspondences"}, "comparison"
    )
    if item["schema_version"] != "1.0.0":
        raise ValueError("unsupported comparison schema_version")
    comparison = GraphComparison(
        _choice(item["status"], get_args(AssessmentStatus), "comparison.status"),
        tuple(_assessment(entry) for entry in _array(item.get("assessments", ()), "assessments")),
        correspondences=tuple(
            _correspondence(entry)
            for entry in _array(item.get("correspondences", ()), "correspondences")
        ),
    )
    comparison.validate()
    return comparison


def _correspondence(value: RawJson) -> EntityCorrespondence:
    item = _fields(value, {"target_id", "observed_ids"}, set(), "correspondence")
    return EntityCorrespondence(
        _text(item["target_id"], "correspondence.target_id"),
        _texts(item["observed_ids"], "correspondence.observed_ids"),
    )


def comparison_bytes(comparison: GraphComparison) -> bytes:
    comparison.validate()
    text: str = json.dumps(asdict(comparison), sort_keys=True, ensure_ascii=False) + "\n"
    return text.encode()


def parse_report(value: RawJson) -> ArchitectureReport:
    item = _fields(
        value,
        {"observed", "target", "schema_version"},
        {"comparison", "unavailable", "findings", "memberships", "decision_gaps"},
        "report",
    )
    if item["schema_version"] != "1.0.0":
        raise ValueError("unsupported report schema_version")
    observed, target, comparison = item["observed"], item["target"], item.get("comparison")
    report = ArchitectureReport(
        None if observed is None else parse_graph(observed),
        None if target is None else parse_graph(target),
        None if comparison is None else parse_comparison(comparison),
        _nullable(item.get("unavailable"), "report.unavailable"),
        findings=tuple(
            _report_finding(entry) for entry in _array(item.get("findings", ()), "findings")
        ),
        decision_gaps=tuple(
            _decision_gap(entry) for entry in _array(item.get("decision_gaps", ()), "decision_gaps")
        ),
        memberships=tuple(
            _membership(entry) for entry in _array(item.get("memberships", ()), "memberships")
        ),
    )
    report.validate()
    return report


def _decision_gap(value: RawJson) -> DependencyDecisionGap:
    item = _fields(value, {"source_id", "target_id", "relationship_ids"}, set(), "decision gap")
    return DependencyDecisionGap(
        _text(item["source_id"], "decision gap.source_id"),
        _text(item["target_id"], "decision gap.target_id"),
        _texts(item["relationship_ids"], "decision gap.relationship_ids"),
    )


def _membership(value: RawJson) -> ComponentMembership:
    item = _fields(value, {"component_id", "module_ids"}, set(), "membership")
    return ComponentMembership(
        _text(item["component_id"], "membership.component_id"),
        _texts(item["module_ids"], "membership.module_ids"),
    )


def _report_finding(value: RawJson) -> ReportFinding:
    item = _fields(
        value,
        {
            "id",
            "kind",
            "title",
            "status",
            "rule_ids",
            "subjects",
            "graph_subject_ids",
            "evidence_ids",
            "provenance",
        },
        set(),
        "finding",
    )
    return ReportFinding(
        _text(item["id"], "finding.id"),
        _text(item["kind"], "finding.kind"),
        _text(item["title"], "finding.title"),
        _choice(item["status"], ("FAIL", "UNKNOWN"), "finding.status"),
        _texts(item["rule_ids"], "finding.rule_ids"),
        tuple(
            _text(entry, "finding.subjects")
            for entry in _array(item["subjects"], "finding.subjects")
        ),
        _texts(item["graph_subject_ids"], "finding.graph_subject_ids"),
        tuple(
            _text(entry, "finding.evidence_ids")
            for entry in _array(item["evidence_ids"], "finding.evidence_ids")
        ),
        _texts(item["provenance"], "finding.provenance"),
    )


def report_bytes(report: ArchitectureReport) -> bytes:
    report.validate()
    encoded: str = json.dumps(asdict(report), sort_keys=True, ensure_ascii=False) + "\n"
    return encoded.encode("utf-8")
