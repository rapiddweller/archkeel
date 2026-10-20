# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Validate contract and rule grammar and preserve canonical contract identity."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable
from dataclasses import asdict
from typing import Final, Literal

from archkeel.ir.architecture_graph import (
    ArchitectureRuleKind,
    DecisionMaker,
    NumericOperandForm,
    _validate_module_target_path,
    validate_layout_rule,
    validate_module_target,
)
from archkeel.ir.codec_governance import _measurement_budget_name
from archkeel.ir.codec_wire import (
    _count,
    _exact,
    _has_field,
    _nonempty,
    _object,
    _raw_object,
    _string,
    _strings,
)
from archkeel.ir.contract_version import CONTRACT_SCHEMA_VERSION as CONTRACT_SCHEMA_VERSION
from archkeel.ir.contract_version import ContractFeature, ContractVersion, supports_feature
from archkeel.ir.facts_codec import record_payload
from archkeel.ir.graph_codec import parse_target
from archkeel.ir.model import (
    AllowedDependencyRule,
    ArchitectureContract,
    ArchitectureRule,
    BoundaryAliasBody,
    BoundaryTypeAllowance,
    BoundaryTypesRule,
    BoundedNumericOperandRule,
    CallOwnerRule,
    CompatibilityLifetime,
    CompatibilityShim,
    CompleteAssignmentRule,
    CompleteExternalScopeRule,
    CompleteRequiresRule,
    ComponentRole,
    ConditionSelector,
    ConditionSelectorKind,
    ConstructSelector,
    ConstructSelectorRole,
    ContractCapability,
    ContractCommand,
    ContractComponent,
    ContractDeclarations,
    ContractMeasurementBudget,
    ContractModuleTarget,
    ContractOwner,
    ContractPath,
    ContractPathKind,
    ContractReviewScope,
    CouplingBudget,
    CycleLevel,
    DependencySelector,
    DependencyTargetKind,
    ExternalDependencyScopeRule,
    FacadeBudget,
    ForbiddenCallArgumentRule,
    ForbiddenConstructKind,
    ForbiddenConstructRule,
    ForbiddenDependencyRule,
    ForbiddenEffectUnderConditionRule,
    InterfaceBoundaryRule,
    LayerOrderRule,
    ModuleObjectGrant,
    NoComponentCyclesRule,
    ProtocolDeclarationRole,
    ProtocolDeclarationSelector,
    ProtocolDeclarationsRule,
    ProtocolDeclarationVisibility,
    Record,
    RequiredComponent,
    RootLayoutRule,
    SelectorMatch,
    SiblingIsolationRule,
    SourceOwnershipMode,
    SourceOwnershipRole,
    SourceOwnershipRule,
    SymbolClassKind,
    SymbolPlacementRule,
    TypeIgnoreAllowance,
)
from archkeel.ir.model import ContractInputError as ContractInputError
from archkeel.ir.model import RawJson as RawJson
from archkeel.ir.target_graph import declared_graph

_PUBLIC_ENTRY = re.compile(
    r"^[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*(?::[A-Za-z_][A-Za-z0-9_]*)?$"
)


_PACKAGE_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*$")
_MODULE_SYMBOL = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)+$")


class ContractVersionError(ValueError):
    """The contract declares a schema version this parser cannot interpret."""

    def __init__(self, actual: str) -> None:
        self.actual = actual
        super().__init__(f"contract.schema_version {actual!r} is not {CONTRACT_SCHEMA_VERSION}")


def _contract_fields(
    raw: RawJson, required: set[str], optional: set[str], label: str
) -> dict[str, RawJson]:
    item: dict[str, RawJson] = _object(raw, label)
    if not required <= set(item) or set(item) - required - optional:
        raise ValueError(f"{label} fields mismatch")
    return item


def _decided_by(raw: RawJson, label: str) -> DecisionMaker:
    value = _nonempty(raw, label)
    try:
        return DecisionMaker(value)
    except ValueError as error:
        raise ValueError(f"{label} must be architect or agent") from error


def _contract_strings(raw: RawJson, label: str, *, required: bool = False) -> tuple[str, ...]:
    values = _strings(raw, label)
    if required and not values:
        raise ValueError(f"{label} must not be empty")
    if any(not value.strip() for value in values) or len(set(values)) != len(values):
        raise ValueError(f"{label} must contain unique non-empty strings")
    return values


def _contract_record(
    raw: RawJson, required: set[str], optional: set[str], label: str
) -> tuple[dict[str, RawJson], str, tuple[str, ...]]:
    item = _contract_fields(raw, required | {"id", "provenance"}, optional, label)
    provenance = _contract_strings(item["provenance"], label + ".provenance", required=True)
    return item, _nonempty(item["id"], label + ".id"), provenance


