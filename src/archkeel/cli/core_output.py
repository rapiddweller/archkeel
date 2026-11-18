# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Read the optional core presentation and atomically write received bytes (AD-440)."""

from __future__ import annotations

import json
import math
import os
import re
import secrets
import stat
from collections.abc import Mapping
from pathlib import Path
from typing import Final

from .core_json import CoreError, as_object, as_text


def read_html(
    frame: Mapping[str, object],
    status: str,
    request: Mapping[str, object] | None,
) -> str | None:
    """The HTML part of a frame if the request asked for it, else `None`."""

    if "html" not in frame and not (request and request.get("html")):
        return None
    part = as_object(frame.get("html"), "html")
    if part["protocol"] != "archkeel-core-html-1" or part["status"] != status:
        raise CoreError("the core HTML part has another protocol or status")
    document = as_text(part["document"], "html.document")
    heading = f"<h1>Verdict: {status}</h1>"
    headings = re.findall(r"<h[1-6]\b[^>]*>\s*Verdict:", document, flags=re.IGNORECASE)
    if document.count(heading) != 1 or headings != ["<h1>Verdict:"]:
        raise CoreError("the core HTML document lacks its one exact verdict heading")
    return document


_TIMINGS_PROTOCOL: Final = "archkeel-core-timings-1"
_PHASES: Final = ("prepare", "collect", "validate", "evaluate", "render", "join")
# The core writes each phase with six decimals, so the rounded phases can exceed the rounded total
# by a few millionths of a second.
_ROUNDING: Final = 1e-5


def _seconds(value: object, name: str) -> float:
    """A finite number of seconds, 0 or more. A JSON integer too large for a float is refused."""
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise CoreError(f"the core timings value {name} is not a number")
    try:
        seconds = float(value)
    except OverflowError as error:
        raise CoreError(f"the core timings value {name} is too large") from error
    if not math.isfinite(seconds) or seconds < 0:
        raise CoreError(
            f"the core timings value {name} is not a finite number of seconds, 0 or more"
        )
    return seconds


def read_timings(stderr: bytes, *, refused: bool) -> bytes | None:
    """The one timings line that the core wrote on standard error for a request that asked (#659).

    `refused` comes from the frame (a refused collection, in whole or in a part of a system run),
    never from this line. The line must agree with it: a refused frame has the line `refused` and
    gives `None` (no file); any other frame has the complete line, which is checked as a whole. A
    missing or second line, another protocol, an unknown or missing field, a number that is not a
    finite number of seconds of 0 or more, or a line that disagrees with the frame is a
    `CoreError`: a run that was asked for its timings must give them.
    """
    lines = stderr.strip().splitlines()
    if len(lines) != 1:
        found = "none" if not lines else f"{len(lines)} lines"
        raise CoreError(
            f"the core must write one timings line when it is asked for them; found {found}"
        )
    try:
        document = json.loads(lines[0])
    except (ValueError, RecursionError) as error:
        raise CoreError("the core timings line is not JSON") from error
    if not isinstance(document, dict) or document.get("protocol") != _TIMINGS_PROTOCOL:
        raise CoreError("the core timings line has another protocol")
    marker = set(document) == {"protocol", "refused"} and document["refused"] is True
    if marker != refused:
        raise CoreError(
            "the core timings line says "
            + ("refused" if marker else "measured")
            + ", and its frame says "
            + ("refused" if refused else "decided")
        )
    if marker:
        return None
    if set(document) != {"protocol", "clock", "unit", "phases", "core_seconds"}:
        raise CoreError("the core timings line has other fields than the protocol names")
    if (document["clock"], document["unit"]) != ("monotonic", "seconds"):
        raise CoreError("the core timings are not monotonic seconds")
    phases = document["phases"]
    if not isinstance(phases, dict) or list(phases) != list(_PHASES):
        raise CoreError("the core timings do not hold the phases in order: " + ", ".join(_PHASES))
    total = sum(_seconds(phases[name], name) for name in _PHASES)
    if total > _seconds(document["core_seconds"], "core_seconds") + _ROUNDING:
        raise CoreError("the core timings phases sum to more than the time of the core")
    return lines[0] + b"\n"


def _parent(path: Path) -> int:
    # Resolve ancestor links once; the handle pins the directory used for the atomic replacement.
    if os.name != "posix":
        raise OSError("atomic report output needs directory handles on this platform")
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    try:
        parent = path.parent.resolve(strict=True)
        return os.open(parent, flags)
    except (OSError, RuntimeError) as error:
        raise OSError(f"cannot open report parent directory {path.parent}: {error}") from error


def _target(directory: int, name: str) -> None:
    try:
        mode = os.stat(name, dir_fd=directory, follow_symlinks=False).st_mode
    except FileNotFoundError:
        return
    if not stat.S_ISREG(mode):
        raise OSError("the report target must be a regular file, not a directory or link")


def check_output(path: Path) -> None:
    """Refuse an unsafe report target before writing its companion file."""
    directory = _parent(path)
    try:
        _target(directory, path.name)
    finally:
        os.close(directory)


def write_output(path: Path, payload: bytes) -> None:
    """Atomically replace one regular file. Refuse final links and missing parents. No sidecars."""
    directory = _parent(path)
    temporary = f".archkeel-{secrets.token_hex(16)}"
    created = False
    try:
        _target(directory, path.name)
        descriptor = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600,
            dir_fd=directory,
        )
        created = True
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        _target(directory, path.name)
        os.replace(temporary, path.name, src_dir_fd=directory, dst_dir_fd=directory)
        created = False
    finally:
        try:
            if created:
                os.unlink(temporary, dir_fd=directory)
        finally:
            os.close(directory)


def write_new(path: Path, payload: bytes) -> None:
    """Create one regular file that does not exist, with all of its bytes, or fail.

    The bytes go to a temporary file in the directory of `path`; the file is then linked under its
    name, which fails when the name exists, also as a link, and when it appears during the write. It
    never replaces a file (`--timings`, #659)."""
    directory = _parent(path)
    temporary = f".archkeel-{secrets.token_hex(16)}"
    created = False
    try:
        descriptor = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600,
            dir_fd=directory,
        )
        created = True
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, path.name, src_dir_fd=directory, dst_dir_fd=directory)
    finally:
        try:
            if created:
                os.unlink(temporary, dir_fd=directory)
        finally:
            os.close(directory)
