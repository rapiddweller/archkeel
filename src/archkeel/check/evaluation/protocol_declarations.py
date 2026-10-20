# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Evaluate exact canonical Protocol identities on selected declarations."""

from __future__ import annotations

from collections.abc import Sequence

from archkeel.ir.facts import RecordData, SymbolClassKind, parse_symbol_class_kind
from archkeel.ir.facts_codec import RawData, RawRecord, classified
from archkeel.ir.model import (
    ArchitectureContract,
    EvidenceClass,
    ModuleExports,
    ProtocolDeclarationRole,
    ProtocolDeclarationSelector,
    ProtocolDeclarationsRule,
    ProtocolDeclarationVisibility,
    in_scope,
    stable_id,
)
from archkeel.ir.profiles import Profile
from archkeel.ir.type_shapes import TypeShapeIndex

from .boundary_types import (
    BindingIndex,
    _canonical_type_identity_verdict,
    _union_parameters,
    boundary_type_indexes,
    resolve_named_type,
)
from .rule_support import UncertainReexportOrigins, _rule_evaluation_receipt, exports_by_module

_SelectedPosition = tuple[RawRecord, str, str | None, tuple[str, ...], bool]


def _public(symbol: RawRecord) -> bool:
    visibility = symbol["data"]["visibility"]
    return isinstance(visibility, str) and visibility == "public_name"


def _attribute_visibility(attribute: RawData) -> str | None:
    if not isinstance(attribute, dict):
        return None
    visibility = attribute.get("visibility")
    if isinstance(visibility, dict):
        kind = visibility.get("kind")
        return kind if isinstance(kind, str) else None
    return None


def _parameter_name(parameter: RawData) -> str | None:
    if not isinstance(parameter, dict):
        return None
    name = parameter.get("name")
    if not isinstance(name, str):
        return None
    return name[2:] if name[:2] == "**" else name[1:] if name[:1] == "*" else name


def _position_binding_uncertain(data: RawData, position: str) -> bool:
    role, _, name = position.partition(".")
    uncertainties = data.get("annotation_binding_uncertainties", {})
    if isinstance(uncertainties, dict | RecordData) and any(
        uncertainties.get(candidate) for candidate in (name, f"*{name}", f"**{name}")
    ):
        return True
    return role == "member" and data.get("class_body_control_flow") is True


def _declaration_binding_proven(symbol: RawRecord) -> bool:
    data: RawData = symbol["data"]
    if symbol["kind"] == "method":
        return (
            data.get("source_final_method_binding") is True
            and data.get("signature_decorators_proven") is True
        )
    if symbol["kind"] == "function":
        return (
            data.get("source_binding_unique") is True
            and data.get("signature_decorators_proven") is True
        )
    return data.get("source_binding_unique") is True


def _classes_named(symbols: Sequence[RawRecord], name: str | None) -> list[RawRecord]:
    result: list[RawRecord] = []
    for symbol in symbols:
        data: RawData = symbol["data"]
        if symbol["kind"] == "class" and data.get("qualified_name") == name:
            result.append(symbol)
    return result


def _member_methods(symbols: Sequence[RawRecord], owner_id: str, name: str) -> list[RawRecord]:
    result: list[RawRecord] = []
    for symbol in symbols:
        data: RawData = symbol["data"]
        if (
            symbol["kind"] == "method"
            and data.get("lexical_parent_id") == owner_id
            and data.get("name") == name
        ):
            result.append(symbol)
    return result


def _nested_class_members(
    symbols: Sequence[RawRecord], owner_id: str, name: str
) -> list[RawRecord]:
    result: list[RawRecord] = []
    for symbol in symbols:
        data: RawData = symbol["data"]
        if (
            symbol["kind"] == "class"
            and data.get("lexical_parent_id") == owner_id
            and data.get("name") == name
        ):
            result.append(symbol)
    return result


