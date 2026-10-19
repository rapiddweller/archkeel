# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Bind repository file evaluator receipts to the declared rule and observed snapshot."""

import hashlib
import json
from dataclasses import asdict

from .codec_repository_files import parse_repository_inventory, parse_repository_selection
from .codec_wire import _object
from .facts import Record, SourceInfo, stable_id
from .facts_codec import record_payload
from .model import SCHEMA_VERSION, Observation
from .repository_files import (
    RepositoryFileExclusionKind,
    RepositoryFileInventory,
    repository_line_overflows,
    repository_path_selected,
)
from .repository_manifest import manifest_file_digests


def repository_inventory_complete(inventory: RepositoryFileInventory) -> bool:
    if inventory.gaps or not inventory.files:
        return False
    candidates = {
        path
        for path in inventory.expected_paths
        if repository_path_selected(inventory.selection, path, b"#!")
    }
    classified = {item.path: item for item in inventory.classifications}
    if set(classified) != candidates:
        return False
    selected = {
        path
        for path, item in classified.items()
        if repository_path_selected(inventory.selection, path, b"#!" if item.shebang else b"")
    }
    paths = {item.path for item in inventory.files} | {
        item.path for item in inventory.excluded_files
    }
    if paths != set(inventory.selected_paths) or paths != selected:
        return False
    if any(
        classified[item.path].sha256 != item.sha256
        for item in (*inventory.files, *inventory.excluded_files)
    ):
        return False
    permissions = _verified_exclusions(inventory)
    return permissions is not None and all(
        permissions.get(item.path) == item.sha256 for item in inventory.excluded_files
    )


def _verified_exclusions(inventory: RepositoryFileInventory) -> dict[str, str] | None:
    manifests = {item.path: item.sha256 for item in inventory.manifest_inputs}
    pinned = {
        item.path: item.sha256
        for item in inventory.selection.exclusions
        if item.kind is RepositoryFileExclusionKind.MANIFEST
    }
    if manifests != pinned:
        return None
    permissions = {
        item.path: item.sha256
        for item in inventory.selection.exclusions
        if item.kind is RepositoryFileExclusionKind.FILE
    }
    for manifest in inventory.manifest_inputs:
        try:
            entries = manifest_file_digests(manifest.path, manifest.content.encode("utf-8"))
        except ValueError:
            return None
        for path, digest in entries:
            if path in permissions and permissions[path] != digest:
                return None
            permissions[path] = digest
    return permissions


def repository_file_binding_id(
    declaration: Record,
    inventory: RepositoryFileInventory,
    source: SourceInfo,
    contract_digest: str,
    schema_version: str = SCHEMA_VERSION,
) -> str:
    payload = {
        "declaration": record_payload(declaration),
        "inventory_digest": inventory.digest,
        "source": asdict(source),
        "contract_digest": contract_digest,
        "schema_version": schema_version,
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()


def repository_file_receipt_complete(
    observation: Observation, declaration: Record, receipt: Record | None
) -> bool:
    if receipt is None or receipt.rule_ids != (declaration.id,):
        return False
    inventories = [
        record
        for record in observation.records("scope_observations") or ()
        if record.kind == "repository_file_inventory" and record.id in receipt.fact_ids
    ]
    if len(inventories) != 1:
        return False
    record = inventories[0]
    try:
        inventory = parse_repository_inventory(record_payload(record)["data"])
        declared_data = _object(record_payload(declaration)["data"], "declaration data")
        declared_selection = parse_repository_selection(declared_data["selection"])
    except (ValueError, TypeError, KeyError):
        return False
    evidence = {item.id: (item.file, item.excerpt) for item in observation.evidence}
    witnesses = (
        *inventory.files,
        *inventory.excluded_files,
        *inventory.manifest_inputs,
        *inventory.classifications,
    )
    return (
        repository_inventory_complete(inventory)
        and inventory.selection == declared_selection
        and _line_findings_match(observation, declaration, inventory)
        and inventory.snapshot_head == observation.source.git_head
        and inventory.snapshot_dirty == observation.source.dirty
        and receipt.data.get("assessment_complete") is True
        and record.id == stable_id("REPOSITORY-FILE-INVENTORY", inventory.digest)
        and receipt.fact_ids == (record.id,)
        and set(receipt.subjects) == set(inventory.selected_paths)
        and set(receipt.evidence_ids) == {item.evidence_id for item in witnesses}
        and all(
            evidence.get(item.evidence_id) == (item.path, f"sha256:{item.sha256}")
            for item in witnesses
        )
        and receipt.data.get("repository_file_binding")
        == repository_file_binding_id(
            declaration,
            inventory,
            observation.source,
            observation.contract.digest,
            observation.schema_version,
        )
    )


def _line_findings_match(
    observation: Observation, declaration: Record, inventory: RepositoryFileInventory
) -> bool:
    limit = declaration.data.get("max_lines")
    if not isinstance(limit, int) or isinstance(limit, bool) or limit < 0:
        return False
    expected = {
        item.path: item.physical_lines for item in repository_line_overflows(inventory, limit)
    }
    violations = [
        item for item in observation.records("violations") or () if declaration.id in item.rule_ids
    ]
    if len(violations) != len(expected) or {item.data.get("file") for item in violations} != set(
        expected
    ):
        return False
    return all(
        item.kind == "max_file_lines"
        and isinstance((path := item.data.get("file")), str)
        and path in expected
        and item.data.get("physical_lines") == expected[path]
        and item.data.get("max_lines") == limit
        for item in violations
    )
