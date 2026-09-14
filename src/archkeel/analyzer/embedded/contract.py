# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Load and validate the repository-owned declared architecture contract."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from archkeel.ir.codec import ContractVersionError, decode_json, parse_contract
from archkeel.ir.model import ArchitectureContract, ContractDeclarations, EvidenceClass

from .records import classified


class ContractError(ValueError):
    """Raised when the machine-readable declaration contract is invalid."""


def load_contract(path: Path) -> tuple[ArchitectureContract, str]:
    try:
        raw = path.read_bytes()
    except (OSError, UnicodeError) as exc:
        raise ContractError(f"cannot read architecture contract: {exc}") from exc
    try:
        contract = parse_contract(decode_json(raw))
    except ContractVersionError:
        raise
    except ValueError as exc:
        raise ContractError(f"invalid architecture contract JSON: {exc}") from exc
    return contract, hashlib.sha256(raw).hexdigest()


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
