# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Evaluate policies over explicit actuals bound to observed formals."""

from collections.abc import Sequence

from archkeel.ir.facts import (
    CallArgument,
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
    last_name,
)

from .call_arguments import BoundCallArguments, bind_call_arguments
from .call_owners import _constructed_target_binding_static, _target_binding_static
from .rule_support import _rule_evaluation_receipt

_BOUND_RECEIVER_ORIGINS = frozenset(
    {"declared_receiver", "stored_receiver", "constructed_receiver", "native_receiver"}
)
_CatalogEntry = tuple[RawRecord, str | None, str]


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
    source_records = _catalog_source_records(modules, symbols, source_modules)
    for rule in contract.rules:
        if not isinstance(rule, (CatalogArgumentRule, CatalogUseRule)):
            continue
        rule_violations, rule_limits, receipt = _catalog_rule_result(
            rule,
            scope,
            source_records,
            calls,
            symbols,
            references,
            complete,
            bindings_measured,
            arguments_measured,
            references_measured,
            blank_modules,
            source_modules,
        )
        violations.extend(rule_violations)
        limits.extend(rule_limits)
        if receipt is not None:
            receipts.append(receipt)
    return violations, limits, receipts


def _catalog_rule_result(
    rule: CatalogArgumentRule | CatalogUseRule,
    scope: str,
    source_records: Sequence[RawRecord],
    calls: Sequence[RawRecord],
    symbols: Sequence[RawRecord],
    references: Sequence[RawRecord],
    complete: bool,
    bindings_measured: bool,
    arguments_measured: bool,
    references_measured: bool,
    blank_modules: frozenset[str],
    source_modules: frozenset[str] | None,
) -> tuple[list[RawRecord], list[RawRecord], RawRecord | None]:
    owners, entries, ambiguous = _catalog_inventory(rule, symbols, source_modules)
    subjects, selected_calls, selected_refs, ref_data = _catalog_scope_records(
        rule, source_records, calls, references, source_modules, blank_modules
    )
    supporting = [*subjects, *owners, *selected_refs]
    violations, limits = _catalog_rule_checks(
        rule,
        scope,
        selected_calls,
        symbols,
        selected_refs,
        ref_data,
        entries,
        owners,
        subjects,
        supporting,
        ambiguous,
        complete,
        bindings_measured,
        arguments_measured,
        references_measured,
        source_modules,
    )
    receipt = (
        None if limits else _rule_evaluation_receipt(rule, scope, [*supporting, *selected_calls])
    )
    return violations, limits, receipt


def _catalog_rule_checks(
    rule: CatalogArgumentRule | CatalogUseRule,
    scope: str,
    calls: Sequence[RawRecord],
    symbols: Sequence[RawRecord],
    references: Sequence[RawRecord],
    reference_data: dict[str, RecordData],
    entries: dict[str, _CatalogEntry],
    owners: Sequence[RawRecord],
    subjects: Sequence[RawRecord],
    supporting: Sequence[RawRecord],
    ambiguous: bool,
    complete: bool,
    bindings_measured: bool,
    arguments_measured: bool,
    references_measured: bool,
    source_modules: frozenset[str] | None,
) -> tuple[list[RawRecord], list[RawRecord]]:
    violations: list[RawRecord] = []
    limits: list[RawRecord] = []
    if not subjects or not complete or ambiguous:
        limits.append(
            _catalog_limit(
                rule,
                scope,
                "A complete selected source and unique enum catalog declarations are required",
                supporting,
            )
        )
    if isinstance(rule, CatalogArgumentRule):
        return _catalog_argument_policy(
            rule,
            scope,
            calls,
            symbols,
            references,
            reference_data,
            entries,
            owners,
            supporting,
            bindings_measured,
            arguments_measured,
            references_measured,
            source_modules,
            violations,
            limits,
        )
    return _catalog_use_policy(
        rule,
        scope,
        entries,
        owners,
        supporting,
        references,
        reference_data,
        references_measured,
        complete,
        violations,
        limits,
    )


