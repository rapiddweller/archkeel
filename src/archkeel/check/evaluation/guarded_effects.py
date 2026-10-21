# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Evaluate bounded, source-certified guarded effect paths."""

from collections.abc import Sequence
from dataclasses import dataclass

from archkeel.ir.facts import (
    CallArgument,
    CallBinding,
    ConditionSelectorKind,
    EvidenceClass,
    GuardedEffectEvidence,
    GuardHelperArgument,
    GuardHelperBinding,
    GuardHelperTokenKind,
    JsonValue,
    RecordData,
    call_arguments,
    call_binding,
    guarded_effect,
    in_scope,
    stable_id,
)
from archkeel.ir.facts_codec import RawRecord, classified, parse_record
from archkeel.ir.model import ArchitectureContract, ForbiddenEffectUnderConditionRule

from .call_arguments import BoundCallArguments, bind_call_arguments
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
    matches = [
        parse_record(row)
        for row in symbols
        if row["data"]["qualified_name"] == rule.condition.owner
    ]
    if len(matches) != 1:
        return False
    data = matches[0].data
    if rule.condition.kind is ConditionSelectorKind.PARAMETER:
        if matches[0].kind not in {"function", "method"}:
            return False
        parameters = data.get("parameters")
        if not isinstance(parameters, tuple):
            return False
        return any(
            isinstance(parameter, RecordData)
            and parameter.get("name") == rule.condition.name
            and parameter.get("annotation") == "bool"
            for parameter in parameters
        )
    if matches[0].kind != "class":
        return False
    declarations = data.get("guard_boolean_members")
    return isinstance(declarations, tuple | list) and any(
        isinstance(declaration, RecordData)
        and declaration.get("name") == rule.condition.name
        and isinstance(declaration.get("evidence_ids"), tuple)
        and bool(declaration.get("evidence_ids"))
        for declaration in declarations
    )


@dataclass(frozen=True, slots=True)
class _HelperContext:
    helper: RawRecord
    helper_data: RecordData
    actuals: tuple[CallArgument, ...]
    bound: BoundCallArguments


def _has_multiple_boolean_parameters(data: RecordData) -> bool:
    parameters = data.get("parameters")
    return (
        isinstance(parameters, tuple)
        and sum(
            isinstance(parameter, RecordData) and parameter.get("annotation") == "bool"
            for parameter in parameters
        )
        > 1
    )


