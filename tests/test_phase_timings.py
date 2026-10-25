# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
import json
import math
import subprocess
import time
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_architecture_demo import _prepare_repo

import tools.report_timing as report_timing
from archkeel.cli import main
from archkeel.ir import phases
from archkeel.ir.phases import Phase, PhaseClock, WorkCounter
from tools.report_timing import main as receipt_main


def _ticks(monkeypatch: pytest.MonkeyPatch, values: list[float]) -> None:
    ticks = iter(values)
    monkeypatch.setattr(phases, "perf_counter", lambda: next(ticks))


def test_clock_adds_a_repeated_phase_and_omits_phases_that_never_ran(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _ticks(monkeypatch, [0.0, 1.5, 2.0, 2.25])
    clock = PhaseClock()
    with clock.measure(Phase.COLLECT):
        pass
    with clock.measure(Phase.COLLECT):
        pass
    clock.count(WorkCounter.FILES_PARSED, 3)
    clock.count(WorkCounter.FILES_PARSED, 4)
    timings = clock.to_dict()
    assert timings == {
        "schema_version": 1,
        "phases": {"collect": 1.75},
        "counters": {"files_parsed": 7},
    }


def test_clock_sorts_keys_and_rounds_seconds_to_three_digits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _ticks(monkeypatch, [0.0, 1.23456, 0.0, 0.0004])
    clock = PhaseClock()
    with clock.measure(Phase.ENCODE):
        pass
    with clock.measure(Phase.RENDER):
        pass
    clock.count(WorkCounter.RECORDS, 2)
    clock.count(WorkCounter.ARCHITECTURE_BYTES, 9)
    timings = clock.to_dict()
    phase_names = list(timings["phases"])
    counter_names = list(timings["counters"])
    assert phase_names == sorted(phase_names) == ["encode", "render"]
    assert counter_names == sorted(counter_names) == ["architecture_bytes", "records"]
    assert timings["phases"] == {"encode": 1.235, "render": 0.0}


def _report(root: Path, output: Path, *extra: str) -> int:
    return main(["report", "--root", str(root), "--output", str(output), "--json", *extra])


def _written_bytes(output: Path) -> dict[str, bytes]:
    return {path.name: path.read_bytes() for path in sorted(output.parent.iterdir())}


def test_timings_file_has_seven_phases_within_the_wall_time(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _prepare_repo(tmp_path, {})
    output = tmp_path / "out" / "architecture.json"
    timings = tmp_path / "timings" / "timings.json"
    started = time.perf_counter()
    assert _report(root, output, "--timings", str(timings)) == 0
    wall = time.perf_counter() - started
    capsys.readouterr()
    written = json.loads(timings.read_text())
    assert set(written["phases"]) == {phase.value for phase in Phase}
    assert all(math.isfinite(seconds) and seconds >= 0 for seconds in written["phases"].values())
    assert sum(written["phases"].values()) <= wall


def test_timings_do_not_change_architecture_pages_or_json_result(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _prepare_repo(tmp_path, {})
    output = tmp_path / "out" / "architecture.json"
    assert _report(root, output) == 0
    plain_stdout = capsys.readouterr().out
    plain_files = _written_bytes(output)
    timings = tmp_path / "timings" / "timings.json"
    assert _report(root, output, "--timings", str(timings)) == 0
    assert capsys.readouterr().out == plain_stdout
    assert _written_bytes(output) == plain_files
    assert timings.is_file()


def test_counters_are_equal_for_two_runs_on_the_same_input(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _prepare_repo(tmp_path, {})
    output = tmp_path / "out" / "architecture.json"
    first = tmp_path / "timings" / "first.json"
    second = tmp_path / "timings" / "second.json"
    assert _report(root, output, "--timings", str(first)) == 0
    assert _report(root, output, "--timings", str(second)) == 0
    capsys.readouterr()
    counters = json.loads(first.read_text())["counters"]
    assert counters == json.loads(second.read_text())["counters"]
    assert counters["files_parsed"] > 0
    assert counters["records"] > 0


def test_failed_run_writes_no_timings_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = tmp_path / "bare"
    root.mkdir()
    timings = tmp_path / "timings" / "timings.json"
    assert _report(root, tmp_path / "out" / "architecture.json", "--timings", str(timings)) == 2
    capsys.readouterr()
    assert not timings.exists()


def test_timings_is_refused_with_a_saved_report(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    saved = tmp_path / "architecture.json"
    saved.write_text("{}")
    timings = tmp_path / "timings.json"
    assert main(["report", "--input", str(saved), "--timings", str(timings), "--json"]) == 2
    assert "--timings" in capsys.readouterr().out
    assert not timings.exists()


@pytest.fixture
def no_step_summary(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)


def _fake_child(
    phase_seconds: dict[str, float], counters: dict[str, int]
) -> Callable[..., subprocess.CompletedProcess[bytes]]:
    def run(command: list[str], *, check: bool) -> subprocess.CompletedProcess[bytes]:
        timings = Path(command[command.index("--timings") + 1])
        timings.parent.mkdir(parents=True, exist_ok=True)
        payload = {"schema_version": 1, "phases": phase_seconds, "counters": counters}
        timings.write_text(json.dumps(payload))
        output = Path(command[command.index("--output") + 1])
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"x" * 10)
        return subprocess.CompletedProcess(command, 0)

    return run


def test_receipt_carries_phases_and_counters_and_a_step_summary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, no_step_summary: None
) -> None:
    # Keys are out of pipeline order on purpose: the table must follow the Phase enum.
    phase_seconds = {"render": 0.2, "providers": 1.2, "collect": 0.6}
    counters = {
        "architecture_bytes": 27825554,
        "calls_analyzed": 28990,
        "records": 90,
        "files_parsed": 4,
    }
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    # Patch only the name the tool imports; platform.processor() also calls the global run.
    fake = SimpleNamespace(run=_fake_child(phase_seconds, counters))
    monkeypatch.setattr(report_timing, "subprocess", fake)
    output = tmp_path / "artifacts/architecture.json"
    assert (
        receipt_main(["--root", str(tmp_path), "--output", str(output), "--max-seconds", "1000"])
        == 0
    )
    receipt = json.loads(output.with_suffix(".timing.json").read_text())
    assert receipt["phase_seconds"] == phase_seconds
    assert receipt["counters"] == counters
    assert receipt["report_exit"] == 0
    assert summary.read_text() == (
        "### Report timing\n"
        "\n"
        "Seconds are wall-clock time on this runner. Counters do not depend on the runner.\n"
        "\n"
        "| Phase | Seconds | Share |\n"
        "| --- | ---: | ---: |\n"
        "| providers | 1.20 | 60.0 % |\n"
        "| collect | 0.60 | 30.0 % |\n"
        "| render | 0.20 | 10.0 % |\n"
        "| **Total** | 2.00 | 100 % |\n"
        "\n"
        "| Counter | Value |\n"
        "| --- | ---: |\n"
        "| Files parsed | 4 |\n"
        "| Calls analyzed | 28,990 |\n"
        "| Records | 90 |\n"
        "| architecture.json | 27.8 MB |\n"
    )


def test_step_summary_says_when_no_timings_were_written() -> None:
    assert report_timing._summary({}, {}) == ("### Report timing\n\nNo timings were written.\n")
