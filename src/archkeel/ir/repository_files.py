# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Repository text selection and authenticated file inventory, independent of language facts."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from enum import StrEnum
from pathlib import PurePosixPath, PureWindowsPath
from typing import Literal

from .architecture_graph import ArchitectureRuleGrammar, ArchitectureRuleKind, DecisionMaker


def repository_file_path(path: str, *, root: bool = False) -> str:
    if not isinstance(path, str) or not path or "\\" in path or "\x00" in path:
        raise ValueError("repository path must be a nonempty relative POSIX path")
    if root and path == ".":
        return path
    if (
        PurePosixPath(path).is_absolute()
        or PureWindowsPath(path).drive
        or any(part in {"", ".", ".."} for part in path.split("/"))
    ):
        raise ValueError("repository path must be normalized and relative")
    return path


def _digest(value: str) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(c not in "0123456789abcdef" for c in value)
    ):
        raise ValueError("sha256 must contain 64 lowercase hexadecimal characters")


class RepositoryFileExclusionKind(StrEnum):
    FILE = "file"
    MANIFEST = "manifest"


class RepositoryFileGapReason(StrEnum):
    ENUMERATION = "enumeration"
    READ = "read"
    DECODE = "decode"
    SYMLINK = "symlink"
    MISSING = "missing"
    HASH_MISMATCH = "hash_mismatch"
    MANIFEST = "manifest"
    EMPTY = "empty"


@dataclass(frozen=True, slots=True)
class RepositoryFileScope:
    root: str
    suffixes: tuple[str, ...] = ()
    exact_filenames: tuple[str, ...] = ()
    shebang: bool = False

    def __post_init__(self) -> None:
        repository_file_path(self.root, root=True)
        if type(self.shebang) is not bool:
            raise ValueError("shebang must be boolean")
        if not self.suffixes and not self.exact_filenames and not self.shebang:
            raise ValueError("file scope requires at least one selector")
        for suffix in self.suffixes:
            if not suffix.startswith(".") or len(suffix) < 2 or "/" in suffix or "\\" in suffix:
                raise ValueError("suffix must start with a dot and contain no path separator")
        for filename in self.exact_filenames:
            repository_file_path(filename)
            if "/" in filename:
                raise ValueError("exact_filenames must contain basenames")
        if len(set(self.suffixes)) != len(self.suffixes) or len(set(self.exact_filenames)) != len(
            self.exact_filenames
        ):
            raise ValueError("duplicate file selector")


@dataclass(frozen=True, slots=True)
class RepositoryFileExclusion:
    kind: RepositoryFileExclusionKind
    path: str
    sha256: str
    rationale: str
    provenance: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.kind, RepositoryFileExclusionKind):
            raise ValueError("exclusion kind must be nominal")
        repository_file_path(self.path)
        _digest(self.sha256)
        if (
            not self.rationale.strip()
            or not self.provenance
            or any(not p.strip() for p in self.provenance)
        ):
            raise ValueError("exclusion requires rationale and provenance")


@dataclass(frozen=True, slots=True)
class RepositoryFileSelection:
    scopes: tuple[RepositoryFileScope, ...]
    exclusions: tuple[RepositoryFileExclusion, ...] = ()

    def __post_init__(self) -> None:
        if not self.scopes or len(set(self.scopes)) != len(self.scopes):
            raise ValueError("selection requires unique scopes")
        if len({item.path for item in self.exclusions}) != len(self.exclusions):
            raise ValueError("duplicate exclusion path")


def repository_path_selected(selection: RepositoryFileSelection, path: str, content: bytes) -> bool:
    repository_file_path(path)
    name = path.rsplit("/", 1)[-1]
    return any(
        (scope.root == "." or path == scope.root or path.startswith(scope.root + "/"))
        and (
            any(name.endswith(suffix) for suffix in scope.suffixes)
            or name in scope.exact_filenames
            or (scope.shebang and content.startswith(b"#!"))
        )
        for scope in selection.scopes
    )


@dataclass(frozen=True, slots=True)
class RepositoryFileDigest:
    path: str
    sha256: str
    evidence_id: str

    def __post_init__(self) -> None:
        repository_file_path(self.path)
        _digest(self.sha256)
        if not self.evidence_id:
            raise ValueError("file digest requires evidence")


