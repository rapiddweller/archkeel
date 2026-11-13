# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""#1023: a one-shot command scans its model less often; the Studio process keeps the default."""

import gc
from collections.abc import Iterator
from pathlib import Path

import pytest

import archkeel.cli as cli


@pytest.fixture(autouse=True)
def _restore_thresholds() -> Iterator[None]:
    before = gc.get_threshold()
    yield
    gc.set_threshold(*before)


def test_a_one_shot_command_raises_the_collector_thresholds(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(cli, "run_guide", lambda *_args: 0)
    gc.set_threshold(700, 10, 10)

    assert cli.main(["guide", "--root", str(tmp_path)]) == 0

    assert gc.get_threshold() == (50_000, 20, 100)
