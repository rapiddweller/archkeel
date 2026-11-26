# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT

"""The nightly native timing budget refuses unusable evidence."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from tools import native_timing_budget as budget

ROOT = Path(__file__).parents[1]


def timings() -> bytes:
    return json.dumps(
        {
            "protocol": "archkeel-core-timings-1",
            "clock": "monotonic",
            "unit": "seconds",
            "phases": {name: 0.01 for name in budget.PHASE_LIMITS},
            "core_seconds": 1,
        }
    ).encode()


def result(status: str = "PASS") -> bytes:
    return json.dumps(
        {
            "outcome": "verdict",
            "status": status,
            "exit_code": 0 if status == "PASS" else 2,
            "frame": {"rules": {"R": ["kind", status]}, "self_test": {"reply": {"files": 1}}},
        }
    ).encode()


def test_below_budget_does_not_call_an_unknown_result_a_pass() -> None:
    text = budget.check(timings(), result("UNKNOWN"))
    assert "UNKNOWN" in text
    assert "PASS" not in text


@pytest.mark.parametrize("field", [*budget.PHASE_LIMITS, "core_seconds"])
def test_an_exceeded_budget_names_its_cause(field: str) -> None:
    document = json.loads(timings())
    if field == "core_seconds":
        document[field] = budget.CORE_LIMIT + 1
    else:
        document["phases"][field] = budget.PHASE_LIMITS[field] + 1
        document["core_seconds"] = budget.CORE_LIMIT
    with pytest.raises(ValueError, match=f"budget_exceeded: {field}"):
        budget.check(json.dumps(document).encode(), result())
    with pytest.raises(ValueError, match=f"budget_exceeded: {field}"):
        budget.check(json.dumps(document).encode(), result("UNKNOWN"))


@pytest.mark.parametrize(
    ("timing", "frame"),
    [
        (b"bad", result()),
        (timings(), b"bad"),
        (timings(), b'{"outcome":"refusal","status":"UNKNOWN"}'),
        (timings(), b'{"outcome":"verdict","status":"PASS"}'),
        (timings(), result("FAIL")),
        (b"{}", result()),
        (timings().replace(b"0.01", b"NaN", 1), result()),
        (b'{"protocol":"archkeel-core-timings-1","refused":true}', result()),
    ],
)
def test_bad_or_refused_evidence_does_not_pass(timing: bytes, frame: bytes) -> None:
    with pytest.raises(ValueError):
        budget.check(timing, frame)


def test_missing_files_fail_the_nightly_command(tmp_path: Path) -> None:
    process = subprocess.run(
        [
            sys.executable,
            "-m",
            "tools.native_timing_budget",
            str(tmp_path / "missing"),
            str(tmp_path / "result"),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert process.returncode != 0
    assert "timing_unavailable" in process.stderr
    (tmp_path / "timing").write_bytes(timings())
    process = subprocess.run(
        [
            sys.executable,
            "-m",
            "tools.native_timing_budget",
            str(tmp_path / "timing"),
            str(tmp_path / "missing"),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert process.returncode != 0
    assert "timing_unavailable" in process.stderr


def test_report_only_names_the_failure_but_does_not_fail_the_pr(tmp_path: Path) -> None:
    process = subprocess.run(
        [
            sys.executable,
            "-m",
            "tools.native_timing_budget",
            str(tmp_path / "missing"),
            str(tmp_path / "result"),
            "--report-only",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert process.returncode == 0
    assert "timing_unavailable" in process.stderr


def test_the_command_enforces_an_overrun_only_without_report_only(tmp_path: Path) -> None:
    document = json.loads(timings())
    document["phases"]["collect"] = budget.PHASE_LIMITS["collect"] + 1
    document["core_seconds"] = budget.CORE_LIMIT
    timing, frame = tmp_path / "timing", tmp_path / "result"
    timing.write_text(json.dumps(document))
    frame.write_bytes(result("UNKNOWN"))
    command = [sys.executable, "-m", "tools.native_timing_budget", str(timing), str(frame)]
    for flags, expected in (([], 1), (["--report-only"], 0)):
        process = subprocess.run(command + flags, capture_output=True, text=True, check=False)
        assert process.returncode == expected
        assert "budget_exceeded: collect" in process.stderr


def test_pr_and_main_report_but_scheduled_full_enforces() -> None:
    for name in ("pr-gate.yml", "ci.yml"):
        text = (ROOT / ".github" / "workflows" / name).read_text()
        assert "tools.native_timing_budget" in text
        assert "test-artifacts/validation-native/result.json --report-only" in text
    full = (ROOT / ".github" / "workflows" / "full-verification.yml").read_text()
    assert "NATIVE_SELFCHECK_TIMINGS:" in full
    assert '[ "$GITHUB_EVENT_NAME" = schedule ]' in full
    assert "tools.native_timing_budget" in full
