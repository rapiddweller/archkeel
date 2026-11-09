# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Narrow one report to the rows a filter selects, without changing any verdict."""

from __future__ import annotations

from archkeel.ir.baseline import require_declared_filter, select_violations
from archkeel.ir.diagnostics import Diagnostic, DiagnosticError, ReportLocation
from archkeel.ir.model import CallRow, FilteredViolation, Observation, ReportFilter
from archkeel.ir.model import DiagnosticKind as _DiagnosticKind

from .ratchets import call_rows, calls_measured


def violations_in(model: Observation, report_filter: ReportFilter) -> tuple[FilteredViolation, ...]:
    return tuple(
        FilteredViolation(
            record,
            tuple(
                ReportLocation(entry.file, entry.line)
                for entry in model.evidence
                if entry.id in record.evidence_ids
            ),
        )
        for record in select_violations(model, report_filter)
    )


def calls_in(model: Observation, report_filter: ReportFilter) -> tuple[CallRow, ...]:
    """AD-100: `--only calls`, narrowed by `--component` to the calls its modules make.

    A profile that does not measure calls has none to list, and an empty list would read as a
    count it never took: refused like an unsupported rule (AD-97).
    """
    if not calls_measured(model):
        raise DiagnosticError(
            Diagnostic(
                _DiagnosticKind.RULE_UNSUPPORTED_BY_PROFILE,
                "--only calls",
                f"The {model.analyzer.name} profile does not measure calls, so it has none "
                "to list.",
                "Drop --only calls; only the Python profile lists unresolved calls.",
            )
        )
    require_declared_filter(model, report_filter)
    return tuple(
        row
        for row in call_rows(model)
        if report_filter.component is None or row.component == report_filter.component
    )


def report_filter_of(
    only_violations: bool,
    rule: str | None,
    component: str | None,
    only_calls: bool,
    only_architecture: bool = False,
    full_architecture: bool = False,
) -> ReportFilter | None:
    if (
        only_violations
        or only_calls
        or only_architecture
        or full_architecture
        or rule is not None
        or component is not None
    ):
        return ReportFilter(
            only_violations,
            rule,
            component,
            only_calls,
            only_architecture,
            full_architecture,
        )
    return None
