# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Load and validate the repository-owned declared architecture contract."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from archkeel.ir.codec import decode_json, parse_contract
from archkeel.ir.model import ArchitectureContract, ContractDeclarations, EvidenceClass

from .records import classified


class ContractError(ValueError):
    """Raised when the machine-readable declaration contract is invalid."""


_COMPONENT_ROLES = frozenset({"component", "interface", "contract", "projection", "foundation"})


def _is_repository_architecture_provenance(value: str) -> bool:
    path = Path(value)
    return (
        path.name in {"AGENTS.md", "ARCHITECTURE.md"}
        or value.startswith("docs/architecture/")
        or value.startswith("docs/adrs/")
    )


def _is_namespace_module_prefix(value: str, *, namespace: str) -> bool:
    return value == namespace or value.startswith(f"{namespace}.")


def load_contract(path: Path) -> tuple[ArchitectureContract, str]:
    try:
        raw = path.read_bytes()
    except (OSError, UnicodeError) as exc:
        raise ContractError(f"cannot read architecture contract: {exc}") from exc
    try:
        contract = parse_contract(decode_json(raw))
    except ValueError as exc:
        raise ContractError(f"invalid architecture contract JSON: {exc}") from exc
    return contract, hashlib.sha256(raw).hexdigest()


def _validate_contract(contract: object, *, root: Path, namespace: str) -> None:
    if not isinstance(contract, dict):
        raise ContractError("architecture contract must be a JSON object")
    if contract.get("schema_version") != "1.1.0":
        raise ContractError("architecture contract schema_version must be 1.1.0")
    required_lists = (
        "capabilities",
        "components",
        "review_scopes",
        "public_api",
        "public_api_provenance",
        "public_commands",
        "context_roots",
        "context_roots_provenance",
        "paths",
        "spot_owners",
        "rules",
    )
    for key in required_lists:
        if not isinstance(contract.get(key), list):
            raise ContractError(f"architecture contract field {key!r} must be a list")

    seen: set[str] = set()
    for section in (
        "capabilities",
        "components",
        "review_scopes",
        "public_commands",
        "paths",
        "spot_owners",
        "rules",
    ):
        for item in contract[section]:
            if not isinstance(item, dict) or not isinstance(item.get("id"), str):
                raise ContractError(f"{section} entries require string IDs")
            item_id = item["id"]
            if item_id in seen:
                raise ContractError(f"duplicate architecture contract ID: {item_id}")
            seen.add(item_id)
            provenance = item.get("provenance", [])
            if (
                not provenance
                or not isinstance(provenance, list)
                or not all(isinstance(value, str) for value in provenance)
            ):
                raise ContractError(f"{item_id}: provenance must be a string list")
            invalid = [
                value for value in provenance if not _is_repository_architecture_provenance(value)
            ]
            if invalid:
                raise ContractError(
                    f"{item_id}: invalid architecture provenance: {', '.join(invalid)}"
                )
            missing = [value for value in provenance if not (root / value).is_file()]
            if missing:
                raise ContractError(f"{item_id}: missing provenance files: {', '.join(missing)}")

    for section in ("public_api_provenance", "context_roots_provenance"):
        values = contract[section]
        if not values or not all(isinstance(value, str) for value in values):
            raise ContractError(f"{section} must contain repository-relative source paths")
        invalid = [value for value in values if not _is_repository_architecture_provenance(value)]
        if invalid:
            raise ContractError(f"{section}: invalid architecture provenance: {', '.join(invalid)}")
        missing = [value for value in values if not (root / value).is_file()]
        if missing:
            raise ContractError(f"{section}: missing provenance files: {', '.join(missing)}")

    if not all(
        isinstance(value, str) and _is_namespace_module_prefix(value, namespace=namespace)
        for value in contract["public_api"]
    ):
        raise ContractError("public_api must contain names under the configured namespace")
    if not all(
        isinstance(value, str) and _is_namespace_module_prefix(value, namespace=namespace)
        for value in contract["context_roots"]
    ):
        raise ContractError("context_roots must contain names under the configured namespace")

    capability_ids: set[str] = set()
    capability_names: set[str] = set()
    capability_orders: set[int] = set()
    if not contract["capabilities"]:
        raise ContractError("capabilities must contain at least one declared capability")
    for capability in contract["capabilities"]:
        for key in ("name", "label"):
            if not isinstance(capability.get(key), str) or not capability[key]:
                raise ContractError(f"{capability['id']}: missing capability field {key}")
        review_order = capability.get("review_order")
        if isinstance(review_order, bool) or not isinstance(review_order, int) or review_order <= 0:
            raise ContractError(f"{capability['id']}: review_order must be a positive integer")
        if review_order in capability_orders:
            raise ContractError(f"duplicate capability review_order: {review_order}")
        capability_ids.add(capability["id"])
        capability_orders.add(review_order)
        if capability["name"] in capability_names:
            raise ContractError(f"duplicate capability name: {capability['name']}")
        capability_names.add(capability["name"])

    component_ids: set[str] = set()
    for component in contract["components"]:
        component_ids.add(component["id"])
        for key in (
            "label",
            "role",
            "packages",
            "responsibilities",
            "forbidden_responsibilities",
        ):
            if key not in component:
                raise ContractError(f"{component['id']}: missing component field {key}")
        if component["role"] not in _COMPONENT_ROLES:
            raise ContractError(f"{component['id']}: invalid component role {component['role']!r}")
        capability_id = component.get("capability_id")
        if component["role"] == "foundation" and capability_id is not None:
            raise ContractError(
                f"{component['id']}: foundation components must not declare a parent capability"
            )
        if component["role"] != "foundation" and capability_id not in capability_ids:
            raise ContractError(f"{component['id']}: unknown parent capability {capability_id!r}")
        if not component["packages"] or not all(
            isinstance(value, str) and _is_namespace_module_prefix(value, namespace=namespace)
            for value in component["packages"]
        ):
            raise ContractError(f"{component['id']}: packages must use the configured namespace")

    for scope in contract["review_scopes"]:
        for key in ("label", "parent_id", "subjects"):
            if key not in scope:
                raise ContractError(f"{scope['id']}: missing review scope field {key}")
        if scope["parent_id"] not in component_ids:
            raise ContractError(f"{scope['id']}: unknown component parent {scope['parent_id']!r}")
        if not scope["subjects"] or not all(
            isinstance(value, str) and _is_namespace_module_prefix(value, namespace=namespace)
            for value in scope["subjects"]
        ):
            raise ContractError(f"{scope['id']}: subjects must use the configured namespace")

    for command in contract["public_commands"]:
        for key in ("command", "description"):
            if not isinstance(command.get(key), str) or not command[key]:
                raise ContractError(f"{command['id']}: missing public command field {key}")

    for owner in contract["spot_owners"]:
        for key in ("label", "owner", "responsibility"):
            if not isinstance(owner.get(key), str) or not owner[key]:
                raise ContractError(f"{owner['id']}: missing SPOT owner field {key}")
        if not _is_namespace_module_prefix(owner["owner"], namespace=namespace):
            raise ContractError(f"{owner['id']}: owner must use the configured namespace")

    dependency_pairs: set[tuple[str, str, str | None]] = set()
    for rule in contract["rules"]:
        rule_id = rule["id"]
        if rule.get("kind") != "forbidden_dependency":
            raise ContractError(f"{rule_id}: only forbidden_dependency rules are supported")
        for key in ("source", "target", "rationale"):
            value = rule.get(key)
            if not isinstance(value, str) or not value.strip():
                raise ContractError(f"{rule_id}: {key} must be a non-empty string")
        source = rule["source"]
        target = rule["target"]
        if not _is_namespace_module_prefix(source, namespace=namespace):
            raise ContractError(f"{rule_id}: source must use the configured namespace")
        if not _is_namespace_module_prefix(target, namespace=namespace):
            raise ContractError(f"{rule_id}: target must use the configured namespace")
        if not isinstance(rule.get("include_type_checking"), bool):
            raise ContractError(f"{rule_id}: include_type_checking must be a boolean")
        target_symbol = rule.get("target_symbol")
        if target_symbol is not None and (
            not isinstance(target_symbol, str) or not target_symbol.isidentifier()
        ):
            raise ContractError(f"{rule_id}: target_symbol must be a Python identifier")
        allowed_sources = rule.get("allowed_sources", [])
        if not isinstance(allowed_sources, list) or not all(
            isinstance(value, str) and _is_namespace_module_prefix(value, namespace=namespace)
            for value in allowed_sources
        ):
            raise ContractError(f"{rule_id}: allowed_sources must use the configured namespace")
        outside_source = [
            value
            for value in allowed_sources
            if value != source and not value.startswith(f"{source}.")
        ]
        if outside_source:
            raise ContractError(f"{rule_id}: allowed_sources must be inside {source}")
        if len(set(allowed_sources)) != len(allowed_sources):
            raise ContractError(f"{rule_id}: allowed_sources must not contain duplicates")
        dependency_pair = (source, target, target_symbol)
        if dependency_pair in dependency_pairs:
            raise ContractError(f"{rule_id}: duplicate forbidden dependency {source} -> {target}")
        dependency_pairs.add(dependency_pair)


