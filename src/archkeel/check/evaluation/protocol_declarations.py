# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Evaluate exact canonical Protocol identities on selected declarations."""

from __future__ import annotations

from collections.abc import Sequence

from archkeel.ir.facts import SymbolClassKind, parse_symbol_class_kind
from archkeel.ir.facts_codec import RawData, RawRecord, classified
from archkeel.ir.model import (
    ArchitectureContract,
    EvidenceClass,
    ModuleExports,
    ProtocolDeclarationRole,
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


def _selected_positions(
    rule: ProtocolDeclarationsRule,
    symbols: Sequence[RawRecord],
    source_modules: frozenset[str] | None,
) -> list[_SelectedPosition]:
    selected: dict[tuple[str, str], _SelectedPosition] = {}
    for symbol in symbols:
        data = symbol["data"]
        module = data.get("module")
        qualified_name = data.get("qualified_name")
        if (
            not isinstance(module, str)
            or not isinstance(qualified_name, str)
            or not in_scope(module, rule.source)
            or (source_modules is not None and module not in source_modules)
        ):
            continue
        for selector in rule.selectors:
            if selector.role is ProtocolDeclarationRole.PARAMETER:
                if symbol["kind"] not in {"function", "method"}:
                    continue
                if selector.visibility is ProtocolDeclarationVisibility.PUBLIC and not _public(
                    symbol
                ):
                    continue
                parameters = data.get("parameters", ())
                for parameter in parameters if isinstance(parameters, (tuple, list)) else ():
                    if (
                        not isinstance(parameter, dict)
                        or _parameter_name(parameter) != selector.name
                    ):
                        continue
                    position = f"parameter.{selector.name}"
                    annotation = parameter.get("annotation")
                    annotation = annotation if isinstance(annotation, str) else None
                    selected.setdefault(
                        (symbol["id"], position),
                        (symbol, position, annotation, tuple(symbol["evidence_ids"]), False),
                    )
            elif selector.role is ProtocolDeclarationRole.MEMBER and symbol["kind"] == "class":
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
                    annotation = annotation if isinstance(annotation, str) else None
                    evidence = attribute.get("evidence_ids", ())
                    key = (symbol["id"], position)
                    evidence_ids = tuple(evidence) if isinstance(evidence, (tuple, list)) else ()
                    previous = selected.get(key)
                    if previous is None:
                        selected[key] = (symbol, position, annotation, evidence_ids, False)
                    else:
                        selected[key] = (
                            symbol,
                            position,
                            None,
                            tuple(dict.fromkeys((*previous[3], *evidence_ids))),
                            True,
                        )
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
        if ambiguous:
            status, reason = "UNKNOWN", "member_binding_ambiguous"
        elif annotation is None:
            status, reason = "FAIL", "missing_annotation"
        else:
            status, reason = _identity_verdict(
                annotation,
                symbol["data"]["module"],
                target,
                contract,
                exports,
                imports_by_binding,
                classes_by_location,
                type_shapes,
                selector.optional,
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
        protocol: str = rule.protocol
        target_module, _, target_name = protocol.rpartition(".")
        target_record = classes_by_location.get((target_module, target_name))
        target_valid = (
            isinstance(target_record, dict)
            and parse_symbol_class_kind(target_record.get("class_kind")) is SymbolClassKind.PROTOCOL
        )
        selected = _selected_positions(rule, symbols, source_modules)
        unmatched = _unmatched_selectors(rule, selected)
        selected_modules = [
            module
            for module in modules
            if in_scope(module["data"]["qualified_name"], rule.source)
            and (source_modules is None or module["data"]["qualified_name"] in source_modules)
        ]
        if not unmatched and target_valid:
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
        if not selected or not target_valid:
            continue
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
    return (
        sorted(violations, key=lambda item: item["id"]),
        sorted(unknowns, key=lambda item: item["id"]),
        receipts,
    )
