# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Print command results for people reading an interactive terminal."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Final

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from archkeel.ir.model import Diagnostic, RunResult

from .summary import Badge, State, Summary, badge

_COLORS: Final[dict[State, str]] = {
    "pass": "green",
    "fail": "red",
    "info": "cyan",
    "unknown": "yellow",
}


@contextmanager
def progress(message: str) -> Iterator[None]:
    """Show a spinner on stderr so stdout stays reserved for the result."""
    console = Console(stderr=True)
    if not console.is_terminal:
        yield
        return
    with console.status(message):
        yield


def _badge(value: Badge) -> Text:
    return Text(f"{value.symbol} {value.label}", style=f"bold {_COLORS[value.state]}")


def _diagnostic(item: Diagnostic) -> Panel:
    fields = Table.grid(padding=(0, 1))
    fields.add_column(style="dim", no_wrap=True)
    fields.add_column()
    for name, value in (
        ("subject", item.subject),
        ("claim", item.unknown_claim),
        ("remedy", item.remedy),
        ("pointer", item.pointer),
        ("code", item.code),
    ):
        if value:
            fields.add_row(name, Text(value))
    return Panel(
        fields,
        title=Text(f"Diagnostic · {item.kind}"),
        title_align="left",
        border_style=_COLORS["unknown"],
        box=box.ROUNDED,
    )


def print_result(
    result: RunResult,
    summary: Summary,
    *,
    artifacts: tuple[str, ...],
    console: Console | None = None,
) -> None:
    """Print the decision, verdicts, regressions, failures, diagnostics and artifact paths."""
    output = console or Console()
    output.print(
        Panel(
            Text.assemble(_badge(summary.decision), "  ", summary.sentence),
            title=Text(f"archkeel {result.command}", style="bold"),
            title_align="left",
            border_style=_COLORS[summary.decision.state],
            box=box.ROUNDED,
        )
    )
    verdicts = Table(
        title="Independent verdicts", title_justify="left", box=box.SIMPLE_HEAD, expand=True
    )
    verdicts.add_column("Verdict", no_wrap=True)
    verdicts.add_column("Result", no_wrap=True)
    verdicts.add_column("Reason", ratio=1)
    for row in summary.verdicts:
        verdicts.add_row(
            Text.assemble(row.label, "\n", (row.key, "dim")),
            _badge(badge(row.value)),
            Text(row.reason),
        )
    output.print(verdicts)
    if summary.claims:
        output.print(Text(summary.claims, style="dim"))
    if summary.regressions:
        regressions = Table(
            title="Regression checks", title_justify="left", box=box.SIMPLE_HEAD, expand=True
        )
        regressions.add_column("Measurement", ratio=1)
        regressions.add_column("Accepted → candidate", justify="right", no_wrap=True)
        regressions.add_column("Status", no_wrap=True)
        for name, accepted, candidate, status in summary.regressions:
            regressions.add_row(
                Text(name), Text(f"{accepted} → {candidate}"), _badge(badge(status))
            )
        output.print(regressions)
    if result.failures:
        output.print(Text("Failures", style="bold"))
        for line in (*(f"• {failure}" for failure in result.failures), *summary.call_sites):
            output.print(Text(f"  {line}"))
    for diagnostic in result.diagnostics:
        output.print(_diagnostic(diagnostic))
    for path in artifacts:
        output.print(Text.assemble(("→ ", "dim"), path))
