# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Evaluate policies over explicit actuals bound to observed formals."""

from collections.abc import Sequence

from archkeel.ir.facts import (
    CallArgumentValueKind,
    CallBinding,
    EvidenceClass,
    RecordData,
    call_arguments,
    call_binding,
    in_scope,
    stable_id,
)
from archkeel.ir.facts_codec import RawRecord, classified, parse_record
from archkeel.ir.model import ArchitectureContract, ForbiddenCallArgumentRule

from .call_arguments import bind_call_arguments
from .call_owners import _constructed_target_binding_static, _target_binding_static
from .rule_support import _rule_evaluation_receipt

_BOUND_RECEIVER_ORIGINS = frozenset(
    {"declared_receiver", "stored_receiver", "constructed_receiver", "native_receiver"}
)


def call_argument_results(
    contract: ArchitectureContract,
    *,
    scope: str,
    calls: Sequence[RawRecord],
    modules: Sequence[RawRecord],
    symbols: Sequence[RawRecord],
    complete: bool,
    bindings_measured: bool,
    arguments_measured: bool,
    blank_modules: frozenset[str],
    source_modules: frozenset[str] | None = None,
) -> tuple[list[RawRecord], list[RawRecord], list[RawRecord]]:
    violations: list[RawRecord] = []
    limits: list[RawRecord] = []
    receipts: list[RawRecord] = []
    for rule in contract.rules:
        if not isinstance(rule, ForbiddenCallArgumentRule):
            continue
        found, unknown, proven = _rule_results(
            rule,
            scope=scope,
            calls=calls,
            modules=modules,
            symbols=symbols,
            complete=complete,
            bindings_measured=bindings_measured,
            arguments_measured=arguments_measured,
            blank_modules=blank_modules,
            source_modules=source_modules,
        )
        violations.extend(found)
        limits.extend(unknown)
        receipts.extend(proven)
    return violations, limits, receipts


def _rule_results(
    rule: ForbiddenCallArgumentRule,
    *,
    scope: str,
    calls: Sequence[RawRecord],
    modules: Sequence[RawRecord],
    symbols: Sequence[RawRecord],
    complete: bool,
    bindings_measured: bool,
    arguments_measured: bool,
    blank_modules: frozenset[str],
    source_modules: frozenset[str] | None,
) -> tuple[list[RawRecord], list[RawRecord], list[RawRecord]]:
    source_records = [
        record
        for record in modules
        if source_modules is None or record["data"]["qualified_name"] in source_modules
    ] + [
        record
        for record in symbols
        if source_modules is None or record["data"]["module"] in source_modules
    ]
    subjects = [
        record
        for record in source_records
        if in_scope(record["data"]["qualified_name"], rule.source)
        and record["data"]["qualified_name"] not in blank_modules
    ]
    selected = [
        call
        for call in calls
        if (source_modules is None or call["data"]["source_module"] in source_modules)
        and in_scope(call["data"]["source_scope"], rule.source)
    ]
    targets = [
        record
        for record in symbols
        if record["data"]["qualified_name"] == rule.target
        and record["kind"] in {"class", "function", "method"}
    ]
    target_proven = len(targets) == 1 and (
        _target_binding_static(targets[0], symbols)
        or _constructed_target_binding_static(targets[0], calls, symbols)
    )
    rule_limits = _rule_limits(
        rule,
        scope,
        subjects,
        targets,
        complete,
        bindings_measured,
        arguments_measured,
        target_proven,
    )
    signature = parse_record(targets[0]).data if target_proven else None
    if target_proven and _signature_available(signature):
        if not _signature_has_parameter(signature, rule.parameter):
            rule_limits.append(
                _limit(
                    rule,
                    scope,
                    "The selected formal parameter is absent from the signature",
                    targets,
                )
            )
            signature = None
    elif target_proven:
        rule_limits.append(
            _limit(rule, scope, "The selected target has no proven callable signature", targets)
        )
    found, unknown = _evaluate_calls(rule, scope, selected, targets, target_proven, signature)
    rule_limits.extend(unknown)
    receipts = (
        [_rule_evaluation_receipt(rule, scope, [*subjects, *targets, *selected])]
        if not rule_limits
        else []
    )
    return found, rule_limits, receipts