def _catalog_argument_policy(
    rule: CatalogArgumentRule,
    scope: str,
    calls: Sequence[RawRecord],
    symbols: Sequence[RawRecord],
    references: Sequence[RawRecord],
    reference_data: dict[str, RecordData],
    entries: dict[str, _CatalogEntry],
    owners: Sequence[RawRecord],
    supporting: Sequence[RawRecord],
    bindings_measured: bool,
    arguments_measured: bool,
    references_measured: bool,
    source_modules: frozenset[str] | None,
    violations: list[RawRecord],
    limits: list[RawRecord],
) -> tuple[list[RawRecord], list[RawRecord]]:
    argument_violations, argument_limits = _catalog_argument_results(
        rule,
        scope,
        calls,
        symbols,
        references,
        reference_data,
        entries,
        owners,
        supporting,
        bindings_measured,
        arguments_measured,
        references_measured,
        source_modules,
    )
    violations.extend(argument_violations)
    limits.extend(argument_limits)
    return violations, limits


def _catalog_use_policy(
    rule: CatalogUseRule,
    scope: str,
    entries: dict[str, _CatalogEntry],
    owners: Sequence[RawRecord],
    supporting: Sequence[RawRecord],
    references: Sequence[RawRecord],
    reference_data: dict[str, RecordData],
    references_measured: bool,
    complete: bool,
    violations: list[RawRecord],
    limits: list[RawRecord],
) -> tuple[list[RawRecord], list[RawRecord]]:
    context_complete = _catalog_reference_context_complete(references, reference_data)
    use_violations, use_limits = _catalog_use_results(
        rule,
        scope,
        entries,
        owners,
        supporting,
        references,
        reference_data,
        context_complete,
        references_measured,
        complete,
    )
    violations.extend(use_violations)
    limits.extend(use_limits)
    return violations, limits


def _catalog_source_records(
    modules: Sequence[RawRecord],
    symbols: Sequence[RawRecord],
    source_modules: frozenset[str] | None,
) -> list[RawRecord]:
    return [
        record
        for record in modules
        if source_modules is None or record["data"]["qualified_name"] in source_modules
    ] + [
        record
        for record in symbols
        if source_modules is None or record["data"]["module"] in source_modules
    ]


def _catalog_selected(name: str, selector: str, match: SelectorMatch) -> bool:
    return name == selector if match is SelectorMatch.EXACT else in_scope(name, selector)


def _catalog_inventory(
    rule: CatalogArgumentRule | CatalogUseRule,
    symbols: Sequence[RawRecord],
    source_modules: frozenset[str] | None,
) -> tuple[list[RawRecord], dict[str, _CatalogEntry], bool]:
    owners = [rule.catalog, *rule.overlays]
    owner_records = [
        record
        for record in symbols
        if record["data"]["qualified_name"] in owners
        and record["kind"] == "class"
        and (source_modules is None or record["data"]["module"] in source_modules)
        and _catalog_owner_static(record)
    ]
    entries: dict[str, _CatalogEntry] = {}
    ambiguous = len({record["data"]["qualified_name"] for record in owner_records}) != len(owners)
    for owner in owner_records:
        ambiguous = _catalog_owner_entries(owner, entries) or ambiguous
    return owner_records, entries, ambiguous


