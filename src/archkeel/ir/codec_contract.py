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
from typing import Final, Literal, TypeGuard, get_args

from archkeel.ir.architecture_graph import (
    ArchitectureRuleKind, DecisionMaker, validate_layout_rule, validate_module_target,
)
from archkeel.ir.codec_governance import _measurement_budget_name
from archkeel.ir.codec_wire import (
    _count,
    _exact,
    _nonempty,
    _object,
    _raw_object,
    _string,
    _strings,
)
from archkeel.ir.facts_codec import record_payload
from archkeel.ir.graph_codec import parse_target
from archkeel.ir.model import (
    AllowedDependencyRule,
    ArchitectureContract,
    ArchitectureRule,
    BoundaryAliasBody,
    BoundaryTypeAllowance,
    BoundaryTypesRule,
    CompatibilityLifetime,
    CompatibilityShim,
    CompleteAssignmentRule,
    CompleteExternalScopeRule,
    CompleteRequiresRule,
    ComponentRole,
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
    DependencySelector,
    DependencyTargetKind,
    ExternalDependencyScopeRule,
    FacadeBudget,
    ForbiddenConstructKind,
    ForbiddenConstructRule,
    ForbiddenDependencyRule,
    InterfaceBoundaryRule,
    LayerOrderRule,
    NoComponentCyclesRule,
    Record,
    RequiredComponent,
    RootLayoutRule,
    SelectorMatch,
    SiblingIsolationRule,
    SymbolClassKind,
    SymbolPlacementRule,
    TypeIgnoreAllowance,
    contract_relative_path,
)
from archkeel.ir.model import ContractInputError as ContractInputError
from archkeel.ir.model import RawJson as RawJson
from archkeel.ir.target_graph import declared_graph

_PUBLIC_ENTRY = re.compile(
    r"^[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*(?::[A-Za-z_][A-Za-z0-9_]*)?$"
)


_PACKAGE_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*$")


CONTRACT_SCHEMA_VERSION: Final = "2.1.0"


class ContractVersionError(ValueError):
    """The contract declares a schema version this parser cannot interpret."""

    def __init__(self, actual: str) -> None:
        self.actual = actual
        super().__init__(f"contract.schema_version {actual!r} is not {CONTRACT_SCHEMA_VERSION}")


def _is_compatibility_lifetime(value: RawJson) -> TypeGuard[CompatibilityLifetime]:
    return value in get_args(CompatibilityLifetime)


def _contract_fields(
    raw: RawJson, required: set[str], optional: set[str], label: str
) -> dict[str, RawJson]:
    item: dict[str, RawJson] = _object(raw, label)
    if not required <= set(item) or set(item) - required - optional:
        raise ValueError(f"{label} fields mismatch")
    return item


