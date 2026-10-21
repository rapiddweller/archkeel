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
    selected_parameter: str = rule.parameter
    parameter = selected_parameter.lstrip("*")
    for call in calls:
        parsed = parse_record(call)
        binding = call_binding(parsed.data.get("call_binding"))
        if binding is not None and binding.target != rule.target:
            continue
        actuals = call_arguments(parsed.data.get("call_arguments"))
        if binding is None or actuals is None:
            limits.append(
                _limit(rule, scope, "Call target or actual arguments are unproven", [call])
            )
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
        literal_evidence = sorted(
            {
                evidence_id
                for index in indexes
                if actuals[index].value_kind is CallArgumentValueKind.STRING_LITERAL
                for evidence_id in actuals[index].evidence_ids
            }
        )
        if literal_evidence:
            violations.append(_violation(rule, scope, call, binding, literal_evidence))
    return violations, limits


def catalog_results(
    contract: ArchitectureContract,
    *,
    scope: str,
    calls: Sequence[RawRecord],
    imports: Sequence[RawRecord],
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
            imports,
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
    imports: Sequence[RawRecord],
    symbols: Sequence[RawRecord],
    references: Sequence[RawRecord],
    complete: bool,
    bindings_measured: bool,
    arguments_measured: bool,
    references_measured: bool,
    blank_modules: frozenset[str],
    source_modules: frozenset[str] | None,
) -> tuple[list[RawRecord], list[RawRecord], RawRecord | None]:
    owners, entries, ambiguous = _catalog_inventory(rule, symbols)
    subjects, selected_calls, selected_refs, ref_data = _catalog_scope_records(
        rule, source_records, calls, references, source_modules, blank_modules
    )
    ambiguous_imports = _catalog_ambiguous_imports(rule, imports, subjects)
    supporting = [
        *subjects,
        *owners,
        *selected_refs,
        *ambiguous_imports,
        *_catalog_target_supports(rule, selected_calls, symbols),
    ]
    violations, limits = _catalog_rule_checks(
        rule,
        scope,
        selected_calls,
        symbols,
        selected_refs,
        ref_data,
        entries,
        owners,
        calls,
        references,
        subjects,
        supporting,
        ambiguous,
        complete,
        bindings_measured,
        arguments_measured,
        not ambiguous_imports,
        references_measured,
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
    all_calls: Sequence[RawRecord],
    all_references: Sequence[RawRecord],
    subjects: Sequence[RawRecord],
    supporting: Sequence[RawRecord],
    ambiguous: bool,
    complete: bool,
    bindings_measured: bool,
    arguments_measured: bool,
    import_context_complete: bool,
    references_measured: bool,
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
            all_calls,
            all_references,
            bindings_measured,
            arguments_measured,
            references_measured,
            violations,
            limits,
            not ambiguous,
        )
    return _catalog_use_policy(
        rule,
        scope,
        calls,
        symbols,
        entries,
        owners,
        supporting,
        references,
        reference_data,
        bindings_measured,
        arguments_measured,
        references_measured,
        complete,
        import_context_complete,
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
    all_calls: Sequence[RawRecord],
    all_references: Sequence[RawRecord],
    bindings_measured: bool,
    arguments_measured: bool,
    references_measured: bool,
    violations: list[RawRecord],
    limits: list[RawRecord],
    inventory_complete: bool,
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
        all_calls,
        all_references,
        supporting,
        bindings_measured,
        arguments_measured,
        references_measured,
    )
    if not inventory_complete:
        argument_violations = []
    violations.extend(argument_violations)
    limits.extend(argument_limits)
    return violations, limits


