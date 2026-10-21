# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Resolve explicit inside-contract topology and its provenance closure."""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Sequence
from dataclasses import replace
from pathlib import PurePosixPath

from archkeel.ir.codec_contract import ContractVersionError, contract_digest, parse_contract
from archkeel.ir.codec_wire import decode_json
from archkeel.ir.model import (
    ArchitectureContract,
    ContractComponent,
    ContractDeclarations,
    contract_relative_path,
)
from archkeel.ir.model import ContractInputError as ContractInputError
from archkeel.ir.model import InsideContractIssue as InsideContractIssue
from archkeel.ir.model import InsideContractMount as InsideContractMount
from archkeel.ir.model import InsideContractTree as InsideContractTree
from archkeel.ir.target_graph import scoped_target


def contract_provenance_locations(
    contract: ArchitectureContract,
) -> tuple[tuple[str, tuple[str, ...]], ...]:
    """Every place a contract cites provenance, as (JSON pointer, paths) (#629)."""
    declarations = contract.declarations or ContractDeclarations()
    uml = declarations.uml
    groups = (
        ("/components", contract.components),
        ("/rules", contract.rules),
        ("/declarations/capabilities", declarations.capabilities),
        ("/declarations/review_scopes", declarations.review_scopes),
        ("/declarations/public_commands", declarations.public_commands),
        ("/declarations/paths", declarations.paths),
        ("/declarations/spot_owners", declarations.spot_owners),
        ("/declarations/measurement_budgets", declarations.measurement_budgets),
        ("/declarations/facade_budgets", declarations.facade_budgets or ()),
        ("/declarations/coupling_budgets", declarations.coupling_budgets or ()),
        ("/declarations/uml/entities", uml.entities if uml else ()),
        ("/declarations/uml/relationships", uml.relationships if uml else ()),
        ("/declarations/uml/scopes", uml.scopes if uml else ()),
    )
    return (
        *(
            (f"{prefix}/{index}/provenance", tuple(record.provenance))
            for prefix, records in groups
            for index, record in enumerate(records)
        ),
        ("/declarations/public_api_provenance", tuple(declarations.public_api_provenance)),
        ("/declarations/context_roots_provenance", tuple(declarations.context_roots_provenance)),
    )


def contract_provenance_paths(contract: ArchitectureContract) -> tuple[str, ...]:
    """Return every repository path cited as contract provenance."""
    return tuple(
        sorted({path for _, paths in contract_provenance_locations(contract) for path in paths})
    )


def _scoped_inside_contract(parent_id: str, contract: ArchitectureContract) -> ArchitectureContract:
    return replace(
        contract,
        components=tuple(
            replace(item, id=f"{parent_id}:{item.id}") for item in contract.components
        ),
        rules=tuple(replace(item, id=f"{parent_id}:{item.id}") for item in contract.rules),
        declarations=replace(
            contract.declarations, uml=scoped_target(contract.declarations.uml, parent_id)
        )
        if contract.declarations is not None
        else None,
    )


def _safe_inside_reference(value: str) -> bool:
    path = PurePosixPath(value)
    return bool(
        value
        and value not in {".", ".."}
        and contract_relative_path(value) is not None
        and path.parts
        and not any(char in value for char in "\x00:")
    )


def _contract_identity(value: str) -> str | None:
    path = contract_relative_path(value)
    return path.as_posix() if path is not None and path.parts else None


def _load_inside_children(
    owner_contract: ArchitectureContract,
    owner_id: str,
    pointer: str,
    active: frozenset[str],
    seen: set[str],
    read_contract: Callable[[str], tuple[bytes, str]],
    mounts: list[InsideContractMount],
    issues: list[InsideContractIssue],
    paths: set[str],
    root_labels: frozenset[str],
    parent_ids: dict[str, str],
    record_ids: set[str],
) -> None:
    for index, parent in enumerate(owner_contract.components):
        if parent.inside is None:
            continue
        mount = _inside_mount(
            owner_contract,
            owner_id,
            pointer,
            index,
            parent,
            active,
            seen,
            read_contract,
            issues,
            paths,
            root_labels,
            parent_ids,
            record_ids,
        )
        if mount is None:
            continue
        mounts.append(mount)
        _load_inside_children(
            mount.contract,
            mount.parent_id,
            mount.pointer,
            active | {mount.identity},
            seen,
            read_contract,
            mounts,
            issues,
            paths,
            root_labels,
            parent_ids,
            record_ids,
        )


