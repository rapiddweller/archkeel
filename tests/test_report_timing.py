# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
import json
from pathlib import Path

import pytest
from test_architecture_demo import _prepare_repo

from tools.report_timing import main


@pytest.mark.parametrize("budget, expected", [("1000", 0), ("0.000000001", 1)])
def test_report_time_is_recorded_and_enforced(tmp_path: Path, budget: str, expected: int):
    root = _prepare_repo(tmp_path, {})
    output = root / "artifacts/architecture.json"
    assert main(["--root", str(root), "--output", str(output), "--max-seconds", budget]) == expected
    receipt = json.loads(output.with_suffix(".timing.json").read_text())
    assert receipt["report_exit"] == 0
    assert receipt["budget_passed"] is (expected == 0)
    assert receipt["wall_seconds"] > 0
    assert output.exists()


def test_report_failure_cannot_pass_timing_budget(tmp_path: Path):
    output = tmp_path / "artifacts/architecture.json"
    assert main(["--root", str(tmp_path), "--output", str(output), "--max-seconds", "1000"]) == 2
    receipt = json.loads(output.with_suffix(".timing.json").read_text())
    assert receipt["report_exit"] == 2
    assert receipt["budget_passed"] is False


@pytest.mark.parametrize("budget", ["0", "-1", "nan", "inf"])
def test_invalid_budget_is_rejected_before_collection(tmp_path: Path, budget: str):
    output = tmp_path / "architecture.json"
    with pytest.raises(SystemExit) as error:
        main(["--root", str(tmp_path), "--output", str(output), "--max-seconds", budget])
    assert error.value.code == 2
    assert not output.with_suffix(".timing.json").exists()
