# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Record pure UML comparison through the existing Core rule/evidence pipeline."""

import json
from dataclasses import asdict, replace

from archkeel.ir.architecture_graph import GraphComparison
from archkeel.ir.codec import parse_record
from archkeel.ir.model import (
    UML_TARGET_KIND,
    Diagnostic,
    EvidenceClass,
    Observation,
    ObservationResult,
    Record,
    Section,
    UmlEligibility,
    stable_id,
)
from archkeel.ir.source_graph import observed_graph
from archkeel.ir.target_records import recorded_target_graph
from archkeel.ir.trace import validate_evidence_classes

from .uml_compare import compare_graphs


def _records(
    declaration: Record, comparison: GraphComparison, *, partial: bool = False
) -> dict[str, list[Record]]:
    receipts: list[Record] = []
    violations: list[Record] = []
    unknowns: list[Record] = []
    additions: dict[str, list[Record]] = {
        "scope_observations": receipts,
        "violations": violations,
        "unknowns": unknowns,
    }
    common = {
        "area": "uml",
        "subjects": list(declaration.subjects),
        "rule_ids": [declaration.id],
        "provenance": list(declaration.provenance),
    }
    facts = sorted({key for item in comparison.assessments for key in item.fact_ids})
    evidence = sorted({key for item in comparison.assessments for key in item.evidence_ids})
    receipt = parse_record(
        {
            **common,
            "id": stable_id("UML-EVALUATION", declaration.id),
            "evidence_class": "FACT",
            "kind": "rule_evaluation",
            "title": "Independent UML target evaluated",
            "fact_ids": facts,
            "evidence_ids": evidence,
            "data": {
                "scope": "root",
                "assessment_complete": not partial
                and comparison.status != "UNKNOWN"
                and not any(item.status == "UNKNOWN" for item in comparison.assessments),
                "comparison": json.loads(json.dumps(asdict(comparison))),
            },
        }
    )
    receipts.append(receipt)
    for assessment in comparison.assessments:
        if assessment.status == "PASS":
            continue
        section = "violations" if assessment.status == "FAIL" else "unknowns"
        findings: list[Record] = additions[section]
        findings.append(
            parse_record(
                {
                    **common,
                    "id": stable_id("UML-FINDING", declaration.id, assessment.id),
                    "evidence_class": "VIOLATION" if assessment.status == "FAIL" else "UNKNOWN",
                    "kind": "uml_conformance",
                    "title": assessment.reason,
                    "fact_ids": list(assessment.fact_ids),
                    "evidence_ids": list(assessment.evidence_ids),
                    "data": json.loads(json.dumps(asdict(assessment))),
                }
            )
        )
    if not comparison.assessments:
        unknowns.append(
            parse_record(
                {
                    **common,
                    "id": stable_id("UML-EMPTY", declaration.id),
                    "evidence_class": "UNKNOWN",
                    "kind": "uml_conformance",
                    "title": "UML target has no assessable intent",
                    "fact_ids": [],
                    "evidence_ids": [],
                    "data": {"reason": "No entities, relationships or scopes were declared."},
                }
            )
        )
    return additions


def _validate_receipt_identity(declaration: Record, receipts: tuple[Record, ...]) -> None:
    for receipt in receipts:
        if (
            declaration.id in receipt.rule_ids
            and receipt.data.get("comparison") is not None
            and (
                receipt.kind != "rule_evaluation"
                or receipt.rule_ids != (declaration.id,)
                or receipt.id != stable_id("UML-EVALUATION", declaration.id)
            )
        ):
            raise ValueError("UML evaluation identity conflicts with recorded content")


def _replace_evaluations(
    model: Observation,
    declarations: tuple[Record, ...],
    additions: dict[str, list[Record]],
) -> Observation:
    known = {record.id: record for section in model.sections for record in section.records}
    for records in additions.values():
        for record in records:
            previous = known.get(record.id)
            if previous is not None and previous != record:
                raise ValueError("UML evaluation identity conflicts with recorded content")
    placeholders = {
        stable_id("UML-UNKNOWN", path)
        for declaration in declarations
        for path in declaration.provenance
    }
    generated = {record.id for records in additions.values() for record in records}
    sections = tuple(
        replace(
            section,
            records=(
                *(
                    record
                    for record in section.records
                    if record.id not in placeholders | generated
                ),
                *additions.get(section.name, ()),
            ),
        )
        for section in model.sections
    )
    present = {section.name for section in model.sections}
    sections = (
        *sections,
        *(
            Section(name, tuple(records))
            for name, records in additions.items()
            if name not in present and records
        ),
    )
    evaluated = replace(model, sections=sections)
    validate_evidence_classes(evaluated)
    return evaluated


def evaluate_uml(result: ObservationResult) -> ObservationResult:
    model = result.observation
    authenticated = result.uml_eligibility == UmlEligibility.AUTHENTICATED_PARTIAL
    partial = (
        authenticated
        and bool(result.partial_uml_diagnostics)
        and result.diagnostics == result.partial_uml_diagnostics
    )
    if authenticated and not partial:
        return replace(result, uml_eligibility=UmlEligibility.BLOCKED)
    if model is None:
        return replace(result, uml_eligibility=UmlEligibility.BLOCKED)
    if result.diagnostics and not partial:
        return result
    declarations = tuple(
        record
        for record in model.records("declarations") or ()
        if record.kind == UML_TARGET_KIND and record.evidence_class == EvidenceClass.DECLARED_RULE
    )
    if not declarations:
        return result
    try:
        validate_evidence_classes(model)
        observed = observed_graph(model)
        additions: dict[str, list[Record]] = {
            "scope_observations": [],
            "violations": [],
            "unknowns": [],
        }
        partial_receipt = False
        for declaration in declarations:
            _validate_receipt_identity(declaration, model.records("scope_observations") or ())
            compared = compare_graphs(observed, recorded_target_graph(model, declaration))
            if partial and compared.status == "PASS":
                continue
            projected: dict[str, list[Record]] = _records(declaration, compared, partial=partial)
            for name, records in projected.items():
                destination: list[Record] = additions[name]
                destination.extend(records)
            partial_receipt = partial_receipt or bool(projected["scope_observations"])
        if partial and not partial_receipt:
            return replace(result, uml_eligibility=UmlEligibility.BLOCKED)
        return replace(result, observation=_replace_evaluations(model, declarations, additions))
    except ValueError as error:
        return replace(
            result,
            uml_eligibility=UmlEligibility.BLOCKED,
            diagnostics=(
                *result.diagnostics,
                Diagnostic(
                    "parse_error",
                    model.contract.path,
                    f"UML comparison cannot be established: {error}",
                    "Repair the recorded facts or intent and repeat the observation.",
                ),
            ),
        )
