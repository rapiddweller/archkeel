# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The nightly reference run of the phase timings on a pinned public Python project (#659, AD-878).

`tests/timing_reference/sympy` holds our files (configuration and contract, drafted by
`archkeel init` and not edited) and the pin of an unchanged release of SymPy: repository, tag and
commit. The run fetches that exact commit (`ARCHKEEL_FETCH_SOURCES=1`), scans it several times
with `validate --timings`, and keeps one timings file for each run, a receipt and a table.

It sets no limit. It checks that each run measured the same verdict, that every timings file keeps
the protocol, and that the core time lies inside the time of the command. A limit needs the spread
of many nightly runs first; see `tests/timing_reference/README.md`.

Offline replay: with `ARCHKEEL_SOURCE_CACHE=DIR` holding the pinned checkout, the run needs no
network (set `ARCHKEEL_FETCH_SOURCES=1` anyway; a cached commit is not fetched again).
"""

import hashlib
import json
import os
import platform
import shutil
import sys
from pathlib import Path

import pytest
from core_support import ROOT

from tools import fixture_source, phase_timings
from tools.fixture_tree import fixture_tree

REFERENCE = ROOT / "tests" / "timing_reference" / "sympy"
RUNS = int(os.environ.get("ARCHKEEL_TIMINGS_RUNS", "5"))
OUT = Path(os.environ.get("ARCHKEEL_TIMINGS_DIR", ROOT / "test-artifacts" / "phase-timings"))
CACHE = Path(os.environ["ARCHKEEL_SOURCE_CACHE"]) if "ARCHKEEL_SOURCE_CACHE" in os.environ else None
# The command patches the place of the core and then runs the product entry.
CODE = (
    "import sys\n"
    "from pathlib import Path\n"
    "from archkeel.cli import core_only, main\n"
    "core = Path(sys.argv.pop(1))\n"
    "core_only.locate_core = lambda: core\n"
    "sys.exit(main())\n"
)


def test_the_phases_of_the_core_on_the_pinned_project(release_core: Path) -> None:
    if not os.environ.get("ARCHKEEL_FETCH_SOURCES"):
        pytest.skip("the pinned source needs the network: the nightly run fetches it")
    spec = fixture_source.load(REFERENCE)
    assert spec is not None and RUNS >= 2
    shutil.rmtree(OUT, ignore_errors=True)
    OUT.mkdir(parents=True)
    env = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
    load = os.getloadavg()[0] if hasattr(os, "getloadavg") else None
    runs, verdicts = [], set()
    with fixture_tree(REFERENCE, None, CACHE) as root:
        for number in range(1, RUNS + 1):
            timings, stdout = OUT / f"run-{number}.timings.json", OUT / f"run-{number}.stdout.json"
            argv = [sys.executable, "-c", CODE, str(release_core), "validate", "--root", str(root)]
            run = phase_timings.measure(
                [*argv, "--json", "--timings", str(timings)], timings, stdout, env
            )
            verdicts.add((run.exit_code, hashlib.sha256(stdout.read_bytes()).hexdigest()))
            runs.append(run)
            stdout.unlink()  # the frame is large; its hash is kept in the receipt
    assert len(verdicts) == 1, "each run must give the same exit code and the same frame"
    assert all(run.core_seconds <= run.cli_wall_seconds for run in runs), (
        "the core is inside the command"
    )
    assert all(sum(run.phases.values()) <= run.core_seconds + 1e-5 for run in runs)
    ((code, digest),) = verdicts
    environment = {
        "platform": platform.platform(),
        "machine": platform.machine(),
        "cpu_count": os.cpu_count(),
        "python": platform.python_version(),
        "load_average_1m_before": load,
        "core": str(release_core.name),
        "exit_code": code,
        "frame_sha256": digest,
    }
    receipt = phase_timings.summary(runs, fixture_source.pin_facts(spec), environment)
    (OUT / "summary.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    table = phase_timings.markdown(receipt)
    (OUT / "summary.md").write_text(table, encoding="utf-8")
    print(table)
    if summary := os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(summary, "a", encoding="utf-8") as stream:
            stream.write(table)
