# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Capture repository text and exact exclusion witnesses without evaluating policy."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Literal

from archkeel.ir.model import stable_id
from archkeel.ir.repository_files import (
    RepositoryFileClassification,
    RepositoryFileDigest,
    RepositoryFileExclusionKind,
    RepositoryFileFact,
    RepositoryFileGap,
    RepositoryFileGapReason,
    RepositoryFileInventory,
    RepositoryFileSelection,
    RepositoryManifestInput,
    repository_file_path,
    repository_path_selected,
)
from archkeel.ir.repository_manifest import manifest_file_digests

from .git import GitError, working_tree_paths
from .ports import RepositorySnapshotPaths


def _digest(path: str, content: bytes) -> RepositoryFileDigest:
    digest = hashlib.sha256(content).hexdigest()
    return RepositoryFileDigest(path, digest, stable_id("EVD", "repository-file", path, digest))


def _read(root: Path, path: str, gaps: list[RepositoryFileGap]) -> bytes | None:
    target = root / repository_file_path(path)
    try:
        if any(
            part.is_symlink() for part in (target, *target.parents) if part != root
        ) or not target.resolve().is_relative_to(root):
            gaps.append(RepositoryFileGap(path, RepositoryFileGapReason.SYMLINK))
        elif not target.is_file():
            gaps.append(RepositoryFileGap(path, RepositoryFileGapReason.MISSING))
        else:
            return target.read_bytes()
    except OSError:
        gaps.append(RepositoryFileGap(path, RepositoryFileGapReason.READ))
    return None


def _exclusions(
    root: Path,
    selection: RepositoryFileSelection,
    gaps: list[RepositoryFileGap],
    contents: dict[str, bytes],
) -> tuple[dict[str, str], tuple[RepositoryManifestInput, ...]]:
    verified: dict[str, str] = {}
    manifests: list[RepositoryManifestInput] = []
    for item in selection.exclusions:
        data = _read(root, item.path, gaps)
        if data is None:
            continue
        contents[item.path] = data
        witness = _digest(item.path, data)
        if witness.sha256 != item.sha256:
            gaps.append(RepositoryFileGap(item.path, RepositoryFileGapReason.HASH_MISMATCH))
            continue
        entries: tuple[tuple[str, str], ...]
        if item.kind is RepositoryFileExclusionKind.FILE:
            entries = ((item.path, item.sha256),)
        else:
            try:
                entries = manifest_file_digests(item.path, data)
                manifests.append(
                    RepositoryManifestInput(
                        witness.path, witness.sha256, witness.evidence_id, data.decode("utf-8")
                    )
                )
            except (ValueError, TypeError, UnicodeError):
                gaps.append(RepositoryFileGap(item.path, RepositoryFileGapReason.MANIFEST))
                continue
        for path, expected in entries:
            content = contents.get(path)
            if content is None:
                content = _read(root, path, gaps)
            if content is None:
                continue
            contents[path] = content
            if hashlib.sha256(content).hexdigest() != expected:
                gaps.append(RepositoryFileGap(path, RepositoryFileGapReason.HASH_MISMATCH))
            else:
                verified[path] = expected
    return verified, tuple(manifests)


def _files(
    root: Path,
    selection: RepositoryFileSelection,
    paths: tuple[str, ...],
    excluded: dict[str, str],
    gaps: list[RepositoryFileGap],
    contents: dict[str, bytes],
) -> tuple[
    tuple[str, ...],
    tuple[RepositoryFileFact, ...],
    tuple[RepositoryFileDigest, ...],
    tuple[RepositoryFileClassification, ...],
]:
    selected: list[str] = []
    classifications: list[RepositoryFileClassification] = []
    facts: list[RepositoryFileFact] = []
    excluded_facts: list[RepositoryFileDigest] = []
    for path in paths:
        if not repository_path_selected(selection, path, b"#!"):
            continue
        data = contents.get(path)
        if data is None:
            data = _read(root, path, gaps)
        if data is None:
            if repository_path_selected(selection, path, b"#!"):
                selected.append(path)
            continue
        contents[path] = data
        digest = _digest(path, data)
        classifications.append(
            RepositoryFileClassification(
                path, digest.sha256, digest.evidence_id, data.startswith(b"#!")
            )
        )
        if not repository_path_selected(selection, path, data):
            continue
        selected.append(path)
        if excluded.get(path) == digest.sha256:
            excluded_facts.append(digest)
            continue
        try:
            data.decode("utf-8")
            if b"\0" in data:
                raise ValueError("binary content")
        except (ValueError, UnicodeError):
            gaps.append(RepositoryFileGap(path, RepositoryFileGapReason.DECODE))
            continue
        facts.append(
            RepositoryFileFact(
                path=path,
                sha256=digest.sha256,
                evidence_id=digest.evidence_id,
                physical_lines=(
                    data.count(b"\n")
                    + data.count(b"\r")
                    - data.count(b"\r\n")
                    + int(bool(data) and not data.endswith((b"\n", b"\r")))
                ),
            )
        )
    return tuple(selected), tuple(facts), tuple(excluded_facts), tuple(classifications)


def read_repository_inputs(
    root: Path,
    selection: RepositoryFileSelection,
    *,
    git_head: str,
    dirty: bool | Literal["unknown"],
    snapshot: RepositorySnapshotPaths | None = None,
) -> RepositoryFileInventory:
    root = root.resolve()
    gaps: list[RepositoryFileGap] = []
    try:
        paths = (
            tuple(sorted(working_tree_paths(root, (".",)))) if snapshot is None else snapshot.paths
        )
        if snapshot is not None and (snapshot.git_head != git_head or snapshot.dirty != dirty):
            raise ValueError("snapshot identity mismatch")
        if len(paths) != len(set(paths)):
            raise ValueError("duplicate repository path")
        for path in paths:
            repository_file_path(path)
    except (GitError, OSError, ValueError):
        paths = ()
        gaps.append(RepositoryFileGap(".", RepositoryFileGapReason.ENUMERATION))
    for scope in selection.scopes:
        if not (root / scope.root).exists():
            gaps.append(RepositoryFileGap(scope.root, RepositoryFileGapReason.MISSING))
    contents: dict[str, bytes] = {}
    excluded, manifests = _exclusions(root, selection, gaps, contents)
    selected, files, excluded_files, classifications = _files(
        root, selection, paths, excluded, gaps, contents
    )
    if not selected:
        gaps.append(RepositoryFileGap(".", RepositoryFileGapReason.EMPTY))
    for path, original in tuple(contents.items()):
        if _read(root, path, gaps) != original:
            gaps.append(RepositoryFileGap(path, RepositoryFileGapReason.HASH_MISMATCH))
    if snapshot is None:
        try:
            if paths != tuple(sorted(working_tree_paths(root, (".",)))):
                gaps.append(RepositoryFileGap(".", RepositoryFileGapReason.ENUMERATION))
        except (GitError, OSError):
            gaps.append(RepositoryFileGap(".", RepositoryFileGapReason.ENUMERATION))
    return RepositoryFileInventory(
        selection,
        paths,
        selected,
        files,
        excluded_files,
        manifests,
        tuple(dict.fromkeys(gaps)),
        git_head,
        dirty,
        classifications,
    )
