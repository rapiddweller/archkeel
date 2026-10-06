# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
import json
import subprocess
from pathlib import Path

import pytest
from test_architecture_demo import _prepare_repo

from tools.report_timing import main


@pytest.mark.parametrize("budget", ["1000", "0.000000001"])
def test_report_time_and_size_are_recorded_and_enforced(tmp_path: Path, budget: str):
    root = _prepare_repo(tmp_path, {})
    output = root / "artifacts/architecture.json"
    assert main(["--root", str(root), "--output", str(output), "--max-seconds", budget]) == 1
    receipt = json.loads(output.with_suffix(".timing.json").read_text())
    assert receipt["report_exit"] == 0
    assert receipt["output_budget_passed"] is False
    assert receipt["output_bytes"] > receipt["max_output_bytes"]
    assert receipt["budget_passed"] is False
    assert receipt["wall_seconds"] > 0
    assert output.exists()


def test_report_failure_cannot_pass_timing_budget(tmp_path: Path):
    output = tmp_path / "artifacts/architecture.json"
    assert main(["--root", str(tmp_path), "--output", str(output), "--max-seconds", "1000"]) == 2
    receipt = json.loads(output.with_suffix(".timing.json").read_text())
    assert receipt["report_exit"] == 2
    assert receipt["budget_passed"] is False


def test_report_output_over_three_times_canonical_fails_budget(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    output = tmp_path / "artifacts/architecture.json"

    def run(command, *, check):
        canonical = Path(command[command.index("--output") + 1])
        canonical.parent.mkdir(parents=True, exist_ok=True)
        canonical.write_bytes(b"x" * 10)
        canonical.with_name("architecture.report.html").write_bytes(b"")
        canonical.with_name("architecture.detail.html").write_bytes(b"y" * 21)
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr("tools.report_timing.subprocess.run", run)
    assert main(["--root", str(tmp_path), "--output", str(output), "--max-seconds", "1000"]) == 1
    receipt = json.loads(output.with_suffix(".timing.json").read_text())
    assert receipt["output_bytes"] == 31
    assert receipt["max_output_bytes"] == 30
    assert receipt["output_budget_passed"] is False
    assert receipt["budget_passed"] is False


def test_report_within_three_times_canonical_can_pass(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    output = tmp_path / "artifacts/architecture.json"

    def run(command, *, check):
        canonical = Path(command[command.index("--output") + 1])
        canonical.parent.mkdir(parents=True, exist_ok=True)
        canonical.write_bytes(b"x" * 100)
        canonical.with_name("architecture.report.html").write_bytes(b"r" * 100)
        canonical.with_name("architecture.detail.html").write_bytes(b"d" * 100)
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr("tools.report_timing.subprocess.run", run)
    assert main(["--root", str(tmp_path), "--output", str(output), "--max-seconds", "1000"]) == 0
    receipt = json.loads(output.with_suffix(".timing.json").read_text())
    assert receipt["output_bytes"] == 300
    assert receipt["output_budget_passed"] is True
    assert receipt["budget_passed"] is True


@pytest.mark.parametrize("budget", ["0", "-1", "nan", "inf"])
def test_invalid_budget_is_rejected_before_collection(tmp_path: Path, budget: str):
    output = tmp_path / "architecture.json"
    with pytest.raises(SystemExit) as error:
        main(["--root", str(tmp_path), "--output", str(output), "--max-seconds", budget])
    assert error.value.code == 2
    assert not output.with_suffix(".timing.json").exists()
