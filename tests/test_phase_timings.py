# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The measurement and the spread of `tools/phase_timings.py` (#659), without the network."""

import json
import sys
from pathlib import Path

import pytest

from tools import phase_timings
from tools.phase_timings import PHASES, Run


def _run(wall: float, core: float, rss: int = 100 << 20) -> Run:
    return Run(0, wall, rss, core, {name: core / 10 for name in PHASES})


def test_the_spread_gives_the_smallest_median_and_largest_value_of_each_figure() -> None:
    found = phase_timings.spread([_run(3.0, 2.0), _run(5.0, 4.0), _run(4.0, 3.0)])
    assert found["cli_wall_seconds"] == {"min": 3.0, "median": 4.0, "max": 5.0, "spread": 0.5}
    assert found["core_seconds"]["median"] == 3.0
    assert found["outside_core_seconds"]["median"] == 1.0
    assert found["phase_collect"]["max"] == pytest.approx(0.4)
    assert found["peak_rss_bytes"]["spread"] == 0.0


def test_the_receipt_sets_no_limit_and_the_table_says_so() -> None:
    pin = {"name": "Project", "ref": "v1", "commit": "0123456789abcdef"}
    receipt = phase_timings.summary([_run(3.0, 2.0)], pin, {"cpu_count": 2})
    assert receipt["limits"].startswith("none") and receipt["pin"] == pin
    table = phase_timings.markdown(receipt)
    assert "| cli_wall_seconds | 3.000 s | 3.000 s | 3.000 s | 0% |" in table
    assert "| peak_rss_bytes | 100.000 MiB |" in table and "No limit is set" in table


def test_one_run_separates_the_wall_time_of_the_command_from_the_core_and_the_memory(
    tmp_path: Path,
) -> None:
    line = {
        "protocol": "archkeel-core-timings-1",
        "clock": "monotonic",
        "unit": "seconds",
        "phases": {name: 0.001 for name in PHASES},
        "core_seconds": 0.01,
    }
    script = (
        "import json, sys; "
        f"open(sys.argv[1], 'w').write(json.dumps({line!r}) + chr(10)); "
        "x = bytearray(50 << 20); print('output')"
    )
    timings, out = tmp_path / "timings.json", tmp_path / "out.txt"
    run = phase_timings.measure([sys.executable, "-c", script, str(timings)], timings, out, {})
    assert run.exit_code == 0 and out.read_text(encoding="utf-8") == "output\n"
    assert run.core_seconds == 0.01 and run.phases["collect"] == 0.001
    assert run.cli_wall_seconds > 0
    assert run.peak_rss_bytes > 50 << 20, "the memory of the command, in bytes"
    assert json.loads(timings.read_text(encoding="utf-8"))["protocol"].endswith("-1")