def _rule_limits(
    rule: ForbiddenCallArgumentRule,
    scope: str,
    subjects: Sequence[RawRecord],
    targets: Sequence[RawRecord],
    complete: bool,
    bindings_measured: bool,
    arguments_measured: bool,
    target_proven: bool,
) -> list[RawRecord]:
    if subjects and target_proven and complete and bindings_measured and arguments_measured:
        return []
    return [
        _limit(
            rule,
            scope,
            "Observed source, target, signatures and complete argument consideration are required",
            [*subjects, *targets],
        )
    ]


def _evaluate_calls(
    rule: ForbiddenCallArgumentRule,
    scope: str,
    calls: Sequence[RawRecord],
    targets: Sequence[RawRecord],
    target_proven: bool,
    signature: RecordData | None,
) -> tuple[list[RawRecord], list[RawRecord]]:
    violations: list[RawRecord] = []
    limits: list[RawRecord] = []
    parameter = rule.parameter.lstrip("*")
    for call in calls:
        parsed = parse_record(call)
        binding = call_binding(parsed.data.get("call_binding"))
        actuals = call_arguments(parsed.data.get("call_arguments"))
        if binding is None or actuals is None:
            limits.append(
                _limit(rule, scope, "Call target or actual arguments are unproven", [call])
            )
            continue
        if binding.target != rule.target:
            continue
        if not target_proven or signature is None:
            continue
        bound = bind_call_arguments(
            signature,
            actuals,
            bound_receiver=binding.origin.value in _BOUND_RECEIVER_ORIGINS,
        )
        if bound is None:
            limits.append(
                _limit(
                    rule,
                    scope,
                    "Actual arguments do not bind to the observed signature",
                    [call, *targets],
                )
            )
            continue
        indexes = next(
            (actuals for formal, actuals in bound.by_parameter if formal == parameter), ()
        )
        for index in indexes:
            argument = actuals[index]
            if argument.value_kind is CallArgumentValueKind.STRING_LITERAL:
                violations.append(_violation(rule, scope, call, binding, argument.evidence_ids))
    return violations, limits


def _limit(
    rule: ForbiddenCallArgumentRule, scope: str, reason: str, facts: Sequence[RawRecord]
) -> RawRecord:
    return classified(
        item_id=stable_id(
            "UNKNOWN-CALL-ARGUMENT", scope, rule.id, reason, *(r["id"] for r in facts)
        ),
        evidence_class=EvidenceClass.UNKNOWN,
        area="calls",
        kind="call_argument_limit",
        title=reason,
        subjects=[rule.source, rule.target, rule.parameter],
        rule_ids=[rule.id],
        fact_ids=[record["id"] for record in facts],
        evidence_ids=sorted(
            {evidence_id for record in facts for evidence_id in record["evidence_ids"]}
        ),
        data={"scope": scope, "reason": reason, "parameter": rule.parameter},
    )


def _signature_available(signature: RecordData | None) -> bool:
    parameters = signature.get("parameters") if signature is not None else None
    return isinstance(parameters, tuple) and all(
        isinstance(parameter, RecordData)
        and isinstance(parameter.get("name"), str)
        and isinstance(parameter.get("kind"), str)
        and parameter.get("default_known") is True
        for parameter in parameters
    )


def _signature_has_parameter(signature: RecordData | None, name: str) -> bool:
    parameters = signature.get("parameters") if signature is not None else None
    if not isinstance(parameters, tuple):
        return False
    for parameter in parameters:
        parameter_name = parameter.get("name") if isinstance(parameter, RecordData) else None
        if isinstance(parameter_name, str) and parameter_name in {name, f"*{name}", f"**{name}"}:
            return True
    return False


def _violation(
    rule: ForbiddenCallArgumentRule,
    scope: str,
    call: RawRecord,
    binding: CallBinding,
    evidence_ids: Sequence[str],
) -> RawRecord:
    data = call["data"]
    return classified(
        item_id=stable_id("VIOL-CALL-ARGUMENT", scope, rule.id, call["id"], rule.parameter),
        evidence_class=EvidenceClass.VIOLATION,
        area="calls",
        kind="forbidden_call_argument",
        title=f"{data['source_scope']} supplies a string literal to {rule.target}.{rule.parameter}",
        subjects=[data["source_scope"], rule.target, rule.parameter],
        evidence_ids=list(evidence_ids),
        fact_ids=[call["id"]],
        rule_ids=[rule.id],
        provenance=list(rule.provenance),
        data={
            "source_module": data["source_module"],
            "target": rule.target,
            "parameter": rule.parameter,
            "binding_origin": binding.origin.value,
            "scope": scope,
        },
    )
