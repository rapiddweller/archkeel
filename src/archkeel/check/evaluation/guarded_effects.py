# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Evaluate bounded, source-certified guarded effect paths."""

from collections.abc import Sequence
from importlib import import_module

from archkeel.ir.facts import (
    ConditionSelectorKind,
    EvidenceClass,
    call_binding,
    guarded_effect,
    in_scope,
    stable_id,
)
from archkeel.ir.facts_codec import RawRecord, classified, parse_record
from archkeel.ir.model import ArchitectureContract, ForbiddenEffectUnderConditionRule

from .rule_support import _rule_evaluation_receipt


def _limit(
    rule: ForbiddenEffectUnderConditionRule,
    scope: str,
    reason: str,
    facts: Sequence[RawRecord],
) -> RawRecord:
    return classified(
        item_id=stable_id(
            "UNKNOWN-GUARDED-EFFECT", scope, rule.id, reason, *(row["id"] for row in facts)
        ),
        evidence_class=EvidenceClass.UNKNOWN,
        area="calls",
        kind="guarded_effect_limit",
        title=reason,
        subjects=[rule.source, rule.target, rule.condition.owner, rule.condition.name],
        rule_ids=[rule.id],
        fact_ids=[row["id"] for row in facts],
        evidence_ids=sorted({evidence for row in facts for evidence in row["evidence_ids"]}),
        data={"scope": scope, "reason": reason},
    )


def _declared_condition(
    rule: ForbiddenEffectUnderConditionRule, symbols: Sequence[RawRecord]
) -> bool:
    matches = [row for row in symbols if row["data"]["qualified_name"] == rule.condition.owner]
    if len(matches) != 1:
        return False
    data = matches[0]["data"]
    if rule.condition.kind is ConditionSelectorKind.PARAMETER:
        if matches[0]["kind"] not in {"function", "method"}:
            return False
        parameters = data.get("parameters")
        return isinstance(parameters, (tuple, list)) and any(
            getattr(parameter, "get", lambda *_: None)("name") == rule.condition.name
            and getattr(parameter, "get", lambda *_: None)("annotation") == "bool"
            for parameter in parameters
        )
    if matches[0]["kind"] != "class":
        return False
    declarations = data.get("guard_boolean_members")
    return isinstance(declarations, tuple | list) and any(
        isinstance(declaration, dict)
        and declaration.get("name") == rule.condition.name
        and isinstance(declaration.get("evidence_ids"), tuple | list)
        and bool(declaration["evidence_ids"])
        for declaration in declarations
    )


