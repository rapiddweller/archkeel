# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""#1206: a child process of a test gets a scalable, named timeout, and a timeout names itself."""

import sys
from pathlib import Path

import pytest
import timeout_support
from timeout_support import bounded, run_bounded

ROOT = Path(__file__).parents[1]


def test_the_timeout_is_the_base_times_the_scale(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(timeout_support, "SCALE", 4.0)
    assert bounded(15) == 60 and bounded(30) == 120


def test_a_timeout_fails_the_test_with_the_limit_the_base_and_the_elapsed_time(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(timeout_support, "SCALE", 1.0)
    with pytest.raises(pytest.fail.Exception) as failed:
        run_bounded([sys.executable, "-c", "import time; time.sleep(5)"], timeout=0.3)
    text = str(failed.value)
    assert "stopped at 0.3 s" in text and "base 0.3 s" in text and "SCALE 1" in text.upper()


def test_a_finished_child_returns_its_result() -> None:
    done = run_bounded(
        [sys.executable, "-c", "print(7)"], timeout=15, capture_output=True, text=True
    )
    assert done.stdout.strip() == "7"