def _catalog_use_policy(
    rule: CatalogUseRule,
    scope: str,
    calls: Sequence[RawRecord],
    symbols: Sequence[RawRecord],
    entries: dict[str, _CatalogEntry],
    owners: Sequence[RawRecord],
    supporting: Sequence[RawRecord],
    references: Sequence[RawRecord],
    reference_data: dict[str, RecordData],
    bindings_measured: bool,
    arguments_measured: bool,
    references_measured: bool,
    complete: bool,
    import_context_complete: bool,
    violations: list[RawRecord],
    limits: list[RawRecord],
) -> tuple[list[RawRecord], list[RawRecord]]:
    context_complete = _catalog_reference_context_complete(references, reference_data)
    use_violations, use_limits = _catalog_use_results(
        rule,
        scope,
        calls,
        symbols,
        entries,
        owners,
        supporting,
        references,
        reference_data,
        bindings_measured,
        arguments_measured,
        context_complete and import_context_complete,
        references_measured,
        complete,
    )
    violations.extend(use_violations)
    limits.extend(use_limits)
    return violations, limits


def _catalog_ambiguous_imports(
    rule: CatalogArgumentRule | CatalogUseRule,
    imports: Sequence[RawRecord],
    subjects: Sequence[RawRecord],
) -> list[RawRecord]:
    catalog_origins = {rule.catalog, *rule.overlays}
    selected_modules = {
        module
        for record in subjects
        if (
            module := _record_text(parse_record(record).data, "module")
            or (
                _record_text(parse_record(record).data, "qualified_name")
                if record["kind"] == "module"
                else None
            )
        )
    }
    ambiguous: list[RawRecord] = []
    for record in imports:
        data: RecordData = parse_record(record).data
        if (
            data.get("source_module") in selected_modules
            and data.get("origin_definition") in catalog_origins
            and data.get("source_binding_unique") is False
        ):
            ambiguous.append(record)
    return ambiguous


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
) -> tuple[list[RawRecord], dict[str, _CatalogEntry], bool]:
    owners = [rule.catalog, *rule.overlays]
    owner_records = [
        record
        for record in symbols
        if record["data"]["qualified_name"] in owners
        and record["kind"] == "class"
        and _catalog_owner_static(
            record, require_unexposed_enum_owner=isinstance(rule, CatalogArgumentRule)
        )
    ]
    entries: dict[str, _CatalogEntry] = {}
    owner_names = tuple(record["data"]["qualified_name"] for record in owner_records)
    expected_owners = set(owners)
    ambiguous = len(owner_records) != len(expected_owners) or set(owner_names) != expected_owners
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
    values = {item.get("name"): item for item in attributes if isinstance(item.get("name"), str)}
    if len(values) != len(attributes):
        return True
    if isinstance(names, tuple):
        member_names = tuple(item for item in names if isinstance(item, str))
        if len(member_names) != len(names) or len(set(member_names)) != len(member_names):
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
    all_calls: Sequence[RawRecord],
    all_references: Sequence[RawRecord],
    supporting_facts: Sequence[RawRecord],
    bindings_measured: bool,
    arguments_measured: bool,
    references_measured: bool,
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
    targets = _catalog_targets(rule, symbols)
    escape_limit = _catalog_unselected_enum_argument_limit(
        rule, scope, calls, entries, references, reference_data, all_calls, all_references
    )
    if escape_limit is not None:
        limits.append(escape_limit)
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


def _catalog_unselected_enum_argument_limit(
    rule: CatalogArgumentRule,
    scope: str,
    calls: Sequence[RawRecord],
    entries: dict[str, _CatalogEntry],
    references: Sequence[RawRecord],
    reference_data: dict[str, RecordData],
    all_calls: Sequence[RawRecord],
    all_references: Sequence[RawRecord],
) -> RawRecord | None:
    entry_owners = {
        owner_name
        for owner, _, _ in entries.values()
        if (owner_name := _record_text(parse_record(owner).data, "qualified_name")) is not None
    }
    for call in calls:
        parsed = parse_record(call)
        binding = call_binding(parsed.data.get("call_binding"))
        actuals = call_arguments(parsed.data.get("call_arguments"))
        if actuals is None:
            continue
        for actual in actuals:
            if any(
                set(actual.evidence_ids) == set(reference["evidence_ids"])
                and _record_text(reference_data[reference["id"]], "reference_context") == "value"
                and entry_owners & set(_record_strings(reference_data[reference["id"]], "targets"))
                for reference in references
            ):
                if binding is not None and binding.target == rule.target:
                    target_calls = [
                        item
                        for item in all_calls
                        if _record_text(parse_record(item).data, "source_scope") == rule.target
                    ]
                    target_writes = [
                        item
                        for item in all_references
                        if item["kind"] == "source_role"
                        and _record_text(parse_record(item).data, "source_scope") == rule.target
                        and _record_text(parse_record(item).data, "role") in {"write", "delete"}
                    ]
                    if not target_calls and not target_writes:
                        continue
                    reason = "Selected operation may mutate an enum member"
                else:
                    reason = "An enum member is passed to an unselected call"
                return _catalog_limit(
                    rule,
                    scope,
                    reason,
                    [call],
                )
    return None


