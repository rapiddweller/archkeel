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
from archkeel.ir.model import (
    ArchitectureContract,
    CatalogArgumentRule,
    CatalogUseRule,
    ForbiddenCallArgumentRule,
    SelectorMatch,
)

from .call_arguments import bind_call_arguments
from .call_owners import _target_binding_static
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
    target_proven = len(targets) == 1 and _target_binding_static(targets[0], symbols)
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
            (actuals for formal, actuals in bound.by_parameter if formal == rule.parameter), ()
        )
        for index in indexes:
            argument = actuals[index]
            if argument.value_kind is CallArgumentValueKind.STRING_LITERAL:
                violations.append(_violation(rule, scope, call, binding, argument.evidence_ids))
    return violations, limits


def catalog_results(
    contract: ArchitectureContract,
    *,
    scope: str,
    calls: Sequence[RawRecord],
    modules: Sequence[RawRecord],
    symbols: Sequence[RawRecord],
    references: Sequence[RawRecord],
    complete: bool,
    bindings_measured: bool,
    arguments_measured: bool,
    references_measured: bool,
    blank_modules: frozenset[str],
    source_modules: frozenset[str] | None = None,
) -> tuple[list[RawRecord], list[RawRecord], list[RawRecord]]:
    """Check literal argument membership and source reads against declared enum owners."""
    violations: list[RawRecord] = []
    limits: list[RawRecord] = []
    receipts: list[RawRecord] = []
    source_records = [
        record
        for record in modules
        if source_modules is None or record["data"]["qualified_name"] in source_modules
    ] + [
        record
        for record in symbols
        if source_modules is None or record["data"]["module"] in source_modules
    ]

    def selected(name: str, selector: str, match: SelectorMatch) -> bool:
        return name == selector if match is SelectorMatch.EXACT else in_scope(name, selector)

    for rule in contract.rules:
        if not isinstance(rule, (CatalogArgumentRule, CatalogUseRule)):
            continue
        catalog_owners = [rule.catalog, *rule.overlays]
        owner_records = [
            record
            for record in symbols
            if record["data"]["qualified_name"] in catalog_owners
            and record["kind"] == "class"
            and (source_modules is None or record["data"]["module"] in source_modules)
            and _catalog_owner_static(record)
        ]
        owners_by_name = {record["data"]["qualified_name"]: record for record in owner_records}
        entries: dict[str, tuple[RawRecord, str | None, str]] = {}
        ambiguous_owner = len(owners_by_name) != len(catalog_owners)
        for owner in owner_records:
            names = owner["data"].get("enum_members")
            attributes = owner["data"].get("attribute_declarations")
            if not isinstance(attributes, (tuple, list)):
                ambiguous_owner = True
                continue
            if not isinstance(names, (tuple, list)):
                names = [
                    item.get("name")
                    for item in attributes
                    if isinstance(item, dict)
                    and item.get("static") is True
                    and isinstance(item.get("literal_value"), str)
                ]
                if len(names) != len(attributes):
                    ambiguous_owner = True
            if not names:
                ambiguous_owner = True
                continue
            values = {
                item.get("name"): item
                for item in attributes
                if isinstance(item, dict) and isinstance(item.get("name"), str)
            }
            for name in names:
                if not isinstance(name, str) or name not in values:
                    ambiguous_owner = True
                    continue
                attribute = values[name]
                literal = attribute.get("literal_value")
                literal_value = literal if type(literal) is str else None
                entries[f"{owner['data']['qualified_name']}.{name}"] = (
                    owner,
                    literal_value,
                    str(attribute.get("definition_id", owner["id"])),
                )
        subjects = [
            record
            for record in source_records
            if selected(record["data"]["qualified_name"], rule.source, rule.source_match)
            and record["data"]["qualified_name"] not in blank_modules
        ]
        selected_calls = [
            call
            for call in calls
            if (source_modules is None or call["data"]["source_module"] in source_modules)
            and selected(call["data"]["source_scope"], rule.source, rule.source_match)
        ]
        selected_scope_refs = [
            reference
            for reference in references
            if (source_modules is None or reference["data"].get("source_module") in source_modules)
            and selected(reference["data"].get("source_scope", ""), rule.source, rule.source_match)
            and reference["data"].get("use") in {"value", "attribute"}
            and reference["kind"] in {"value_reference", "attribute_reference"}
        ]
        reference_context_complete = all(
            reference["data"].get("reference_context") in {"value", "annotation"}
            for reference in selected_scope_refs
        )
        selected_refs = [
            reference
            for reference in selected_scope_refs
            if reference["data"].get("declaration_scope") is None
        ]
        selected_value_refs = [
            reference
            for reference in selected_refs
            if reference["data"].get("reference_context") == "value"
        ]
        rule_limits: list[RawRecord] = []
        supporting_facts = [*subjects, *owner_records, *selected_refs]
        if not subjects or not complete or ambiguous_owner:
            rule_limits.append(
                _catalog_limit(
                    rule,
                    scope,
                    "A complete selected source and unique enum catalog declarations are required",
                    supporting_facts,
                )
            )
        if isinstance(rule, CatalogArgumentRule):
            if not bindings_measured or not arguments_measured:
                rule_limits.append(
                    _catalog_limit(
                        rule,
                        scope,
                        "Complete call bindings and written arguments are required",
                        supporting_facts,
                    )
                )
            targets = [
                record
                for record in symbols
                if record["data"]["qualified_name"] == rule.target
                and record["kind"] in {"class", "function", "method"}
                and (source_modules is None or record["data"]["module"] in source_modules)
            ]
            target_proven = len(targets) == 1 and _target_binding_static(targets[0], symbols)
            signature = parse_record(targets[0]).data if target_proven else None
            if (
                not target_proven
                or not _signature_available(signature)
                or not _signature_has_parameter(signature, rule.parameter)
            ):
                rule_limits.append(
                    _catalog_limit(
                        rule,
                        scope,
                        "The selected operation and formal parameter are unproven",
                        [*targets, *supporting_facts],
                    )
                )
            for call in selected_calls:
                parsed = parse_record(call)
                binding = call_binding(parsed.data.get("call_binding"))
                actuals = call_arguments(parsed.data.get("call_arguments"))
                if binding is None or actuals is None:
                    if binding is None and _unrelated_resolved_call(call, rule.target):
                        continue
                    rule_limits.append(
                        _catalog_limit(
                            rule, scope, "Call identity or actual arguments are unproven", [call]
                        )
                    )
                    continue
                if binding.target != rule.target:
                    continue
                if signature is None:
                    continue
                bound = bind_call_arguments(
                    signature,
                    actuals,
                    bound_receiver=binding.origin.value in _BOUND_RECEIVER_ORIGINS,
                )
                if bound is None:
                    rule_limits.append(
                        _catalog_limit(
                            rule,
                            scope,
                            "Actual arguments do not bind to the selected formal",
                            [call, *targets],
                        )
                    )
                    continue
                for index in dict(bound.by_parameter).get(rule.parameter, ()):
                    actual = actuals[index]
                    member_refs = [
                        reference
                        for reference in selected_refs
                        if set(reference["evidence_ids"]).intersection(actual.evidence_ids)
                        and rule.catalog in reference["data"].get("targets", ())
                    ]
                    if member_refs:
                        expression = member_refs[0]["data"].get("expression", "")
                        identity = f"{rule.catalog}.{expression.rsplit('.', 1)[-1]}"
                        if identity not in entries:
                            rule_limits.append(
                                _catalog_limit(
                                    rule,
                                    scope,
                                    "Enum member argument identity is ambiguous",
                                    [call, *member_refs],
                                )
                            )
                    elif actual.value_kind is CallArgumentValueKind.STRING_LITERAL:
                        value = actual.value
                        if not isinstance(value, str):
                            rule_limits.append(
                                _catalog_limit(
                                    rule, scope, "Written catalog argument is not a string", [call]
                                )
                            )
                        elif any(literal is None for _, literal, _ in entries.values()):
                            rule_limits.append(
                                _catalog_limit(
                                    rule,
                                    scope,
                                    "The selected catalog has entries without "
                                    "canonical string values",
                                    [*owner_records, call],
                                )
                            )
                        elif not any(literal == value for _, literal, _ in entries.values()):
                            violations.append(
                                _catalog_violation(
                                    rule,
                                    scope,
                                    call,
                                    f"{value!r} is not in the selected catalog",
                                    [call],
                                )
                            )
                    else:
                        rule_limits.append(
                            _catalog_limit(
                                rule,
                                scope,
                                "Catalog argument is dynamic or not a canonical member reference",
                                [call],
                            )
                        )
            if not targets or not references_measured:
                rule_limits.append(
                    _catalog_limit(
                        rule,
                        scope,
                        "Selected catalog or reference inventory is incomplete",
                        supporting_facts,
                    )
                )
        else:
            if not references_measured or not reference_context_complete:
                rule_limits.append(
                    _catalog_limit(
                        rule,
                        scope,
                        "A complete source reference inventory with typed value contexts is "
                        "required",
                        [*supporting_facts, *selected_scope_refs],
                    )
                )
            selected_entries = {
                identity: value
                for identity, value in entries.items()
                if rule.member is None or identity.rsplit(".", 1)[-1] == rule.member
            }
            if rule.member is not None and not selected_entries:
                rule_limits.append(
                    _catalog_limit(
                        rule,
                        scope,
                        "The selected catalog member has no canonical declaration",
                        owner_records,
                    )
                )
            for identity, (owner, _, _definition_id) in selected_entries.items():
                uses = [
                    reference
                    for reference in selected_value_refs
                    if owner["data"]["qualified_name"] in reference["data"].get("targets", ())
                    and reference["data"].get("expression", "").rsplit(".", 1)[-1]
                    == identity.rsplit(".", 1)[-1]
                ]
                if not uses and complete and references_measured:
                    violations.append(
                        _catalog_violation(
                            rule,
                            scope,
                            owner,
                            f"{identity} has no source read in {rule.source}",
                            [owner],
                        )
                    )
        if rule_limits:
            limits.extend(rule_limits)
        else:
            receipts.append(
                _rule_evaluation_receipt(
                    rule,
                    scope,
                    [*supporting_facts, *selected_calls],
                )
            )
    return violations, limits, receipts


