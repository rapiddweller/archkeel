# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Evaluate one declared physical line limit over authenticated repository text facts."""

from archkeel.ir.codec_repository_files import repository_inventory_payload
from archkeel.ir.facts import EvidenceClass, SourceInfo, stable_id
from archkeel.ir.facts_codec import RawRecord, classified, parse_record
from archkeel.ir.repository_file_proof import (
    repository_file_binding_id,
    repository_inventory_complete,
)
from archkeel.ir.repository_files import (
    MaxFileLinesRule,
    RepositoryFileFact,
    RepositoryFileInventory,
    repository_line_overflows,
)


def repository_file_results(
    rule: MaxFileLinesRule,
    inventory: RepositoryFileInventory | None,
    *,
    scope: str,
    source: SourceInfo,
    contract_digest: str,
    declaration: RawRecord,
) -> tuple[list[RawRecord], list[RawRecord], list[RawRecord]]:
    violations: list[RawRecord] = []
    limits: list[RawRecord] = []
    receipts: list[RawRecord] = []
    if inventory is None or inventory.selection != rule.selection:
        limits.append(_limit(rule, scope, "missing_inventory", []))
        return violations, limits, receipts
    if inventory.snapshot_head != source.git_head or inventory.snapshot_dirty != source.dirty:
        return [], [_limit(rule, scope, "snapshot_mismatch", [])], []
    inventory_id = stable_id("REPOSITORY-FILE-INVENTORY", inventory.digest)
    witnesses = (
        *inventory.files,
        *inventory.excluded_files,
        *inventory.manifest_inputs,
        *inventory.classifications,
    )
    evidence_ids = sorted({item.evidence_id for item in witnesses})
    receipts.append(
        classified(
            item_id=inventory_id,
            evidence_class=EvidenceClass.FACT,
            area="repository_files",
            kind="repository_file_inventory",
            title="Authenticated repository text inventory",
            subjects=list(inventory.selected_paths),
            evidence_ids=evidence_ids,
            data=repository_inventory_payload(inventory),
        )
    )
    for item in repository_line_overflows(inventory, rule.max_lines):
        violations.append(_violation(rule, scope, item, inventory_id))
    complete = repository_inventory_complete(inventory)
    for gap in inventory.gaps:
        limits.append(_limit(rule, scope, f"{gap.path}: {gap.reason}", [inventory_id]))
    if not complete and not limits:
        limits.append(_limit(rule, scope, "incomplete_inventory", [inventory_id]))
    declared = parse_record(declaration)
    receipts.append(
        classified(
            item_id=stable_id("RULE-EVALUATION", scope, rule.id),
            evidence_class=EvidenceClass.FACT,
            area="repository_files",
            kind="rule_evaluation",
            title=f"{rule.id} evaluator completed",
            subjects=list(inventory.selected_paths),
            rule_ids=[rule.id],
            fact_ids=[inventory_id],
            evidence_ids=evidence_ids,
            data={
                "scope": scope,
                "assessment_complete": complete,
                "repository_file_binding": repository_file_binding_id(
                    declared, inventory, source, contract_digest
                ),
            },
        )
    )
    return violations, limits, receipts


def _limit(rule: MaxFileLinesRule, scope: str, reason: str, facts: list[str]) -> RawRecord:
    return classified(
        item_id=stable_id("UNKNOWN-REPOSITORY-FILES", scope, rule.id, reason),
        evidence_class=EvidenceClass.UNKNOWN,
        area="repository_files",
        kind="repository_file_limit",
        title=reason,
        subjects=[item.root for item in rule.selection.scopes],
        rule_ids=[rule.id],
        fact_ids=facts,
        data={"scope": scope, "reason": reason},
    )


def _violation(
    rule: MaxFileLinesRule, scope: str, item: RepositoryFileFact, inventory_id: str
) -> RawRecord:
    return classified(
        item_id=stable_id("MAX-FILE-LINES", scope, rule.id, item.path),
        evidence_class=EvidenceClass.VIOLATION,
        area="repository_files",
        kind="max_file_lines",
        title=f"{item.path} has {item.physical_lines} lines (maximum {rule.max_lines})",
        subjects=[item.path],
        rule_ids=[rule.id],
        fact_ids=[inventory_id],
        evidence_ids=[item.evidence_id],
        data={
            "file": item.path,
            "physical_lines": item.physical_lines,
            "max_lines": rule.max_lines,
        },
    )