def _inside_mount(
    owner_contract: ArchitectureContract,
    owner_id: str,
    pointer: str,
    index: int,
    parent: ContractComponent,
    active: frozenset[str],
    seen: set[str],
    read_contract: Callable[[str], tuple[bytes, str]],
    issues: list[InsideContractIssue],
    paths: set[str],
    root_labels: frozenset[str],
    parent_ids: dict[str, str],
    record_ids: set[str],
) -> InsideContractMount | None:
    parent_id = f"{owner_id}:{parent.label}" if owner_id else parent.label
    location = f"{pointer}/components/{index}/inside"
    reference = parent.inside
    if reference is None:
        return None
    paths.add(reference)
    if owner_id and parent_id in root_labels:
        reason = "generated inside parent ID collision"
    elif (previous := parent_ids.get(parent_id)) is not None and previous != location:
        reason = "generated inside parent ID collision"
    elif not _safe_inside_reference(reference):
        reason = "unsafe repository path"
    else:
        parent_ids[parent_id] = location
        return _read_inside_mount(
            owner_contract,
            owner_id,
            parent,
            parent_id,
            location,
            reference,
            active,
            seen,
            read_contract,
            issues,
            paths,
            record_ids,
        )
    issues.append(InsideContractIssue(parent, parent_id, location, reference, reason))
    return None


def _read_inside_mount(
    owner_contract: ArchitectureContract,
    owner_id: str,
    parent: ContractComponent,
    parent_id: str,
    location: str,
    reference: str,
    active: frozenset[str],
    seen: set[str],
    read_contract: Callable[[str], tuple[bytes, str]],
    issues: list[InsideContractIssue],
    paths: set[str],
    record_ids: set[str],
) -> InsideContractMount | None:
    try:
        payload, raw_identity = read_contract(reference)
        identity = _contract_identity(raw_identity)
        if identity is None:
            raise ValueError("unsafe repository path")
        if identity in active or identity in seen:
            raise ValueError("reference cycle" if identity in active else "duplicate mount")
        contract = parse_contract(decode_json(payload))
    except ContractInputError as error:
        issues.append(
            InsideContractIssue(parent, parent_id, location, reference, str(error), error)
        )
        return None
    except (OSError, ContractVersionError, ValueError) as error:
        issues.append(InsideContractIssue(parent, parent_id, location, reference, str(error)))
        return None
    seen.add(identity)
    _record_inside_policy(parent, parent_id, location, reference, contract, paths, issues)
    scoped = _scoped_inside_contract(parent_id, contract)
    scoped_ids = _contract_record_ids(scoped)
    collision = next((item for item in sorted(scoped_ids) if item in record_ids), None)
    if collision is not None:
        issues.append(
            InsideContractIssue(
                parent,
                parent_id,
                location,
                reference,
                f"generated declaration ID collision: {collision}",
            )
        )
        return None
    record_ids.update(scoped_ids)
    return InsideContractMount(
        parent,
        owner_contract,
        owner_id,
        parent_id,
        location,
        reference,
        identity,
        scoped,
        hashlib.sha256(payload).hexdigest(),
        contract_digest(contract),
    )


def _record_inside_policy(
    parent: ContractComponent,
    parent_id: str,
    location: str,
    reference: str,
    contract: ArchitectureContract,
    paths: set[str],
    issues: list[InsideContractIssue],
) -> None:
    declarations = contract.declarations or ContractDeclarations()
    unsupported = _unsupported_inside_declaration_fields(declarations)
    if unsupported:
        issues.append(
            InsideContractIssue(
                parent,
                parent_id,
                location,
                reference,
                f"unsupported non-empty declarations: {', '.join(unsupported)}",
            )
        )
    paths.update(contract_provenance_paths(contract))


def _unsupported_inside_declaration_fields(declarations: ContractDeclarations) -> tuple[str, ...]:
    fields = (
        ("capabilities", declarations.capabilities),
        ("review_scopes", declarations.review_scopes),
        ("public_api", declarations.public_api),
        ("public_api_provenance", declarations.public_api_provenance),
        ("public_commands", declarations.public_commands),
        ("context_roots", declarations.context_roots),
        ("context_roots_provenance", declarations.context_roots_provenance),
        ("paths", declarations.paths),
        ("spot_owners", declarations.spot_owners),
        ("compat", declarations.compat),
        ("measurement_budgets", declarations.measurement_budgets),
        ("facade_budgets", declarations.facade_budgets or ()),
        ("coupling_budgets", declarations.coupling_budgets or ()),
    )
    return tuple(name for name, values in fields if values)


