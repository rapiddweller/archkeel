# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Strict JSON grammar for repository text rules and their inventory evidence."""

from dataclasses import asdict
from typing import Literal

from .architecture_graph import ArchitectureRuleKind, DecisionMaker
from .codec_wire import _count, _nonempty, _object, _raw_object, _string, _strings
from .model import RawJson
from .repository_files import (
    MaxFileLinesRule,
    RepositoryFileClassification,
    RepositoryFileDigest,
    RepositoryFileExclusion,
    RepositoryFileExclusionKind,
    RepositoryFileFact,
    RepositoryFileGap,
    RepositoryFileGapReason,
    RepositoryFileInventory,
    RepositoryFileScope,
    RepositoryFileSelection,
    RepositoryManifestInput,
)


def _fields(raw: RawJson, names: set[str]) -> dict[str, RawJson]:
    item = _object(raw, "repository files")
    if set(item) != names:
        raise ValueError("repository file fields mismatch")
    return item


def _items(raw: RawJson) -> list[RawJson]:
    if not isinstance(raw, list):
        raise ValueError("repository file entries must be an array")
    return raw


def parse_repository_selection(raw: RawJson) -> RepositoryFileSelection:
    item = _fields(raw, {"scopes", "exclusions"})
    scopes: list[RepositoryFileScope] = []
    for value in _items(item["scopes"]):
        scope = _fields(value, {"root", "suffixes", "exact_filenames", "shebang"})
        shebang = scope["shebang"]
        if type(shebang) is not bool:
            raise ValueError("shebang must be boolean")
        scopes.append(
            RepositoryFileScope(
                _nonempty(scope["root"], "root"),
                _strings(scope["suffixes"], "suffixes"),
                _strings(scope["exact_filenames"], "exact_filenames"),
                shebang,
            )
        )
    exclusions: list[RepositoryFileExclusion] = []
    for value in _items(item["exclusions"]):
        exclusion = _fields(value, {"kind", "path", "sha256", "rationale", "provenance"})
        exclusions.append(
            RepositoryFileExclusion(
                RepositoryFileExclusionKind(_nonempty(exclusion["kind"], "kind")),
                _nonempty(exclusion["path"], "path"),
                _nonempty(exclusion["sha256"], "sha256"),
                _nonempty(exclusion["rationale"], "rationale"),
                _strings(exclusion["provenance"], "provenance"),
            )
        )
    return RepositoryFileSelection(tuple(scopes), tuple(exclusions))


def repository_selection_payload(selection: RepositoryFileSelection) -> dict[str, RawJson]:
    return _raw_object(asdict(selection))


def parse_max_file_lines(raw: RawJson, label: str) -> MaxFileLinesRule:
    item = _fields(
        raw, {"id", "kind", "selection", "max_lines", "rationale", "provenance", "decided_by"}
    )
    if item["kind"] != ArchitectureRuleKind.MAX_FILE_LINES:
        raise ValueError(f"{label}.kind must be max_file_lines")
    provenance = _strings(item["provenance"], "provenance")
    if not provenance or any(not path.strip() for path in provenance):
        raise ValueError("rule provenance must not be empty")
    return MaxFileLinesRule(
        _nonempty(item["id"], "id"),
        ArchitectureRuleKind.MAX_FILE_LINES,
        parse_repository_selection(item["selection"]),
        _count(item["max_lines"], "max_lines"),
        _nonempty(item["rationale"], "rationale"),
        provenance,
        DecisionMaker(_nonempty(item["decided_by"], "decided_by")),
    )


def _file_digest(raw: RawJson) -> RepositoryFileDigest:
    item = _fields(raw, {"path", "sha256", "evidence_id"})
    return RepositoryFileDigest(
        _nonempty(item["path"], "path"),
        _nonempty(item["sha256"], "sha256"),
        _nonempty(item["evidence_id"], "evidence_id"),
    )


def _file_fact(raw: RawJson) -> RepositoryFileFact:
    item = _fields(raw, {"path", "sha256", "evidence_id", "physical_lines"})
    return RepositoryFileFact(
        _nonempty(item["path"], "path"),
        _nonempty(item["sha256"], "sha256"),
        _nonempty(item["evidence_id"], "evidence_id"),
        _count(item["physical_lines"], "physical_lines"),
    )


def _file_classification(raw: RawJson) -> RepositoryFileClassification:
    item = _fields(raw, {"path", "sha256", "evidence_id", "shebang"})
    shebang = item["shebang"]
    if not isinstance(shebang, bool):
        raise ValueError("file shebang classification must be boolean")
    return RepositoryFileClassification(
        _nonempty(item["path"], "path"),
        _nonempty(item["sha256"], "sha256"),
        _nonempty(item["evidence_id"], "evidence_id"),
        shebang,
    )


def _manifest_input(raw: RawJson) -> RepositoryManifestInput:
    item = _fields(raw, {"path", "sha256", "evidence_id", "content"})
    return RepositoryManifestInput(
        _nonempty(item["path"], "path"),
        _nonempty(item["sha256"], "sha256"),
        _nonempty(item["evidence_id"], "evidence_id"),
        _string(item["content"], "content"),
    )


def parse_repository_inventory(raw: RawJson) -> RepositoryFileInventory:
    item = _fields(
        raw,
        {
            "selection",
            "expected_paths",
            "selected_paths",
            "files",
            "excluded_files",
            "manifest_inputs",
            "gaps",
            "snapshot_head",
            "snapshot_dirty",
            "digest",
            "classifications",
        },
    )
    dirty = item["snapshot_dirty"]
    snapshot_dirty: bool | Literal["unknown"]
    if isinstance(dirty, bool):
        snapshot_dirty = dirty
    elif dirty == "unknown":
        snapshot_dirty = "unknown"
    else:
        raise ValueError("invalid snapshot dirty state")
    gaps: list[RepositoryFileGap] = []
    for value in _items(item["gaps"]):
        gap = _fields(value, {"path", "reason"})
        gaps.append(
            RepositoryFileGap(
                _nonempty(gap["path"], "path"),
                RepositoryFileGapReason(_nonempty(gap["reason"], "reason")),
            )
        )
    inventory = RepositoryFileInventory(
        parse_repository_selection(item["selection"]),
        _strings(item["expected_paths"], "expected_paths"),
        _strings(item["selected_paths"], "selected_paths"),
        tuple(_file_fact(v) for v in _items(item["files"])),
        tuple(_file_digest(v) for v in _items(item["excluded_files"])),
        tuple(_manifest_input(v) for v in _items(item["manifest_inputs"])),
        tuple(gaps),
        _nonempty(item["snapshot_head"], "snapshot_head"),
        snapshot_dirty,
        tuple(_file_classification(v) for v in _items(item["classifications"])),
    )
    if item["digest"] != inventory.digest:
        raise ValueError("repository inventory digest mismatch")
    return inventory


def repository_inventory_payload(inventory: RepositoryFileInventory) -> dict[str, RawJson]:
    return {**_raw_object(asdict(inventory)), "digest": inventory.digest}