def _helper_effects(
    rule: ForbiddenEffectUnderConditionRule,
    scope: str,
    caller: RawRecord,
    caller_proof: object,
    helper_fact: object,
    *,
    calls: Sequence[RawRecord],
    symbols: Sequence[RawRecord],
) -> tuple[list[RawRecord], list[RawRecord], list[RawRecord]]:
    """Substitute one private helper through the shared #614 binder."""
    from archkeel.ir.facts import GuardedEffectEvidence, GuardHelperBinding

    if not isinstance(caller_proof, GuardedEffectEvidence) or not isinstance(
        helper_fact, GuardHelperBinding
    ):
        return [], [_limit(rule, scope, "The helper path is malformed", [caller])], []
    if caller_proof.condition_value is False:
        return [], [], []
    helper_symbols = [
        row for row in symbols if row["data"].get("qualified_name") == helper_fact.target
    ]
    if len(helper_symbols) != 1:
        return (
            [],
            [_limit(rule, scope, "The private helper declaration is ambiguous", [caller])],
            [],
        )
    helper = helper_symbols[0]
    helper_data = helper["data"]
    visibility = helper_data.get("visibility_detail")
    if (
        helper["kind"] != "function"
        or not isinstance(visibility, dict)
        or visibility.get("kind") != "private"
        or helper_data.get("source_binding_unique") is not True
        or helper_data.get("source_binding_static") is not True
        or helper_data.get("decorators")
    ):
        return (
            [],
            [_limit(rule, scope, "The helper is not a unique private function", [caller, helper])],
            [helper],
        )
    parsed_caller = parse_record(caller)
    try:
        facts_api = import_module("archkeel.ir.facts")
        binder_api = import_module("archkeel.check.evaluation.call_arguments")
        actuals = facts_api.call_arguments(parsed_caller.data.get("call_arguments"))
        bound = (
            binder_api.bind_call_arguments(parse_record(helper).data, actuals, bound_receiver=False)
            if actuals is not None
            else None
        )
    except (ImportError, AttributeError, ValueError):
        bound = None
        actuals = None
    if bound is None:
        return (
            [],
            [
                _limit(
                    rule,
                    scope,
                    "Helper actuals do not bind to its observed signature",
                    [caller, helper],
                )
            ],
            [helper],
        )
    actual_tokens = {argument.argument_index: argument for argument in helper_fact.arguments}
    call_actuals = {index: argument for index, argument in enumerate(actuals)}
    helper_calls = [row for row in calls if row["data"]["source_scope"] == helper_fact.target]
    violations: list[RawRecord] = []
    limits: list[RawRecord] = []
    evidence_facts: list[RawRecord] = [helper]
    effect_seen = False
    for inner_call in helper_calls:
        inner_parsed = parse_record(inner_call)
        inner_binding = call_binding(inner_parsed.data.get("call_binding"))
        if inner_binding is None:
            limits.append(
                _limit(
                    rule,
                    scope,
                    "The helper body contains an unbound call",
                    [caller, helper, inner_call],
                )
            )
            evidence_facts.append(inner_call)
            continue
        if inner_binding.target != rule.target:
            if inner_parsed.data.get("guarded_effect"):
                limits.append(
                    _limit(
                        rule,
                        scope,
                        "Helper chains and recursion are unsupported",
                        [caller, helper, inner_call],
                    )
                )
                evidence_facts.append(inner_call)
            continue
        effect_seen = True
        evidence_facts.append(inner_call)
        proofs_raw = inner_parsed.data.get("guarded_effect", ())
        if not isinstance(proofs_raw, tuple):
            limits.append(
                _limit(
                    rule,
                    scope,
                    "The helper effect has no typed path inventory",
                    [caller, helper, inner_call],
                )
            )
            continue
        inner_proofs = [guarded_effect(item) for item in proofs_raw]
        parameters = helper_data.get("parameters")
        helper_parameters = parameters if isinstance(parameters, tuple | list) else ()
        matched = [
            item
            for item in inner_proofs
            if item.condition.kind is ConditionSelectorKind.PARAMETER
            and item.condition.owner == helper_fact.target
            and any(
                isinstance(parameter, dict)
                and parameter.get("name") == item.condition.name
                and parameter.get("annotation") == "bool"
                for parameter in helper_parameters
            )
        ]
        if not matched:
            limits.append(
                _limit(
                    rule,
                    scope,
                    "The helper effect lacks a bound Boolean path",
                    [caller, helper, inner_call],
                )
            )
            continue
        for inner_proof in matched:
            indexes = dict(bound.by_parameter).get(inner_proof.condition.name)
            if indexes is None or len(indexes) != 1:
                limits.append(
                    _limit(
                        rule,
                        scope,
                        "The helper condition has no unique bound actual",
                        [caller, helper, inner_call],
                    )
                )
                continue
            index = indexes[0]
            token = actual_tokens.get(index)
            actual = call_actuals.get(index)
            if token is None or actual is None or token.evidence_ids != actual.evidence_ids:
                limits.append(
                    _limit(
                        rule,
                        scope,
                        "The helper actual evidence is incomplete",
                        [caller, helper, inner_call],
                    )
                )
                continue
            if not inner_proof.complete:
                limits.append(
                    _limit(
                        rule,
                        scope,
                        "The helper effect path is incomplete",
                        [caller, helper, inner_call],
                    )
                )
                continue
            substituted: bool | None
            if token.token_kind == "boolean_literal":
                substituted = token.token_value
            elif token.token_kind in {"condition", "not_condition"}:
                selector = token.condition
                if (
                    selector is None
                    or selector.kind is not rule.condition.kind
                    or selector.owner != rule.condition.owner
                    or selector.name != rule.condition.name
                ):
                    limits.append(
                        _limit(
                            rule,
                            scope,
                            "The helper actual refers to another condition",
                            [caller, helper, inner_call],
                        )
                    )
                    continue
                substituted = (
                    True if caller_proof.condition_value is None else caller_proof.condition_value
                )
                if token.token_kind == "not_condition" and substituted is not None:
                    substituted = not substituted
            else:
                limits.append(
                    _limit(
                        rule,
                        scope,
                        "The helper condition actual is not statically bounded",
                        [caller, helper, inner_call],
                    )
                )
                continue
            path_value = inner_proof.condition_value
            if path_value is None:
                violation = substituted is not False
            elif substituted is None:
                limits.append(
                    _limit(
                        rule,
                        scope,
                        "The helper path polarity cannot be substituted",
                        [caller, helper, inner_call],
                    )
                )
                continue
            else:
                violation = substituted is path_value
            if violation:
                violations.append(
                    classified(
                        item_id=stable_id(
                            "VIOL-GUARDED-HELPER", scope, rule.id, caller["id"], inner_call["id"]
                        ),
                        evidence_class=EvidenceClass.VIOLATION,
                        area="calls",
                        kind="forbidden_effect_under_condition",
                        title=(
                            f"{rule.target} can execute through {helper_fact.target} "
                            "while the condition is true"
                        ),
                        subjects=[caller["data"]["source_scope"], helper_fact.target, rule.target],
                        rule_ids=[rule.id],
                        fact_ids=[caller["id"], helper["id"], inner_call["id"]],
                        evidence_ids=sorted(
                            {
                                *caller_proof.condition_evidence_ids,
                                *caller_proof.path_evidence_ids,
                                *caller_proof.effect_binding_evidence_ids,
                                *inner_proof.condition_evidence_ids,
                                *inner_proof.path_evidence_ids,
                                *inner_proof.effect_binding_evidence_ids,
                                *helper_fact.evidence_ids,
                                *token.evidence_ids,
                                *inner_binding.evidence_ids,
                            }
                        ),
                        provenance=list(rule.provenance),
                        data={
                            "scope": scope,
                            "source_module": caller["data"]["source_module"],
                            "target": rule.target,
                            "condition_owner": rule.condition.owner,
                            "condition_name": rule.condition.name,
                            "condition_value": True,
                            "helper": helper_fact.target,
                        },
                    )
                )
    if not effect_seen and not limits:
        limits.append(
            _limit(
                rule, scope, "The helper body has no complete effect inventory", [caller, helper]
            )
        )
    return violations, limits, evidence_facts