def parse_contract(raw: object) -> ArchitectureContract:
    """Parse Contract 2.0 structure without repository-dependent reference checks."""
    root = _contract_fields(
        _object(raw, "contract"),
        {"schema_version", "components", "rules"},
        {"$schema", "declarations"},
        "contract",
    )
    try:
        version = ContractVersion(_string(root["schema_version"], "contract.schema_version"))
    except ValueError as error:
        raise ContractVersionError(str(root["schema_version"])) from error
    components_raw = root["components"]
    rules_raw = root["rules"]
    if not isinstance(components_raw, list) or not isinstance(rules_raw, list):
        raise ValueError("contract components and rules must be arrays")

    declarations_raw = root.get("declarations")
    declarations = (
        _contract_fields(
            declarations_raw,
            set(),
            {
                "capabilities",
                "review_scopes",
                "public_api",
                "public_api_provenance",
                "public_commands",
                "context_roots",
                "context_roots_provenance",
                "paths",
                "spot_owners",
                "compat",
                "measurement_budgets",
                "facade_budgets",
                "coupling_budgets",
                "modules",
                "uml",
            },
            "contract.declarations",
        )
        if declarations_raw is not None
        else {}
    )

    def records(key: str) -> list[RawJson]:
        value = declarations.get(key, [])
        if not isinstance(value, list):
            raise ValueError(f"contract.declarations.{key} must be an array")
        return value

    capabilities = tuple(
        _parse_capability(value, f"capabilities[{index}]")
        for index, value in enumerate(records("capabilities"))
    )
    components = tuple(
        _parse_component(value, f"components[{index}]", version=version)
        for index, value in enumerate(components_raw)
    )
    for component in components:
        if (
            component.namespace is not None
            and sum(component.namespace in other.packages for other in components) != 1
        ):
            raise ValueError(
                f"component {component.label!r}.namespace must identify one component package"
            )
    scopes = tuple(
        _parse_review_scope(value, f"review_scopes[{index}]")
        for index, value in enumerate(records("review_scopes"))
    )
    commands = tuple(
        _parse_command(value, f"public_commands[{index}]")
        for index, value in enumerate(records("public_commands"))
    )
    paths = tuple(
        _parse_contract_path(value, f"paths[{index}]")
        for index, value in enumerate(records("paths"))
    )
    owners = tuple(
        _parse_owner(value, f"spot_owners[{index}]")
        for index, value in enumerate(records("spot_owners"))
    )
    compat = tuple(
        _parse_compat(value, f"compat[{index}]") for index, value in enumerate(records("compat"))
    )
    if len({item.module for item in compat}) != len(compat):
        raise ValueError("contract.declarations.compat modules must be unique")
    budgets = tuple(
        _parse_measurement_budget(value, f"measurement_budgets[{index}]")
        for index, value in enumerate(records("measurement_budgets"))
    )
    if len({item.name for item in budgets}) != len(budgets):
        raise ValueError("contract.declarations.measurement_budgets repeats a name")
    facade_budgets = (
        tuple(
            _parse_facade_budget(value, f"facade_budgets[{index}]")
            for index, value in enumerate(records("facade_budgets"))
        )
        if _has_field(declarations, "facade_budgets")
        else None
    )
    coupling_budgets = (
        tuple(
            _parse_coupling_budget(value, f"coupling_budgets[{index}]")
            for index, value in enumerate(records("coupling_budgets"))
        )
        if _has_field(declarations, "coupling_budgets")
        else None
    )
    modules = (
        tuple(
            _parse_module_target(value, f"modules[{index}]")
            for index, value in enumerate(records("modules"))
        )
        if _has_field(declarations, "modules")
        else None
    )
    if modules is not None and len({item.path for item in modules}) != len(modules):
        raise ValueError("contract.declarations.modules repeats a path")
    if _has_field(declarations, "uml") and not supports_feature(version, ContractFeature.UML):
        raise ValueError("UML declarations require contract schema_version 2.2.0")
    uml = parse_target(declarations["uml"]) if _has_field(declarations, "uml") else None
    kinds = tuple(_rule_kind(value, f"rules[{index}]") for index, value in enumerate(rules_raw))
    if (
        not supports_feature(version, ContractFeature.BOUNDED_NUMERIC_OPERAND)
        and ArchitectureRuleKind.BOUNDED_NUMERIC_OPERAND in kinds
    ):
        raise ValueError("bounded_numeric_operand requires contract schema_version 3.8.0")
    if (
        not supports_feature(version, ContractFeature.CALL_OWNER)
        and ArchitectureRuleKind.CALL_OWNER in kinds
    ):
        raise ValueError("call_owner requires contract schema_version 3.7.0")
    if (
        not supports_feature(version, ContractFeature.PROTOCOL_DECLARATIONS)
        and ArchitectureRuleKind.PROTOCOL_DECLARATIONS in kinds
    ):
        raise ValueError("protocol_declarations requires contract schema_version 3.9.0")
    if (
        not supports_feature(version, ContractFeature.FORBIDDEN_CALL_ARGUMENT)
        and ArchitectureRuleKind.FORBIDDEN_CALL_ARGUMENT in kinds
    ):
        raise ValueError("forbidden_call_argument requires contract schema_version 3.10.0")
    if not supports_feature(version, ContractFeature.CONSTRUCT_SELECTOR) and any(
        _has_field(_object(value, "rule"), "selector") for value in rules_raw
    ):
        raise ValueError("construct selectors require contract schema_version 3.11.0")
    if (
        not supports_feature(version, ContractFeature.GUARDED_EFFECT)
        and ArchitectureRuleKind.FORBIDDEN_EFFECT_UNDER_CONDITION in kinds
    ):
        raise ValueError("forbidden_effect_under_condition requires contract schema_version 3.13.0")
    if (
        not supports_feature(version, ContractFeature.LAYERS)
        and ArchitectureRuleKind.LAYER_ORDER in kinds
    ):
        raise ValueError("layer_order requires contract schema_version 2.3.0")
    if not supports_feature(version, ContractFeature.MODULE_SELECTORS) and any(
        _has_field(_object(value, "rule"), "source_match")
        or _has_field(_object(value, "rule"), "target_match")
        for value in rules_raw
    ):
        raise ValueError("dependency module selectors require contract schema_version 3.4.0")
    if not supports_feature(version, ContractFeature.IMPORT_NAMESPACES) and any(
        _has_field(_object(value, "rule"), "target_kind") for value in rules_raw
    ):
        raise ValueError("import namespace targets require contract schema_version 3.5.0")
    if (
        not supports_feature(version, ContractFeature.SOURCE_OWNERSHIP)
        and ArchitectureRuleKind.SOURCE_OWNERSHIP in kinds
    ):
        raise ValueError("source_ownership requires contract schema_version 3.12.0")
    if not supports_feature(version, ContractFeature.MODULE_OBJECT_GRANTS) and any(
        _has_field(_object(value, "rule"), "module_object_grants") for value in rules_raw
    ):
        raise ValueError("module_object_grants require contract schema_version 3.6.0")
    rules = tuple(
        _parse_rule(value, f"rules[{index}]", kind)
        for index, (value, kind) in enumerate(zip(rules_raw, kinds, strict=True))
    )
    if not supports_feature(version, ContractFeature.ALIAS_BODY) and any(
        isinstance(rule, BoundaryTypesRule)
        and any(item.alias_body is not None for item in rule.allowed_positions)
        for rule in rules
    ):
        raise ValueError("alias_body requires contract schema_version 3.0.0")
    if not supports_feature(version, ContractFeature.KEY_ALIAS_BODY) and any(
        isinstance(rule, BoundaryTypesRule)
        and any(item.key_alias_body is not None for item in rule.allowed_positions)
        for rule in rules
    ):
        raise ValueError("key_alias_body requires contract schema_version 3.1.0")
    if not supports_feature(version, ContractFeature.LITERAL_MAPPING_ARM) and any(
        isinstance(rule, BoundaryTypesRule)
        and any(item.literal_mapping_arm is not None for item in rule.allowed_positions)
        for rule in rules
    ):
        raise ValueError("literal_mapping_arm requires contract schema_version 3.2.0")
    if not supports_feature(version, ContractFeature.NATIVE_MAPPING) and any(
        isinstance(rule, BoundaryTypesRule)
        and any(
            item.native_mapping
            or (item.literal_mapping_arm is not None and item.container_depth is not None)
            for item in rule.allowed_positions
        )
        for rule in rules
    ):
        raise ValueError(
            "native_mapping and literal-arm object values require contract schema_version 3.3.0"
        )
    labels = {component.label for component in components}
    seen_labels: set[str] = set()
    for component_index, component in enumerate(components):
        if component.label in seen_labels:
            raise ContractInputError(
                f"/components/{component_index}/label",
                component.label,
                f"component label {component.label!r} is not unique in this contract",
            )
        seen_labels.add(component.label)
        for requires_index, entry in enumerate(component.requires or ()):
            if entry.component not in labels:
                raise ContractInputError(
                    f"/components/{component_index}/requires/{requires_index}/component",
                    entry.component,
                    f"{entry.component!r} is not a component label in this contract",
                )
    for index, rule in enumerate(rules):
        if isinstance(rule, NoComponentCyclesRule | LayerOrderRule) and rule.components is not None:
            unknown = sorted(set(rule.components) - labels)
            if unknown:
                raise ValueError(
                    f"rules[{index}].components names no declared component: {unknown}"
                )
    _check_interface_budgets(components, rules, facade_budgets or (), coupling_budgets or ())
    ids = [
        item.id
        for group in (capabilities, components, scopes, commands, paths, owners, rules)
        for item in group
    ]
    if uml is not None:
        ids.extend(entity.id for entity in uml.entities)
        ids.extend(edge.id for edge in uml.relationships)
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate contract ID")
    schema = root.get("$schema")
    contract = ArchitectureContract(
        version,
        components,
        rules,
        _nonempty(schema, "contract.$schema") if schema is not None else None,
        ContractDeclarations(
            capabilities,
            scopes,
            _contract_strings(
                declarations.get("public_api", []), "contract.declarations.public_api"
            ),
            _contract_strings(
                declarations.get("public_api_provenance", []),
                "contract.declarations.public_api_provenance",
            ),
            commands,
            _contract_strings(
                declarations.get("context_roots", []), "contract.declarations.context_roots"
            ),
            _contract_strings(
                declarations.get("context_roots_provenance", []),
                "contract.declarations.context_roots_provenance",
            ),
            paths,
            owners,
            compat,
            budgets,
            facade_budgets,
            coupling_budgets,
            modules,
            uml,
        )
        if declarations_raw is not None
        else None,
    )
    if uml is not None:
        declared_graph(contract)
    return contract


def _validate_encoding_version(contract: ArchitectureContract) -> None:
    if not supports_feature(
        contract.schema_version, ContractFeature.BOUNDED_NUMERIC_OPERAND
    ) and any(isinstance(rule, BoundedNumericOperandRule) for rule in contract.rules):
        raise ValueError("bounded_numeric_operand requires contract schema_version 3.8.0")
    if not supports_feature(contract.schema_version, ContractFeature.CALL_OWNER) and any(
        isinstance(rule, CallOwnerRule) for rule in contract.rules
    ):
        raise ValueError("call_owner requires contract schema_version 3.7.0")
    if not supports_feature(contract.schema_version, ContractFeature.PROTOCOL_DECLARATIONS) and any(
        isinstance(rule, ProtocolDeclarationsRule) for rule in contract.rules
    ):
        raise ValueError("protocol_declarations requires contract schema_version 3.9.0")
    if not supports_feature(
        contract.schema_version, ContractFeature.FORBIDDEN_CALL_ARGUMENT
    ) and any(isinstance(rule, ForbiddenCallArgumentRule) for rule in contract.rules):
        raise ValueError("forbidden_call_argument requires contract schema_version 3.10.0")
    if not supports_feature(contract.schema_version, ContractFeature.GUARDED_EFFECT) and any(
        isinstance(rule, ForbiddenEffectUnderConditionRule) for rule in contract.rules
    ):
        raise ValueError("forbidden_effect_under_condition requires contract schema_version 3.13.0")
    if not supports_feature(contract.schema_version, ContractFeature.CONSTRUCT_SELECTOR) and any(
        isinstance(rule, ForbiddenConstructRule) and rule.selector is not None
        for rule in contract.rules
    ):
        raise ValueError("construct selectors require contract schema_version 3.11.0")
    if not supports_feature(contract.schema_version, ContractFeature.SOURCE_OWNERSHIP) and any(
        isinstance(rule, SourceOwnershipRule) for rule in contract.rules
    ):
        raise ValueError("source_ownership requires contract schema_version 3.12.0")
    if not supports_feature(contract.schema_version, ContractFeature.MODULE_OBJECT_GRANTS) and any(
        isinstance(rule, InterfaceBoundaryRule) and rule.module_object_grants is not None
        for rule in contract.rules
    ):
        raise ValueError("module_object_grants require contract schema_version 3.6.0")
    _validate_layer_feature_version(contract)


