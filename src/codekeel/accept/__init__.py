# Codekeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The CI acceptance command is not part of this milestone."""

from codekeel.ir.model import Diagnostic, RunResult


def unavailable() -> RunResult:
    return RunResult(
        "accept",
        2,
        diagnostics=(
            Diagnostic(
                "missing_tool",
                "codekeel accept",
                "CI acceptance is not implemented.",
                "Use the existing protected-branch CI acceptance process.",
            ),
        ),
    )