def _class_binding_proven(symbol: RawRecord, symbols: Sequence[RawRecord]) -> bool:
    pending = [symbol]
    visited: set[str] = set()
    while pending:
        current = pending.pop()
        data: RawData = current["data"]
        name = data.get("qualified_name")
        bases = data.get("bases", ())
        declarations = data.get("base_declarations", ())
        if current["kind"] != "class" or not isinstance(name, str):
            return False
        if name in visited:
            continue
        if (
            data.get("class_header_static") is not True
            or not _nested_class_binding_proven(current, symbols)
            or not isinstance(bases, (tuple, list))
            or not isinstance(declarations, (tuple, list))
            or len(bases) != len(declarations)
            or any(
                not isinstance(item, dict | RecordData) or item.get("status") != "resolved"
                for item in declarations
            )
        ):
            return False
        visited.add(name)
        for declaration in declarations:
            targets = declaration.get("targets", ())
            if not isinstance(targets, (tuple, list)):
                return False
            for target in targets:
                if not isinstance(target, str):
                    return False
                owners = _classes_named(symbols, target)
                if owners:
                    if len(owners) != 1:
                        return False
                    pending.append(owners[0])
    return True


def _nested_class_binding_proven(symbol: RawRecord, symbols: Sequence[RawRecord]) -> bool:
    data: RawData = symbol["data"]
    if data.get("source_binding_unique") is True:
        return True
    name = data.get("name")
    parent = data.get("parent")
    owners = _classes_named(symbols, parent)
    if not isinstance(name, str) or len(owners) != 1:
        return False
    owner_data: RawData = owners[0]["data"]
    members = owner_data.get("class_members", ())
    return (
        owner_data.get("source_member_binding_static") is True
        and owner_data.get("class_body_control_flow") is not True
        and isinstance(members, (tuple, list))
        and name in members
        and _class_binding_proven(owners[0], symbols)
    )


def _method_name_unshadowed_by_class(
    symbol: RawRecord, owner: RawRecord, symbols: Sequence[RawRecord]
) -> bool:
    data: RawData = symbol["data"]
    name = data.get("name")
    return isinstance(name, str) and not _nested_class_members(symbols, owner["id"], name)


def _decorated_method_binding_proven(
    symbol: RawRecord, owner: RawRecord, symbols: Sequence[RawRecord]
) -> bool:
    data: RawData = symbol["data"]
    decorators = data.get("decorators", ())
    owner_data: RawData = owner["data"]
    inventories = owner_data.get("member_inventories", ())
    attributes = owner_data.get("attribute_declarations", ())
    inventory = next(
        (
            item
            for item in (inventories if isinstance(inventories, (tuple, list)) else ())
            if isinstance(item, dict | RecordData) and item.get("kind") == "method"
        ),
        None,
    )
    definitions = (
        inventory.get("definition_ids", ()) if isinstance(inventory, dict | RecordData) else ()
    )
    return (
        data.get("signature_decorators_proven") is True
        and isinstance(decorators, (tuple, list))
        and bool(decorators)
        and all(isinstance(item, str) for item in decorators)
        and isinstance(inventory, dict | RecordData)
        and inventory.get("status") == "complete"
        and isinstance(definitions, (tuple, list))
        and symbol["id"] in definitions
        and isinstance(attributes, (tuple, list))
        and not any(
            isinstance(item, dict | RecordData) and item.get("name") == data.get("name")
            for item in attributes
        )
        and _method_name_unshadowed_by_class(symbol, owner, symbols)
    )


def _nested_method_binding_proven(
    symbol: RawRecord, owner: RawRecord, symbols: Sequence[RawRecord]
) -> bool:
    data: RawData = symbol["data"]
    name = data.get("name")
    owner_data: RawData = owner["data"]
    inventory = next(
        (
            item
            for item in owner_data.get("member_inventories", ())
            if isinstance(item, dict | RecordData) and item.get("kind") == "method"
        ),
        None,
    )
    definitions = (
        inventory.get("definition_ids", ()) if isinstance(inventory, dict | RecordData) else ()
    )
    attributes = owner_data.get("attribute_declarations", ())
    attribute_conflict = isinstance(attributes, (tuple, list)) and any(
        isinstance(item, dict | RecordData) and item.get("name") == name for item in attributes
    )
    return (
        isinstance(name, str)
        and data.get("signature_decorators_proven") is True
        and isinstance(inventory, dict | RecordData)
        and inventory.get("status") == "complete"
        and isinstance(definitions, (tuple, list))
        and definitions.count(symbol["id"]) == 1
        and len(_member_methods(symbols, owner["id"], name)) == 1
        and _method_name_unshadowed_by_class(symbol, owner, symbols)
        and name in owner_data.get("class_members", ())
        and not attribute_conflict
        and owner_data.get("class_body_control_flow") is not True
        and _class_binding_proven(owner, symbols)
    )


