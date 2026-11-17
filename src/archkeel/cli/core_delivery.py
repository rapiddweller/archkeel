# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The files that one run writes: the report page or frame (`--output`) and the baseline file
(`--write-baseline`), and the refusal of each file that was not written (AD-731).

A file that is not written keeps the frame of the run; the exit decision reads the refusals.
"""

from __future__ import annotations

from pathlib import Path
from typing import Final

from .core_arguments import Options
from .core_baseline import BaselineResult, BaselineState
from .core_frame import CoreError, CoreFrame, RefusalKind
from .core_output import write_output

_Refusal = tuple[RefusalKind, str]
_NOT_WRITTEN: Final = (
    "the run cannot be written as a baseline: a part of it is refused, and no baseline accepts a "
    "refused part; no baseline file was written"
)


def _deliver(options: Options, frame: CoreFrame, stdout: bytes, root: Path) -> list[_Refusal]:
    """Write each requested file. Each file that was not written, in the order of the request."""
    failures: list[_Refusal] = []
    try:
        _write_report(options, frame, stdout)
    except OSError as error:
        message = f"cannot write report file {options.output}: {error}; no report file was written"
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


def _write_report(options: Options, frame: CoreFrame, stdout: bytes) -> None:
    if options.output is None:
        return
    if options.format == "html":
        if frame.html is None:
            raise CoreError("the core frame lacks the requested HTML")
        payload = frame.html.encode("utf-8")
    else:
        payload = stdout
    write_output(options.output, payload)
