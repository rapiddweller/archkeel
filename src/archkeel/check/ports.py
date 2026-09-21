# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Callable ports consumed by the check workflows."""

from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from archkeel.ir.host_records import HostRecord
from archkeel.ir.model import ObservationResult


@dataclass(frozen=True, slots=True)
class ScanConfig:
    roots: tuple[str, ...]
    namespace: str
    contract: str
    digest: str


class FilesToWrite(Mapping[str, bytes]):
    """The files a run produced, by repository-relative path, for the caller to write.

    `run_init` and `run_validate` used to return this as a bare `dict[str, bytes]`, which is
    exactly the untyped container `boundary_types` (AD-58) exists to reject: a consumer had to
    know an undocumented shape rather than read a declared one. Every existing caller only
    ever reads it as a mapping (`files[path]`, `files.items()`, `set(files)`, `files == {}`),
    so it stays one instead of adding an attribute nothing needs.
    """

    def __init__(self, files: Mapping[str, bytes] | None = None) -> None:
        self._files = dict(files) if files is not None else {}

    def __getitem__(self, key: str) -> bytes:
        return self._files[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._files)

    def __len__(self) -> int:
        return len(self._files)


class Analyzer(Protocol):
    def __call__(
        self,
        source_root: Path,
        *,
        roots: tuple[str, ...],
        namespace: str,
        contract: str,
        git_head: str,
        dirty: bool,
        contract_root: Path,
    ) -> ObservationResult: ...


class Host(Protocol):
    def __call__(
        self,
        root: Path,
        *,
        expectation_sha: str,
        candidate_sha: str,
        environ: Mapping[str, str],
    ) -> tuple[HostRecord, ...]: ...
