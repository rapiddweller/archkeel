# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""A named, scalable timeout for a test that runs a child process (#1206).

A fixed 15 s or 30 s timeout fails on a loaded machine and says nothing about the code. The base
seconds of a call are multiplied by `ARCHKEEL_TEST_TIMEOUT_SCALE` (default 4), and a timeout names
itself, its base and the elapsed time.
"""

from __future__ import annotations

import os
import subprocess
import time
from typing import Any

import pytest

SCALE = float(os.environ.get("ARCHKEEL_TEST_TIMEOUT_SCALE", "4"))


def bounded(base_seconds: float) -> float:
    """The timeout of a call whose run on an idle machine is well below `base_seconds`."""
    return base_seconds * SCALE


def run_bounded(*args: Any, timeout: float, **kwargs: Any) -> subprocess.CompletedProcess[Any]:
    """`subprocess.run` with `bounded(timeout)`; a timeout fails the test with a message."""
    limit = bounded(timeout)
    started = time.monotonic()
    try:
        return subprocess.run(*args, timeout=limit, **kwargs)
    except subprocess.TimeoutExpired as error:
        elapsed = time.monotonic() - started
        pytest.fail(
            f"the child ran {elapsed:.1f} s and was stopped at {limit:g} s "
            f"(base {timeout:g} s x ARCHKEEL_TEST_TIMEOUT_SCALE {SCALE:g}): {error.cmd}"
        )