def _validate_layer_feature_version(contract: ArchitectureContract) -> None:
    if supports_feature(contract.schema_version, ContractFeature.LAYERS):
        return
    if any(component.layer is not None for component in contract.components) or any(
        isinstance(rule, LayerOrderRule) for rule in contract.rules
    ):
        raise ValueError("layer and layer_order require contract schema_version 2.3.0")
    if not supports_feature(contract.schema_version, ContractFeature.ALIAS_BODY) and any(
        isinstance(rule, BoundaryTypesRule)
        and any(item.alias_body is not None for item in rule.allowed_positions)
        for rule in contract.rules
    ):
        raise ValueError("alias_body requires contract schema_version 3.0.0")
    if not supports_feature(contract.schema_version, ContractFeature.KEY_ALIAS_BODY) and any(
        isinstance(rule, BoundaryTypesRule)
        and any(item.key_alias_body is not None for item in rule.allowed_positions)
        for rule in contract.rules
    ):
        raise ValueError("key_alias_body requires contract schema_version 3.1.0")
    if not supports_feature(contract.schema_version, ContractFeature.LITERAL_MAPPING_ARM) and any(
        isinstance(rule, BoundaryTypesRule)
        and any(item.literal_mapping_arm is not None for item in rule.allowed_positions)
        for rule in contract.rules
    ):
        raise ValueError("literal_mapping_arm requires contract schema_version 3.2.0")
    if not supports_feature(contract.schema_version, ContractFeature.NATIVE_MAPPING) and any(
        isinstance(rule, BoundaryTypesRule)
        and any(
            item.native_mapping
            or (item.literal_mapping_arm is not None and item.container_depth is not None)
            for item in rule.allowed_positions
        )
        for rule in contract.rules
    ):
        raise ValueError(
            "native_mapping and literal-arm object values require contract schema_version 3.3.0"
        )
    if not supports_feature(
        contract.schema_version, ContractFeature.FORBIDDEN_CALL_ARGUMENT
    ) and any(isinstance(rule, ForbiddenCallArgumentRule) for rule in contract.rules):
        raise ValueError("forbidden_call_argument requires contract schema_version 3.10.0")
    if not supports_feature(contract.schema_version, ContractFeature.MODULE_SELECTORS) and any(
        isinstance(rule, ForbiddenDependencyRule)
        and (
            rule.source_match is not SelectorMatch.PREFIX
            or rule.target_match is not SelectorMatch.PREFIX
        )
        for rule in contract.rules
    ):
        raise ValueError("dependency module selectors require contract schema_version 3.4.0")
    if not supports_feature(contract.schema_version, ContractFeature.IMPORT_NAMESPACES) and any(
        isinstance(rule, ForbiddenDependencyRule)
        and rule.target_kind is not DependencyTargetKind.MODULE
        for rule in contract.rules
    ):
        raise ValueError("import namespace targets require contract schema_version 3.5.0")


def contract_bytes(contract: ArchitectureContract) -> bytes:
    """Encode a contract in Contract 2.0 key order so parse_contract returns the same value."""
    _validate_encoding_version(contract)
    fields = asdict(contract)
    # An absent permission must preserve existing amendment digests.
    for rule, encoded in zip(contract.rules, fields["rules"], strict=True):
        if isinstance(rule, ForbiddenDependencyRule):
            for name, default in (
                ("source_match", SelectorMatch.PREFIX),
                ("target_match", SelectorMatch.PREFIX),
                ("target_kind", DependencyTargetKind.MODULE),
            ):
                if encoded[name] == default:
                    del encoded[name]
        if isinstance(rule, BoundaryTypesRule):
            for item, selector in zip(
                rule.allowed_positions, encoded["allowed_positions"], strict=True
            ):
                if not item.native_mapping:
                    encoded_selector: dict[str, object] = selector
                    encoded_selector.pop("native_mapping")
        if isinstance(rule, ForbiddenConstructRule) and not rule.allowed_type_ignores:
            encoded_rule: dict[str, object] = encoded
            encoded_rule.pop("allowed_type_ignores")
    schema = fields.pop("schema")
    document = {**({"$schema": schema} if schema is not None else {}), **fields}
    encoded = _object(_without_none(document), "contract")
    if contract.declarations is not None and contract.declarations.uml is not None:
        declarations = _object(encoded["declarations"], "declarations")
        declarations["uml"] = asdict(contract.declarations.uml)
    text: str = json.dumps(encoded, indent=2, ensure_ascii=False) + "\n"
    return text.encode()


def contract_digest(contract: ArchitectureContract) -> str:
    """The digest an amendment binds to (AD-61): the canonical bytes `contract_bytes` writes."""
    return hashlib.sha256(contract_bytes(contract)).hexdigest()


def absent_contract_digest(path: str) -> str:
    """The digest an amendment binds to for no contract at `path`, a repository path (AD-104).

    A canonical contract is a JSON object, so no contract's bytes begin with the NUL these do;
    the path keeps a record for one introduction from verifying a contract moved to another.
    """
    return hashlib.sha256(b"\0no contract at " + path.encode()).hexdigest()


def _without_none(value: object) -> object:
    if isinstance(value, dict):
        return {key: _without_none(item) for key, item in value.items() if item is not None}
    if isinstance(value, list | tuple):
        return [_without_none(item) for item in value]
    return value


def _parse_capability(raw: RawJson, label: str) -> ContractCapability:
    item, item_id, provenance = _contract_record(
        raw, {"name", "label", "review_order"}, set(), label
    )
    order = item["review_order"]
    if not isinstance(order, int) or isinstance(order, bool) or order < 1:
        raise ValueError(f"{label}.review_order must be a positive integer")
    name = _nonempty(item["name"], f"{label}.name")
    title = _nonempty(item["label"], f"{label}.label")
    return ContractCapability(item_id, name, title, order, provenance)


def _parse_compat(raw: RawJson, label: str) -> CompatibilityShim:
    item = _contract_fields(raw, {"module", "target", "lifetime"}, set(), label)
    module = _string(item["module"], f"{label}.module")
    target = _string(item["target"], f"{label}.target")
    if _PACKAGE_NAME.fullmatch(module) is None:
        raise ValueError(f"{label}.module must be a dotted module name")
    if _PACKAGE_NAME.fullmatch(target) is None:
        raise ValueError(f"{label}.target must be a dotted module name")
    if module == target:
        raise ValueError(f"{label}.module and target must differ")
    lifetime = item["lifetime"]
    if not isinstance(lifetime, str):
        raise ValueError(f"{label}.lifetime must be permanent or migration")
    try:
        parsed_lifetime = CompatibilityLifetime(lifetime)
    except ValueError as error:
        raise ValueError(f"{label}.lifetime must be permanent or migration") from error
    return CompatibilityShim(module, target, parsed_lifetime)


def _parse_module_target(raw: RawJson, label: str) -> ContractModuleTarget:
    item = _contract_fields(raw, {"path", "responsibility"}, set(), label)
    path = _nonempty(item["path"], f"{label}.path")
    try:
        _validate_module_target_path(path)
    except ValueError as error:
        raise ValueError(f"{label}.{error}") from error
    responsibility = _nonempty(item["responsibility"], f"{label}.responsibility")
    target = ContractModuleTarget(path, responsibility)
    try:
        validate_module_target(target)
    except ValueError as error:
        raise ValueError(f"{label}.{error}") from error
    return target


def _public_entry(value: str, label: str) -> str:
    if _PUBLIC_ENTRY.fullmatch(value) is None:
        raise ValueError(f"{label} must be pkg.module or pkg.module:Name")
    return value


def _public_entries(raw: RawJson, label: str) -> tuple[str, ...] | None:
    if raw is None:
        return None
    return tuple(
        _public_entry(value, f"{label}[{index}]")
        for index, value in enumerate(_contract_strings(raw, label))
    )


def parse_required_component(raw: RawJson, label: str = "requires") -> RequiredComponent:
    item = _contract_fields(raw, {"component", "rationale"}, {"through", "decided_by"}, label)
    decided_by = item.get("decided_by")
    return RequiredComponent(
        _nonempty(item["component"], f"{label}.component"),
        _nonempty(item["rationale"], f"{label}.rationale"),
        _contract_strings(item.get("through", []), f"{label}.through"),
        _decided_by(decided_by, f"{label}.decided_by") if decided_by is not None else None,
    )


