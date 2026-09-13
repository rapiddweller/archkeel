"""The CI acceptance command is not part of this milestone."""

from pledge.ir.model import Diagnostic, RunResult


def unavailable() -> RunResult:
    return RunResult(
        "accept",
        2,
        diagnostics=(
            Diagnostic(
                "missing_tool",
                "pledge accept",
                "CI acceptance is not implemented.",
                "Use the existing protected-branch CI acceptance process.",
            ),
        ),
    )
