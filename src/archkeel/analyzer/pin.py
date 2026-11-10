# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Check the file of a pinned collector against its digest before the host starts it (AD-344)."""

import hashlib
import os
import shutil
from pathlib import Path

PIN_PREFIX = "sha256:"


def is_pin(value: str) -> bool:
    """Whether the text is `sha256:` and 64 lowercase hexadecimal digits."""
    digits = value.removeprefix(PIN_PREFIX)
    return (
        value.startswith(PIN_PREFIX)
        and len(digits) == 64
        and all(char in "0123456789abcdef" for char in digits)
    )


def pin_refusal(program: str, root: str, search_path: str, expected: str) -> str | None:
    """The reason to refuse the program, or None when its file has the pinned digest.

    A name with a directory part is relative to the scanned root, as the process starts there.
    Any other name is found on the search path. The file is read once, just before the start. A
    file that changes between this read and the start is outside this check.
    """
    if os.sep in program or (os.altsep is not None and os.altsep in program):
        located: str | None = str(Path(root, program))
    else:
        located = shutil.which(program, path=search_path)
    if located is None:
        return f"Collector could not execute: {program}"
    try:
        actual = PIN_PREFIX + hashlib.sha256(Path(located).read_bytes()).hexdigest()
    except OSError as error:
        return f"Collector could not execute: {error}"
    if actual != expected:
        return (
            f"The collector file {program} has digest {actual}, which does not match the "
            f"pinned digest {expected}. Pin the digest of the collector that you intend to use."
        )
    return None
