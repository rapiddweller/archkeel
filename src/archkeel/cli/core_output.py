# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Read the optional core presentation and atomically write received bytes (AD-440)."""

from __future__ import annotations

import os
import re
import secrets
import stat
from collections.abc import Mapping
from pathlib import Path

from .core_json import CoreError, _fields, _text


def read_html(
    frame: Mapping[str, object],
    status: str,
    request: Mapping[str, object] | None,
) -> str | None:
    if "html" not in frame and not (request and request.get("html")):
        return None
    part = _fields(frame.get("html"), "html", frozenset({"protocol", "status", "document"}))
    if part["protocol"] != "archkeel-core-html-1" or part["status"] != status:
        raise CoreError("the core HTML part has another protocol or status")
    document = _text(part["document"], "html.document")
    heading = f"<h1>Verdict: {status}</h1>"
    headings = re.findall(r"<h[1-6]\b[^>]*>\s*Verdict:", document, flags=re.IGNORECASE)
    if document.count(heading) != 1 or headings != ["<h1>Verdict:"]:
        raise CoreError("the core HTML document lacks its one exact verdict heading")
    return document


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
