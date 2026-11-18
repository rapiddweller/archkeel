# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The files that one run writes: the report page or frame (`--output`) and the baseline file
(`--write-baseline`), and the refusal of each file that was not written (AD-731).

A file that is not written keeps the frame of the run; the exit decision reads the refusals.
"""

from __future__ import annotations

import hashlib
import html
import json
import os
import stat
from collections.abc import Mapping
from pathlib import Path
from typing import Final
from urllib.parse import quote

from .core_arguments import Options
from .core_baseline import BaselineResult, BaselineState
from .core_frame import CoreError, CoreFrame, RefusalKind
from .core_output import check_output, write_new, write_output

_Refusal = tuple[RefusalKind, str]
_NOT_WRITTEN: Final = (
    "the run cannot be written as a baseline: a part of it is refused, and no baseline accepts a "
    "refused part; no baseline file was written"
)


def _refuse_timings_target(options: Options, root: Path) -> None:
    """`--timings` must not name the baseline file that the same run writes (#659). No other input
    can collide: `--timings` names a file that does not exist, and `--output` is compared when the
    options are read."""
    if options.timings is None or options.write_baseline is None:
        return
    if options.timings.resolve() == (root / options.write_baseline).resolve():
        raise CoreError("--timings and --write-baseline name the same file; use two names")


def _deliver(
    options: Options,
    frame: CoreFrame,
    stdout: bytes,
    root: Path,
    document: Mapping[str, object],
    timings: bytes | None = None,
) -> list[_Refusal]:
    """Write each requested file. Each file that was not written, in the order of the request."""
    failures: list[_Refusal] = []
    try:
        _write_report(options, frame, stdout, document)
    except OSError as error:
        message = f"cannot write report file {options.output}: {error}; no report file was written"
        failures.append((RefusalKind.IO_ERROR, message))
    if options.timings is not None and timings is not None:
        try:
            write_new(options.timings, timings)
        except OSError as error:
            message = (
                f"cannot write timings file {options.timings}: {error}; no timings file was written"
            )
            failures.append((RefusalKind.IO_ERROR, message))
    if options.write_baseline is None:
        return failures
    # No part (a refused scan) or `not_written`: the core gave no bytes, and the frame stays.
    if frame.baseline is None or frame.baseline.state is BaselineState.NOT_WRITTEN:
        failures.append((RefusalKind.BASELINE_NOT_WRITTEN, _NOT_WRITTEN))
        return failures
    try:
        _write_baseline(options.write_baseline, frame.baseline, root)
    except OSError as error:
        message = f"cannot write the baseline file {error}; no baseline file was written"
        failures.append((RefusalKind.IO_ERROR, message))
    return failures


def _write_baseline(path: str, part: BaselineResult, root: Path) -> None:
    """Write the bytes that the core gave for `--write-baseline` below the project root, where
    `--baseline` reads them (AD-735). The shell adds nothing."""
    if part.file is None:
        raise CoreError(f"the core frame baseline is {part.state} and holds no bytes to write")
    try:
        write_output(root / path, part.file.encode("utf-8"))
    except OSError as error:
        raise OSError(f"{path}: {error}") from error


_GAP_MARKER = '<section id="gap-records-file">Gap records file unavailable.</section>'


def _gap_file(target: Path, document: Mapping[str, object], count: int) -> str:
    """Write the same run's frame under its content digest, without replacing another file."""
    content = json.dumps(document, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    digest = hashlib.sha256(content).hexdigest()
    path = target.with_name(f"archkeel-gaps-{digest}.json")
    try:
        write_new(path, content)
    except FileExistsError:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(descriptor, "rb") as existing:
            if not stat.S_ISREG(os.fstat(existing.fileno()).st_mode):
                raise OSError("the gap records file is not a regular file") from None
            if hashlib.file_digest(existing, "sha256").hexdigest() != digest:
                raise OSError("the existing gap records file has a different digest") from None
    href = html.escape(quote(path.name), quote=True)
    return (
        '<section id="gap-records-file"><h2>Gap records</h2>'
        f'<p><a href="{href}">Open gap records JSON</a> · {count} gap records</p>'
        f'<p>SHA-256: <code class="rp-code">{digest}</code></p>'
        "<p>Keep this file with the report. If the file is missing, the link cannot open it.</p>"
        "</section>"
    )


def _write_report(
    options: Options, frame: CoreFrame, stdout: bytes, document: Mapping[str, object]
) -> None:
    if options.output is None:
        return
    if options.format == "html":
        if frame.html is None:
            raise CoreError("the core frame lacks the requested HTML")
        page = frame.html
        gaps = document.get("collection_gaps")
        if _GAP_MARKER in page and isinstance(gaps, list):
            check_output(options.output)
            page = page.replace(_GAP_MARKER, _gap_file(options.output, document, len(gaps)), 1)
        payload = page.encode("utf-8")
    else:
        payload = stdout
    write_output(options.output, payload)
