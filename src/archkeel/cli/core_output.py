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
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise CoreError(f"the core timings value {name} is not a number")
    if not math.isfinite(value) or value < 0:
        raise CoreError(
            f"the core timings value {name} is not a finite number of seconds, 0 or more"
        )
    return float(value)


def read_timings(stderr: bytes) -> bytes | None:
    """The one timings line that the core wrote on standard error for a request that asked (#659).

    A refused scan, in whole or in a part of a system run, has the line `refused` and no seconds:
    the result is `None` and no file is written. A missing line, more than one line, another
    protocol, a missing or unknown field or a number that is not finite and not negative is a
    `CoreError`: a successful run that was asked for its timings must give them.
    """
    lines = stderr.strip().splitlines()
    if len(lines) != 1:
        found = "none" if not lines else f"{len(lines)} lines"
        raise CoreError(
            f"the core must write one timings line when it is asked for them; found {found}"
        )
    try:
        document = json.loads(lines[0])
    except ValueError as error:
        raise CoreError("the core timings line is not JSON") from error
    if not isinstance(document, dict) or document.get("protocol") != _TIMINGS_PROTOCOL:
        raise CoreError("the core timings line has another protocol")
    if set(document) == {"protocol", "refused"} and document["refused"] is True:
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
