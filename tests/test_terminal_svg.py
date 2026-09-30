"""Real-process checks for terminal SVG capture evidence."""

import os
import subprocess
import sys
from pathlib import Path
from xml.etree import ElementTree

import pytest

from tools.terminal_svg import capture, capture_inside_violation

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


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


def test_demo_screenshots_routes_terminal_export_through_module(tmp_path: Path) -> None:
    result = subprocess.run(
        ["make", "-n", "demo-screenshots", f"OUTPUT={tmp_path}"],
        capture_output=True,
        check=False,
        cwd=REPOSITORY_ROOT,
        env={key: value for key, value in os.environ.items() if key != "PYTHONPATH"},
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "python -m tools.terminal_svg" in result.stdout


def test_module_exports_real_inside_capture_without_pythonpath(tmp_path: Path) -> None:
    from fixtures.reproduce_milestone1 import reproduce

    output = tmp_path / "demo"
    reproduce(output)
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    result = subprocess.run(
        [sys.executable, "-m", "tools.terminal_svg", str(output)],
        capture_output=True,
        check=False,
        cwd=REPOSITORY_ROOT,
        env=env,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    document = ElementTree.parse(output / "archkeel-shop-inside-violation.svg")
    svg = " ".join(" ".join(document.getroot().itertext()).replace("\u00a0", " ").split())
    assert "rule.violated" in svg
    assert "NOT CHECKED" in svg
