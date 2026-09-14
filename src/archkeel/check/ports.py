# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Callable ports consumed by the check workflows."""

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from archkeel.host.records import HostRecord
from archkeel.ir.model import ObservationResult


@dataclass(frozen=True, slots=True)
class ScanConfig:
    roots: tuple[str, ...]
    namespace: str
    contract: str
    digest: str


class Producer(Protocol):
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
