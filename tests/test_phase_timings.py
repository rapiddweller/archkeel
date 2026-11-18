# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The measurement and the spread of `tools/phase_timings.py` (#659), without the network."""

import json
import os
import sys
import threading
from pathlib import Path

import pytest
from core_support import HONEST, ROOT, case_root
from test_cli_phase_timings_reference import reference_command
from test_report_gallery_sources import _upstream

from tools import phase_timings
from tools.fixture_source import SourceError
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
    receipt["environment"]["command"] = "report"
    assert "Phase timings (report)" in phase_timings.markdown(receipt)


def test_reference_report_writes_distinct_pages_and_measures_render(
    release_core: Path, tmp_path: Path
) -> None:
    """The nightly command asks the real core for an HTML page, not just a report frame."""
    env = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
    frames = []
    with case_root(HONEST) as root:
        for number in (1, 2):
            timings = tmp_path / f"run-{number}.timings.json"
            output = tmp_path / f"run-{number}.stdout.json"
            run = phase_timings.measure(
                reference_command(release_core, "report", root, timings), timings, output, env
            )
            assert run.exit_code == 0
            assert run.phases["render"] > 0
            assert timings.with_suffix(".html").read_bytes().startswith(b"<!doctype html>")
            frames.append(output.read_bytes())
        validate = reference_command(release_core, "validate", root, tmp_path / "validate.json")
        assert "--output" not in validate
    assert frames[0] == frames[1], "the different page names do not change the JSON frame"


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


# The output folders and the pinned source of the reference run (#659, review of PR #1838).
# A local repository stands in for the project; nothing here needs the network.
LINE = {
    "protocol": "archkeel-core-timings-1",
    "clock": "monotonic",
    "unit": "seconds",
    "phases": {name: 0.001 for name in PHASES},
    "core_seconds": 0.01,
}
STUB = (
    "import json, sys\n"
    "open(sys.argv[1], 'w').write(json.dumps(%r) + chr(10))\n"
    "print('frame of ' + sys.argv[2])\n"
)


def _reference(tmp_path: Path) -> Path:
    """A fixture folder of ours with the pin of a local repository."""
    reference = tmp_path / "reference"
    reference.mkdir()
    (reference / "SOURCE.json").write_text(json.dumps(_upstream(tmp_path)), encoding="utf-8")
    return reference


def _command(root: Path, timings: Path) -> list[str]:
    return [sys.executable, "-c", STUB % (LINE,), str(timings), str(root)]


def _sentinel(folder: Path) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "inner").mkdir(exist_ok=True)
    (folder / "inner" / "deep.txt").write_text("keep\n")
    (folder / "important.txt").write_text("keep\n")
    return folder


def _intact(folder: Path) -> bool:
    return (folder / "important.txt").read_text() == "keep\n" and (
        folder / "inner" / "deep.txt"
    ).read_text() == "keep\n"


def test_a_run_folder_is_new_and_nothing_in_the_output_folder_is_deleted(tmp_path: Path) -> None:
    out = _sentinel(tmp_path / "out")
    folders = [phase_timings.new_run_dir(out) for _ in range(3)]
    assert len({*folders}) == 3 and all(folder.is_dir() for folder in folders)
    assert _intact(out)
    assert {path.name for path in out.iterdir()} == {
        "important.txt",
        "inner",
        *(f.name for f in folders),
    }


def test_many_runs_at_once_get_folders_of_their_own(tmp_path: Path) -> None:
    out, found = tmp_path / "out", []
    threads = [
        threading.Thread(target=lambda: found.append(phase_timings.new_run_dir(out)))
        for _ in range(16)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert len({*found}) == 16 == len(list(out.iterdir()))


def test_a_reference_run_keeps_one_folder_with_its_files_and_leaves_the_rest(
    tmp_path: Path,
) -> None:
    reference, out = _reference(tmp_path), _sentinel(tmp_path / "out")
    folder, runs, verdicts = phase_timings.reference_run(
        reference, _command, runs=2, out=out, cache=tmp_path / "cache", env={}
    )
    assert _intact(out) and folder.parent == out and len(runs) == 2 and len(verdicts) == 1
    assert sorted(path.name for path in folder.iterdir()) == [
        "run-1.timings.json",
        "run-2.timings.json",
    ]


def test_two_reference_runs_at_once_do_not_delete_each_other(tmp_path: Path) -> None:
    reference, out = _reference(tmp_path), _sentinel(tmp_path / "out")
    cache, folders, errors = tmp_path / "cache", [], []

    def run() -> None:
        try:
            folders.append(
                phase_timings.reference_run(
                    reference, _command, runs=2, out=out, cache=cache, env={}
                )[0]
            )
        except BaseException as error:  # noqa: BLE001 - the test reports it
            errors.append(error)

    threads = [threading.Thread(target=run) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert not errors, errors
    assert len({*folders}) == 2 and _intact(out)
    assert all(len(list(folder.iterdir())) == 2 for folder in folders)


def test_a_failed_fetch_or_a_refused_cache_leaves_the_output_folder_as_it_was(
    tmp_path: Path,
) -> None:
    reference, out = _reference(tmp_path), _sentinel(tmp_path / "out")
    pinned = (reference / "SOURCE.json").read_text()
    gone = {**json.loads(pinned), "commit": "0" * 40}
    (reference / "SOURCE.json").write_text(json.dumps(gone))
    with pytest.raises(SourceError):
        phase_timings.reference_run(
            reference, _command, runs=2, out=out, cache=tmp_path / "c1", env={}
        )
    assert _intact(out) and {path.name for path in out.iterdir()} == {"important.txt", "inner"}
    # A cache with the right name and other bytes: refused, and out is untouched.
    (reference / "SOURCE.json").write_text(pinned)
    cache = tmp_path / "cache"
    phase_timings.reference_run(
        reference, _command, runs=2, out=tmp_path / "o2", cache=cache, env={}
    )
    (next(cache.iterdir()) / "pkg" / "a.py").write_text("x = 2\n")
    before = {path.name for path in out.iterdir()}
    with pytest.raises(SourceError, match="differs from the pinned commit"):
        phase_timings.reference_run(reference, _command, runs=2, out=out, cache=cache, env={})
    assert _intact(out) and {path.name for path in out.iterdir()} == before
