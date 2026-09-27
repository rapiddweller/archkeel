# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Project evaluator receipts and findings into one row per declared rule."""

from collections import Counter
from collections.abc import Mapping

from .model import (
    RULE_KINDS,
    EvidenceClass,
    Observation,
    RuleAssessment,
    RuleAssessmentStatus,
    in_scope,
)


def rule_assessments(
    observation: Observation,
    *,
    undecided_by_rule: Mapping[str, int],
    complete: bool = True,
) -> tuple[RuleAssessment, ...]:
    records = {record.id: record for section in observation.sections for record in section.records}
    declarations = [
        record
        for record in records.values()
        if record.evidence_class == EvidenceClass.DECLARED_RULE and record.kind in RULE_KINDS
    ]
    violations: Counter[str] = Counter(
        rule_id for record in observation.records("violations") or () for rule_id in record.rule_ids
    )
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
        undecided = undecided_by_rule.get(identifier, 0)
        violation_count = violations[identifier]
        declared_only = declaration.kind == "allowed_dependency"
        if declared_only:
            status: RuleAssessmentStatus = "DECLARATION"
            reason = "Permission declaration; it does not evaluate conformance."
        elif violation_count:
            status = "FAIL"
            reason = "The evaluator recorded one or more violations."
        elif not complete:
            status = "UNKNOWN"
            reason = "The observation is incomplete; a complete evaluator scope is not proven."
        elif identifier not in receipts:
            status = "UNKNOWN"
            reason = "No complete evaluator receipt exists for this rule and scope."
        elif undecided:
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
