# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""`--timings FILE` writes the seconds of the phases of the core and changes nothing else (#659)."""

import json
from pathlib import Path

from core_support import HONEST, SUFFIX, case_root
from test_cli_core_only_scan import command

PHASES = ["prepare", "collect", "validate", "evaluate", "render", "join"]


def _timings(path: Path) -> dict[str, object]:
    document = json.loads(path.read_text(encoding="utf-8"))
    assert document["protocol"] == "archkeel-core-timings-1"
    assert (document["clock"], document["unit"]) == ("monotonic", "seconds")
    assert list(document["phases"]) == PHASES
    return document


def test_validate_writes_the_phases_and_the_output_stays_the_same(
    built: Path, tmp_path: Path
) -> None:
    binary = built / f"archkeel-core{SUFFIX}"
    target = tmp_path / "timings.json"
    with case_root(HONEST) as root:
        plain = command(binary, root, "--json")
        timed = command(binary, root, "--json", "--timings", str(target))
    assert timed.returncode == plain.returncode == 0, plain.stderr + timed.stderr
    assert timed.stdout == plain.stdout and timed.stderr == plain.stderr == ""
    document = _timings(target)
    seconds = list(document["phases"].values())
    assert all(isinstance(time, float) and time >= 0 for time in seconds)
    assert document["phases"]["join"] == 0, "one configuration has no system join"
    assert sum(seconds) <= document["core_seconds"] + 1e-5


def test_report_writes_the_page_and_the_phases(built: Path, tmp_path: Path) -> None:
    binary = built / f"archkeel-core{SUFFIX}"
    page, target = tmp_path / "report.html", tmp_path / "timings.json"
    with case_root(HONEST) as root:
        done = command(binary, root, "--output", str(page), "--timings", str(target), verb="report")
    assert done.returncode == 0, done.stdout + done.stderr
    assert page.read_text(encoding="utf-8").startswith("<!doctype html>")
    assert _timings(target)["phases"]["render"] > 0


def test_a_refused_run_writes_no_timings_file(built: Path, tmp_path: Path) -> None:
    binary = built / f"archkeel-core{SUFFIX}"
    target = tmp_path / "timings.json"
    empty = tmp_path / "empty"
    empty.mkdir()
    done = command(binary, empty, "--no-init", "--timings", str(target))
    assert done.returncode == 2, done.stdout + done.stderr
    assert not target.exists()


def test_a_timings_target_must_be_a_file(built: Path, tmp_path: Path) -> None:
    binary = built / f"archkeel-core{SUFFIX}"
    with case_root(HONEST) as root:
        done = command(binary, root, "--timings", "-")
    assert done.returncode == 2
    assert "--timings" in done.stdout + done.stderr
