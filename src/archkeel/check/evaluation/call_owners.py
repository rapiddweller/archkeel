# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Evaluate caller permissions over explicit source binding proofs."""

from collections.abc import Sequence

from archkeel.ir.facts import (
    CallBinding,
    CallBindingOrigin,
    EvidenceClass,
    call_binding,
    in_scope,
    stable_id,
)
from archkeel.ir.facts_codec import RawData, RawRecord, classified, parse_record
from archkeel.ir.model import ArchitectureContract, CallOwnerRule

from .rule_support import _rule_evaluation_receipt


def _target_binding_static(target: RawRecord, symbols: Sequence[RawRecord]) -> bool:
    data = target["data"]
    if target["kind"] == "class":
        return data.get("source_binding_unique") is True and (
            data.get("class_header_static") is True
            or data.get("source_class_header_static") is True
            or data.get("typed_dict_header_static") is True
        )
    if data.get("decorators"):
        return False
    if target["kind"] == "method":
        parent = data.get("parent")
        owners = [r for r in symbols if r["data"]["qualified_name"] == parent]
        if len(owners) != 1 or owners[0]["kind"] != "class":
            return False
        owner_data: dict[str, object] = owners[0]["data"]
        return (
            owner_data.get("source_binding_unique") is True
            and owner_data.get("source_member_binding_static") is True
        )
    return data.get("source_binding_unique") is True and data.get("source_binding_static") is True


def _constructed_target_binding_static(
    target: RawRecord, calls: Sequence[RawRecord], symbols: Sequence[RawRecord]
) -> bool:
    """Use an observed constructed call only when both linked class owners are static."""
    if target["kind"] != "method":
        return False
    target_data: RawData = target["data"]
    parent = target_data.get("parent")
    if not isinstance(parent, str):
        return False
    method_owners = _class_symbols(parent, symbols)
    if len(method_owners) != 1 or not _owner_static(method_owners[0]):
        return False
    target_name = target_data.get("qualified_name")
    for call in calls:
        parsed_call = parse_record(call)
        call_data = parsed_call.data
        binding = call_binding(call_data.get("call_binding"))
        if binding is None or binding.origin is not CallBindingOrigin.CONSTRUCTED_RECEIVER:
            continue
        proof = binding.proof
        constructed_name = proof.get("target") if proof is not None else None
        if not isinstance(constructed_name, str):
            continue
        constructed_owners = _class_symbols(constructed_name, symbols)
        if (
            binding.target == target_name
            and proof is not None
            and proof.get("kind") == "construction"
            and len(constructed_owners) == 1
            and _owner_static(constructed_owners[0])
        ):
            return True
    return False


def _class_symbols(name: str, symbols: Sequence[RawRecord]) -> list[RawRecord]:
    return [
        symbol
        for symbol in symbols
        if symbol["kind"] == "class" and symbol["data"]["qualified_name"] == name
    ]


def _owner_static(symbol: RawRecord) -> bool:
    data: RawData = symbol["data"]
    return (
        data.get("source_binding_unique") is True and data.get("source_member_owner_static") is True
    )


def _native_target_witnessed(target: str, calls: Sequence[RawRecord]) -> bool:
    origins = {
        CallBindingOrigin.NATIVE,
        CallBindingOrigin.NATIVE_RECEIVER,
        CallBindingOrigin.CONSTRUCTOR,
    }
    for call in calls:
        parsed_call = parse_record(call)
        call_data = parsed_call.data
        binding = call_binding(call_data.get("call_binding"))
        proof = binding.proof if binding is not None else None
        if (
            binding is None
            or binding.target != target
            or binding.origin not in origins
            or proof is None
            or proof.get("target") != target
            or proof.get("kind") not in {"provider_member", "native_descriptor"}
        ):
            continue
        return True
    return False