def _component_names(
    item: dict[str, RawJson], label: str
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    packages = _contract_strings(item["packages"], f"{label}.packages")
    exact = (
        _contract_strings(item["exact_modules"], f"{label}.exact_modules")
        if _has_field(item, "exact_modules")
        else ()
    )
    if any(re.fullmatch(_PACKAGE_NAME.pattern, name) is None for name in exact):
        raise ValueError(f"{label}.exact_modules must contain dotted identifiers")
    if not packages and not exact:
        raise ValueError(f"{label} must claim at least one package or exact module")
    return packages, exact


def _parse_component(raw: RawJson, label: str, *, version: ContractVersion) -> ContractComponent:
    if _has_field(_object(raw, label), "layer") and not supports_feature(
        version, ContractFeature.LAYERS
    ):
        raise ValueError(f"{label}.layer requires contract schema_version 2.3.0")
    item, item_id, provenance = _contract_record(
        raw,
        {"label", "role", "packages", "responsibilities", "forbidden_responsibilities"},
        {
            "capability_id",
            "decided_by",
            "inside",
            "planned",
            "public",
            "requires",
            "namespace",
            "exact_modules",
            "layer",
        },
        label,
    )
    try:
        role = ComponentRole(_string(item["role"], f"{label}.role"))
    except ValueError as exc:
        raise ValueError(f"{label}.role is invalid") from exc
    capability = item.get("capability_id")
    public = _public_entries(item.get("public"), f"{label}.public")
    planned = _public_entries(item.get("planned"), f"{label}.planned")
    requires_raw = item.get("requires")
    if requires_raw is not None and not isinstance(requires_raw, list):
        raise ValueError(f"{label}.requires must be a list")
    requires = (
        tuple(
            parse_required_component(value, f"{label}.requires[{index}]")
            for index, value in enumerate(requires_raw)
        )
        if requires_raw is not None
        else None
    )
    inside = item.get("inside")
    decided_by = item.get("decided_by")
    packages, exact_modules = _component_names(item, label)
    namespace_raw = item.get("namespace")
    namespace = (
        _nonempty(namespace_raw, f"{label}.namespace") if namespace_raw is not None else None
    )
    if namespace is not None and _PACKAGE_NAME.fullmatch(namespace) is None:
        raise ValueError(f"{label}.namespace must be a dotted Python package")
    if namespace is not None and namespace not in packages:
        raise ValueError(f"{label}.namespace must name one of {label}.packages")
    return ContractComponent(
        item_id,
        _nonempty(item["label"], f"{label}.label"),
        role,
        packages,
        _contract_strings(item["responsibilities"], f"{label}.responsibilities"),
        _contract_strings(
            item["forbidden_responsibilities"], f"{label}.forbidden_responsibilities"
        ),
        provenance,
        _nonempty(capability, f"{label}.capability_id") if capability is not None else None,
        requires,
        _nonempty(inside, f"{label}.inside") if inside is not None else None,
        public,
        planned,
        _decided_by(decided_by, f"{label}.decided_by") if decided_by is not None else None,
        namespace,
        exact_modules or None,
        _nonempty(item["layer"], f"{label}.layer") if _has_field(item, "layer") else None,
    )


def _parse_review_scope(raw: RawJson, label: str) -> ContractReviewScope:
    item, item_id, provenance = _contract_record(
        raw, {"label", "parent_id", "subjects"}, set(), label
    )
    title = _nonempty(item["label"], f"{label}.label")
    parent_id = _nonempty(item["parent_id"], f"{label}.parent_id")
    subjects = _contract_strings(item["subjects"], f"{label}.subjects", required=True)
    return ContractReviewScope(item_id, title, parent_id, subjects, provenance)


def _parse_command(raw: RawJson, label: str) -> ContractCommand:
    item, item_id, provenance = _contract_record(raw, {"command", "description"}, set(), label)
    command = _nonempty(item["command"], f"{label}.command")
    description = _nonempty(item["description"], f"{label}.description")
    return ContractCommand(item_id, command, description, provenance)


def _parse_contract_path(raw: RawJson, label: str) -> ContractPath:
    item, item_id, provenance = _contract_record(raw, {"label", "kind", "steps"}, set(), label)
    try:
        kind = ContractPathKind(_string(item["kind"], f"{label}.kind"))
    except ValueError as exc:
        raise ValueError(f"{label}.kind is invalid") from exc
    title = _nonempty(item["label"], f"{label}.label")
    steps = _contract_strings(item["steps"], f"{label}.steps", required=True)
    return ContractPath(item_id, title, kind, steps, provenance)


def _parse_owner(raw: RawJson, label: str) -> ContractOwner:
    item, item_id, provenance = _contract_record(
        raw, {"label", "owner", "responsibility"}, set(), label
    )
    title = _nonempty(item["label"], f"{label}.label")
    owner = _nonempty(item["owner"], f"{label}.owner")
    responsibility = _nonempty(item["responsibility"], f"{label}.responsibility")
    return ContractOwner(item_id, title, owner, responsibility, provenance)


def _parse_measurement_budget(raw: RawJson, label: str) -> ContractMeasurementBudget:
    item = _contract_fields(raw, {"name", "provenance"}, set(), label)
    return ContractMeasurementBudget(
        _measurement_budget_name(item["name"], f"{label}.name"),
        _contract_strings(item["provenance"], f"{label}.provenance", required=True),
    )


def _parse_facade_budget(raw: RawJson, label: str) -> FacadeBudget:
    item = _contract_fields(raw, {"component", "max_names", "provenance"}, set(), label)
    return FacadeBudget(
        _nonempty(item["component"], f"{label}.component"),
        _count(item["max_names"], f"{label}.max_names"),
        _contract_strings(item["provenance"], f"{label}.provenance", required=True),
    )


def _parse_coupling_budget(raw: RawJson, label: str) -> CouplingBudget:
    item = _contract_fields(raw, {"source", "target", "max_names", "provenance"}, set(), label)
    return CouplingBudget(
        _nonempty(item["source"], f"{label}.source"),
        _nonempty(item["target"], f"{label}.target"),
        _count(item["max_names"], f"{label}.max_names"),
        _contract_strings(item["provenance"], f"{label}.provenance", required=True),
    )


def _budget_component(public: dict[str, bool], label: str, component: str, *, facade: bool) -> None:
    if component not in public:
        raise ValueError(f"contract.declarations.{label} names no component: {component!r}")
    if facade and not public[component]:
        raise ValueError(f"contract.declarations.{label} {component!r} declares no public facade")


def _check_interface_budgets(
    components: tuple[ContractComponent, ...],
    rules: tuple[ArchitectureRule, ...],
    facades: tuple[FacadeBudget, ...],
    pairs: tuple[CouplingBudget, ...],
) -> None:
    """AD-99: a budget counts a declared facade, so an unknown key is an error, not a PASS.

    A pair counts only names its source reaches through the target's facade. An import past
    the facade, `TYPE_CHECKING` ones included, must therefore be an `interface_boundary`
    finding instead, or the budget would pass on names it never saw.
    """
    public = {item.label: item.public is not None for item in components}
    if pairs and not any(
        isinstance(rule, InterfaceBoundaryRule) and rule.include_type_checking for rule in rules
    ):
        raise ValueError(
            "contract.declarations.coupling_budgets need an interface_boundary rule that "
            "includes TYPE_CHECKING imports, or an import past the facade is counted nowhere"
        )
    for index, budget in enumerate(facades):
        _budget_component(
            public, f"facade_budgets[{index}].component", budget.component, facade=True
        )
    for index, pair in enumerate(pairs):
        _budget_component(public, f"coupling_budgets[{index}].source", pair.source, facade=False)
        _budget_component(public, f"coupling_budgets[{index}].target", pair.target, facade=True)
        if pair.source == pair.target:
            raise ValueError(
                f"contract.declarations.coupling_budgets[{index}] names one component twice"
            )
    for key, subjects in (
        ("facade_budgets", [item.subject for item in facades]),
        ("coupling_budgets", [item.subject for item in pairs]),
    ):
        repeated = sorted({subject for subject in subjects if subjects.count(subject) > 1})
        if repeated:
            raise ValueError(f"contract.declarations.{key} repeats {repeated[0]!r}")


def _parse_forbidden_dependency(raw: RawJson, label: str) -> ForbiddenDependencyRule:
    item, item_id, provenance = _contract_record(
        raw,
        {"kind", "source", "target", "include_type_checking", "rationale", "decided_by"},
        {"target_symbol", "allowed_sources", "source_match", "target_match", "target_kind"},
        label,
    )
    include = item["include_type_checking"]
    if not isinstance(include, bool):
        raise ValueError(f"{label}.include_type_checking must be a boolean")
    selected = _dependency_selector(item, label)
    rationale = _nonempty(item["rationale"], f"{label}.rationale")
    decided_by = _decided_by(item["decided_by"], f"{label}.decided_by")
    allowed = _contract_strings(item.get("allowed_sources", []), f"{label}.allowed_sources")

    return ForbiddenDependencyRule(
        item_id,
        ArchitectureRuleKind.FORBIDDEN_DEPENDENCY,
        selected.source,
        selected.target,
        include,
        rationale,
        provenance,
        decided_by,
        selected.target_symbol,
        allowed,
        selected.source_match,
        selected.target_match,
        selected.target_kind,
    )


def _dependency_selector(data: dict[str, RawJson], label: str) -> DependencySelector:
    symbol = data.get("target_symbol")
    if symbol is not None and (not isinstance(symbol, str) or not symbol.isidentifier()):
        raise ValueError(f"{label}.target_symbol must be an identifier")
    return DependencySelector(
        _nonempty(data.get("source"), f"{label}.source"),
        _nonempty(data.get("target"), f"{label}.target"),
        symbol,
        SelectorMatch(
            _string(data.get("source_match", SelectorMatch.PREFIX), f"{label}.source_match")
        ),
        SelectorMatch(
            _string(data.get("target_match", SelectorMatch.PREFIX), f"{label}.target_match")
        ),
        DependencyTargetKind(
            _string(data.get("target_kind", DependencyTargetKind.MODULE), f"{label}.target_kind")
        ),
    )


def parse_dependency_selector(record: Record) -> DependencySelector:
    """Decode a dependency selector once at the record-to-model boundary."""
    data = _object(record_payload(record)["data"], "dependency declaration")
    return _dependency_selector(data, "dependency declaration")


def _parse_allowed_dependency(raw: RawJson, label: str) -> AllowedDependencyRule:
    item, item_id, provenance = _contract_record(
        raw, {"kind", "source", "target", "rationale", "decided_by"}, set(), label
    )
    return AllowedDependencyRule(
        item_id,
        ArchitectureRuleKind.ALLOWED_DEPENDENCY,
        _nonempty(item["source"], f"{label}.source"),
        _nonempty(item["target"], f"{label}.target"),
        _nonempty(item["rationale"], f"{label}.rationale"),
        provenance,
        _decided_by(item["decided_by"], f"{label}.decided_by"),
    )


def _parse_forbidden_construct(raw: RawJson, label: str) -> ForbiddenConstructRule:
    item, item_id, provenance = _contract_record(
        raw,
        {"kind", "source", "constructs", "rationale", "decided_by"},
        {"allowed_sources", "exact_sources", "allowed_type_ignores", "selector"},
        label,
    )
    raw_constructs = _contract_strings(item["constructs"], f"{label}.constructs", required=True)
    try:
        constructs = tuple(ForbiddenConstructKind(value) for value in raw_constructs)
    except ValueError as exc:
        raise ValueError(f"{label}.constructs contains an unsupported construct") from exc
    allowed = _contract_strings(item.get("allowed_sources", []), f"{label}.allowed_sources")
    exact = _contract_strings(item.get("exact_sources", []), f"{label}.exact_sources")
    raw_ignores = item.get("allowed_type_ignores", [])
    if not isinstance(raw_ignores, list):
        raise ValueError(f"{label}.allowed_type_ignores must be an array")
    ignores: list[TypeIgnoreAllowance] = []
    for index, value in enumerate(raw_ignores):
        entry_label = f"{label}.allowed_type_ignores[{index}]"
        entry = _exact(value, {"qualified_name", "line", "statement", "tag"}, entry_label)
        line = entry["line"]
        if not isinstance(line, int) or isinstance(line, bool) or line < 1:
            raise ValueError(f"{entry_label}.line must be a positive integer")
        ignores.append(
            TypeIgnoreAllowance(
                _nonempty(entry["qualified_name"], f"{entry_label}.qualified_name"),
                line,
                _nonempty(entry["statement"], f"{entry_label}.statement"),
                _nonempty(entry["tag"], f"{entry_label}.tag"),
            )
        )
    if len(set(ignores)) != len(ignores):
        raise ValueError(f"{label}.allowed_type_ignores must contain unique entries")
    selector = _parse_construct_selector(item, label)
    return ForbiddenConstructRule(
        item_id,
        ArchitectureRuleKind.FORBIDDEN_CONSTRUCT,
        _nonempty(item["source"], f"{label}.source"),
        constructs,
        _nonempty(item["rationale"], f"{label}.rationale"),
        provenance,
        _decided_by(item["decided_by"], f"{label}.decided_by"),
        allowed,
        exact,
        tuple(ignores),
        selector,
    )


def _qualified_names(raw: RawJson, label: str, *, required: bool = False) -> tuple[str, ...]:
    values = _contract_strings(raw, label, required=required)
    if any(not all(part.isidentifier() for part in value.split(".")) for value in values):
        raise ValueError(f"{label} must contain qualified identifiers")
    return values


def _parse_source_ownership(raw: RawJson, label: str) -> SourceOwnershipRule:
    item, item_id, provenance = _contract_record(
        raw,
        {"kind", "source", "mode", "roles", "rationale", "decided_by"},
        {"symbols", "parameters", "owner", "value_owner"},
        label,
    )
    try:
        mode = SourceOwnershipMode(_string(item["mode"], f"{label}.mode"))
        roles = tuple(
            SourceOwnershipRole(value)
            for value in _contract_strings(item["roles"], f"{label}.roles", required=True)
        )
    except ValueError as error:
        raise ValueError(f"{label}.mode or roles contains an unsupported value") from error
    if len(set(roles)) != len(roles):
        raise ValueError(f"{label}.roles must contain unique values")
    symbols = _qualified_names(item.get("symbols", []), f"{label}.symbols")
    parameters = _qualified_names(item.get("parameters", []), f"{label}.parameters")
    if any(not value.rpartition(".")[0] for value in parameters):
        raise ValueError(f"{label}.parameters must name function.parameter")
    owner = item.get("owner")
    owner = _nonempty(owner, f"{label}.owner") if owner is not None else None
    value_owner = item.get("value_owner")
    value_owner = (
        _nonempty(value_owner, f"{label}.value_owner") if value_owner is not None else None
    )
    symbol_roles = {
        SourceOwnershipRole.DEFINITION,
        SourceOwnershipRole.READ,
        SourceOwnershipRole.WRITE,
        SourceOwnershipRole.DELETE,
        SourceOwnershipRole.VALUE_TRANSFER,
    }
    parameter_roles = {SourceOwnershipRole.PARAMETER_DEFAULT, SourceOwnershipRole.FALLBACK}
    selected_symbol_roles = set(roles) & symbol_roles
    selected_parameter_roles = set(roles) & parameter_roles
    if bool(symbols) != bool(selected_symbol_roles) or bool(parameters) != bool(
        selected_parameter_roles
    ):
        raise ValueError(f"{label} selectors must match their selected roles")
    if mode is SourceOwnershipMode.RETIRED:
        if (
            (
                set(roles)
                - {
                    SourceOwnershipRole.DEFINITION,
                    SourceOwnershipRole.READ,
                    SourceOwnershipRole.WRITE,
                    SourceOwnershipRole.DELETE,
                }
            )
            or owner is not None
            or value_owner is not None
        ):
            raise ValueError(
                f"{label}.retired cannot select owners, parameters, defaults, or fallbacks"
            )
    elif (bool(selected_symbol_roles) != (owner is not None)) or (
        bool(selected_parameter_roles) != (value_owner is not None)
    ):
        raise ValueError(f"{label}.confined needs the owner for every selected role")
    return SourceOwnershipRule(
        item_id,
        ArchitectureRuleKind.SOURCE_OWNERSHIP,
        _nonempty(item["source"], f"{label}.source"),
        mode,
        roles,
        _nonempty(item["rationale"], f"{label}.rationale"),
        provenance,
        _decided_by(item["decided_by"], f"{label}.decided_by"),
        symbols,
        parameters,
        owner,
        value_owner,
    )


def _parse_construct_selector(item: dict[str, RawJson], label: str) -> ConstructSelector | None:
    if not _has_field(item, "selector"):
        return None
    selected = _contract_fields(
        _object(item["selector"], f"{label}.selector"),
        {"receiver", "role"},
        {"member", "literal"},
        f"{label}.selector",
    )
    try:
        role = ConstructSelectorRole(_nonempty(selected["role"], f"{label}.selector.role"))
    except ValueError as exc:
        raise ValueError(f"{label}.selector.role is unsupported") from exc
    receiver = _nonempty(selected["receiver"], f"{label}.selector.receiver")
    member_value = selected.get("member")
    member = (
        _nonempty(member_value, f"{label}.selector.member") if member_value is not None else None
    )
    literal = selected.get("literal")
    if literal is not None and not isinstance(literal, str):
        raise ValueError(f"{label}.selector.literal must be a string")
    literal_roles = {
        ConstructSelectorRole.EQUALITY,
        ConstructSelectorRole.MEMBERSHIP,
        ConstructSelectorRole.MATCH,
        ConstructSelectorRole.STARTSWITH,
        ConstructSelectorRole.ENDSWITH,
    }
    access_roles = {
        ConstructSelectorRole.READ,
        ConstructSelectorRole.WRITE,
        ConstructSelectorRole.CALL,
    }
    if role in access_roles and literal is not None:
        raise ValueError(f"{label}.selector.literal is not valid for access roles")
    memberless_roles = {ConstructSelectorRole.CONSTRUCTOR, ConstructSelectorRole.TYPE_PROBE}
    if (role in memberless_roles) == (member is not None):
        raise ValueError(f"{label}.selector.member is required for member roles")
    if (role in literal_roles) != (literal is not None):
        raise ValueError(f"{label}.selector.literal is required only for operand roles")
    if not all(part.isidentifier() for part in receiver.split(".")) or (
        member is not None and not member.isidentifier()
    ):
        raise ValueError(f"{label}.selector receiver and member must be qualified identifiers")
    return ConstructSelector(receiver, member, role, literal)


def _parse_external_dependency_scope(raw: RawJson, label: str) -> ExternalDependencyScopeRule:
    item, item_id, provenance = _contract_record(
        raw,
        {"kind", "dependency", "rationale", "decided_by"},
        {"allowed_sources", "exact_sources"},
        label,
    )
    dependency = _nonempty(item["dependency"], f"{label}.dependency")
    if (
        not dependency.isidentifier()
        and re.fullmatch(r"(?:@[a-z0-9_-]+/)?[a-z0-9][a-z0-9._-]*", dependency) is None
    ):
        raise ValueError(f"{label}.dependency must be an import name or package identity")
    allowed = _contract_strings(item.get("allowed_sources", []), f"{label}.allowed_sources")
    exact = _contract_strings(item.get("exact_sources", []), f"{label}.exact_sources")
    if not allowed and not exact:
        raise ValueError(f"{label} must name allowed_sources or exact_sources")
    return ExternalDependencyScopeRule(
        item_id,
        ArchitectureRuleKind.EXTERNAL_DEPENDENCY_SCOPE,
        dependency,
        allowed,
        _nonempty(item["rationale"], f"{label}.rationale"),
        provenance,
        _decided_by(item["decided_by"], f"{label}.decided_by"),
        exact,
    )


def _parse_complete_assignment(raw: RawJson, label: str) -> CompleteAssignmentRule:
    item, item_id, provenance = _contract_record(
        raw, {"kind", "source", "rationale", "decided_by"}, set(), label
    )
    return CompleteAssignmentRule(
        item_id,
        ArchitectureRuleKind.COMPLETE_ASSIGNMENT,
        _nonempty(item["source"], f"{label}.source"),
        _nonempty(item["rationale"], f"{label}.rationale"),
        provenance,
        _decided_by(item["decided_by"], f"{label}.decided_by"),
    )


def _parse_root_layout(raw: RawJson, label: str) -> RootLayoutRule:
    item, item_id, provenance = _contract_record(
        raw, {"kind", "root", "allowed_children", "rationale", "decided_by"}, set(), label
    )
    root = _nonempty(item["root"], f"{label}.root")
    allowed_children = _contract_strings(item["allowed_children"], f"{label}.allowed_children")
    rule = RootLayoutRule(
        item_id,
        ArchitectureRuleKind.ROOT_LAYOUT,
        root,
        allowed_children,
        _nonempty(item["rationale"], f"{label}.rationale"),
        provenance,
        _decided_by(item["decided_by"], f"{label}.decided_by"),
    )
    try:
        validate_layout_rule(rule)
    except ValueError as error:
        raise ValueError(f"{label}.{error}") from error
    return rule


def _parse_complete_external_scope(raw: RawJson, label: str) -> CompleteExternalScopeRule:
    item, item_id, provenance = _contract_record(
        raw, {"kind", "source", "rationale", "decided_by"}, set(), label
    )
    return CompleteExternalScopeRule(
        item_id,
        ArchitectureRuleKind.COMPLETE_EXTERNAL_SCOPE,
        _nonempty(item["source"], f"{label}.source"),
        _nonempty(item["rationale"], f"{label}.rationale"),
        provenance,
        _decided_by(item["decided_by"], f"{label}.decided_by"),
    )


def _parse_complete_requires(raw: RawJson, label: str) -> CompleteRequiresRule:
    item, item_id, provenance = _contract_record(
        raw, {"kind", "rationale", "decided_by"}, {"include_type_checking"}, label
    )
    include = item.get("include_type_checking", True)
    if not isinstance(include, bool):
        raise ValueError(f"{label}.include_type_checking must be a boolean")
    return CompleteRequiresRule(
        item_id,
        ArchitectureRuleKind.COMPLETE_REQUIRES,
        _nonempty(item["rationale"], f"{label}.rationale"),
        provenance,
        _decided_by(item["decided_by"], f"{label}.decided_by"),
        include,
    )


def _parse_layer_order(raw: RawJson, label: str) -> LayerOrderRule:
    item, item_id, provenance = _contract_record(
        raw, {"kind", "layers", "rationale", "decided_by"}, {"components"}, label
    )
    layers = _contract_strings(item["layers"], f"{label}.layers", required=True)
    return LayerOrderRule(
        item_id,
        ArchitectureRuleKind.LAYER_ORDER,
        layers,
        _nonempty(item["rationale"], f"{label}.rationale"),
        provenance,
        _decided_by(item["decided_by"], f"{label}.decided_by"),
        _contract_strings(item["components"], f"{label}.components", required=True)
        if _has_field(item, "components")
        else None,
    )


def _cycle_level(raw: RawJson, label: str) -> Literal[CycleLevel.MODULE] | None:
    value = _nonempty(raw, label)
    try:
        level = CycleLevel(value)
    except ValueError as error:
        raise ValueError(f"{label} must be component or module") from error
    return None if level is CycleLevel.COMPONENT else level


def _parse_no_component_cycles(raw: RawJson, label: str) -> NoComponentCyclesRule:
    item, item_id, provenance = _contract_record(
        raw, {"kind", "rationale", "decided_by"}, {"level", "components"}, label
    )
    level = item.get("level")
    components = item.get("components")
    return NoComponentCyclesRule(
        item_id,
        ArchitectureRuleKind.NO_COMPONENT_CYCLES,
        _nonempty(item["rationale"], f"{label}.rationale"),
        provenance,
        _decided_by(item["decided_by"], f"{label}.decided_by"),
        _cycle_level(level, f"{label}.level") if level is not None else None,
        _contract_strings(components, f"{label}.components", required=True)
        if components is not None
        else None,
    )


def _parse_module_object_grants(raw: RawJson, label: str) -> tuple[ModuleObjectGrant, ...]:
    if not isinstance(raw, list):
        raise ValueError(f"{label} must be an array")
    grants = []
    for index, value in enumerate(raw):
        entry_label = f"{label}[{index}]"
        entry = _contract_fields(value, {"source_module", "target_module"}, set(), entry_label)
        source = _string(entry["source_module"], f"{entry_label}.source_module")
        target = _string(entry["target_module"], f"{entry_label}.target_module")
        for field, module in (("source_module", source), ("target_module", target)):
            if re.fullmatch(_PACKAGE_NAME.pattern, module) is None:
                raise ValueError(f"{entry_label}.{field} must be a dotted module name")
        grants.append(ModuleObjectGrant(source, target))
    if len(set(grants)) != len(grants):
        raise ValueError(f"{label} must contain unique entries")
    return tuple(grants)


def _parse_interface_boundary(raw: RawJson, label: str) -> InterfaceBoundaryRule:
    item, item_id, provenance = _contract_record(
        raw,
        {"kind", "rationale", "decided_by"},
        {"include_type_checking", "module_object_grants"},
        label,
    )
    include = item.get("include_type_checking", True)
    if not isinstance(include, bool):
        raise ValueError(f"{label}.include_type_checking must be a boolean")
    grants = (
        _parse_module_object_grants(item["module_object_grants"], f"{label}.module_object_grants")
        if _has_field(item, "module_object_grants")
        else None
    )
    return InterfaceBoundaryRule(
        item_id,
        ArchitectureRuleKind.INTERFACE_BOUNDARY,
        _nonempty(item["rationale"], f"{label}.rationale"),
        provenance,
        _decided_by(item["decided_by"], f"{label}.decided_by"),
        include,
        grants,
    )


def _parse_sibling_isolation(raw: RawJson, label: str) -> SiblingIsolationRule:
    item, item_id, provenance = _contract_record(
        raw, {"kind", "members", "rationale", "decided_by"}, {"include_type_checking"}, label
    )
    members = _contract_strings(item["members"], f"{label}.members", required=True)
    if len(members) < 2:
        raise ValueError(f"{label}.members must name at least two peers")
    include = item.get("include_type_checking", True)
    if not isinstance(include, bool):
        raise ValueError(f"{label}.include_type_checking must be a boolean")
    return SiblingIsolationRule(
        item_id,
        ArchitectureRuleKind.SIBLING_ISOLATION,
        members,
        _nonempty(item["rationale"], f"{label}.rationale"),
        provenance,
        _decided_by(item["decided_by"], f"{label}.decided_by"),
        include,
    )


def _parse_symbol_placement(raw: RawJson, label: str) -> SymbolPlacementRule:
    item, item_id, provenance = _contract_record(
        raw,
        {"kind", "source", "class_kinds", "rationale", "decided_by"},
        {"allowed_sources", "exact_sources"},
        label,
    )
    raw_kinds = _contract_strings(item["class_kinds"], f"{label}.class_kinds", required=True)
    try:
        class_kinds = tuple(SymbolClassKind(value) for value in raw_kinds)
    except ValueError as exc:
        raise ValueError(f"{label}.class_kinds contains an unsupported class kind") from exc
    allowed = _contract_strings(item.get("allowed_sources", []), f"{label}.allowed_sources")
    exact = _contract_strings(item.get("exact_sources", []), f"{label}.exact_sources")
    if not allowed and not exact:
        raise ValueError(f"{label} must name allowed_sources or exact_sources")
    return SymbolPlacementRule(
        item_id,
        ArchitectureRuleKind.SYMBOL_PLACEMENT,
        _nonempty(item["source"], f"{label}.source"),
        class_kinds,
        _nonempty(item["rationale"], f"{label}.rationale"),
        provenance,
        _decided_by(item["decided_by"], f"{label}.decided_by"),
        allowed,
        exact,
    )


# Bare mappings do not name their members; exact object payloads explicitly accept opacity.


def _parse_boundary_type_allowance(value: RawJson, label: str) -> BoundaryTypeAllowance:
    entry = _contract_fields(
        value,
        {"qualified_name", "position", "annotation"},
        {
            "field_path",
            "container_depth",
            "mapping_depth",
            "alias_body",
            "key_alias_body",
            "literal_mapping_arm",
            "native_mapping",
        },
        label,
    )
    qualified_name = _nonempty(entry["qualified_name"], f"{label}.qualified_name")
    position = _nonempty(entry["position"], f"{label}.position")
    raw_field_path = entry.get("field_path", "")
    field_path = (
        ""
        if isinstance(raw_field_path, str) and not raw_field_path
        else _nonempty(raw_field_path, f"{label}.field_path")
    )
    annotation = _nonempty(entry["annotation"], f"{label}.annotation")
    depth: int | None = None
    if _has_field(entry, "container_depth"):
        raw_depth = entry["container_depth"]
        if isinstance(raw_depth, bool) or not isinstance(raw_depth, int) or raw_depth < 1:
            raise ValueError(f"{label}.container_depth must be a positive integer")
        depth = raw_depth
    mapping_depth: int | None = None
    if _has_field(entry, "mapping_depth"):
        raw_mapping_depth = entry["mapping_depth"]
        if type(raw_mapping_depth) is not int or raw_mapping_depth < 1:
            raise ValueError(f"{label}.mapping_depth must be a positive integer")
        mapping_depth = raw_mapping_depth
        if field_path:
            raise ValueError(f"{label}.mapping_depth cannot select a DTO field")
        if depth is not None and depth != mapping_depth + 1:
            raise ValueError(f"{label}.container_depth must be mapping_depth plus one")
    alias_body: BoundaryAliasBody | None = None
    if _has_field(entry, "alias_body"):
        body_label = f"{label}.alias_body"
        body = _exact(entry["alias_body"], {"origin", "shape"}, body_label)
        alias_body = BoundaryAliasBody(
            _nonempty(body["origin"], f"{body_label}.origin"),
            _nonempty(body["shape"], f"{body_label}.shape"),
        )
        if field_path or mapping_depth is not None:
            raise ValueError(f"{body_label} requires empty field_path and absent mapping_depth")
    key_alias_body: BoundaryAliasBody | None = None
    if _has_field(entry, "key_alias_body"):
        body_label = f"{label}.key_alias_body"
        body = _exact(entry["key_alias_body"], {"origin", "shape"}, body_label)
        key_alias_body = BoundaryAliasBody(
            _nonempty(body["origin"], f"{body_label}.origin"),
            _nonempty(body["shape"], f"{body_label}.shape"),
        )
        if field_path or depth is not None or mapping_depth is not None:
            raise ValueError(
                f"{body_label} requires empty field_path and absent container_depth/mapping_depth"
            )
    literal_mapping_arm = _parse_literal_mapping_arm(entry, field_path, label)
    native_mapping = _parse_native_mapping(entry, annotation, label)
    if re.fullmatch(r"dict", annotation) is not None and not native_mapping:
        raise ValueError(f"{label}.annotation cannot allow bare dict")
    if not field_path and re.fullmatch(r"(?:Dict|Mapping|MutableMapping)", annotation) is not None:
        raise ValueError(f"{label}.annotation cannot allow bare {annotation} at the root")
    return BoundaryTypeAllowance(
        qualified_name,
        position,
        field_path,
        annotation,
        depth,
        mapping_depth,
        alias_body,
        key_alias_body,
        literal_mapping_arm,
        native_mapping,
    )


def _parse_native_mapping(entry: dict[str, RawJson], annotation: str, label: str) -> bool:
    if not _has_field(entry, "native_mapping"):
        return False
    if entry["native_mapping"] is not True:
        raise ValueError(f"{label}.native_mapping must be true")
    if re.fullmatch(r"(?:dict(?: \| None)?|list\[dict\])", annotation) is None or any(
        name in entry
        for name in (
            "container_depth",
            "mapping_depth",
            "alias_body",
            "key_alias_body",
            "literal_mapping_arm",
        )
    ):
        raise ValueError(f"{label}.native_mapping requires an exact bare dict shape only")
    return True


def _parse_literal_mapping_arm(
    entry: dict[str, RawJson],
    field_path: str,
    label: str,
) -> str | None:
    if not _has_field(entry, "literal_mapping_arm"):
        return None
    arm = _nonempty(entry["literal_mapping_arm"], f"{label}.literal_mapping_arm")
    if field_path or any(
        name in entry
        for name in ("mapping_depth", "alias_body", "key_alias_body", "native_mapping")
    ):
        raise ValueError(
            f"{label}.literal_mapping_arm requires empty field_path and no other selectors"
        )
    return arm


def _parse_boundary_types(raw: RawJson, label: str) -> BoundaryTypesRule:
    item, item_id, provenance = _contract_record(
        raw,
        {"kind", "source", "rationale", "decided_by"},
        {"allowed_sources", "exact_sources", "allowed_positions"},
        label,
    )
    allowed = _contract_strings(item.get("allowed_sources", []), f"{label}.allowed_sources")
    exact = _contract_strings(item.get("exact_sources", []), f"{label}.exact_sources")
    raw_positions = item.get("allowed_positions", [])
    if not isinstance(raw_positions, list):
        raise ValueError(f"{label}.allowed_positions must be an array")
    positions: list[BoundaryTypeAllowance] = []
    for index, value in enumerate(raw_positions):
        positions.append(
            _parse_boundary_type_allowance(value, f"{label}.allowed_positions[{index}]")
        )
    if len(set(positions)) != len(positions):
        raise ValueError(f"{label}.allowed_positions must contain unique entries")
    return BoundaryTypesRule(
        item_id,
        ArchitectureRuleKind.BOUNDARY_TYPES,
        _nonempty(item["source"], f"{label}.source"),
        _nonempty(item["rationale"], f"{label}.rationale"),
        provenance,
        _decided_by(item["decided_by"], f"{label}.decided_by"),
        allowed,
        exact,
        tuple(positions),
    )


def _parse_protocol_declarations(raw: RawJson, label: str) -> ProtocolDeclarationsRule:
    item, item_id, provenance = _contract_record(
        raw,
        {"kind", "source", "protocol", "selectors", "rationale", "decided_by"},
        set(),
        label,
    )
    source = _nonempty(item["source"], f"{label}.source")
    protocol = _nonempty(item["protocol"], f"{label}.protocol")
    if _PACKAGE_NAME.fullmatch(source) is None:
        raise ValueError(f"{label}.source must be a dotted source identity")
    if _MODULE_SYMBOL.fullmatch(protocol) is None:
        raise ValueError(f"{label}.protocol must be a canonical module.symbol")
    raw_selectors = item["selectors"]
    if not isinstance(raw_selectors, list) or not raw_selectors:
        raise ValueError(f"{label}.selectors must be a nonempty array")
    selectors: list[ProtocolDeclarationSelector] = []
    for index, value in enumerate(raw_selectors):
        selector_label = f"{label}.selectors[{index}]"
        selector = _contract_fields(
            value,
            {"role", "name", "visibility"},
            {"optional"},
            selector_label,
        )
        try:
            role = ProtocolDeclarationRole(_nonempty(selector["role"], f"{selector_label}.role"))
            visibility = ProtocolDeclarationVisibility(
                _nonempty(selector["visibility"], f"{selector_label}.visibility")
            )
        except ValueError as error:
            raise ValueError(f"{selector_label} has an unsupported role or visibility") from error
        optional = selector.get("optional", False)
        if not isinstance(optional, bool):
            raise ValueError(f"{selector_label}.optional must be boolean")
        name = _nonempty(selector["name"], f"{selector_label}.name")
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name) is None:
            raise ValueError(f"{selector_label}.name must be one exact source identifier")
        selectors.append(
            ProtocolDeclarationSelector(
                role,
                name,
                visibility,
                optional,
            )
        )
    if len({(item.role, item.name) for item in selectors}) != len(selectors):
        raise ValueError(f"{label}.selectors must not repeat a role and name")
    return ProtocolDeclarationsRule(
        item_id,
        ArchitectureRuleKind.PROTOCOL_DECLARATIONS,
        source,
        protocol,
        tuple(selectors),
        _nonempty(item["rationale"], f"{label}.rationale"),
        provenance,
        _decided_by(item["decided_by"], f"{label}.decided_by"),
    )


