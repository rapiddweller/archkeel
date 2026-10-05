# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Rationale validation diagnostics."""

from __future__ import annotations

import re

from archkeel.ir.model import ArchitectureContract, Diagnostic, DiagnosticCode

from .diagnostics import _diagnostic

_REPEATED_RATIONALE = re.compile(r"(?:The )?\S+ does not depend on \S+\.", re.IGNORECASE)

# Requires grants permission; detect filler without requiring a prohibition (AD-32).
_REPEATED_REQUIRES = re.compile(
    r"(?:The )?\S+ (?:depends on|requires|uses|needs) \S+\.", re.IGNORECASE
)

_PLACEHOLDER_RATIONALE = re.compile(r"(?:todo|tbd|placeholder)(?:\b|:)", re.IGNORECASE)


def rationale_diagnostics(contract: ArchitectureContract) -> tuple[Diagnostic, ...]:
    """Reject placeholder rationales and rationales that only repeat the rule."""
    diagnostics = []
    for index, rule in enumerate(contract.rules):
        rationale = rule.rationale.strip()
        code: DiagnosticCode
        if _REPEATED_RATIONALE.fullmatch(rationale):
            code = "rationale.repeated"
            claim = "The rationale repeats the forbidden dependency without explaining why."
        elif _PLACEHOLDER_RATIONALE.match(rationale):
            code = "rationale.placeholder"
            claim = "The rationale is a placeholder."
        else:
            continue
        diagnostics.append(
            _diagnostic(
                code,
                f"/rules/{index}/rationale",
                rule.id,
                claim,
                "Explain the architectural reason for this dependency boundary.",
            )
        )
    for index, component in enumerate(contract.components):
        for position, entry in enumerate(component.requires or ()):
            rationale = entry.rationale.strip()
            entry_code: DiagnosticCode
            if _REPEATED_REQUIRES.fullmatch(rationale):
                entry_code = "rationale.repeated"
                claim = "The rationale repeats the requires entry without explaining why."
            elif _PLACEHOLDER_RATIONALE.match(rationale):
                entry_code = "rationale.placeholder"
                claim = "The rationale is a placeholder."
            else:
                continue
            diagnostics.append(
                _diagnostic(
                    entry_code,
                    f"/components/{index}/requires/{position}/rationale",
                    f"{component.label} -> {entry.component}",
                    claim,
                    "Explain the architectural reason for this dependency boundary.",
                )
            )
    return tuple(diagnostics)
