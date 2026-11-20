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
from collections.abc import Mapping
from pathlib import Path
from typing import Final
from urllib.parse import quote

from .core_arguments import Options
from .core_baseline import BaselineResult, BaselineState
from .core_frame import CoreError, CoreFrame, RefusalKind
from .core_json import as_object
from .core_output import write_new, write_output

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


def _gap_file(
    target: Path,
    document: Mapping[str, object],
    count: int,
    *,
    note: str = "Keep this file with the report. If the file is missing, the link cannot open it.",
) -> tuple[str, Path, bytes]:
    """Name the same run's frame by the digest of its bytes."""
    content = json.dumps(document, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    digest = hashlib.sha256(content).hexdigest()
    path = target.with_name(f"archkeel-gaps-{digest}.json")
    href = html.escape(quote(path.name), quote=True)
    markup = (
        '<section id="gap-records-file"><h2>Gap records</h2>'
        f'<p><a href="{href}">Open gap records JSON</a> · {count} gap records</p>'
        f'<p>SHA-256: <code class="rp-code">{digest}</code></p>'
        f"<p>{html.escape(note)}</p>"
        "</section>"
    )
    return markup, path, content


def _write_report(
    options: Options, frame: CoreFrame, stdout: bytes, document: Mapping[str, object]
) -> None:
    if options.output is None:
        return
    companion = None
    if options.format == "html":
        if frame.html is None:
            raise CoreError("the core frame lacks the requested HTML")
        page = frame.html
        gaps = document.get("collection_gaps")
        if _GAP_MARKER in page and isinstance(gaps, list):
            markup, path, content = _gap_file(options.output, document, len(gaps))
            page = page.replace(_GAP_MARKER, markup, 1)
            companion = (path, content)
        payload = page.encode("utf-8")
    else:
        payload = stdout
    write_output(options.output, payload, companion=companion)


def _explorer_report(stdout: bytes, frame: CoreFrame) -> tuple[str, tuple[str, bytes]]:
    if frame.html is None:
        raise CoreError("the core did not give the native report")
    document = as_object(json.loads(stdout), "frame")
    document.pop("html", None)
    gaps = document.get("collection_gaps")
    if not isinstance(gaps, list):
        raise CoreError("the core frame has no collection gaps")
    markup, path, content = _gap_file(
        Path("report.html"),
        document,
        len(gaps),
        note="This link is available while the Explorer is running.",
    )
    return frame.html.replace(_GAP_MARKER, markup, 1), (path.name, content)