def _parse_call_owner(raw: RawJson, label: str) -> CallOwnerRule:
    item, item_id, provenance = _contract_record(
        raw,
        {"kind", "source", "target", "rationale", "decided_by"},
        {"allowed_sources", "exact_sources"},
        label,
    )
    return CallOwnerRule(
        item_id,
        ArchitectureRuleKind.CALL_OWNER,
        _nonempty(item["source"], f"{label}.source"),
        _nonempty(item["target"], f"{label}.target"),
        _nonempty(item["rationale"], f"{label}.rationale"),
        provenance,
        _decided_by(item["decided_by"], f"{label}.decided_by"),
        _contract_strings(item.get("allowed_sources", []), f"{label}.allowed_sources"),
        _contract_strings(item.get("exact_sources", []), f"{label}.exact_sources"),
    )


def _parse_bounded_numeric_operand(raw: RawJson, label: str) -> BoundedNumericOperandRule:
    item, item_id, provenance = _contract_record(
        raw,
        {"kind", "source", "form", "terminal_suffix", "minimum_value", "rationale", "decided_by"},
        set(),
        label,
    )
    try:
        form = NumericOperandForm(_string(item["form"], f"{label}.form"))
    except ValueError as error:
        raise ValueError(f"{label}.form is invalid") from error
    minimum = _count(item["minimum_value"], f"{label}.minimum_value")
    suffix = _nonempty(item["terminal_suffix"], f"{label}.terminal_suffix")
    return BoundedNumericOperandRule(
        item_id,
        ArchitectureRuleKind.BOUNDED_NUMERIC_OPERAND,
        _nonempty(item["source"], f"{label}.source"),
        form,
        suffix,
        minimum,
        _nonempty(item["rationale"], f"{label}.rationale"),
        provenance,
        _decided_by(item["decided_by"], f"{label}.decided_by"),
    )


