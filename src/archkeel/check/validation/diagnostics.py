# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Shared contract diagnostics."""

from __future__ import annotations

from archkeel.ir.model import Diagnostic, DiagnosticCode, ReportLocation


def _diagnostic(
    code: DiagnosticCode,
    pointer: str,
    subject: str,
    claim: str,
    remedy: str,
    locations: tuple[ReportLocation, ...] = (),
    contract_path: str | None = None,
) -> Diagnostic:
    return Diagnostic(
        "contract_invalid", subject, claim, remedy, pointer, code, locations, contract_path
    )


def _sorted(diagnostics: list[Diagnostic]) -> tuple[Diagnostic, ...]:
    return tuple(
        sorted(
            diagnostics,
            key=lambda item: (item.pointer or "", item.subject, item.unknown_claim, item.remedy),
        )
    )