def _prepare_helper(
    rule: ForbiddenEffectUnderConditionRule,
    scope: str,
    caller: RawRecord,
    helper_fact: GuardHelperBinding,
    symbols: Sequence[RawRecord],
) -> tuple[_HelperContext | None, list[RawRecord], list[RawRecord]]:
    helper_symbols = []
    for row in symbols:
        symbol_data = parse_record(row).data
        if symbol_data.get("qualified_name") == helper_fact.target:
            helper_symbols.append(row)
    if len(helper_symbols) != 1:
        return (
            None,
            [_limit(rule, scope, "The private helper declaration is ambiguous", [caller])],
            [],
        )
    helper = helper_symbols[0]
    helper_data = parse_record(helper).data
    visibility = helper_data.get("visibility_detail")
    if (
        helper["kind"] != "function"
        or not isinstance(visibility, RecordData)
        or visibility.get("kind") != "private"
        or helper_data.get("source_binding_unique") is not True
        or helper_data.get("source_binding_static") is not True
        or helper_data.get("decorators")
    ):
        return (
            None,
            [_limit(rule, scope, "The helper is not a unique private function", [caller, helper])],
            [helper],
        )
    if _has_multiple_boolean_parameters(helper_data):
        return (
            None,
            [
                _limit(
                    rule,
                    scope,
                    "Helpers with multiple Boolean parameters are unsupported",
                    [caller, helper],
                )
            ],
            [helper],
        )
    parsed_caller = parse_record(caller)
    try:
        actuals = call_arguments(parsed_caller.data.get("call_arguments"))
    except ValueError:
        actuals = None
    bound = (
        bind_call_arguments(parse_record(helper).data, actuals, bound_receiver=False)
        if actuals is not None
        else None
    )
    if bound is None or actuals is None:
        return (
            None,
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
    return _HelperContext(helper, helper_data, actuals, bound), [], [helper]


def _helper_effects(
    rule: ForbiddenEffectUnderConditionRule,
    scope: str,
    caller: RawRecord,
    caller_proof: GuardedEffectEvidence,
    helper_fact: GuardHelperBinding,
    *,
    calls: Sequence[RawRecord],
    symbols: Sequence[RawRecord],
) -> tuple[list[RawRecord], list[RawRecord], list[RawRecord]]:
    """Substitute one private helper through the shared #614 binder."""
    if caller_proof.condition_value is False:
        return [], [], []
    context, limits, evidence_facts = _prepare_helper(rule, scope, caller, helper_fact, symbols)
    if context is None:
        return [], limits, evidence_facts
    helper = context.helper
    actual_tokens: dict[int, GuardHelperArgument] = {
        argument.argument_index: argument for argument in helper_fact.arguments
    }
    call_actuals = {index: argument for index, argument in enumerate(context.actuals)}
    helper_calls = [row for row in calls if row["data"]["source_scope"] == helper_fact.target]
    violations: list[RawRecord] = []
    effect_seen = False
    for inner_call in helper_calls:
        found, call_violations, call_limits, call_facts = _helper_call_effects(
            rule,
            scope,
            caller,
            caller_proof,
            helper_fact,
            context,
            inner_call,
            actual_tokens,
            call_actuals,
        )
        effect_seen = effect_seen or found
        violations = [*violations, *call_violations]
        limits = [*limits, *call_limits]
        evidence_facts = [*evidence_facts, *call_facts]
    if helper_calls and not effect_seen and not limits:
        limits = [
            *limits,
            _limit(
                rule, scope, "The helper body has no complete effect inventory", [caller, helper]
            ),
        ]
    return violations, limits, evidence_facts


def _helper_call_effects(
    rule: ForbiddenEffectUnderConditionRule,
    scope: str,
    caller: RawRecord,
    caller_proof: GuardedEffectEvidence,
    helper_fact: GuardHelperBinding,
    context: _HelperContext,
    inner_call: RawRecord,
    actual_tokens: dict[int, GuardHelperArgument],
    call_actuals: dict[int, CallArgument],
) -> tuple[bool, list[RawRecord], list[RawRecord], list[RawRecord]]:
    parsed = parse_record(inner_call)
    binding = call_binding(parsed.data.get("call_binding"))
    if binding is None:
        limit = _limit(
            rule,
            scope,
            "The helper body contains an unbound call",
            [caller, context.helper, inner_call],
        )
        return False, [], [limit], [inner_call]
    if binding.target != rule.target:
        if parsed.data.get("guarded_effect"):
            limit = _limit(
                rule,
                scope,
                "Helper chains and recursion are unsupported",
                [caller, context.helper, inner_call],
            )
            return False, [], [limit], [inner_call]
        return False, [], [], []
    raw_proofs = parsed.data.get("guarded_effect", ())
    if not isinstance(raw_proofs, tuple):
        limit = _limit(
            rule,
            scope,
            "The helper effect has no typed path inventory",
            [caller, context.helper, inner_call],
        )
        return True, [], [limit], [inner_call]
    matched = _matched_helper_proofs(raw_proofs, context.helper_data, helper_fact.target)
    if not matched:
        limit = _limit(
            rule,
            scope,
            "The helper effect lacks a bound Boolean path",
            [caller, context.helper, inner_call],
        )
        return True, [], [limit], [inner_call]
    violations: list[RawRecord] = []
    limits: list[RawRecord] = []
    for proof in matched:
        proof_violation, proof_limit = _helper_proof_effect(
            rule,
            scope,
            caller,
            caller_proof,
            helper_fact,
            context,
            binding.evidence_ids,
            inner_call,
            proof,
            actual_tokens,
            call_actuals,
        )
        if proof_violation is not None:
            violations.append(proof_violation)
        if proof_limit is not None:
            limits.append(proof_limit)
    return True, violations, limits, [inner_call]


def _matched_helper_proofs(
    raw_proofs: tuple[JsonValue, ...], helper_data: RecordData, target: str
) -> list[GuardedEffectEvidence]:
    proofs = [guarded_effect(item) for item in raw_proofs]
    parameters = helper_data.get("parameters")
    helper_parameters = parameters if isinstance(parameters, tuple) else ()
    return [
        proof
        for proof in proofs
        if proof.condition.kind is ConditionSelectorKind.PARAMETER
        and proof.condition.owner == target
        and any(
            isinstance(parameter, RecordData)
            and parameter.get("name") == proof.condition.name
            and parameter.get("annotation") == "bool"
            for parameter in helper_parameters
        )
    ]


def _helper_proof_effect(
    rule: ForbiddenEffectUnderConditionRule,
    scope: str,
    caller: RawRecord,
    caller_proof: GuardedEffectEvidence,
    helper_fact: GuardHelperBinding,
    context: _HelperContext,
    binding_evidence_ids: tuple[str, ...],
    inner_call: RawRecord,
    proof: GuardedEffectEvidence,
    actual_tokens: dict[int, GuardHelperArgument],
    call_actuals: dict[int, CallArgument],
) -> tuple[RawRecord | None, RawRecord | None]:
    indexes = None
    for parameter_name, parameter_indexes in context.bound.by_parameter:
        if parameter_name == proof.condition.name:
            indexes = parameter_indexes
            break
    if indexes is None or len(indexes) != 1:
        return None, _limit(
            rule,
            scope,
            "The helper condition has no unique bound actual",
            [caller, context.helper, inner_call],
        )
    index = indexes[0]
    token = actual_tokens.get(index)
    actual = call_actuals.get(index)
    if token is None or actual is None or token.evidence_ids != actual.evidence_ids:
        return None, _limit(
            rule,
            scope,
            "The helper actual evidence is incomplete",
            [caller, context.helper, inner_call],
        )
    if not proof.complete:
        return None, _limit(
            rule,
            scope,
            "The helper effect path is incomplete",
            [caller, context.helper, inner_call],
        )
    substituted, limit = (
        (None, None)
        if proof.condition_value is None
        else _helper_condition_value(
            rule, scope, caller, caller_proof, context.helper, inner_call, token
        )
    )
    if limit is not None:
        return None, limit
    violation = _helper_path_violates(proof.condition_value, substituted)
    if violation is None:
        return None, _limit(
            rule,
            scope,
            "The helper path polarity cannot be substituted",
            [caller, context.helper, inner_call],
        )
    if not violation:
        return None, None
    return _helper_violation(
        rule,
        scope,
        caller,
        caller_proof,
        helper_fact,
        context.helper,
        inner_call,
        proof,
        binding_evidence_ids,
        token,
    ), None


def _helper_condition_value(
    rule: ForbiddenEffectUnderConditionRule,
    scope: str,
    caller: RawRecord,
    caller_proof: GuardedEffectEvidence,
    helper: RawRecord,
    inner_call: RawRecord,
    token: GuardHelperArgument,
) -> tuple[bool | None, RawRecord | None]:
    if token.token_kind is GuardHelperTokenKind.BOOLEAN_LITERAL:
        return token.token_value, None
    selector = token.condition
    if token.token_kind not in {GuardHelperTokenKind.CONDITION, GuardHelperTokenKind.NOT_CONDITION}:
        return None, _limit(
            rule,
            scope,
            "The helper condition actual is not statically bounded",
            [caller, helper, inner_call],
        )
    if (
        selector is None
        or selector.kind is not rule.condition.kind
        or selector.owner != rule.condition.owner
        or selector.name != rule.condition.name
    ):
        return None, _limit(
            rule,
            scope,
            "The helper actual refers to another condition",
            [caller, helper, inner_call],
        )
    value = True if caller_proof.condition_value is None else caller_proof.condition_value
    return (not value if token.token_kind is GuardHelperTokenKind.NOT_CONDITION else value), None


def _helper_path_violates(path_value: bool | None, substituted: bool | None) -> bool | None:
    if path_value is None:
        return True
    if substituted is None:
        return None
    return substituted is path_value


def _helper_violation(
    rule: ForbiddenEffectUnderConditionRule,
    scope: str,
    caller: RawRecord,
    caller_proof: GuardedEffectEvidence,
    helper_fact: GuardHelperBinding,
    helper: RawRecord,
    inner_call: RawRecord,
    proof: GuardedEffectEvidence,
    binding_evidence_ids: tuple[str, ...],
    token: GuardHelperArgument,
) -> RawRecord:
    return classified(
        item_id=stable_id("VIOL-GUARDED-HELPER", scope, rule.id, caller["id"], inner_call["id"]),
        evidence_class=EvidenceClass.VIOLATION,
        area="calls",
        kind="forbidden_effect_under_condition",
        title=f"{rule.target} can execute through {helper_fact.target} while the condition is true",
        subjects=[caller["data"]["source_scope"], helper_fact.target, rule.target],
        rule_ids=[rule.id],
        fact_ids=[caller["id"], helper["id"], inner_call["id"]],
        evidence_ids=sorted(
            {
                *caller_proof.condition_evidence_ids,
                *caller_proof.path_evidence_ids,
                *caller_proof.effect_binding_evidence_ids,
                *proof.condition_evidence_ids,
                *proof.path_evidence_ids,
                *proof.effect_binding_evidence_ids,
                *helper_fact.evidence_ids,
                *token.evidence_ids,
                *binding_evidence_ids,
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
        rule_violations, rule_limits, receipt = _guarded_rule_results(
            rule,
            scope,
            calls,
            scoped_modules,
            scoped_symbols,
            complete=complete,
            bindings_measured=bindings_measured,
            paths_measured=paths_measured,
            source_modules=source_modules,
        )
        violations.extend(rule_violations)
        limits.extend(rule_limits)
        if receipt is not None:
            receipts.append(receipt)
    return violations, limits, receipts


def _guarded_rule_results(
    rule: ForbiddenEffectUnderConditionRule,
    scope: str,
    calls: Sequence[RawRecord],
    scoped_modules: Sequence[RawRecord],
    scoped_symbols: Sequence[RawRecord],
    *,
    complete: bool,
    bindings_measured: bool,
    paths_measured: bool,
    source_modules: frozenset[str] | None,
) -> tuple[list[RawRecord], list[RawRecord], RawRecord | None]:
    subjects, selected, condition_scopes = _rule_inventory(
        rule, calls, scoped_modules, scoped_symbols, source_modules
    )
    limits: list[RawRecord] = []
    receipt_facts: list[RawRecord] = [*subjects, *selected]
    if not subjects:
        limits.append(_limit(rule, scope, "The selected source scope was not observed", []))
    if not _declared_condition(rule, scoped_symbols):
        limits.append(
            _limit(
                rule, scope, "The selected Boolean condition declaration is not proven", subjects
            )
        )
    if not complete or not bindings_measured or not paths_measured:
        limits.append(
            _limit(
                rule, scope, "Complete source and call-binding inventories are required", subjects
            )
        )
    violations: list[RawRecord] = []
    for call in selected:
        call_violations, call_limits, call_facts = _guarded_call_results(
            rule, scope, call, selected, scoped_symbols, condition_scopes
        )
        violations.extend(call_violations)
        limits.extend(call_limits)
        receipt_facts.extend(call_facts)
    receipt = _rule_evaluation_receipt(rule, scope, receipt_facts) if not limits else None
    return violations, limits, receipt


def _rule_inventory(
    rule: ForbiddenEffectUnderConditionRule,
    calls: Sequence[RawRecord],
    scoped_modules: Sequence[RawRecord],
    scoped_symbols: Sequence[RawRecord],
    source_modules: frozenset[str] | None,
) -> tuple[list[RawRecord], list[RawRecord], set[str]]:
    condition_scopes = {rule.condition.owner}
    if rule.condition.kind is ConditionSelectorKind.MEMBER:
        for row in scoped_symbols:
            if row["kind"] != "method":
                continue
            data = parse_record(row).data
            if data.get("parent") == rule.condition.owner:
                owner = data.get("qualified_name")
                if isinstance(owner, str):
                    condition_scopes.add(owner)
    subjects = []
    for row in (*scoped_modules, *scoped_symbols):
        data = parse_record(row).data
        name = data.get("qualified_name")
        if isinstance(name, str) and in_scope(name, rule.source):
            subjects.append(row)
    selected = [
        row
        for row in calls
        if (source_modules is None or row["data"]["source_module"] in source_modules)
        and in_scope(row["data"]["source_scope"], rule.source)
    ]
    return subjects, selected, condition_scopes


def _guarded_call_results(
    rule: ForbiddenEffectUnderConditionRule,
    scope: str,
    call: RawRecord,
    selected: Sequence[RawRecord],
    scoped_symbols: Sequence[RawRecord],
    condition_scopes: set[str],
) -> tuple[list[RawRecord], list[RawRecord], list[RawRecord]]:
    parsed = parse_record(call)
    raw_proofs = parsed.data.get("guarded_effect", ())
    proofs: list[GuardedEffectEvidence] = []
    limits: list[RawRecord] = []
    if isinstance(raw_proofs, tuple):
        for raw_proof in raw_proofs:
            try:
                proof = guarded_effect(raw_proof)
            except ValueError:
                limits.append(_limit(rule, scope, "Guarded-effect facts are invalid", [call]))
                continue
            if _matches_condition(proof, rule):
                proofs.append(proof)
    binding = call_binding(parsed.data.get("call_binding"))
    data = call["data"]
    if (
        binding is not None
        and binding.target == rule.target
        and any(in_scope(data["source_scope"], owner) for owner in condition_scopes)
        and not proofs
    ):
        limits.append(
            _limit(rule, scope, "The selected effect has no typed condition path inventory", [call])
        )
    violations: list[RawRecord] = []
    facts: list[RawRecord] = []
    for proof in proofs:
        effect_violations, effect_limits, effect_facts = _guarded_proof_results(
            rule, scope, call, proof, binding, selected, scoped_symbols
        )
        violations.extend(effect_violations)
        limits.extend(effect_limits)
        facts.extend(effect_facts)
    return violations, limits, facts


def _matches_condition(
    proof: GuardedEffectEvidence, rule: ForbiddenEffectUnderConditionRule
) -> bool:
    return (
        proof.condition.kind is rule.condition.kind
        and proof.condition.owner == rule.condition.owner
        and proof.condition.name == rule.condition.name
    )


def _guarded_proof_results(
    rule: ForbiddenEffectUnderConditionRule,
    scope: str,
    call: RawRecord,
    proof: GuardedEffectEvidence,
    binding: CallBinding | None,
    selected: Sequence[RawRecord],
    scoped_symbols: Sequence[RawRecord],
) -> tuple[list[RawRecord], list[RawRecord], list[RawRecord]]:
    reason = proof.unknown_reason
    prefix = "raise_constructor_builtin:"
    if (
        binding is None
        and not proof.complete
        and reason is not None
        and (
            reason[: len(prefix)] == prefix
            and reason[len(prefix) :] != rule.target
            or proof.condition_value is False
            and reason == "canonical_call_binding_missing"
        )
    ):
        return [], [], []
    if not proof.complete or binding is None:
        return (
            [],
            [_limit(rule, scope, "The call path or canonical target is unproven", [call])],
            [],
        )
    if proof.condition_value is False:
        return [], [], []
    if binding.target != rule.target:
        return _helper_proof_results(rule, scope, call, proof, binding, selected, scoped_symbols)
    return [_direct_violation(rule, scope, call, proof, binding)], [], []


def _helper_proof_results(
    rule: ForbiddenEffectUnderConditionRule,
    scope: str,
    call: RawRecord,
    proof: GuardedEffectEvidence,
    binding: CallBinding,
    selected: Sequence[RawRecord],
    scoped_symbols: Sequence[RawRecord],
) -> tuple[list[RawRecord], list[RawRecord], list[RawRecord]]:
    violations: list[RawRecord] = []
    limits: list[RawRecord] = []
    facts: list[RawRecord] = []
    matched_helper = False
    for helper in proof.helper_bindings:
        if helper.target != binding.target or helper.call_id != call["id"]:
            continue
        matched_helper = True
        helper_violations, helper_limits, helper_facts = _helper_effects(
            rule, scope, call, proof, helper, calls=selected, symbols=scoped_symbols
        )
        violations.extend(helper_violations)
        limits.extend(helper_limits)
        facts.extend(helper_facts)
    unresolved_helper_effect = False
    if not matched_helper:
        for row in selected:
            row_data = parse_record(row).data
            inner_binding = call_binding(row_data.get("call_binding"))
            if (
                row_data.get("source_scope") == binding.target
                and inner_binding is not None
                and inner_binding.target == rule.target
            ):
                unresolved_helper_effect = True
                break
    if unresolved_helper_effect:
        helper_symbol = call
        for symbol in scoped_symbols:
            symbol_data = parse_record(symbol).data
            if symbol_data.get("qualified_name") == binding.target:
                helper_symbol = symbol
                break
        limits.append(
            _limit(
                rule,
                scope,
                "The resolved local helper is not eligible for bounded proof",
                [call, helper_symbol],
            )
        )
    return violations, limits, facts


def _direct_violation(
    rule: ForbiddenEffectUnderConditionRule,
    scope: str,
    call: RawRecord,
    proof: GuardedEffectEvidence,
    binding: CallBinding,
) -> RawRecord:
    data = call["data"]
    return classified(
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