def _parse_forbidden_call_argument(raw: RawJson, label: str) -> ForbiddenCallArgumentRule:
    item, item_id, provenance = _contract_record(
        raw,
        {"kind", "source", "target", "parameter", "rationale", "decided_by"},
        set(),
        label,
    )
    return ForbiddenCallArgumentRule(
        item_id,
        ArchitectureRuleKind.FORBIDDEN_CALL_ARGUMENT,
        _nonempty(item["source"], f"{label}.source"),
        _nonempty(item["target"], f"{label}.target"),
        _nonempty(item["parameter"], f"{label}.parameter"),
        _nonempty(item["rationale"], f"{label}.rationale"),
        provenance,
        _decided_by(item["decided_by"], f"{label}.decided_by"),
    )


def _parse_forbidden_effect_under_condition(
    raw: RawJson, label: str
) -> ForbiddenEffectUnderConditionRule:
    item, item_id, provenance = _contract_record(
        raw,
        {"kind", "source", "target", "condition", "rationale", "decided_by"},
        set(),
        label,
    )
    selector = _exact(item["condition"], {"kind", "owner", "name"}, f"{label}.condition")
    return ForbiddenEffectUnderConditionRule(
        item_id,
        ArchitectureRuleKind.FORBIDDEN_EFFECT_UNDER_CONDITION,
        _nonempty(item["source"], f"{label}.source"),
        _nonempty(item["target"], f"{label}.target"),
        ConditionSelector(
            ConditionSelectorKind(_nonempty(selector["kind"], f"{label}.condition.kind")),
            _nonempty(selector["owner"], f"{label}.condition.owner"),
            _nonempty(selector["name"], f"{label}.condition.name"),
        ),
        _nonempty(item["rationale"], f"{label}.rationale"),
        provenance,
        _decided_by(item["decided_by"], f"{label}.decided_by"),
    )


