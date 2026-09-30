"""Real-process checks for terminal SVG capture evidence."""

import subprocess
import sys

import pytest

from tools.terminal_svg import capture, capture_inside_violation


def test_capture_keeps_terminal_output_and_checks_expected_nonzero_exit() -> None:
    output = capture(
        [
            sys.executable,
            "-c",
            "import sys; print('rule.violated'); "
            "print('stderr evidence', file=sys.stderr); sys.exit(2)",
        ],
        expected_exit_code=2,
        required_output=("rule.violated", "stderr evidence"),
    )

    assert "rule.violated" in output
    assert "stderr evidence" in output


def test_capture_rejects_an_unexpected_exit_code() -> None:
    with pytest.raises(subprocess.CalledProcessError) as error:
        capture([sys.executable, "-c", "raise SystemExit(2)"], expected_exit_code=0)

    assert error.value.returncode == 2


def test_inside_violation_capture_shows_all_findings_without_claiming_pass() -> None:
    output = capture_inside_violation()

    assert output.count("rule.violated") == 3
    assert "NOT CHECKED" in output
    assert "PASS" not in output
