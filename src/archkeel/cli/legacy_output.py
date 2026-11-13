# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Publish the existing shell's artifacts; core-only commands never load this module."""

import hashlib
import io
import json
import re
import sys
from pathlib import Path

from ..ir.model import RunResult
from ..ir.phases import PhaseClock
from ..ir.view_spec import ViewCheck
from .arguments import Command
from .legacy_bindings import (
    check_summary,
    init_summary,
    print_result,
    render_result,
    report_summary,
)
from .output_path import html_path as html_path


def write_files(root: Path, files: tuple[tuple[str, bytes], ...], artifacts: list[Path]) -> None:
    for relative, payload in files:
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
        artifacts.append(target)


def write_timings(path: Path, clock: PhaseClock) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(clock.to_dict(), indent=2) + "\n")


def write_json(artifact: Path, architecture: bytes) -> None:
    """Write architecture.json first, so a render failure still leaves the evidence."""
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_bytes(architecture)


def write_pages(
    artifact: Path, pages: tuple[tuple[str, bytes], ...], artifacts: list[Path]
) -> None:
    """Write the report pages beside architecture.json and drop obsolete details."""
    report_html = html_path(artifact, "report")
    for name, payload in pages:
        detail = artifact.parent / name
        detail.write_bytes(payload)
        if detail != report_html:
            artifacts.append(detail)
    written = {name for name, _ in pages}
    if written != {report_html.name}:
        for previous in report_pages(artifact):
            if previous.name not in written:
                previous.unlink()
    artifacts.extend((artifact, report_html))


def report_pages(artifact: Path) -> list[Path]:
    """The report pages a run writes beside architecture.json: main, detail and per component."""
    pages = (
        rf"{re.escape(artifact.stem)}\."
        r"(?:report|detail(?:-(?:component-[0-9a-f]{16}|unknown))?)\.html"
    )
    return [
        previous
        for previous in artifact.parent.glob(f"{artifact.stem}.*.html")
        if re.fullmatch(pages, previous.name)
    ]


def clear_report(artifact: Path) -> None:
    """Remove the files a run writes, so a link in their place is never followed."""
    for previous in (artifact, *report_pages(artifact)):
        previous.unlink(missing_ok=True)


def show_view(
    view: ViewCheck, text: str, spec: bytes, snapshot_path: Path, output: Path | None
) -> Path | None:
    """AD-287: write the Explorer of the checked snapshot with the check result in it."""
    from .arguments import Command, cache_folder
    from .legacy_bindings import render_architecture_pages, run_saved_report

    snapshot = snapshot_path.read_bytes()
    report = run_saved_report(snapshot_path)
    if report.architecture_projection is None:
        return None
    # Each view of each snapshot gets its own folder, so no view overwrites another.
    key = hashlib.sha256(
        f"{view.snapshot.source_digest}:{view.snapshot.contract_digest}:".encode() + spec
    ).hexdigest()[:16]
    artifact = (output or cache_folder(Command.VIEW, key)) / "architecture.json"
    clear_report(artifact)
    write_json(artifact, snapshot)
    pages = render_architecture_pages(
        report,
        snapshot,
        # The snapshot names no repository; the page heading names the view.
        repository=view.title,
        architecture_href=artifact.name,
        view_check=text,
    )
    write_pages(artifact, pages, [])
    return html_path(artifact, Command.REPORT)


def show_result(
    result: RunResult, command: Command, interactive: bool, artifacts: list[Path]
) -> int:
    if interactive and command in {Command.VIEW, Command.STORY}:
        # A view check or trace that did not run has no scan or rule verdicts to show.
        name = "view check" if command is Command.VIEW else "story trace"
        for item in result.diagnostics:
            print(f"archkeel {name} did not run on {item.subject}: {item.unknown_claim}")
            print(item.remedy)
        return result.exit_code
    if interactive:
        summary = (
            check_summary(result)
            if command is Command.CHECK
            else init_summary(result)
            if command is Command.INIT
            else report_summary(result)
        )
        print_result(result, summary, artifacts=tuple(str(path) for path in artifacts))
    else:
        payload = render_result(result)
        if isinstance(sys.stdout, io.TextIOWrapper):
            sys.stdout.buffer.write(payload)
        else:
            sys.stdout.write(payload.decode("utf-8"))
    return result.exit_code