def _catalog_owner_entries(owner: RawRecord, entries: dict[str, _CatalogEntry]) -> bool:
    data = parse_record(owner).data
    raw_attributes = data.get("attribute_declarations")
    names = data.get("enum_members")
    if not isinstance(raw_attributes, tuple) or any(
        not isinstance(item, RecordData) for item in raw_attributes
    ):
        return True
    attributes = tuple(item for item in raw_attributes if isinstance(item, RecordData))
    if isinstance(names, tuple):
        member_names = tuple(item for item in names if isinstance(item, str))
        if len(member_names) != len(names):
            return True
    else:
        member_names = tuple(
            name
            for item in attributes
            if item.get("static") is True
            and isinstance(item.get("literal_value"), str)
            and isinstance(name := item.get("name"), str)
        )
        if len(member_names) != len(attributes):
            return True
    if not member_names:
        return True
    values = {item.get("name"): item for item in attributes if isinstance(item.get("name"), str)}
    for name in member_names:
        attribute = values.get(name)
        if attribute is None:
            return True
        literal = attribute.get("literal_value")
        entries[f"{_record_text(data, 'qualified_name')}.{name}"] = (
            owner,
            literal if type(literal) is str else None,
            _record_text(attribute, "definition_id") or owner["id"],
        )
    return False


def _catalog_scope_records(
    rule: CatalogArgumentRule | CatalogUseRule,
    source_records: Sequence[RawRecord],
    calls: Sequence[RawRecord],
    references: Sequence[RawRecord],
    source_modules: frozenset[str] | None,
    blank_modules: frozenset[str],
) -> tuple[list[RawRecord], list[RawRecord], list[RawRecord], dict[str, RecordData]]:
    subjects = [
        record
        for record in source_records
        if _catalog_selected(record["data"]["qualified_name"], rule.source, rule.source_match)
        and record["data"]["qualified_name"] not in blank_modules
    ]
    selected_calls = [
        call
        for call in calls
        if (source_modules is None or call["data"]["source_module"] in source_modules)
        and _catalog_selected(call["data"]["source_scope"], rule.source, rule.source_match)
    ]
    selected_refs: list[RawRecord] = []
    reference_data: dict[str, RecordData] = {}
    for reference in references:
        if reference["kind"] not in {"value_reference", "attribute_reference"}:
            continue
        data = parse_record(reference).data
        reference_data[reference["id"]] = data
        if (
            (source_modules is None or data.get("source_module") in source_modules)
            and _catalog_selected(
                _record_text(data, "source_scope") or "", rule.source, rule.source_match
            )
            and data.get("use") in {"value", "attribute"}
        ):
            selected_refs.append(reference)
    return subjects, selected_calls, selected_refs, reference_data


def _catalog_reference_context_complete(
    references: Sequence[RawRecord], reference_data: dict[str, RecordData]
) -> bool:
    return all(
        _catalog_reference_context_known(reference, reference_data) for reference in references
    )


def _catalog_reference_context_known(
    reference: RawRecord, reference_data: dict[str, RecordData]
) -> bool:
    data = reference_data[reference["id"]]
    context = _record_text(data, "reference_context")
    return context in {"value", "annotation"} or (
        context is None and _record_text(data, "declaration_scope") is not None
    )


def _catalog_argument_results(
    rule: CatalogArgumentRule,
    scope: str,
    calls: Sequence[RawRecord],
    symbols: Sequence[RawRecord],
    references: Sequence[RawRecord],
    reference_data: dict[str, RecordData],
    entries: dict[str, _CatalogEntry],
    owners: Sequence[RawRecord],
    supporting_facts: Sequence[RawRecord],
    bindings_measured: bool,
    arguments_measured: bool,
    references_measured: bool,
    source_modules: frozenset[str] | None,
) -> tuple[list[RawRecord], list[RawRecord]]:
    violations: list[RawRecord] = []
    limits: list[RawRecord] = []
    if not bindings_measured or not arguments_measured:
        limits.append(
            _catalog_limit(
                rule,
                scope,
                "Complete call bindings and written arguments are required",
                supporting_facts,
            )
        )
    targets = _catalog_targets(rule, symbols, source_modules)
    signature = (
        parse_record(targets[0]).data
        if len(targets) == 1 and _target_binding_static(targets[0], symbols)
        else None
    )
    if not _catalog_signature_has_parameter(signature, rule.parameter):
        limits.append(
            _catalog_limit(
                rule,
                scope,
                "The selected operation and formal parameter are unproven",
                [*targets, *supporting_facts],
            )
        )
    for call in calls:
        found, blocked = _catalog_argument_call(
            rule, scope, call, targets, signature, references, reference_data, entries, owners
        )
        violations.extend(found)
        limits.extend(blocked)
    if not targets or not references_measured:
        limits.append(
            _catalog_limit(
                rule,
                scope,
                "Selected catalog or reference inventory is incomplete",
                supporting_facts,
            )
        )
    return violations, limits


