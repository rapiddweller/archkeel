# Codekeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Validate the rule, fact, and source-evidence chain of reported violations."""

from pathlib import Path

from .model import Evidence, EvidenceClass, Observation, Record


def validate_evidence_classes(model: Observation) -> None:
    records: dict[str, Record] = {}
    evidence_ids = {item.id for item in model.evidence}
    for section in model.sections:
        for item in section.records:
            if not item.id:
                raise ValueError(f"{section.name} contains a record without a stable ID")
            if item.id in records:
                raise ValueError(f"duplicate ArchitectureIR ID: {item.id}")
            records[item.id] = item
            if item.evidence_class == EvidenceClass.HYPOTHESIS:
                raise ValueError(f"analyzer must not generate HYPOTHESIS items ({item.id})")
            missing_evidence = set(item.evidence_ids) - evidence_ids
            if missing_evidence:
                raise ValueError(
                    f"{section.name}:{item.id} references missing evidence "
                    f"{sorted(missing_evidence)}"
                )
    for item in records.values():
        for rule_id in item.rule_ids:
            referenced = records.get(rule_id)
            if referenced is None or referenced.evidence_class != EvidenceClass.DECLARED_RULE:
                raise ValueError(f"{item.id} references non-rule {rule_id}")
        for fact_id in item.fact_ids:
            referenced = records.get(fact_id)
            if referenced is None or referenced.evidence_class != EvidenceClass.FACT:
                raise ValueError(f"{item.id} references non-fact {fact_id}")
        if item.evidence_class == EvidenceClass.DECLARED_RULE and not item.provenance:
            raise ValueError(f"declared rule {item.id} lacks repository provenance")
        if item.evidence_class == EvidenceClass.VIOLATION and (
            not item.rule_ids or not item.fact_ids
        ):
            raise ValueError(f"violation {item.id} must reference both a rule and a fact")


def trace_valid_violations(model: Observation) -> tuple[Record, ...]:
    records = {item.id: item for section in model.sections for item in section.records}
    evidence = {item.id: item for item in model.evidence}
    return tuple(
        violation
        for violation in model.records("violations") or ()
        if _has_complete_violation_trace(violation, records, evidence)
    )


def _has_complete_violation_trace(
    violation: Record, records: dict[str, Record], evidence: dict[str, Evidence]
) -> bool:
    if (
        violation.evidence_class != EvidenceClass.VIOLATION
        or not violation.rule_ids
        or not violation.fact_ids
    ):
        return False
    for rule_id in violation.rule_ids:
        rule = records.get(rule_id)
        if (
            rule is None
            or rule.evidence_class != EvidenceClass.DECLARED_RULE
            or not rule.provenance
            or not all(rule.provenance)
        ):
            return False
    for fact_id in violation.fact_ids:
        fact = records.get(fact_id)
        if fact is None or fact.evidence_class != EvidenceClass.FACT or not fact.evidence_ids:
            return False
        if any(not _valid_source_evidence(evidence.get(key)) for key in fact.evidence_ids):
            return False
    return True


def _valid_source_evidence(value: Evidence | None) -> bool:
    if (
        value is None
        or not value.file
        or Path(value.file).is_absolute()
        or ".." in Path(value.file).parts
    ):
        return False
    return value.line > 0 and bool(value.excerpt)