def _catalog_targets(
    rule: CatalogArgumentRule | CatalogUseRule, symbols: Sequence[RawRecord]
) -> list[RawRecord]:
    if rule.target is None:
        return []
    return [
        record
        for record in symbols
        if record["data"]["qualified_name"] == rule.target
        and record["kind"] in {"class", "function", "method"}
    ]


def _catalog_target_supports(
    rule: CatalogArgumentRule | CatalogUseRule,
    calls: Sequence[RawRecord],
    symbols: Sequence[RawRecord],
) -> list[RawRecord]:
    target = rule.target
    if target is None:
        return []
    target_name: str = target
    names = {target_name, target_name.rpartition(".")[0]}
    for call in calls:
        call_data: RecordData = parse_record(call).data
        binding = call_binding(call_data.get("call_binding"))
        proof = binding.proof if binding is not None else None
        proof_target = proof.get("target") if proof is not None else None
        if binding is not None and binding.target == target and isinstance(proof_target, str):
            names |= {proof_target}
    return [symbol for symbol in symbols if symbol["data"]["qualified_name"] in names]


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
    if binding is not None and binding.target != rule.target:
        return [], []
    actuals = call_arguments(parsed.data.get("call_arguments"))
    if binding is None or actuals is None:
        if binding is None and _unrelated_resolved_call(call, rule.target):
            return [], []
        return [], [
            _catalog_limit(rule, scope, "Call identity or actual arguments are unproven", [call])
        ]
    if signature is None:
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
        identities, ambiguous = _catalog_actual_entries(actual, entries, references, reference_data)
        if identities:
            continue
        if ambiguous:
            limits.append(
                _catalog_limit(
                    rule,
                    scope,
                    "Enum member argument identity is ambiguous",
                    [call],
                )
            )
        elif actual.value_kind is CallArgumentValueKind.STRING_LITERAL:
            _catalog_literal_actual(
                rule,
                scope,
                call,
                actual,
                entries,
                owners,
                violations,
                limits,
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
    actual: CallArgument,
    entries: dict[str, _CatalogEntry],
    owners: Sequence[RawRecord],
    violations: list[RawRecord],
    limits: list[RawRecord],
) -> None:
    value = actual.value
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
                rule,
                scope,
                call,
                f"{value!r} is not in the selected catalog",
                [call],
                identity_evidence=actual.evidence_ids,
            )
        )