@dataclass(frozen=True, slots=True)
class RepositoryFileClassification(RepositoryFileDigest):
    shebang: bool

    def __post_init__(self) -> None:
        RepositoryFileDigest.__post_init__(self)
        if type(self.shebang) is not bool:
            raise ValueError("file shebang classification must be boolean")


@dataclass(frozen=True, slots=True)
class RepositoryManifestInput(RepositoryFileDigest):
    content: str

    def __post_init__(self) -> None:
        RepositoryFileDigest.__post_init__(self)
        if (
            not isinstance(self.content, str)
            or hashlib.sha256(self.content.encode("utf-8")).hexdigest() != self.sha256
        ):
            raise ValueError("manifest bytes do not match their pinned digest")


@dataclass(frozen=True, slots=True)
class RepositoryFileFact(RepositoryFileDigest):
    physical_lines: int

    def __post_init__(self) -> None:
        RepositoryFileDigest.__post_init__(self)
        if type(self.physical_lines) is not int or self.physical_lines < 0:
            raise ValueError("physical_lines must be a nonnegative integer")


@dataclass(frozen=True, slots=True)
class RepositoryFileGap:
    path: str
    reason: RepositoryFileGapReason

    def __post_init__(self) -> None:
        repository_file_path(self.path, root=True)
        if not isinstance(self.reason, RepositoryFileGapReason):
            raise ValueError("gap reason must be nominal")


@dataclass(frozen=True, slots=True)
class RepositoryFileInventory:
    selection: RepositoryFileSelection
    expected_paths: tuple[str, ...]
    selected_paths: tuple[str, ...]
    files: tuple[RepositoryFileFact, ...]
    excluded_files: tuple[RepositoryFileDigest, ...]
    manifest_inputs: tuple[RepositoryManifestInput, ...]
    gaps: tuple[RepositoryFileGap, ...]
    snapshot_head: str
    snapshot_dirty: bool | Literal["unknown"]
    classifications: tuple[RepositoryFileClassification, ...] = ()

    def __post_init__(self) -> None:
        for paths in (self.expected_paths, self.selected_paths):
            for path in paths:
                repository_file_path(path)
            if len(set(paths)) != len(paths):
                raise ValueError("duplicate inventory path")
        if not set(self.selected_paths) <= set(self.expected_paths):
            raise ValueError("selected paths must belong to the enumerated snapshot")
        for entries in (
            self.files,
            self.excluded_files,
            self.manifest_inputs,
            self.classifications,
        ):
            if len({entry.path for entry in entries}) != len(entries):
                raise ValueError("duplicate inventory fact")
        actual = {item.path for item in self.files}
        excluded = {item.path for item in self.excluded_files}
        if actual & excluded or not actual | excluded <= set(self.selected_paths):
            raise ValueError("file facts and exclusions must be disjoint selected paths")
        if not isinstance(self.snapshot_head, str) or not self.snapshot_head:
            raise ValueError("snapshot head must be explicit")
        if type(self.snapshot_dirty) is not bool and self.snapshot_dirty != "unknown":
            raise ValueError("invalid snapshot dirty state")

    @property
    def digest(self) -> str:
        return hashlib.sha256(
            json.dumps(
                asdict(self), sort_keys=True, separators=(",", ":"), ensure_ascii=False
            ).encode()
        ).hexdigest()


@dataclass(frozen=True, slots=True)
class MaxFileLinesRule(ArchitectureRuleGrammar):
    id: str
    kind: Literal[ArchitectureRuleKind.MAX_FILE_LINES]
    selection: RepositoryFileSelection
    max_lines: int
    rationale: str
    provenance: tuple[str, ...]
    decided_by: DecisionMaker

    def __post_init__(self) -> None:
        ArchitectureRuleGrammar.__post_init__(self)
        if type(self.max_lines) is not int or self.max_lines < 0:
            raise ValueError("max_lines must be a nonnegative integer")


def repository_line_overflows(
    inventory: RepositoryFileInventory, max_lines: int
) -> tuple[RepositoryFileFact, ...]:
    """The line-limit decision shared by evaluation and saved-receipt verification."""
    return tuple(item for item in inventory.files if item.physical_lines > max_lines)


@dataclass(frozen=True, slots=True)
class RepositorySnapshotPaths:
    paths: tuple[str, ...]
    git_head: str
    dirty: bool | Literal["unknown"]

    def __post_init__(self) -> None:
        for path in self.paths:
            repository_file_path(path)
        if len(set(self.paths)) != len(self.paths):
            raise ValueError("duplicate snapshot path")
