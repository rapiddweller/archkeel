# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Phase seconds and work counters for one report run, passed as a value and never global."""

from collections.abc import Iterator, Mapping
from contextlib import AbstractContextManager, contextmanager, nullcontext
from enum import StrEnum
from time import perf_counter
from typing import Final

from .model import Observation


class Phase(StrEnum):
    PROVIDERS = "providers"
    COLLECT = "collect"
    DECODE = "decode"
    ASSEMBLE = "assemble"
    RESULT = "result"
    ENCODE = "encode"
    RENDER = "render"


class WorkCounter(StrEnum):
    FILES_PARSED = "files_parsed"
    MODULES = "modules"
    CALLS_ANALYZED = "calls_analyzed"
    RECORDS = "records"
    EVIDENCE_RECORDS = "evidence_records"
    COLLECTOR_WIRE_BYTES = "collector_wire_bytes"
    ARCHITECTURE_BYTES = "architecture_bytes"
    REPORT_PAGE_BYTES = "report_page_bytes"


# Display order and labels for the Markdown counter rows; the JSON keeps the enum values.
COUNTER_LABELS: Final[dict[WorkCounter, str]] = {
    WorkCounter.FILES_PARSED: "Files parsed",
    WorkCounter.MODULES: "Modules",
    WorkCounter.CALLS_ANALYZED: "Calls analyzed",
    WorkCounter.RECORDS: "Records",
    WorkCounter.EVIDENCE_RECORDS: "Evidence records",
    WorkCounter.COLLECTOR_WIRE_BYTES: "Collector wire",
    WorkCounter.ARCHITECTURE_BYTES: "architecture.json",
    WorkCounter.REPORT_PAGE_BYTES: "Report pages",
}


class PhaseClock:
    """Sum wall-clock seconds per phase and integer counts per counter for one run."""

    def __init__(self) -> None:
        self._seconds: dict[Phase, float] = {}
        self._counts: dict[WorkCounter, int] = {}

    @contextmanager
    def measure(self, phase: Phase) -> Iterator[None]:
        started = perf_counter()
        try:
            yield
        finally:
            self._seconds[phase] = self._seconds.get(phase, 0.0) + perf_counter() - started

    def count(self, counter: WorkCounter, value: int) -> None:
        self._counts[counter] = self._counts.get(counter, 0) + value

    def count_all(self, counts: Mapping[WorkCounter, int]) -> None:
        for counter, value in counts.items():
            self.count(counter, value)

    def to_dict(self) -> dict[str, object]:
        # Round at output only; rounding each add would drift the sums.
        return {
            "schema_version": 1,
            "phases": {
                phase.value: round(self._seconds[phase], 3)
                for phase in sorted(self._seconds, key=lambda item: item.value)
            },
            "counters": {
                counter.value: self._counts[counter]
                for counter in sorted(self._counts, key=lambda item: item.value)
            },
        }


def measured(clock: PhaseClock | None, phase: Phase) -> AbstractContextManager[None]:
    """Time a block only when a run asked for timings, so the default path measures nothing."""
    return nullcontext() if clock is None else clock.measure(phase)


def observation_counters(observation: Observation) -> dict[WorkCounter, int]:
    """Derive the deterministic work counts from the observed model, not from timing."""
    coverage = observation.coverage
    counters = {
        WorkCounter.FILES_PARSED: coverage.files_parsed,
        WorkCounter.MODULES: len(observation.records("modules") or ()),
        WorkCounter.RECORDS: sum(len(section.records) for section in observation.sections),
        WorkCounter.EVIDENCE_RECORDS: len(observation.evidence),
    }
    # An unknown call count stays absent, like a phase that did not run.
    if coverage.calls_analyzed is not None:
        counters[WorkCounter.CALLS_ANALYZED] = coverage.calls_analyzed
    return counters