def _public_declaration(symbol: RawRecord, symbols: Sequence[RawRecord]) -> bool:
    if not _public(symbol):
        return False
    data: RawData = symbol["data"]
    parent = data.get("parent") if symbol["kind"] in {"method", "class"} else None
    while isinstance(parent, str):
        owners = _classes_named(symbols, parent)
        if len(owners) != 1 or not _public(owners[0]):
            return False
        owner_data: RawData = owners[0]["data"]
        parent = owner_data.get("parent")
    return True


def _attribute_inventory_complete(symbol: RawRecord) -> bool:
    data: RawData = symbol["data"]
    inventories = data.get("member_inventories", ())
    return isinstance(inventories, (tuple, list)) and any(
        isinstance(item, dict | RecordData)
        and item.get("kind") == "attribute"
        and item.get("status") == "complete"
        for item in inventories
    )


def _select_parameter(
    selected: dict[tuple[str, str], _SelectedPosition],
    symbol: RawRecord,
    selector: ProtocolDeclarationSelector,
    symbols: Sequence[RawRecord],
) -> None:
    if symbol["kind"] not in {"function", "method"}:
        return
    if selector.visibility is ProtocolDeclarationVisibility.PUBLIC and not _public_declaration(
        symbol, symbols
    ):
        return
    data: RawData = symbol["data"]
    parameters = data.get("parameters", ())
    for parameter in parameters if isinstance(parameters, (tuple, list)) else ():
        if not isinstance(parameter, dict) or _parameter_name(parameter) != selector.name:
            continue
        position = f"parameter.{selector.name}"
        annotation = parameter.get("annotation")
        selected.setdefault(
            (symbol["id"], position),
            (
                symbol,
                position,
                annotation if isinstance(annotation, str) else None,
                tuple(symbol["evidence_ids"]),
                False,
            ),
        )


def _select_member(
    selected: dict[tuple[str, str], _SelectedPosition],
    symbol: RawRecord,
    selector: ProtocolDeclarationSelector,
    symbols: Sequence[RawRecord],
) -> None:
    if symbol["kind"] != "class":
        return
    if selector.visibility is ProtocolDeclarationVisibility.PUBLIC and not _public_declaration(
        symbol, symbols
    ):
        return
    data: RawData = symbol["data"]
    attributes = data.get("attribute_declarations", ())
    for attribute in attributes if isinstance(attributes, (tuple, list)) else ():
        if not isinstance(attribute, dict) or attribute.get("name") != selector.name:
            continue
        if (
            selector.visibility is ProtocolDeclarationVisibility.PUBLIC
            and _attribute_visibility(attribute) != "public"
        ):
            continue
        position = f"member.{selector.name}"
        annotation = attribute.get("annotation")
        evidence = attribute.get("evidence_ids", ())
        evidence_ids = tuple(evidence) if isinstance(evidence, (tuple, list)) else ()
        key = (symbol["id"], position)
        previous = selected.get(key)
        overridden = bool(
            _member_methods(symbols, symbol["id"], selector.name)
            or _nested_class_members(symbols, symbol["id"], selector.name)
        )
        uncertain = not _attribute_inventory_complete(symbol) or overridden
        if previous is None:
            selected[key] = (
                symbol,
                position,
                annotation if isinstance(annotation, str) else None,
                evidence_ids,
                uncertain,
            )
        else:
            selected[key] = (
                symbol,
                position,
                None,
                tuple(dict.fromkeys((*previous[3], *evidence_ids))),
                True,
            )