def guarded_effect_results(
    contract: ArchitectureContract,
    *,
    scope: str,
    calls: Sequence[RawRecord],
    modules: Sequence[RawRecord],
    symbols: Sequence[RawRecord],
    complete: bool,
    bindings_measured: bool,
    paths_measured: bool = True,
    source_modules: frozenset[str] | None = None,
) -> tuple[list[RawRecord], list[RawRecord], list[RawRecord]]:
    """Return violations, undecided paths and replay receipts for selected effect rules."""
    violations: list[RawRecord] = []
    limits: list[RawRecord] = []
    receipts: list[RawRecord] = []
    scoped_modules = [
        row
        for row in modules
        if source_modules is None or row["data"]["qualified_name"] in source_modules
    ]
    scoped_symbols = [
        row for row in symbols if source_modules is None or row["data"]["module"] in source_modules
    ]
    for rule in contract.rules:
        if not isinstance(rule, ForbiddenEffectUnderConditionRule):
            continue
        condition_scopes = {rule.condition.owner}
        if rule.condition.kind is ConditionSelectorKind.MEMBER:
            condition_scopes.update(
                row["data"]["qualified_name"]
                for row in scoped_symbols
                if row["kind"] == "method" and row["data"].get("parent") == rule.condition.owner
            )
        subjects = [
            row
            for row in (*scoped_modules, *scoped_symbols)
            if in_scope(row["data"]["qualified_name"], rule.source)
        ]
        selected = [
            row
            for row in calls
            if (source_modules is None or row["data"]["source_module"] in source_modules)
            and in_scope(row["data"]["source_scope"], rule.source)
        ]
        rule_limits: list[RawRecord] = []
        receipt_facts: list[RawRecord] = [*subjects, *selected]
        if not subjects:
            rule_limits.append(
                _limit(rule, scope, "The selected source scope was not observed", [])
            )
        if not _declared_condition(rule, scoped_symbols):
            rule_limits.append(
                _limit(
                    rule,
                    scope,
                    "The selected Boolean condition declaration is not proven",
                    subjects,
                )
            )
        if not complete or not bindings_measured or not paths_measured:
            rule_limits.append(
                _limit(
                    rule,
                    scope,
                    "Complete source and call-binding inventories are required",
                    subjects,
                )
            )
        for call in selected:
            data = call["data"]
            parsed_call = parse_record(call)
            raw_proofs = parsed_call.data.get("guarded_effect", ())
            relevant = []
            if isinstance(raw_proofs, tuple):
                for raw_proof in raw_proofs:
                    try:
                        proof = guarded_effect(raw_proof)
                    except ValueError:
                        # The source-fact boundary should reject this before evaluation.
                        rule_limits.append(
                            _limit(rule, scope, "Guarded-effect facts are invalid", [call])
                        )
                        continue
                    if (
                        proof.condition.kind is rule.condition.kind
                        and proof.condition.owner == rule.condition.owner
                        and proof.condition.name == rule.condition.name
                    ):
                        relevant.append(proof)
            binding = call_binding(parsed_call.data.get("call_binding"))
            if (
                binding is not None
                and binding.target == rule.target
                and any(in_scope(data["source_scope"], owner) for owner in condition_scopes)
                and not relevant
            ):
                rule_limits.append(
                    _limit(
                        rule,
                        scope,
                        "The selected effect has no typed condition path inventory",
                        [call],
                    )
                )
            for proof in relevant:
                if (
                    binding is None
                    and not proof.complete
                    and proof.unknown_reason is not None
                    and (
                        proof.unknown_reason.startswith("raise_constructor_builtin:")
                        and proof.unknown_reason.removeprefix("raise_constructor_builtin:")
                        != rule.target
                        or proof.condition_value is False
                        and proof.unknown_reason == "canonical_call_binding_missing"
                    )
                ):
                    continue
                if not proof.complete or binding is None:
                    rule_limits.append(
                        _limit(rule, scope, "The call path or canonical target is unproven", [call])
                    )
                    continue
                if binding.target != rule.target:
                    matching_helpers = [
                        helper
                        for helper in proof.helper_bindings
                        if helper.target == binding.target and helper.call_id == call["id"]
                    ]
                    if matching_helpers and proof.condition_value is not False:
                        for helper in matching_helpers:
                            helper_violations, helper_limits, helper_facts = _helper_effects(
                                rule,
                                scope,
                                call,
                                proof,
                                helper,
                                calls=selected,
                                symbols=scoped_symbols,
                            )
                            violations.extend(helper_violations)
                            rule_limits.extend(helper_limits)
                            receipt_facts.extend(helper_facts)
                    continue
                if proof.condition_value is not False:
                    violations.append(
                        classified(
                            item_id=stable_id("VIOL-GUARDED-EFFECT", scope, rule.id, call["id"]),
                            evidence_class=EvidenceClass.VIOLATION,
                            area="calls",
                            kind="forbidden_effect_under_condition",
                            title=f"{rule.target} can execute while {rule.condition.name} is true",
                            subjects=[data["source_scope"], rule.target, rule.condition.owner],
                            rule_ids=[rule.id],
                            fact_ids=[call["id"]],
                            evidence_ids=sorted(
                                {
                                    *proof.condition_evidence_ids,
                                    *proof.path_evidence_ids,
                                    *proof.effect_binding_evidence_ids,
                                    *binding.evidence_ids,
                                }
                            ),
                            provenance=list(rule.provenance),
                            data={
                                "scope": scope,
                                "source_module": data["source_module"],
                                "target": rule.target,
                                "condition_owner": rule.condition.owner,
                                "condition_name": rule.condition.name,
                                "condition_value": True,
                            },
                        )
                    )
        limits.extend(rule_limits)
        if not rule_limits:
            receipts.append(_rule_evaluation_receipt(rule, scope, receipt_facts))
    return violations, limits, receipts