def _catalog_targets(
    rule: CatalogArgumentRule,
    symbols: Sequence[RawRecord],
    source_modules: frozenset[str] | None,
) -> list[RawRecord]:
    return [
        record
        for record in symbols
        if record["data"]["qualified_name"] == rule.target
        and record["kind"] in {"class", "function", "method"}
        and (source_modules is None or record["data"]["module"] in source_modules)
    ]


def _catalog_signature_has_parameter(signature: RecordData | None, parameter: str) -> bool:
    return (
        signature is not None
        and _signature_available(signature)
        and _signature_has_parameter(signature, parameter)
    )


def _catalog_argument_call(
    rule: CatalogArgumentRule,
    scope: str,
    call: RawRecord,
    targets: Sequence[RawRecord],
    signature: RecordData | None,
    references: Sequence[RawRecord],
    reference_data: dict[str, RecordData],
    entries: dict[str, _CatalogEntry],
    owners: Sequence[RawRecord],
) -> tuple[list[RawRecord], list[RawRecord]]:
    parsed = parse_record(call)
    binding = call_binding(parsed.data.get("call_binding"))
    actuals = call_arguments(parsed.data.get("call_arguments"))
    if binding is None or actuals is None:
        if binding is None and _unrelated_resolved_call(call, rule.target):
            return [], []
        return [], [
            _catalog_limit(rule, scope, "Call identity or actual arguments are unproven", [call])
        ]
    if binding.target != rule.target or signature is None:
        return [], []
    bound = bind_call_arguments(
        signature,
        actuals,
        bound_receiver=binding.origin.value in _BOUND_RECEIVER_ORIGINS,
    )
    if bound is None:
        return [], [
            _catalog_limit(
                rule,
                scope,
                "Actual arguments do not bind to the selected formal",
                [call, *targets],
            )
        ]
    return _catalog_argument_actuals(
        rule,
        scope,
        call,
        actuals,
        _bound_argument_indexes(bound, rule.parameter),
        references,
        reference_data,
        entries,
        owners,
    )


def _catalog_argument_actuals(
    rule: CatalogArgumentRule,
    scope: str,
    call: RawRecord,
    actuals: tuple[CallArgument, ...],
    indexes: Sequence[int],
    references: Sequence[RawRecord],
    reference_data: dict[str, RecordData],
    entries: dict[str, _CatalogEntry],
    owners: Sequence[RawRecord],
) -> tuple[list[RawRecord], list[RawRecord]]:
    violations: list[RawRecord] = []
    limits: list[RawRecord] = []
    for index in indexes:
        actual = actuals[index]
        member_refs = [
            reference
            for reference in references
            if any(item in actual.evidence_ids for item in reference["evidence_ids"])
            and rule.catalog in _record_strings(reference_data[reference["id"]], "targets")
        ]
        if member_refs:
            expression = _record_text(reference_data[member_refs[0]["id"]], "expression") or ""
            if f"{rule.catalog}.{last_name(expression)}" not in entries:
                limits.append(
                    _catalog_limit(
                        rule,
                        scope,
                        "Enum member argument identity is ambiguous",
                        [call, *member_refs],
                    )
                )
        elif actual.value_kind is CallArgumentValueKind.STRING_LITERAL:
            _catalog_literal_actual(
                rule, scope, call, actual.value, entries, owners, violations, limits
            )
        else:
            limits.append(
                _catalog_limit(
                    rule,
                    scope,
                    "Catalog argument is dynamic or not a canonical member reference",
                    [call],
                )
            )
    return violations, limits


