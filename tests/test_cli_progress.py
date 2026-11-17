# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""#1621: a scan that runs past the delay writes a progress line to standard error only."""

import io
from time import sleep

from archkeel.cli.native_scan import _progress as progress


class _Tty(io.StringIO):
    def isatty(self) -> bool:
        return True


def test_a_quick_scan_writes_nothing() -> None:
    out = io.StringIO()
    with progress("p", stream=out, delay=5.0):
        pass
    assert out.getvalue() == ""


def test_a_slow_scan_on_a_pipe_writes_one_line() -> None:
    out = io.StringIO()
    with progress("proj", stream=out, delay=0.05):
        sleep(0.3)
    assert out.getvalue() == "archkeel: scanning proj, 0 s so far...\n"


def test_a_terminal_rewrites_the_line_and_clears_it() -> None:
    out = _Tty()
    with progress("proj", stream=out, delay=0.05):
        sleep(0.3)
    assert out.getvalue().startswith("\rarchkeel: scanning proj")
    assert out.getvalue().endswith("\r\033[K")