def _selected_positions(
    rule: ProtocolDeclarationsRule,
    symbols: Sequence[RawRecord],
    source_modules: frozenset[str] | None,
) -> list[_SelectedPosition]:
    selected: dict[tuple[str, str], _SelectedPosition] = {}
    for symbol in symbols:
        data: RawData = symbol["data"]
        module = data.get("module")
        qualified_name = data.get("qualified_name")
        if (
            not isinstance(module, str)
            or not isinstance(qualified_name, str)
            or data.get("namespace_bound") is not True
            or not in_scope(module, rule.source)
            or (source_modules is not None and module not in source_modules)
        ):
            continue
        for selector in rule.selectors:
            if selector.role is ProtocolDeclarationRole.PARAMETER:
                _select_parameter(selected, symbol, selector, symbols)
            elif selector.role is ProtocolDeclarationRole.MEMBER:
                _select_member(selected, symbol, selector, symbols)
    return list(selected.values())


def _identity_verdict(
    annotation: str,
    module: str,
    target: tuple[str, str],
    contract: ArchitectureContract,
    exports: ModuleExports,
    imports_by_binding: BindingIndex,
    classes_by_location: BindingIndex,
    type_shapes: TypeShapeIndex,
    optional: bool,
) -> tuple[str, str]:
    source_annotation: str = annotation
    if resolve_named_type(source_annotation, module, imports_by_binding, classes_by_location) == (
        "typing",
        "Any",
    ):
        return "FAIL", "broad_any"
    shape = type_shapes.get(source_annotation)
    normalized_annotation = source_annotation
    if source_annotation.startswith(("'", '"')) and shape is not None:
        normalized_annotation = shape.text
    verdict = _canonical_type_identity_verdict(
        normalized_annotation,
        module,
        contract,
        exports,
        imports_by_binding,
        classes_by_location,
        type_shapes=type_shapes,
    )
    if verdict.undecidable is not None:
        return "UNKNOWN", str(verdict.undecidable)
    arms = _union_parameters(
        normalized_annotation, module, imports_by_binding, type_shapes=type_shapes
    )
    if arms is not None:
        if not optional:
            return (
                "FAIL",
                "optional_union_not_allowed" if "None" in arms else "wrong_protocol_identity",
            )
        if len(arms) != 2 or arms.count("None") != 1:
            return "FAIL", "wrong_protocol_identity"
        member = next(arm for arm in arms if arm != "None")
        optional_verdict = _canonical_type_identity_verdict(
            member,
            module,
            contract,
            exports,
            imports_by_binding,
            classes_by_location,
            type_shapes=type_shapes,
        )
        if optional_verdict.undecidable is not None:
            return "UNKNOWN", str(optional_verdict.undecidable)
        return (
            ("PASS", "optional_canonical_protocol")
            if set(optional_verdict.resolved) == {target}
            else ("FAIL", "wrong_protocol_identity")
        )
    actual = set(verdict.resolved)
    if actual == {target}:
        return "PASS", "canonical_protocol"
    return "FAIL", "wrong_protocol_identity"


def _protocol_position_finding(
    rule: ProtocolDeclarationsRule,
    symbol: RawRecord,
    position: str,
    annotation: str | None,
    evidence_ids: tuple[str, ...],
    facts: list[str],
    status: str,
    reason: str,
) -> RawRecord | None:
    if status not in {"FAIL", "UNKNOWN"}:
        return None
    failed = status == "FAIL"
    data: RawData = {
        "qualified_name": symbol["data"]["qualified_name"],
        "position": position,
        "protocol": rule.protocol,
        "reason": reason,
    }
    if failed:
        data["annotation"] = annotation
    return classified(
        item_id=stable_id(
            "VIO" if failed else "UNKNOWN-PROTOCOL-DECLARATION", rule.id, symbol["id"], position
        ),
        evidence_class=EvidenceClass.VIOLATION if failed else EvidenceClass.UNKNOWN,
        area="api_surface" if failed else "analysis_coverage",
        kind="protocol_declaration" if failed else "protocol_declaration_limit",
        title=(
            f"{symbol['data']['qualified_name']} {position} does not declare {rule.protocol}"
            if failed
            else f"{symbol['data']['qualified_name']} {position} cannot be resolved"
        ),
        subjects=[symbol["data"]["qualified_name"], position, rule.protocol],
        evidence_ids=list(evidence_ids),
        rule_ids=[rule.id],
        fact_ids=facts,
        data=data,
    )