def _catalog_limit(
    rule: CatalogArgumentRule | CatalogUseRule, scope: str, reason: str, facts: Sequence[RawRecord]
) -> RawRecord:
    return classified(
        item_id=stable_id(
            "UNKNOWN-CATALOG", scope, rule.id, reason, *(record["id"] for record in facts)
        ),
        evidence_class=EvidenceClass.UNKNOWN,
        area="references",
        kind="catalog_limit",
        title=reason,
        subjects=[rule.source, rule.catalog],
        rule_ids=[rule.id],
        fact_ids=[record["id"] for record in facts],
        evidence_ids=sorted({identity for record in facts for identity in record["evidence_ids"]}),
        data={"scope": scope, "reason": reason},
    )


def _catalog_owner_static(record: RawRecord) -> bool:
    data = record["data"]
    if data.get("source_binding_unique") is not True:
        return False
    if data.get("class_kind") == "enum":
        return data.get("class_header_static") is True
    return (
        data.get("class_header_static") is True
        and data.get("source_member_binding_static") is True
        and data.get("class_body_control_flow") is False
    )


def _catalog_violation(
    rule: CatalogArgumentRule | CatalogUseRule,
    scope: str,
    fact: RawRecord,
    reason: str,
    facts: Sequence[RawRecord],
) -> RawRecord:
    return classified(
        item_id=stable_id(
            "VIOL-CATALOG", scope, rule.id, reason, *(record["id"] for record in facts)
        ),
        evidence_class=EvidenceClass.VIOLATION,
        area="references",
        kind=rule.kind.value,
        title=reason,
        subjects=[rule.source, rule.catalog],
        rule_ids=[rule.id],
        fact_ids=[record["id"] for record in facts],
        evidence_ids=sorted({identity for record in facts for identity in record["evidence_ids"]}),
        provenance=list(rule.provenance),
        data={"scope": scope, "catalog": rule.catalog, "fact": fact["id"]},
    )


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


def _unrelated_resolved_call(call: RawRecord, target: str) -> bool:
    data = call["data"]
    targets = data.get("targets")
    return (
        data.get("status") == "resolved"
        and data.get("candidate_count") == 1
        and isinstance(targets, (tuple, list))
        and len(targets) == 1
        and isinstance(targets[0], str)
        and targets[0] != target
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
