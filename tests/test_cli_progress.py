# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""#1621: a scan that runs past the delay writes a progress line to standard error only."""

import io
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from time import sleep

import pytest

from archkeel.cli import native_scan
from archkeel.cli.native_scan import _progress as progress
from archkeel.cli.native_scan import scan_progress


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


def test_the_scan_progress_line_names_the_root_not_the_working_folder(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """#1963-7: the line names the scanned root, so `--root other` says `other`."""
    labels: list[str] = []

    @contextmanager
    def record(where: str) -> Iterator[None]:
        labels.append(where)
        yield

    monkeypatch.setattr(native_scan, "_progress", record)
    with scan_progress(tmp_path / "other"):
        pass
    assert labels == ["other"]


def test_a_root_without_a_name_is_named_by_its_path(monkeypatch: pytest.MonkeyPatch) -> None:
    labels: list[str] = []

    @contextmanager
    def record(where: str) -> Iterator[None]:
        labels.append(where)
        yield

    monkeypatch.setattr(native_scan, "_progress", record)
    with scan_progress(Path("/")):
        pass
    assert labels == ["/"]