def _limit(rule: CallOwnerRule, scope: str, reason: str, facts: Sequence[RawRecord]) -> RawRecord:
    return classified(
        item_id=stable_id("UNKNOWN-CALL-OWNER", scope, rule.id, reason, *(r["id"] for r in facts)),
        evidence_class=EvidenceClass.UNKNOWN,
        area="calls",
        kind="call_owner_limit",
        title=reason,
        subjects=[rule.source, rule.target],
        rule_ids=[rule.id],
        fact_ids=[r["id"] for r in facts],
        evidence_ids=sorted({e for r in facts for e in r["evidence_ids"]}),
        data={"scope": scope, "reason": reason},
    )


def _rule_target_proven(
    rule: CallOwnerRule,
    targets: Sequence[RawRecord],
    calls: Sequence[RawRecord],
    symbols: Sequence[RawRecord],
) -> bool:
    if not targets:
        return _native_target_witnessed(rule.target, calls)
    return len(targets) == 1 and (
        _target_binding_static(targets[0], symbols)
        or _constructed_target_binding_static(targets[0], calls, symbols)
    )


def call_owner_results(
    contract: ArchitectureContract,
    *,
    scope: str,
    calls: Sequence[RawRecord],
    modules: Sequence[RawRecord],
    symbols: Sequence[RawRecord],
    complete: bool,
    bindings_measured: bool,
    blank_modules: frozenset[str],
    source_modules: frozenset[str] | None = None,
) -> tuple[list[RawRecord], list[RawRecord], list[RawRecord]]:
    violations: list[RawRecord] = []
    limits: list[RawRecord] = []
    receipts: list[RawRecord] = []
    source_records = [
        r
        for r in modules
        if source_modules is None or r["data"]["qualified_name"] in source_modules
    ] + [r for r in symbols if source_modules is None or r["data"]["module"] in source_modules]
    for rule in contract.rules:
        if not isinstance(rule, CallOwnerRule):
            continue
        subjects = [
            r
            for r in source_records
            if in_scope(r["data"]["qualified_name"], rule.source)
            and r["data"]["qualified_name"] not in blank_modules
        ]
        selected = [
            r
            for r in calls
            if (source_modules is None or r["data"]["source_module"] in source_modules)
            and in_scope(r["data"]["source_scope"], rule.source)
        ]
        targets = [
            r
            for r in symbols
            if r["data"]["qualified_name"] == rule.target
            and r["kind"] in {"class", "function", "method"}
        ]
        rule_limits: list[RawRecord] = []
        target_proven = _rule_target_proven(rule, targets, selected, symbols)
        if not subjects or not target_proven or not complete or not bindings_measured:
            rule_limits.append(
                _limit(
                    rule,
                    scope,
                    "Observed source, target and complete call-binding consideration are required",
                    [*subjects, *targets],
                )
            )
        for call in selected:
            data = call["data"]
            if any(
                in_scope(data["source_scope"], allowed) for allowed in rule.allowed_sources
            ) or any(
                exact in {data["source_module"], data["source_scope"]}
                for exact in rule.exact_sources
            ):
                continue
            if not bindings_measured:
                continue
            parsed_call = parse_record(call)
            binding = call_binding(parsed_call.data.get("call_binding"))
            if binding is None:
                rule_limits.append(
                    _limit(rule, scope, "The call has no proven disjoint or exact target", [call])
                )
            elif binding.target == rule.target:
                violations.append(_violation(rule, scope, call, binding))
        limits.extend(rule_limits)
        if not rule_limits:
            receipts.append(_rule_evaluation_receipt(rule, scope, [*subjects, *targets, *selected]))
    return violations, limits, receipts


def _violation(rule: CallOwnerRule, scope: str, call: RawRecord, binding: CallBinding) -> RawRecord:
    data = call["data"]
    return classified(
        item_id=stable_id("VIOL-CALL-OWNER", scope, rule.id, call["id"]),
        evidence_class=EvidenceClass.VIOLATION,
        area="calls",
        kind="call_owner",
        title=f"{data['source_scope']} invokes {rule.target} outside its owner",
        subjects=[data["source_scope"], rule.target],
        evidence_ids=list(binding.evidence_ids),
        fact_ids=[call["id"]],
        rule_ids=[rule.id],
        provenance=list(rule.provenance),
        data={
            "source_module": data["source_module"],
            "target": rule.target,
            "binding_origin": binding.origin,
            "scope": scope,
        },
    )