_RULE_PARSERS: Final[dict[ArchitectureRuleKind, Callable[[RawJson, str], ArchitectureRule]]] = {
    ArchitectureRuleKind.BOUNDED_NUMERIC_OPERAND: _parse_bounded_numeric_operand,
    ArchitectureRuleKind.CALL_OWNER: _parse_call_owner,
    ArchitectureRuleKind.FORBIDDEN_CALL_ARGUMENT: _parse_forbidden_call_argument,
    ArchitectureRuleKind.FORBIDDEN_EFFECT_UNDER_CONDITION: _parse_forbidden_effect_under_condition,
    ArchitectureRuleKind.FORBIDDEN_DEPENDENCY: _parse_forbidden_dependency,
    ArchitectureRuleKind.ALLOWED_DEPENDENCY: _parse_allowed_dependency,
    ArchitectureRuleKind.FORBIDDEN_CONSTRUCT: _parse_forbidden_construct,
    ArchitectureRuleKind.SOURCE_OWNERSHIP: _parse_source_ownership,
    ArchitectureRuleKind.EXTERNAL_DEPENDENCY_SCOPE: _parse_external_dependency_scope,
    ArchitectureRuleKind.COMPLETE_ASSIGNMENT: _parse_complete_assignment,
    ArchitectureRuleKind.ROOT_LAYOUT: _parse_root_layout,
    ArchitectureRuleKind.COMPLETE_EXTERNAL_SCOPE: _parse_complete_external_scope,
    ArchitectureRuleKind.COMPLETE_REQUIRES: _parse_complete_requires,
    ArchitectureRuleKind.LAYER_ORDER: _parse_layer_order,
    ArchitectureRuleKind.NO_COMPONENT_CYCLES: _parse_no_component_cycles,
    ArchitectureRuleKind.INTERFACE_BOUNDARY: _parse_interface_boundary,
    ArchitectureRuleKind.SIBLING_ISOLATION: _parse_sibling_isolation,
    ArchitectureRuleKind.SYMBOL_PLACEMENT: _parse_symbol_placement,
    ArchitectureRuleKind.BOUNDARY_TYPES: _parse_boundary_types,
    ArchitectureRuleKind.PROTOCOL_DECLARATIONS: _parse_protocol_declarations,
}


