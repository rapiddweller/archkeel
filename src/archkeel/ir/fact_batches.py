# ArchKeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Versioned language-neutral batches of canonical source facts."""

from dataclasses import dataclass

from .facts import Evidence, Record

FACT_BATCH_FORMAT_VERSION = "1.0.0"
MAX_FACT_BATCH_FRAME_BYTES = 1_048_576


@dataclass(frozen=True, slots=True)
class FactBatch:
    snapshot_id: str
    sequence: int
    records: tuple[Record, ...]
    evidence: tuple[Evidence, ...]