def _contract_record_ids(contract: ArchitectureContract) -> set[str]:
    declarations = contract.declarations or ContractDeclarations()
    return {
        item.id
        for items in (
            contract.components,
            contract.rules,
            declarations.capabilities,
            declarations.review_scopes,
            declarations.public_commands,
            declarations.paths,
            declarations.spot_owners,
            declarations.uml.entities if declarations.uml is not None else (),
            declarations.uml.relationships if declarations.uml is not None else (),
        )
        for item in items
    }


def _duplicate_module_target_issues(
    root_path: str, root_contract: ArchitectureContract, mounts: Sequence[InsideContractMount]
) -> list[InsideContractIssue]:
    paths: dict[str, str] = {}
    issues: list[InsideContractIssue] = []
    contracts = [
        (root_path, root_contract, None),
        *((item.path, item.contract, item) for item in mounts),
    ]
    for path, contract, mount in contracts:
        modules = (contract.declarations or ContractDeclarations()).modules or ()
        for index, target in enumerate(modules):
            previous = paths.get(target.path)
            if previous is None:
                paths[target.path] = path
            elif mount is not None:
                message = (
                    f"duplicate module target path {target.path!r} in {path!r}; "
                    f"already declared in {previous!r}"
                )
                issues.append(
                    InsideContractIssue(
                        mount.parent,
                        mount.parent_id,
                        mount.pointer,
                        path,
                        message,
                        ContractInputError(
                            f"/declarations/modules/{index}/path", target.path, message
                        ),
                    )
                )
    return issues


def load_inside_contract_tree(
    root_path: str,
    root_contract: ArchitectureContract,
    root_digest: str,
    root_identity: str,
    read_contract: Callable[[str], tuple[bytes, str]],
) -> InsideContractTree:
    """Resolve every explicit inside once; the reader supplies bytes and canonical identity."""
    canonical_root_path = _contract_identity(root_path)
    canonical_root_identity = _contract_identity(root_identity)
    if canonical_root_path is None or canonical_root_identity is None:
        raise ValueError("unsafe root contract path")
    root_path = canonical_root_path
    root_identity = canonical_root_identity
    mounts: list[InsideContractMount] = []
    issues: list[InsideContractIssue] = []
    paths = {root_path, *contract_provenance_paths(root_contract)}
    root_labels = frozenset(component.label for component in root_contract.components)
    _load_inside_children(
        root_contract,
        "",
        "",
        frozenset({root_identity}),
        {root_identity},
        read_contract,
        mounts,
        issues,
        paths,
        root_labels,
        {},
        _contract_record_ids(root_contract),
    )
    issues.extend(_duplicate_module_target_issues(root_path, root_contract, mounts))
    digests = [root_digest, *(item.digest for item in mounts)]
    digest = root_digest if not mounts else hashlib.sha256("".join(digests).encode()).hexdigest()
    canonical_digests = [
        contract_digest(root_contract),
        *(item.canonical_digest for item in mounts),
    ]
    comparison_digest = (
        canonical_digests[0]
        if not mounts
        else hashlib.sha256("".join(canonical_digests).encode()).hexdigest()
    )
    comparison_contract = replace(
        root_contract,
        components=(
            *root_contract.components,
            *(item for mount in mounts for item in mount.contract.components),
        ),
        rules=(*root_contract.rules, *(item for mount in mounts for item in mount.contract.rules)),
    )
    return InsideContractTree(
        root_contract,
        tuple(mounts),
        tuple(issues),
        tuple(sorted(paths)),
        digest,
        comparison_digest,
        comparison_contract,
    )


def declaration_paths(
    payload: bytes,
    contract_path: str,
    *,
    read_contract: Callable[[str], tuple[bytes, str]],
) -> tuple[str, ...]:
    """Every transitive contract and provenance path read by one repository declaration tree."""
    contract = parse_contract(decode_json(payload))
    _, root_identity = read_contract(contract_path)
    tree = load_inside_contract_tree(
        contract_path,
        contract,
        hashlib.sha256(payload).hexdigest(),
        root_identity,
        read_contract,
    )
    if tree.issues:
        issue = next(
            (candidate for candidate in tree.issues if candidate.input_error is not None),
            tree.issues[0],
        )
        if issue.input_error is not None:
            raise ContractInputError(
                f"{issue.pointer}{issue.input_error.pointer}",
                issue.input_error.subject,
                str(issue.input_error),
            )
        raise ValueError(f"inside {issue.path!r}: {issue.reason}")
    return tree.paths
