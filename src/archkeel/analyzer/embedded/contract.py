# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Load and validate the repository-owned declared architecture contract."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import assert_never

from archkeel.ir.codec import ContractVersionError, decode_json, parse_contract
from archkeel.ir.model import (
    AllowedDependencyRule,
    ArchitectureContract,
    ArchitectureRule,
    CompleteAssignmentRule,
    CompleteExternalScopeRule,
    ContractDeclarations,
    EvidenceClass,
    ExternalDependencyScopeRule,
    ForbiddenConstructRule,
    ForbiddenDependencyRule,
    InterfaceBoundaryRule,
    NoComponentCyclesRule,
    SiblingIsolationRule,
)

from .records import RawRecord, RecordData, classified


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


def _rule_declaration(rule: ArchitectureRule) -> RawRecord:
    subjects: list[str]
    data: RecordData
    if isinstance(rule, ForbiddenDependencyRule):
        target = ".".join(filter(None, (rule.target, rule.target_symbol)))
        area, title, subjects = (
            "dependency_violations",
            f"{rule.source} must not depend on {target}",
            [rule.source, target],
        )
        data = {
            "source": rule.source,
            "target": rule.target,
            "include_type_checking": rule.include_type_checking,
            "rationale": rule.rationale,
            "allowed_sources": sorted(rule.allowed_sources),
            **({"target_symbol": rule.target_symbol} if rule.target_symbol else {}),
        }
    elif isinstance(rule, AllowedDependencyRule):
        area, title, subjects = (
            "dependency_violations",
            f"{rule.source} may depend on {rule.target}",
            [rule.source, rule.target],
        )
        data = {"source": rule.source, "target": rule.target, "rationale": rule.rationale}
    elif isinstance(rule, ForbiddenConstructRule):
        constructs = [item.value for item in rule.constructs]
        area, title, subjects = (
            "type_architecture",
            f"{rule.source} forbids {', '.join(constructs)}",
            [rule.source],
        )
        data = {"source": rule.source, "constructs": constructs, "rationale": rule.rationale}
    elif isinstance(rule, ExternalDependencyScopeRule):
        area, title, subjects = (
            "dependency_violations",
            f"{rule.dependency} is allowed only in {', '.join(rule.allowed_sources)}",
            [rule.dependency, *rule.allowed_sources],
        )
        data = {
            "dependency": rule.dependency,
            "allowed_sources": sorted(rule.allowed_sources),
            "rationale": rule.rationale,
        }
    elif isinstance(rule, CompleteAssignmentRule):
        area, title, subjects = (
            "components",
            f"Every module in {rule.source} belongs to one component",
            [rule.source],
        )
        data = {"source": rule.source, "rationale": rule.rationale}
    elif isinstance(rule, CompleteExternalScopeRule):
        area, title, subjects = (
            "dependencies",
            f"Every dependency {rule.source} imports is declared",
            [rule.source],
        )
        data = {"source": rule.source, "rationale": rule.rationale}
    elif isinstance(rule, InterfaceBoundaryRule):
        area, title, subjects = (
            "api_surface",
            "Cross-component imports must reach the target's declared public interface",
            [],
        )
        data = {
            "include_type_checking": rule.include_type_checking,
            "rationale": rule.rationale,
        }
    elif isinstance(rule, SiblingIsolationRule):
        area, title, subjects = (
            "dependency_violations",
            f"{len(rule.members)} peers must not import each other",
            list(rule.members),
        )
        data = {
            "include_type_checking": rule.include_type_checking,
            "rationale": rule.rationale,
        }
    elif isinstance(rule, NoComponentCyclesRule):
        area, title, subjects = "cycles", "Component dependencies form no cycle", []
        data = {"rationale": rule.rationale}
    else:
        assert_never(rule)
    data["decided_by"] = rule.decided_by
    return classified(
        item_id=rule.id,
        evidence_class=EvidenceClass.DECLARED_RULE,
        area=area,
        kind=rule.kind,
        title=title,
        subjects=subjects,
        provenance=list(rule.provenance),
        data=data,
    )


def project_declarations(contract: ArchitectureContract) -> list[RawRecord]:
    """Project the contract into classified records consumed by JSON and HTML."""
    declarations = contract.declarations or ContractDeclarations()
    items: list[RawRecord] = []
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
                    **(
                        {"public": sorted(component.public)} if component.public is not None else {}
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
    items.extend(_rule_declaration(rule) for rule in contract.rules)
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