def _rule_kind(raw: RawJson, label: str) -> ArchitectureRuleKind:
    value = _object(raw, label).get("kind")
    if not isinstance(value, str):
        raise ValueError(f"{label}.kind is unsupported")
    try:
        return ArchitectureRuleKind(value)
    except ValueError as error:
        raise ValueError(f"{label}.kind is unsupported") from error


def _parse_rule(raw: RawJson, label: str, kind: ArchitectureRuleKind) -> ArchitectureRule:
    return _RULE_PARSERS[kind](raw, label)


def _rule_payload(rule: ArchitectureRule) -> dict[str, RawJson]:
    fields = asdict(rule)
    if isinstance(rule, ForbiddenDependencyRule):
        for name, default in (
            ("source_match", SelectorMatch.PREFIX),
            ("target_match", SelectorMatch.PREFIX),
            ("target_kind", DependencyTargetKind.MODULE),
        ):
            if fields[name] == default:
                del fields[name]
    if isinstance(rule, BoundaryTypesRule):
        for item, encoded in zip(rule.allowed_positions, fields["allowed_positions"], strict=True):
            if item.alias_body is None:
                del encoded["alias_body"]
            if item.key_alias_body is None:
                del encoded["key_alias_body"]
            if item.literal_mapping_arm is None:
                del encoded["literal_mapping_arm"]
            if not item.native_mapping:
                del encoded["native_mapping"]
    return {key: value for key, value in _raw_object(fields).items() if value is not None}
