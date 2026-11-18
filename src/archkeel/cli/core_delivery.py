# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The files that one run writes: the report page or frame (`--output`) and the baseline file
(`--write-baseline`), and the refusal of each file that was not written (AD-731).

A file that is not written keeps the frame of the run; the exit decision reads the refusals.
"""

from __future__ import annotations

import os
from collections.abc import Iterator, Mapping
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


def _same_file(first: Path, second: Path) -> bool:
    """The same file, also through a link or a second name (a final link is followed)."""
    try:
        return first.resolve() == second.resolve() or os.path.samestat(first.stat(), second.stat())
    except OSError:
        return False


def _inputs(
    options: Options, root: Path, document: Mapping[str, object]
) -> Iterator[tuple[str, Path]]:
    """Each file that the run read and that no output file may replace: the configuration, the
    system document and the configuration of each part, the contract files, the baseline and the
    document of `--part-of` (#659)."""
    config = Path(options.config)
    yield "the configuration", Path.cwd() / config
    yield "the configuration", root / config
    system = document.get("system")
    if isinstance(system, dict):
        yield "the system document", root / str(system.get("document", ""))
        for part in system.get("parts", []):
            yield "the configuration of a part", root / str(part.get("config", ""))
    collect = (document.get("self_test") or {}).get("collect")  # type: ignore[attr-defined]
    files = collect.get("contract_files") if isinstance(collect, dict) else None
    for name in sorted(files) if isinstance(files, dict) else []:
        yield "a contract file", root / name
    for flag, name in (("--baseline", options.baseline), ("--part-of", options.part_of)):
        if name is not None:
            yield flag, root / name


def _source_names(document: Mapping[str, object]) -> set[str]:
    """The repository paths of the files that hold evidence of the run."""
    locations = document.get("locations")
    places = locations.values() if isinstance(locations, dict) else []
    return {str(place.get("path", "")) for place in places if isinstance(place, dict)}


def _collisions(options: Options, root: Path, document: Mapping[str, object]) -> list[str]:
    """Each target that names another target or an input of the run. Checked before any write, so
    a refused run changes no file (#659)."""
    write_baseline = None if options.write_baseline is None else root / options.write_baseline
    targets = [
        (flag, path)
        for flag, path in (
            ("--output", options.output),
            ("--timings", options.timings),
            ("--write-baseline", write_baseline),
        )
        if path is not None
    ]
    found = [
        f"{first[0]} and {second[0]} name the same file {first[1]}"
        for index, first in enumerate(targets)
        for second in targets[index + 1 :]
        if _same_file(first[1], second[1])
    ]
    inputs = list(_inputs(options, root, document)) if targets else []
    found += [
        f"{flag} {path} is {what} of this run and must not be replaced"
        for flag, path in targets
        for what, other in inputs
        if _same_file(path, other)
    ]
    sources = _source_names(document) if targets else set()
    for flag, path in targets:
        try:
            inside = path.resolve().relative_to(root.resolve()).as_posix()
        except (OSError, ValueError):
            continue
        if inside in sources:
            found.append(f"{flag} {path} is a source file of this run and must not be replaced")
    return found


def _deliver(
    options: Options,
    frame: CoreFrame,
    stdout: bytes,
    root: Path,
    timings: bytes | None = None,
    document: Mapping[str, object] | None = None,
) -> list[_Refusal]:
    """Write each requested file. Each file that was not written, in the order of the request.

    A target that names another target or an input of the run is refused before the first write:
    no file changes, and each refusal is named."""
    if collisions := _collisions(options, root, document or {}):
        return [(RefusalKind.IO_ERROR, f"{message}; no file was written") for message in collisions]
    failures: list[_Refusal] = []
    try:
        _write_report(options, frame, stdout)
    except OSError as error:
        message = f"cannot write report file {options.output}: {error}; no report file was written"
        failures.append((RefusalKind.IO_ERROR, message))
    if options.timings is not None and timings is not None:
        try:
            write_output(options.timings, timings)
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
