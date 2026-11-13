# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Explore finds the findings of an import cell by subject id, not by a scan of the report."""

from __future__ import annotations

import random
from types import SimpleNamespace
from typing import Any, cast

import pytest

from archkeel.ir.architecture_graph import ArchitectureReport, GraphAssessment, ReportFinding
from archkeel.ir.report_graph import CellFindings

Found = tuple[tuple[ReportFinding, ...], tuple[GraphAssessment, ...]]


class _Scan:
    """The earlier definition: test every finding and assessment of the report for each cell."""

    def __init__(self, report: ArchitectureReport) -> None:
        self.report = report

    def of(self, references: set[str]) -> Found:
        report = self.report
        findings = tuple(
            item for item in report.findings if references.intersection(item.graph_subject_ids)
        )
        graph_assessments = (
            tuple(
                item
                for item in report.comparison.assessments
                if references.intersection(item.observed_ids)
            )
            if report.comparison
            else ()
        )
        return findings, graph_assessments


def _generated(seed: int) -> tuple[ArchitectureReport, list[set[str]]]:
    rng = random.Random(seed)
    subjects = [f"r{index}" for index in range(rng.randint(1, 12))]

    def some(low: int = 0) -> tuple[str, ...]:
        # Repeated ids and unknown ids are allowed.
        return tuple(rng.choice([*subjects, "other"]) for _ in range(rng.randint(low, 4)))

    findings = tuple(
        SimpleNamespace(id=f"f{index}", graph_subject_ids=some())
        for index in range(rng.randint(0, 20))
    )
    assessments = tuple(
        SimpleNamespace(id=f"a{index}", observed_ids=some()) for index in range(rng.randint(0, 20))
    )
    comparison = SimpleNamespace(assessments=assessments) if rng.random() < 0.8 else None
    report = cast(ArchitectureReport, SimpleNamespace(findings=findings, comparison=comparison))
    cells = [set(some(1)) for _ in range(rng.randint(1, 15))] + [set()]
    return report, cells


@pytest.mark.parametrize("seed", range(300))
def test_the_index_returns_what_the_scan_returned_for_any_cell(seed: int) -> None:
    report, cells = _generated(seed)
    index, oracle = CellFindings(report), _Scan(report)
    for references in cells:
        assert index.of(references) == oracle.of(references)


def test_the_index_keeps_report_order_and_lists_a_finding_once() -> None:
    first = SimpleNamespace(id="f0", graph_subject_ids=("b", "a", "a"))
    second = SimpleNamespace(id="f1", graph_subject_ids=("a",))
    third = SimpleNamespace(id="f2", graph_subject_ids=("c",))
    report = cast(
        ArchitectureReport,
        SimpleNamespace(findings=(first, second, third), comparison=None),
    )
    findings, assessments = CellFindings(report).of({"a", "b", "c"})
    assert [item.id for item in cast(Any, findings)] == ["f0", "f1", "f2"]
    assert assessments == ()
    assert CellFindings(report).of({"b"})[0] == (first,)