def _position_status(
    selector: ProtocolDeclarationSelector,
    symbol: RawRecord,
    position: str,
    annotation: str | None,
    ambiguous: bool,
    symbols: Sequence[RawRecord],
    target: tuple[str, str],
    contract: ArchitectureContract,
    exports: ModuleExports,
    imports_by_binding: BindingIndex,
    classes_by_location: BindingIndex,
    type_shapes: TypeShapeIndex,
) -> tuple[str, str]:
    data: RawData = symbol["data"]
    binding_is_unique = _declaration_binding_proven(symbol)
    owner_name = data.get("parent") if symbol["kind"] == "method" else None
    class_owners = _classes_named(symbols, owner_name)
    if symbol["kind"] == "method" and len(class_owners) == 1:
        owner = class_owners[0]
        binding_is_unique |= _decorated_method_binding_proven(symbol, owner, symbols) or (
            _nested_method_binding_proven(symbol, owner, symbols)
        )
    if symbol["kind"] == "method":
        class_header_is_static = len(class_owners) == 1 and _class_binding_proven(
            class_owners[0], symbols
        )
    elif symbol["kind"] == "class":
        class_header_is_static = _class_binding_proven(symbol, symbols)
    else:
        class_header_is_static = True
    if not binding_is_unique or not class_header_is_static:
        return "UNKNOWN", "declaration_binding_ambiguous"
    if ambiguous:
        return "UNKNOWN", "member_binding_ambiguous"
    if annotation is None:
        return "FAIL", "missing_annotation"
    if _position_binding_uncertain(data, position):
        return "UNKNOWN", "annotation_binding_uncertain"
    return _identity_verdict(
        annotation,
        data["module"],
        target,
        contract,
        exports,
        imports_by_binding,
        classes_by_location,
        type_shapes,
        selector.optional,
    )


def _protocol_findings(
    rule: ProtocolDeclarationsRule,
    selected: Sequence[_SelectedPosition],
    symbols: Sequence[RawRecord],
    target: tuple[str, str],
    contract: ArchitectureContract,
    exports: ModuleExports,
    imports_by_binding: BindingIndex,
    classes_by_location: BindingIndex,
    type_shapes: TypeShapeIndex,
) -> tuple[list[RawRecord], list[RawRecord]]:
    violations: list[RawRecord] = []
    unknowns: list[RawRecord] = []
    target_module, target_name = target
    for symbol, position, annotation, evidence_ids, ambiguous in selected:
        selector = next(
            selector
            for selector in rule.selectors
            if position == f"{selector.role.value}.{selector.name}"
        )
        status, reason = _position_status(
            selector,
            symbol,
            position,
            annotation,
            ambiguous,
            symbols,
            target,
            contract,
            exports,
            imports_by_binding,
            classes_by_location,
            type_shapes,
        )
        facts = [symbol["id"]]
        target_fact = next(
            (
                item["id"]
                for item in symbols
                if item["data"]["module"] == target_module
                and item["data"]["name"] == target_name
                and item["kind"] == "class"
            ),
            None,
        )
        if target_fact is not None:
            facts.append(target_fact)
        finding = _protocol_position_finding(
            rule, symbol, position, annotation, evidence_ids, facts, status, reason
        )
        if finding is not None:
            if status == "FAIL":
                violations.append(finding)
            else:
                unknowns.append(finding)
    return violations, unknowns


def _protocol_scope_limit(
    rule: ProtocolDeclarationsRule, modules: Sequence[RawRecord], reason: str
) -> RawRecord:
    return classified(
        item_id=stable_id("UNKNOWN-PROTOCOL-DECLARATIONS", rule.id, reason),
        evidence_class=EvidenceClass.UNKNOWN,
        area="analysis_coverage",
        kind="protocol_declaration_limit",
        title=f"{rule.id} cannot evaluate selected Protocol declarations: {reason}",
        subjects=[rule.source, rule.protocol],
        rule_ids=[rule.id],
        fact_ids=[item["id"] for item in modules],
        evidence_ids=sorted({evidence for item in modules for evidence in item["evidence_ids"]}),
        data={"source": rule.source, "protocol": rule.protocol, "reason": reason},
    )


def _unmatched_selectors(
    rule: ProtocolDeclarationsRule,
    selected: Sequence[_SelectedPosition],
) -> tuple[str, ...]:
    positions = {item[1] for item in selected}
    return tuple(
        position
        for selector in rule.selectors
        if (position := f"{selector.role.value}.{selector.name}") not in positions
    )


