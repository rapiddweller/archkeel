# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Resolve a pinned collector once and check its file against its digest (AD-344)."""

import hashlib
import os
import shutil
from pathlib import Path

PIN_PREFIX = "sha256:"


class PinError(ValueError):
    """The host must not start the pinned collector."""


def is_pin(value: str) -> bool:
    """Whether the text is `sha256:` and 64 lowercase hexadecimal digits."""
    digits = value.removeprefix(PIN_PREFIX)
    return (
        value.startswith(PIN_PREFIX)
        and len(digits) == 64
        and all(char in "0123456789abcdef" for char in digits)
    )


def pinned_path(program: str, root: str, search_path: str, expected: str) -> str:
    """The absolute path of the program, after its file has the pinned digest.

    A name with a directory part is relative to the scanned root, as the process starts there.
    A bare name is found on the search path only, never in the root. The caller starts the
    returned path, not the name, so the file that is hashed is the file that runs. A file inside
    the scanned root is refused: the repository under test must not supply its own collector.
    The file is read once, just before the start. A change between this read and the start is
    outside this check.
    """
    if os.sep in program or (os.altsep is not None and os.altsep in program):
        located: str | None = str(Path(root, program))
    else:
        located = shutil.which(program, path=search_path)
    if located is None or not Path(located).is_absolute():
        raise PinError(f"Collector could not execute: {program}")
    # The path to start keeps its links: a virtual environment finds its packages by its own path.
    started = os.path.abspath(located)
    if Path(started).resolve().is_relative_to(Path(root).resolve()):
        raise PinError(
            f"The pinned collector {program} is inside the scanned repository. "
            "Install the collector outside the repository."
        )
    try:
        actual = PIN_PREFIX + hashlib.sha256(Path(started).read_bytes()).hexdigest()
    except OSError as error:
        raise PinError(f"Collector could not execute: {error}") from error
    if actual != expected:
        raise PinError(
            f"The collector file {program} has digest {actual}, which does not match the "
            f"pinned digest {expected}. Pin the digest of the collector that you intend to use."
        )
    return started