def project_declarations(contract: ArchitectureContract) -> list[dict[str, Any]]:
    """Project the contract into classified records consumed by JSON and HTML."""
    declarations = contract.declarations or ContractDeclarations()
    items: list[dict[str, Any]] = []
    for capability in declarations.capabilities:
        items.append(
            classified(
                item_id=capability.id,
                evidence_class=EvidenceClass.DECLARED_RULE,
                area="components",
                kind="capability",
                title=capability.label,
                subjects=[capability.name],
                provenance=list(capability.provenance),
                data={"name": capability.name, "review_order": capability.review_order},
            )
        )
    for component in contract.components:
        items.append(
            classified(
                item_id=component.id,
                evidence_class=EvidenceClass.DECLARED_RULE,
                area="components",
                kind="component_responsibility",
                title=component.label,
                subjects=list(component.packages),
                provenance=list(component.provenance),
                data={
                    **(
                        {"capability_id": component.capability_id}
                        if component.capability_id
                        else {}
                    ),
                    "role": component.role.value,
                    "responsibilities": sorted(component.responsibilities),
                    "forbidden_responsibilities": sorted(component.forbidden_responsibilities),
                },
            )
        )
    for scope in declarations.review_scopes:
        items.append(
            classified(
                item_id=scope.id,
                evidence_class=EvidenceClass.DECLARED_RULE,
                area="components",
                kind="review_scope",
                title=scope.label,
                subjects=list(scope.subjects),
                provenance=list(scope.provenance),
                data={"parent_id": scope.parent_id},
            )
        )
    for path in declarations.paths:
        items.append(
            classified(
                item_id=path.id,
                evidence_class=EvidenceClass.DECLARED_RULE,
                area="read_write_paths",
                kind=f"declared_{path.kind.value}_path",
                title=path.label,
                subjects=list(path.steps),
                provenance=list(path.provenance),
                data={"steps": path.steps},
            )
        )
    for rule in contract.rules:
        target = ".".join(filter(None, (rule.target, rule.target_symbol)))
        items.append(
            classified(
                item_id=rule.id,
                evidence_class=EvidenceClass.DECLARED_RULE,
                area="dependency_violations",
                kind=rule.kind,
                title=f"{rule.source} must not depend on {target}",
                subjects=[rule.source, target],
                provenance=list(rule.provenance),
                data={
                    "source": rule.source,
                    "target": rule.target,
                    "include_type_checking": rule.include_type_checking,
                    "rationale": rule.rationale,
                    "allowed_sources": sorted(rule.allowed_sources),
                    **({"target_symbol": rule.target_symbol} if rule.target_symbol else {}),
                },
            )
        )
    for api in sorted(declarations.public_api):
        items.append(
            classified(
                item_id=f"API-{hashlib.sha256(api.encode()).hexdigest()[:16]}",
                evidence_class=EvidenceClass.DECLARED_RULE,
                area="api_surface",
                kind="declared_public_api",
                title=api,
                subjects=[api],
                provenance=list(declarations.public_api_provenance),
                data={"qualified_name": api},
            )
        )
    for command in declarations.public_commands:
        items.append(
            classified(
                item_id=command.id,
                evidence_class=EvidenceClass.DECLARED_RULE,
                area="api_surface",
                kind="declared_public_command",
                title=command.command,
                subjects=[command.command],
                provenance=list(command.provenance),
                data={
                    "command": command.command,
                    "description": command.description,
                },
            )
        )
    for context in sorted(declarations.context_roots):
        items.append(
            classified(
                item_id=f"CTX-{hashlib.sha256(context.encode()).hexdigest()[:16]}",
                evidence_class=EvidenceClass.DECLARED_RULE,
                area="contexts_state",
                kind="declared_context_root",
                title=context,
                subjects=[context],
                provenance=list(declarations.context_roots_provenance),
                data={"qualified_name": context},
            )
        )
    for owner in declarations.spot_owners:
        items.append(
            classified(
                item_id=owner.id,
                evidence_class=EvidenceClass.DECLARED_RULE,
                area="spot_ownership",
                kind="spot_owner",
                title=owner.label,
                subjects=[owner.owner],
                provenance=list(owner.provenance),
                data={
                    "owner": owner.owner,
                    "responsibility": owner.responsibility,
                },
            )
        )
    return sorted(items, key=lambda item: item["id"])