def _protocol_rule_results(
    rule: ProtocolDeclarationsRule,
    symbols: Sequence[RawRecord],
    modules: Sequence[RawRecord],
    contract: ArchitectureContract,
    source_modules: frozenset[str] | None,
    exports: ModuleExports,
    imports_by_binding: BindingIndex,
    classes_by_location: BindingIndex,
    type_shapes: TypeShapeIndex,
    scope: str,
    receipt_scope_complete: bool,
) -> tuple[list[RawRecord], list[RawRecord], list[RawRecord]]:
    """Evaluate one selector rule and issue only a complete source-scope receipt."""
    protocol_name: str = rule.protocol
    target_module, _, target_name = protocol_name.rpartition(".")
    target_record = classes_by_location.get((target_module, target_name))
    target_symbols = _classes_named(symbols, protocol_name)
    target_valid = (
        isinstance(target_record, dict | RecordData)
        and parse_symbol_class_kind(target_record.get("class_kind")) is SymbolClassKind.PROTOCOL
        and len(target_symbols) == 1
        and _class_binding_proven(target_symbols[0], symbols)
    )
    selected = _selected_positions(rule, symbols, source_modules)
    unmatched = _unmatched_selectors(rule, selected)
    selected_modules = [
        module
        for module in modules
        if in_scope(module["data"]["qualified_name"], rule.source)
        and (source_modules is None or module["data"]["qualified_name"] in source_modules)
    ]
    receipts = []
    unknowns = []
    violations = []
    if not unmatched and target_valid and receipt_scope_complete:
        receipts.append(
            _rule_evaluation_receipt(
                rule,
                scope,
                selected_modules,
                subjects=sorted({item[0]["data"]["qualified_name"] for item in selected}),
                data={"protocol": rule.protocol},
            )
        )
    if unmatched or not target_valid:
        reason = "empty_scope" if unmatched else "protocol_missing_or_ambiguous"
        unknowns.append(_protocol_scope_limit(rule, selected_modules, reason))
    if not receipt_scope_complete:
        unknowns.append(_protocol_scope_limit(rule, selected_modules, "incomplete_scope"))
    if selected and target_valid:
        target = (target_module, target_name)
        failed, undecided = _protocol_findings(
            rule,
            selected,
            symbols,
            target,
            contract,
            exports,
            imports_by_binding,
            classes_by_location,
            type_shapes,
        )
        violations.extend(failed)
        unknowns.extend(undecided)
    return violations, unknowns, receipts


def protocol_declaration_results(
    *,
    symbols: Sequence[RawRecord],
    imports: Sequence[RawRecord],
    modules: Sequence[RawRecord],
    contract: ArchitectureContract,
    source_modules: frozenset[str] | None,
    uncertain_reexport_origins: UncertainReexportOrigins | None,
    type_shapes: TypeShapeIndex,
    profile: Profile,
    scope: str = "root",
    receipt_scope_complete: bool = True,
) -> tuple[list[RawRecord], list[RawRecord], list[RawRecord]]:
    rules = [
        rule
        for rule in contract.rules
        if isinstance(rule, ProtocolDeclarationsRule) and rule.kind not in profile.unsupported_rules
    ]
    if not rules:
        return [], [], []
    exports = exports_by_module(modules)
    imports_by_binding, classes_by_location = boundary_type_indexes(
        symbols,
        imports,
        contract,
        exports,
        uncertain_reexport_origins or {},
    )
    violations: list[RawRecord] = []
    unknowns: list[RawRecord] = []
    receipts: list[RawRecord] = []
    for rule in rules:
        failed, undecided, issued = _protocol_rule_results(
            rule,
            symbols,
            modules,
            contract,
            source_modules,
            exports,
            imports_by_binding,
            classes_by_location,
            type_shapes,
            scope,
            receipt_scope_complete,
        )
        violations.extend(failed)
        unknowns.extend(undecided)
        receipts.extend(issued)
    return (
        sorted(violations, key=lambda item: item["id"]),
        sorted(unknowns, key=lambda item: item["id"]),
        receipts,
    )