def _decided_by(raw: RawJson, label: str) -> Literal["architect", "agent"]:
    """Narrow to the Literal by value, never by cast (AD-16)."""
    value = _nonempty(raw, label)
    if value == "architect":
        return "architect"
    if value == "agent":
        return "agent"
    raise ValueError(f"{label} must be architect or agent")


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
    if root["schema_version"] == "2.1.0":
        version: Literal[
            "2.1.0", "2.2.0", "2.3.0", "3.0.0", "3.1.0", "3.2.0", "3.3.0", "3.4.0", "3.5.0"
        ] = "2.1.0"
    elif root["schema_version"] == "2.2.0":
        version = "2.2.0"
    elif root["schema_version"] == "2.3.0":
        version = "2.3.0"
    elif root["schema_version"] == "3.0.0":
        version = "3.0.0"
    elif root["schema_version"] == "3.1.0":
        version = "3.1.0"
    elif root["schema_version"] == "3.2.0":
        version = "3.2.0"
    elif root["schema_version"] == "3.3.0":
        version = "3.3.0"
    elif root["schema_version"] == "3.4.0":
        version = "3.4.0"
    elif root["schema_version"] == "3.5.0":
        version = "3.5.0"
    else:
        raise ContractVersionError(str(root["schema_version"]))
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
        if "facade_budgets" in declarations
        else None
    )
    coupling_budgets = (
        tuple(
            _parse_coupling_budget(value, f"coupling_budgets[{index}]")
            for index, value in enumerate(records("coupling_budgets"))
        )
        if "coupling_budgets" in declarations
        else None
    )
    modules = (
        tuple(
            _parse_module_target(value, f"modules[{index}]")
            for index, value in enumerate(records("modules"))
        )
        if "modules" in declarations
        else None
    )
    if modules is not None and len({item.path for item in modules}) != len(modules):
        raise ValueError("contract.declarations.modules repeats a path")
    if "uml" in declarations and version == "2.1.0":
        raise ValueError("UML declarations require contract schema_version 2.2.0")
    uml = parse_target(declarations["uml"]) if "uml" in declarations else None
    if version not in {"2.3.0", "3.0.0", "3.1.0", "3.2.0", "3.3.0", "3.4.0", "3.5.0"}:
        for raw in rules_raw:
            rule_data: dict[str, RawJson] = _object(raw, "rule")
            if rule_data.get("kind") == "layer_order":
                raise ValueError("layer_order requires contract schema_version 2.3.0")
    if version not in {"3.4.0", "3.5.0"} and any(
        "source_match" in _object(value, "rule") or "target_match" in _object(value, "rule")
        for value in rules_raw
    ):
        raise ValueError("dependency module selectors require contract schema_version 3.4.0")
    if version != "3.5.0" and any("target_kind" in _object(value, "rule") for value in rules_raw):
        raise ValueError("import namespace targets require contract schema_version 3.5.0")
    rules = tuple(_parse_rule(value, f"rules[{index}]") for index, value in enumerate(rules_raw))
    if version not in {"3.0.0", "3.1.0", "3.2.0", "3.3.0", "3.4.0", "3.5.0"} and any(
        isinstance(rule, BoundaryTypesRule)
        and any(item.alias_body is not None for item in rule.allowed_positions)
        for rule in rules
    ):
        raise ValueError("alias_body requires contract schema_version 3.0.0")
    if version not in {"3.1.0", "3.2.0", "3.3.0", "3.4.0", "3.5.0"} and any(
        isinstance(rule, BoundaryTypesRule)
        and any(item.key_alias_body is not None for item in rule.allowed_positions)
        for rule in rules
    ):
        raise ValueError("key_alias_body requires contract schema_version 3.1.0")
    if version not in {"3.2.0", "3.3.0", "3.4.0", "3.5.0"} and any(
        isinstance(rule, BoundaryTypesRule)
        and any(item.literal_mapping_arm is not None for item in rule.allowed_positions)
        for rule in rules
    ):
        raise ValueError("literal_mapping_arm requires contract schema_version 3.2.0")
    if version not in {"3.3.0", "3.4.0", "3.5.0"} and any(
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
    if contract.schema_version not in {
        "2.3.0",
        "3.0.0",
        "3.1.0",
        "3.2.0",
        "3.3.0",
        "3.4.0",
        "3.5.0",
    } and (
        any(component.layer is not None for component in contract.components)
        or any(isinstance(rule, LayerOrderRule) for rule in contract.rules)
    ):
        raise ValueError("layer and layer_order require contract schema_version 2.3.0")
    if contract.schema_version not in {
        "3.0.0",
        "3.1.0",
        "3.2.0",
        "3.3.0",
        "3.4.0",
        "3.5.0",
    } and any(
        isinstance(rule, BoundaryTypesRule)
        and any(item.alias_body is not None for item in rule.allowed_positions)
        for rule in contract.rules
    ):
        raise ValueError("alias_body requires contract schema_version 3.0.0")
    if contract.schema_version not in {"3.1.0", "3.2.0", "3.3.0", "3.4.0", "3.5.0"} and any(
        isinstance(rule, BoundaryTypesRule)
        and any(item.key_alias_body is not None for item in rule.allowed_positions)
        for rule in contract.rules
    ):
        raise ValueError("key_alias_body requires contract schema_version 3.1.0")
    if contract.schema_version not in {"3.2.0", "3.3.0", "3.4.0", "3.5.0"} and any(
        isinstance(rule, BoundaryTypesRule)
        and any(item.literal_mapping_arm is not None for item in rule.allowed_positions)
        for rule in contract.rules
    ):
        raise ValueError("literal_mapping_arm requires contract schema_version 3.2.0")
    if contract.schema_version not in {"3.3.0", "3.4.0", "3.5.0"} and any(
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
    if contract.schema_version not in {"3.4.0", "3.5.0"} and any(
        isinstance(rule, ForbiddenDependencyRule)
        and (
            rule.source_match is not SelectorMatch.PREFIX
            or rule.target_match is not SelectorMatch.PREFIX
        )
        for rule in contract.rules
    ):
        raise ValueError("dependency module selectors require contract schema_version 3.4.0")
    if contract.schema_version != "3.5.0" and any(
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
    if not _is_compatibility_lifetime(lifetime):
        raise ValueError(f"{label}.lifetime must be permanent or migration")
    return CompatibilityShim(module, target, lifetime)


def _parse_module_target(raw: RawJson, label: str) -> ContractModuleTarget:
    item = _contract_fields(raw, {"path", "responsibility"}, set(), label)
    path = _nonempty(item["path"], f"{label}.path")
    relative = contract_relative_path(path)
    if (
        relative is None
        or "\x00" in path
        or str(relative) != path
        or re.match(r"^[A-Za-z]:", path) is not None
        or relative.suffix
        not in {".py", ".dart", ".ts", ".tsx", ".mts", ".cts", ".js", ".jsx", ".mjs", ".cjs"}
    ):
        raise ValueError(f"{label}.path must be a repository-relative source path")
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
        if "exact_modules" in item
        else ()
    )
    if any(re.fullmatch(_PACKAGE_NAME.pattern, name) is None for name in exact):
        raise ValueError(f"{label}.exact_modules must contain dotted identifiers")
    if not packages and not exact:
        raise ValueError(f"{label} must claim at least one package or exact module")
    return packages, exact


def _parse_component(raw: RawJson, label: str, *, version: str) -> ContractComponent:
    if "layer" in _object(raw, label) and version not in {
        "2.3.0",
        "3.0.0",
        "3.1.0",
        "3.2.0",
        "3.3.0",
        "3.4.0",
        "3.5.0",
    }:
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
        _nonempty(item["layer"], f"{label}.layer") if "layer" in item else None,
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
    if item["kind"] != "forbidden_dependency":
        raise ValueError(f"{label}.kind is unsupported")
    include = item["include_type_checking"]
    if not isinstance(include, bool):
        raise ValueError(f"{label}.include_type_checking must be a boolean")
    selected = _dependency_selector(item, label)
    rationale = _nonempty(item["rationale"], f"{label}.rationale")
    decided_by = _decided_by(item["decided_by"], f"{label}.decided_by")
    allowed = _contract_strings(item.get("allowed_sources", []), f"{label}.allowed_sources")

    return ForbiddenDependencyRule(
        item_id,
        "forbidden_dependency",
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
    if item["kind"] != "allowed_dependency":
        raise ValueError(f"{label}.kind is unsupported")
    return AllowedDependencyRule(
        item_id,
        "allowed_dependency",
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
        {"allowed_sources", "exact_sources", "allowed_type_ignores"},
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
    return ForbiddenConstructRule(
        item_id,
        "forbidden_construct",
        _nonempty(item["source"], f"{label}.source"),
        constructs,
        _nonempty(item["rationale"], f"{label}.rationale"),
        provenance,
        _decided_by(item["decided_by"], f"{label}.decided_by"),
        allowed,
        exact,
        tuple(ignores),
    )


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
        DecisionMaker(_decided_by(item["decided_by"], f"{label}.decided_by")),
        exact,
    )


def _parse_complete_assignment(raw: RawJson, label: str) -> CompleteAssignmentRule:
    item, item_id, provenance = _contract_record(
        raw, {"kind", "source", "rationale", "decided_by"}, set(), label
    )
    return CompleteAssignmentRule(
        item_id,
        "complete_assignment",
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
        DecisionMaker(_decided_by(item["decided_by"], f"{label}.decided_by")),
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
        "complete_external_scope",
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
        "complete_requires",
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
        "layer_order",
        layers,
        _nonempty(item["rationale"], f"{label}.rationale"),
        provenance,
        _decided_by(item["decided_by"], f"{label}.decided_by"),
        _contract_strings(item["components"], f"{label}.components", required=True)
        if "components" in item
        else None,
    )


def _cycle_level(raw: RawJson, label: str) -> Literal["module"] | None:
    """Narrow to the Literal by value; the default component level parses to absent (AD-98)."""
    value = _nonempty(raw, label)
    if value == "component":
        return None
    if value == "module":
        return "module"
    raise ValueError(f"{label} must be component or module")


def _parse_no_component_cycles(raw: RawJson, label: str) -> NoComponentCyclesRule:
    item, item_id, provenance = _contract_record(
        raw, {"kind", "rationale", "decided_by"}, {"level", "components"}, label
    )
    level = item.get("level")
    components = item.get("components")
    return NoComponentCyclesRule(
        item_id,
        "no_component_cycles",
        _nonempty(item["rationale"], f"{label}.rationale"),
        provenance,
        _decided_by(item["decided_by"], f"{label}.decided_by"),
        _cycle_level(level, f"{label}.level") if level is not None else None,
        _contract_strings(components, f"{label}.components", required=True)
        if components is not None
        else None,
    )


def _parse_interface_boundary(raw: RawJson, label: str) -> InterfaceBoundaryRule:
    item, item_id, provenance = _contract_record(
        raw, {"kind", "rationale", "decided_by"}, {"include_type_checking"}, label
    )
    include = item.get("include_type_checking", True)
    if not isinstance(include, bool):
        raise ValueError(f"{label}.include_type_checking must be a boolean")
    return InterfaceBoundaryRule(
        item_id,
        "interface_boundary",
        _nonempty(item["rationale"], f"{label}.rationale"),
        provenance,
        _decided_by(item["decided_by"], f"{label}.decided_by"),
        include,
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
        "sibling_isolation",
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
        "symbol_placement",
        _nonempty(item["source"], f"{label}.source"),
        class_kinds,
        _nonempty(item["rationale"], f"{label}.rationale"),
        provenance,
        _decided_by(item["decided_by"], f"{label}.decided_by"),
        allowed,
        exact,
    )


# Bare mappings do not name their members; exact object payloads explicitly accept opacity.
_BARE_BROAD_ANNOTATIONS: Final = frozenset({"Dict", "Mapping", "MutableMapping"})


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
    field_path = (
        ""
        if entry.get("field_path", "") == ""
        else _nonempty(entry["field_path"], f"{label}.field_path")
    )
    annotation = _nonempty(entry["annotation"], f"{label}.annotation")
    depth: int | None = None
    if "container_depth" in entry:
        raw_depth = entry["container_depth"]
        if isinstance(raw_depth, bool) or not isinstance(raw_depth, int) or raw_depth < 1:
            raise ValueError(f"{label}.container_depth must be a positive integer")
        depth = raw_depth
    mapping_depth: int | None = None
    if "mapping_depth" in entry:
        raw_mapping_depth = entry["mapping_depth"]
        if type(raw_mapping_depth) is not int or raw_mapping_depth < 1:
            raise ValueError(f"{label}.mapping_depth must be a positive integer")
        mapping_depth = raw_mapping_depth
        if field_path:
            raise ValueError(f"{label}.mapping_depth cannot select a DTO field")
        if depth is not None and depth != mapping_depth + 1:
            raise ValueError(f"{label}.container_depth must be mapping_depth plus one")
    alias_body: BoundaryAliasBody | None = None
    if "alias_body" in entry:
        body_label = f"{label}.alias_body"
        body = _exact(entry["alias_body"], {"origin", "shape"}, body_label)
        alias_body = BoundaryAliasBody(
            _nonempty(body["origin"], f"{body_label}.origin"),
            _nonempty(body["shape"], f"{body_label}.shape"),
        )
        if field_path or mapping_depth is not None:
            raise ValueError(f"{body_label} requires empty field_path and absent mapping_depth")
    key_alias_body: BoundaryAliasBody | None = None
    if "key_alias_body" in entry:
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
    native_mapping = _parse_native_mapping(entry, label)
    if annotation == "dict" and not native_mapping:
        raise ValueError(f"{label}.annotation cannot allow bare dict")
    if not field_path and annotation in _BARE_BROAD_ANNOTATIONS:
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


def _parse_native_mapping(entry: dict[str, RawJson], label: str) -> bool:
    if "native_mapping" not in entry:
        return False
    if entry["native_mapping"] is not True:
        raise ValueError(f"{label}.native_mapping must be true")
    if entry["annotation"] not in ("dict", "dict | None", "list[dict]") or any(
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
    if "literal_mapping_arm" not in entry:
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
        "boundary_types",
        _nonempty(item["source"], f"{label}.source"),
        _nonempty(item["rationale"], f"{label}.rationale"),
        provenance,
        _decided_by(item["decided_by"], f"{label}.decided_by"),
        allowed,
        exact,
        tuple(positions),
    )


_RULE_PARSERS: Final[dict[str, Callable[[RawJson, str], ArchitectureRule]]] = {
    "forbidden_dependency": _parse_forbidden_dependency,
    "allowed_dependency": _parse_allowed_dependency,
    "forbidden_construct": _parse_forbidden_construct,
    "external_dependency_scope": _parse_external_dependency_scope,
    "complete_assignment": _parse_complete_assignment,
    "root_layout": _parse_root_layout,
    "complete_external_scope": _parse_complete_external_scope,
    "complete_requires": _parse_complete_requires,
    "layer_order": _parse_layer_order,
    "no_component_cycles": _parse_no_component_cycles,
    "interface_boundary": _parse_interface_boundary,
    "sibling_isolation": _parse_sibling_isolation,
    "symbol_placement": _parse_symbol_placement,
    "boundary_types": _parse_boundary_types,
}


def _parse_rule(raw: RawJson, label: str) -> ArchitectureRule:
    kind = _object(raw, label).get("kind")
    if not isinstance(kind, str) or kind not in _RULE_PARSERS:
        raise ValueError(f"{label}.kind is unsupported")
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
