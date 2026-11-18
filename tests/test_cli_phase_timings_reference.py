# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The nightly reference run of the phase timings on a pinned public Python project (#659, AD-878).

`tests/timing_reference/sympy` holds our files (configuration and contract, drafted by
`archkeel init` and not edited) and the pin of an unchanged release of SymPy: repository, tag and
commit. The run fetches that exact commit (`ARCHKEEL_FETCH_SOURCES=1`), checks that the bytes it
uses are that commit, scans it with `validate --timings` and `report --output --timings`, and keeps
each series in its own folder below the output folder.

It sets no limit. It checks that each run measured the same verdict, that every timings file keeps
the protocol, and that the core time lies inside the time of the command. A limit needs the spread
of many nightly runs first; see `tests/timing_reference/README.md`.

Offline replay: with `ARCHKEEL_SOURCE_CACHE=DIR` holding the pinned checkout, the run needs no
network (set `ARCHKEEL_FETCH_SOURCES=1` anyway). A cached checkout whose bytes are not the pinned
commit is refused, not fetched again and not deleted.
"""

import os
import platform
import sys
from pathlib import Path

import pytest
from core_support import ROOT

from tools import fixture_source, phase_timings

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


def reference_command(core: Path, verb: str, root: Path, timings: Path) -> list[str]:
    """The command for one reference run. A report gets its own page beside its timings."""
    arguments = [verb, "--root", str(root), "--json", "--timings", str(timings)]
    if verb == "report":
        arguments += ["--output", str(timings.with_suffix(".html"))]
    return [sys.executable, "-c", CODE, str(core), *arguments]


@pytest.mark.parametrize("verb", ["validate", "report"])
def test_the_phases_of_the_core_on_the_pinned_project(release_core: Path, verb: str) -> None:
    if not os.environ.get("ARCHKEEL_FETCH_SOURCES"):
        pytest.skip("the pinned source needs the network: the nightly run fetches it")
    spec = fixture_source.load(REFERENCE)
    assert spec is not None and RUNS >= 2

    def command(root: Path, timings: Path) -> list[str]:
        return reference_command(release_core, verb, root, timings)

    env = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
    load = os.getloadavg()[0] if hasattr(os, "getloadavg") else None
    folder, runs, verdicts = phase_timings.reference_run(
        REFERENCE, command, runs=RUNS, out=OUT / verb, cache=CACHE, env=env
    )
    assert len(verdicts) == 1, "each run must give the same exit code and the same frame"
    assert all(run.core_seconds <= run.cli_wall_seconds for run in runs), "core inside command"
    assert all(sum(run.phases.values()) <= run.core_seconds + 1e-5 for run in runs)
    if verb == "report":
        for number, run in enumerate(runs, start=1):
            page = folder / f"run-{number}.timings.html"
            assert page.read_bytes().startswith(b"<!doctype html>"), "the core wrote an HTML report"
            assert run.phases["render"] > 0, "the report render phase was measured"
    ((code, digest),) = verdicts
    environment = {
        "platform": platform.platform(),
        "machine": platform.machine(),
        "cpu_count": os.cpu_count(),
        "python": platform.python_version(),
        "load_average_1m_before": load,
        "core": release_core.name,
        "command": verb,
        "exit_code": code,
        "frame_sha256": digest,
        "run_folder": folder.name,
    }
    receipt = phase_timings.summary(runs, fixture_source.pin_facts(spec), environment)
    table = phase_timings.write_receipt(folder, receipt)
    print(f"{table}\nfiles: {folder}")
    if summary := os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(summary, "a", encoding="utf-8") as stream:
            stream.write(f"{table}\nFiles: `{verb}/{folder.name}` in `phase-timings-*`.\n")