def _catalog_use_results(
    rule: CatalogUseRule,
    scope: str,
    calls: Sequence[RawRecord],
    symbols: Sequence[RawRecord],
    entries: dict[str, _CatalogEntry],
    owners: Sequence[RawRecord],
    supporting_facts: Sequence[RawRecord],
    references: Sequence[RawRecord],
    reference_data: dict[str, RecordData],
    bindings_measured: bool,
    arguments_measured: bool,
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
    call_uses, uncertain_calls = _catalog_call_argument_uses(
        rule,
        calls,
        symbols,
        entries,
        selected_entries,
        references,
        reference_data,
        owners,
        bindings_measured,
        arguments_measured,
    )
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
    entry_violations, entry_limits = _catalog_use_entry_results(
        rule,
        scope,
        selected_entries,
        value_refs,
        reference_data,
        call_uses,
        uncertain_calls,
        supporting_facts,
        context_complete,
        references_measured,
        complete,
    )
    violations.extend(entry_violations)
    limits.extend(entry_limits)
    return violations, limits


def _catalog_use_entry_results(
    rule: CatalogUseRule,
    scope: str,
    selected_entries: dict[str, _CatalogEntry],
    value_refs: Sequence[RawRecord],
    reference_data: dict[str, RecordData],
    call_uses: set[str],
    uncertain_calls: Sequence[RawRecord],
    supporting_facts: Sequence[RawRecord],
    context_complete: bool,
    references_measured: bool,
    complete: bool,
) -> tuple[list[RawRecord], list[RawRecord]]:
    violations: list[RawRecord] = []
    limits: list[RawRecord] = []
    unused: list[tuple[str, RawRecord]] = []
    for identity, (owner, _, _) in selected_entries.items():
        owner_name = _record_text(parse_record(owner).data, "qualified_name")
        used = (
            any(
                owner_name in _record_strings(reference_data[reference["id"]], "targets")
                and last_name(_record_text(reference_data[reference["id"]], "expression") or "")
                == last_name(identity)
                for reference in value_refs
            )
            or identity in call_uses
        )
        if used:
            continue
        unused.append((identity, owner))
        if uncertain_calls:
            limits.append(
                _catalog_limit(
                    rule,
                    scope,
                    "Selected read calls do not prove whether the entry is used",
                    [owner, *uncertain_calls],
                )
            )
        elif complete and references_measured and context_complete:
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


def _catalog_call_argument_uses(
    rule: CatalogUseRule,
    calls: Sequence[RawRecord],
    symbols: Sequence[RawRecord],
    entries: dict[str, _CatalogEntry],
    selected_entries: dict[str, _CatalogEntry],
    references: Sequence[RawRecord],
    reference_data: dict[str, RecordData],
    owners: Sequence[RawRecord],
    bindings_measured: bool,
    arguments_measured: bool,
) -> tuple[set[str], tuple[RawRecord, ...]]:
    if rule.target is None or rule.parameter is None:
        return set(), ()
    targets = _catalog_targets(rule, symbols)
    target = targets[0] if len(targets) == 1 else None
    signature = parse_record(target).data if target is not None else None
    proven = target is not None and (
        _target_binding_static(target, symbols)
        or _constructed_target_binding_static(target, calls, symbols)
    )
    if (
        not proven
        or signature is None
        or not _catalog_signature_has_parameter(signature, rule.parameter)
    ):
        return set(), tuple(targets or owners)
    if not bindings_measured or not arguments_measured:
        return set(), tuple(calls or targets)
    used: set[str] = set()
    uncertain: list[RawRecord] = []
    for call in calls:
        call_uses, uncertain_call = _catalog_use_call_entries(
            rule,
            call,
            signature,
            entries,
            selected_entries,
            references,
            reference_data,
        )
        used |= call_uses
        if uncertain_call:
            uncertain.append(call)
    unique_uncertain: dict[str, RawRecord] = {record["id"]: record for record in uncertain}
    return used, tuple(unique_uncertain[identifier] for identifier in unique_uncertain)


def _catalog_use_call_entries(
    rule: CatalogUseRule,
    call: RawRecord,
    signature: RecordData,
    entries: dict[str, _CatalogEntry],
    selected_entries: dict[str, _CatalogEntry],
    references: Sequence[RawRecord],
    reference_data: dict[str, RecordData],
) -> tuple[set[str], bool]:
    call_data: RecordData = parse_record(call).data
    binding = call_binding(call_data.get("call_binding"))
    if binding is None:
        return set(), not _unrelated_resolved_call(call, rule.target or "")
    if binding.target != rule.target:
        return set(), False
    actuals = call_arguments(call_data.get("call_arguments"))
    if actuals is None:
        return set(), True
    bound = bind_call_arguments(
        signature,
        actuals,
        bound_receiver=binding.origin.value in _BOUND_RECEIVER_ORIGINS,
    )
    if bound is None:
        return set(), True
    indexes = _bound_argument_indexes(bound, rule.parameter or "")
    used: set[str] = set()
    uncertain = False
    for index in indexes:
        actual = actuals[index]
        found, ambiguous = _catalog_actual_entries(
            actual,
            entries,
            references,
            reference_data,
            selected_entries=selected_entries,
            require_unique_value=True,
        )
        used |= found
        if ambiguous or (actual.value_kind is CallArgumentValueKind.OTHER and not found):
            uncertain = True
    return used, uncertain


def _catalog_actual_entries(
    actual: CallArgument,
    entries: dict[str, _CatalogEntry],
    references: Sequence[RawRecord],
    reference_data: dict[str, RecordData],
    *,
    selected_entries: dict[str, _CatalogEntry] | None = None,
    require_unique_value: bool = False,
) -> tuple[set[str], bool]:
    entry_owners = {
        owner_name
        for owner, _, _ in entries.values()
        if (owner_name := _record_text(parse_record(owner).data, "qualified_name")) is not None
    }
    member_refs = [
        reference
        for reference in references
        if set(actual.evidence_ids) == set(reference["evidence_ids"])
        and _record_text(reference_data[reference["id"]], "reference_context") == "value"
        and entry_owners & set(_record_strings(reference_data[reference["id"]], "targets"))
    ]
    if member_refs:
        identities: set[str] = set()
        target_owners: set[str] = set()
        for item in member_refs:
            data = reference_data[item["id"]]
            expression = _record_text(data, "expression") or ""
            targets = set(_record_strings(data, "targets"))
            for owner in entry_owners & targets:
                target_owners |= {owner}
                identities |= {f"{owner}.{last_name(expression)}"}
        selected = identities & entries.keys()
        exact_owner = len(target_owners) == 1 and all(
            set(_record_strings(reference_data[item["id"]], "targets")) == target_owners
            for item in member_refs
        )
        if len(member_refs) != 1 or not exact_owner or len(selected) != 1:
            return set(), True
        return selected, False
    if actual.value_kind is not CallArgumentValueKind.STRING_LITERAL:
        return set(), True
    matches = {identity for identity, (_, literal, _) in entries.items() if literal == actual.value}
    if require_unique_value and len(matches) > 1:
        return set(), True
    scoped_entries: dict[str, _CatalogEntry] = (
        selected_entries if selected_entries is not None else entries
    )
    selected = matches & set(scoped_entries)
    has_unknown_selected_value = any(
        scoped_entries[identity][1] is None for identity in scoped_entries
    )
    return selected, require_unique_value and has_unknown_selected_value


def _record_text(data: RecordData, key: str) -> str | None:
    value = data.get(key)
    return value if isinstance(value, str) else None


def _record_strings(data: RecordData, key: str) -> tuple[str, ...]:
    value = data.get(key)
    return (
        tuple(item for item in value if isinstance(item, str)) if isinstance(value, tuple) else ()
    )


def _bound_argument_indexes(bound: BoundCallArguments, parameter: str) -> tuple[int, ...]:
    name = parameter[2:] if parameter.startswith("**") else parameter.removeprefix("*")
    return next(
        (indexes for formal, indexes in bound.by_parameter if formal == name),
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


def _catalog_owner_static(record: RawRecord, *, require_unexposed_enum_owner: bool = False) -> bool:
    data = parse_record(record).data
    if data.get("source_binding_unique") is not True:
        return False
    if data.get("class_kind") == "enum":
        return data.get("class_header_static") is True and (
            not require_unexposed_enum_owner or data.get("source_member_owner_static") is True
        )
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
    *,
    identity_evidence: Sequence[str] = (),
) -> RawRecord:
    return classified(
        item_id=stable_id(
            "VIOL-CATALOG",
            scope,
            rule.id,
            reason,
            *(record["id"] for record in facts),
            *identity_evidence,
        ),
        evidence_class=EvidenceClass.VIOLATION,
        area="references",
        kind=rule.kind.value,
        title=reason,
        subjects=[rule.source, rule.catalog],
        rule_ids=[rule.id],
        fact_ids=[record["id"] for record in facts],
        evidence_ids=sorted(
            {identity for record in facts for identity in record["evidence_ids"]}
            | set(identity_evidence)
        ),
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
        if not isinstance(parameter_name, str):
            continue
        formal_name: str = parameter_name
        if name in {formal_name, formal_name.lstrip("*")}:
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
