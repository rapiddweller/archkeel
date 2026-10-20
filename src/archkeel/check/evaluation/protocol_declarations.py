# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Evaluate exact canonical Protocol identities on selected declarations."""

from __future__ import annotations

from collections.abc import Sequence

from archkeel.ir.facts import SymbolClassKind, parse_symbol_class_kind
from archkeel.ir.facts_codec import RawRecord, classified
from archkeel.ir.model import (
    ArchitectureContract,
    EvidenceClass,
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
    _boundary_type_verdict,
    _union_parameters,
    boundary_type_indexes,
    resolve_named_type,
)
from .rule_support import UncertainReexportOrigins, _rule_evaluation_receipt, exports_by_module


def _public(symbol: RawRecord) -> bool:
    return symbol["data"].get("visibility") == "public_name"


def _attribute_visibility(attribute: object) -> str | None:
    if not isinstance(attribute, dict):
        return None
    visibility = attribute.get("visibility")
    if isinstance(visibility, dict):
        kind = visibility.get("kind")
        return kind if isinstance(kind, str) else None
    return None


def _selected_positions(
    rule: ProtocolDeclarationsRule,
    symbols: Sequence[RawRecord],
    source_modules: frozenset[str] | None,
) -> list[tuple[RawRecord, str, str | None, tuple[str, ...]]]:
    selected: dict[tuple[str, str], tuple[RawRecord, str, str | None, tuple[str, ...]]] = {}
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
                    if not isinstance(parameter, dict) or parameter.get("name") != selector.name:
                        continue
                    position = f"parameter.{selector.name}"
                    annotation = parameter.get("annotation")
                    annotation = annotation if isinstance(annotation, str) else None
                    selected.setdefault(
                        (symbol["id"], position),
                        (symbol, position, annotation, tuple(symbol["evidence_ids"])),
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
                    selected.setdefault(
                        (symbol["id"], position),
                        (
                            symbol,
                            position,
                            annotation,
                            tuple(evidence) if isinstance(evidence, (tuple, list)) else (),
                        ),
                    )
    return list(selected.values())


def _identity_verdict(
    annotation: str,
    module: str,
    target: tuple[str, str],
    contract: ArchitectureContract,
    exports: dict[str, frozenset[str]],
    imports_by_binding: BindingIndex,
    classes_by_location: BindingIndex,
    type_shapes: TypeShapeIndex,
    optional: bool,
) -> tuple[str, str]:
    if annotation.strip() == "typing.Any" or resolve_named_type(
        annotation, module, imports_by_binding, classes_by_location
    ) == ("typing", "Any"):
        return "FAIL", "broad_any"
    shape = type_shapes.get(annotation)
    if annotation.startswith(("'", '"')) and shape is not None:
        annotation = shape.text
    verdict = _boundary_type_verdict(
        annotation,
        module,
        contract,
        exports,
        imports_by_binding,
        classes_by_location,
        enter_fields=False,
        type_shapes=type_shapes,
    )
    if verdict.undecidable is not None:
        return "UNKNOWN", str(verdict.undecidable)
    arms = _union_parameters(annotation, module, imports_by_binding, type_shapes=type_shapes)
    if arms is not None:
        if not optional:
            return (
                "FAIL",
                "optional_union_not_allowed" if "None" in arms else "wrong_protocol_identity",
            )
        if len(arms) != 2 or arms.count("None") != 1:
            return "FAIL", "wrong_protocol_identity"
        member = next(arm for arm in arms if arm != "None")
        optional_verdict = _boundary_type_verdict(
            member,
            module,
            contract,
            exports,
            imports_by_binding,
            classes_by_location,
            enter_fields=False,
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
        target_module, _, target_name = rule.protocol.rpartition(".")
        target_record = classes_by_location.get((target_module, target_name))
        target_valid = (
            isinstance(target_record, dict)
            and parse_symbol_class_kind(target_record.get("class_kind")) is SymbolClassKind.PROTOCOL
        )
        selected = _selected_positions(rule, symbols, source_modules)
        selected_modules = [
            module
            for module in modules
            if in_scope(module["data"].get("qualified_name", ""), rule.source)
            and (source_modules is None or module["data"].get("qualified_name") in source_modules)
        ]
        if selected and target_valid:
            receipts.append(
                _rule_evaluation_receipt(
                    rule,
                    scope,
                    selected_modules,
                    subjects=sorted({item[0]["data"]["qualified_name"] for item in selected}),
                    data={"protocol": rule.protocol},
                )
            )
        if not selected or not target_valid:
            reason = "empty_scope" if not selected else "protocol_missing_or_ambiguous"
            unknowns.append(
                classified(
                    item_id=stable_id("UNKNOWN-PROTOCOL-DECLARATIONS", rule.id, reason),
                    evidence_class=EvidenceClass.UNKNOWN,
                    area="analysis_coverage",
                    kind="protocol_declaration_limit",
                    title=f"{rule.id} cannot evaluate selected Protocol declarations: {reason}",
                    subjects=[rule.source, rule.protocol],
                    rule_ids=[rule.id],
                    fact_ids=[item["id"] for item in selected_modules],
                    evidence_ids=sorted(
                        {evidence for item in selected_modules for evidence in item["evidence_ids"]}
                    ),
                    data={"source": rule.source, "protocol": rule.protocol, "reason": reason},
                )
            )
            continue
        target = (target_module, target_name)
        for symbol, position, annotation, evidence_ids in selected:
            selector = next(
                selector
                for selector in rule.selectors
                if position == f"{selector.role.value}.{selector.name}"
            )
            if annotation is None:
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
            if isinstance(target_record, dict):
                target_fact = next(
                    (
                        item["id"]
                        for item in symbols
                        if item["data"].get("module") == target_module
                        and item["data"].get("name") == target_name
                        and item["kind"] == "class"
                    ),
                    None,
                )
                if target_fact is not None:
                    facts.append(target_fact)
            if status == "FAIL":
                violations.append(
                    classified(
                        item_id=stable_id("VIO", rule.id, symbol["id"], position),
                        evidence_class=EvidenceClass.VIOLATION,
                        area="api_surface",
                        kind="protocol_declaration",
                        title=(
                            f"{symbol['data']['qualified_name']} {position} "
                            f"does not declare {rule.protocol}"
                        ),
                        subjects=[symbol["data"]["qualified_name"], position, rule.protocol],
                        evidence_ids=list(evidence_ids),
                        rule_ids=[rule.id],
                        fact_ids=facts,
                        data={
                            "qualified_name": symbol["data"]["qualified_name"],
                            "position": position,
                            "annotation": annotation,
                            "protocol": rule.protocol,
                            "reason": reason,
                        },
                    )
                )
            elif status == "UNKNOWN":
                unknowns.append(
                    classified(
                        item_id=stable_id(
                            "UNKNOWN-PROTOCOL-DECLARATION", rule.id, symbol["id"], position
                        ),
                        evidence_class=EvidenceClass.UNKNOWN,
                        area="analysis_coverage",
                        kind="protocol_declaration_limit",
                        title=f"{symbol['data']['qualified_name']} {position} cannot be resolved",
                        subjects=[symbol["data"]["qualified_name"], position, rule.protocol],
                        evidence_ids=list(evidence_ids),
                        rule_ids=[rule.id],
                        fact_ids=facts,
                        data={
                            "qualified_name": symbol["data"]["qualified_name"],
                            "position": position,
                            "protocol": rule.protocol,
                            "reason": reason,
                        },
                    )
                )
    return (
        sorted(violations, key=lambda item: item["id"]),
        sorted(unknowns, key=lambda item: item["id"]),
        receipts,
    )