def _catalog_literal_actual(
    rule: CatalogArgumentRule,
    scope: str,
    call: RawRecord,
    value: str | None,
    entries: dict[str, _CatalogEntry],
    owners: Sequence[RawRecord],
    violations: list[RawRecord],
    limits: list[RawRecord],
) -> None:
    if not isinstance(value, str):
        limits.append(
            _catalog_limit(rule, scope, "Written catalog argument is not a string", [call])
        )
    elif any(literal is None for _, literal, _ in entries.values()):
        limits.append(
            _catalog_limit(
                rule,
                scope,
                "The selected catalog has entries without canonical string values",
                [*owners, call],
            )
        )
    elif not any(literal == value for _, literal, _ in entries.values()):
        violations.append(
            _catalog_violation(
                rule, scope, call, f"{value!r} is not in the selected catalog", [call]
            )
        )


def _catalog_use_results(
    rule: CatalogUseRule,
    scope: str,
    entries: dict[str, _CatalogEntry],
    owners: Sequence[RawRecord],
    supporting_facts: Sequence[RawRecord],
    references: Sequence[RawRecord],
    reference_data: dict[str, RecordData],
    context_complete: bool,
    references_measured: bool,
    complete: bool,
) -> tuple[list[RawRecord], list[RawRecord]]:
    violations: list[RawRecord] = []
    limits: list[RawRecord] = []
    if not references_measured:
        limits.append(
            _catalog_limit(
                rule,
                scope,
                "A complete source reference inventory with typed value contexts is required",
                supporting_facts,
            )
        )
    selected_entries = {
        identity: value
        for identity, value in entries.items()
        if rule.member is None or last_name(identity) == rule.member
    }
    if rule.member is not None and not selected_entries:
        limits.append(
            _catalog_limit(
                rule,
                scope,
                "The selected catalog member has no canonical declaration",
                owners,
            )
        )
    value_refs = [
        reference
        for reference in references
        if _record_text(reference_data[reference["id"]], "declaration_scope") is None
        and _record_text(reference_data[reference["id"]], "reference_context") == "value"
    ]
    unused: list[tuple[str, RawRecord]] = []
    for identity, (owner, _, _) in selected_entries.items():
        owner_name = _record_text(parse_record(owner).data, "qualified_name")
        used = any(
            owner_name in _record_strings(reference_data[reference["id"]], "targets")
            and last_name(_record_text(reference_data[reference["id"]], "expression") or "")
            == last_name(identity)
            for reference in value_refs
        )
        if used:
            continue
        unused.append((identity, owner))
        if complete and references_measured and context_complete:
            violations.append(
                _catalog_violation(
                    rule,
                    scope,
                    owner,
                    f"{identity} has no source read in {rule.source}",
                    [owner],
                )
            )
    if unused and references_measured and not context_complete:
        limits.append(
            _catalog_limit(
                rule,
                scope,
                "Incomplete reference contexts cannot prove an entry has no source read",
                [*supporting_facts, *(owner for _, owner in unused)],
            )
        )
    return violations, limits


def _record_text(data: RecordData, key: str) -> str | None:
    value = data.get(key)
    return value if isinstance(value, str) else None


def _record_strings(data: RecordData, key: str) -> tuple[str, ...]:
    value = data.get(key)
    return (
        tuple(item for item in value if isinstance(item, str)) if isinstance(value, tuple) else ()
    )


def _bound_argument_indexes(bound: BoundCallArguments, parameter: str) -> tuple[int, ...]:
    return next(
        (indexes for name, indexes in bound.by_parameter if name == parameter),
        (),
    )


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
    data = parse_record(record).data
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
