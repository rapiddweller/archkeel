# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Project evaluator receipts and findings into one row per declared rule."""

from collections import Counter

from .model import EvidenceClass, Observation, RuleAssessment, RuleAssessmentStatus, in_scope


def rule_assessments(observation: Observation) -> tuple[RuleAssessment, ...]:
    records = {record.id: record for section in observation.sections for record in section.records}
    declarations = [
        record
        for record in records.values()
        if record.evidence_class == EvidenceClass.DECLARED_RULE
        and record.kind
        in {
            "forbidden_dependency",
            "allowed_dependency",
            "forbidden_construct",
            "external_dependency_scope",
            "complete_assignment",
            "root_layout",
            "complete_external_scope",
            "complete_requires",
            "no_component_cycles",
            "interface_boundary",
            "sibling_isolation",
            "symbol_placement",
            "boundary_types",
        }
    ]
    violations: Counter[str] = Counter(
        rule_id for record in observation.records("violations") or () for rule_id in record.rule_ids
    )
    unknown_records = [
        record for record in observation.records("unknowns") or () if record.rule_ids
    ]
    components = [
        record
        for record in records.values()
        if record.kind in {"component_responsibility", "inside_component_responsibility"}
    ]
    receipts = {
        record.rule_ids[0]
        for record in observation.records("scope_observations") or ()
        if record.kind == "rule_evaluation" and record.rule_ids
    }
    rows: list[RuleAssessment] = []
    for declaration in declarations:
        identifier = declaration.id
        rule_unknowns = [item for item in unknown_records if identifier in item.rule_ids]
        # A boundary limit summarizes the undecidable positions also listed individually.
        limit = next((item for item in rule_unknowns if item.kind == "boundary_type_limit"), None)
        undecided = limit.data.get("undecidable", 0) if limit is not None else len(rule_unknowns)
        if not isinstance(undecided, int):
            undecided = len(rule_unknowns)
        violation_count = violations[identifier]
        declared_only = declaration.kind == "allowed_dependency"
        if declared_only:
            status: RuleAssessmentStatus = "DECLARATION"
            reason = "Permission declaration; it does not evaluate conformance."
        elif violation_count:
            status = "FAIL"
            reason = "The evaluator recorded one or more violations."
        elif identifier not in receipts:
            status = "UNKNOWN"
            reason = "No complete evaluator receipt exists for this rule and scope."
        elif rule_unknowns:
            status = "UNKNOWN"
            reason = "The evaluator left one or more positions undecided."
        else:
            status = "PASS"
            reason = "The evaluator completed this rule's observed scope without violations."
        parent_id = declaration.data.get("parent_id")
        scope = str(parent_id) if isinstance(parent_id, str) else "root"
        parent = records.get(scope)
        if parent is not None:
            scope = parent.title
        rule_components = {
            component.title
            for component in components
            if component.id == parent_id
            or any(
                in_scope(subject, package)
                for subject in declaration.subjects
                for package in component.subjects
            )
        }
        decided_by = declaration.data.get("decided_by", "UNKNOWN")
        rationale = declaration.data.get("rationale", "")
        rows.append(
            RuleAssessment(
                identifier,
                declaration.kind,
                status,
                violation_count,
                undecided,
                decided_by if isinstance(decided_by, str) else "UNKNOWN",
                rationale if isinstance(rationale, str) else "",
                declaration.provenance,
                reason,
                scope,
                tuple(sorted(rule_components)),
            )
        )
    return tuple(sorted(rows, key=lambda item: (item.scope, item.id)))
