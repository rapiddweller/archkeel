# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-7: report bytes depend on declared inputs, never on the environment.

The scanned sources are two clones of the committed repository that share a basename but
differ in parent path; the running Archkeel is the working tree's installed package. Runs
vary hash seed, time zone, locale and working directory, and one run repeats verbatim.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parents[1]


def _clone(source: Path, dest: Path) -> None:
    result = subprocess.run(
        ["git", "clone", "-q", str(source), str(dest)], capture_output=True, text=True
    )
    assert result.returncode == 0, (result.stdout, result.stderr)


def _report(clone: Path, *, cwd: Path, env: dict[str, str]) -> tuple[bytes, bytes, bytes]:
    output = clone / "out" / "architecture.json"
    run = subprocess.run(
        [
            sys.executable,
            "-m",
            "archkeel.cli",
            "report",
            "--root",
            str(clone),
            "--output",
            str(output),
        ],
        cwd=cwd,
        env=env,
        capture_output=True,
    )
    assert run.returncode == 0, (run.stdout, run.stderr)
    html = output.with_name("architecture.report.html")
    return output.read_bytes(), html.read_bytes(), run.stdout


def test_report_bytes_are_independent_of_seed_timezone_locale_and_cwd(tmp_path: Path) -> None:
    clone_a = tmp_path / "a" / "archkeel"
    clone_b = tmp_path / "b" / "deeper" / "archkeel"
    _clone(ROOT, clone_a)
    _clone(ROOT, clone_b)

    env_a = {**os.environ, "PYTHONHASHSEED": "0", "TZ": "UTC", "LC_ALL": "C"}
    env_b = {**os.environ, "PYTHONHASHSEED": "4242", "TZ": "Asia/Ho_Chi_Minh"}
    env_b.pop("LC_ALL", None)

    run1 = _report(clone_a, cwd=clone_a, env=env_a)
    run2 = _report(clone_b, cwd=tmp_path, env=env_b)
    shutil.rmtree(clone_a / "out")
    run3 = _report(clone_a, cwd=clone_a, env=env_a)

    for name, index in (("architecture.json", 0), ("architecture.report.html", 1), ("stdout", 2)):
        # No normalization: a leaked path or environment byte must fail here (AD-7).
        assert run1[index] == run3[index], f"{name} differs between run 1 and run 3 (repeat)"
        assert run1[index] == run2[index], f"{name} differs between run 1 and run 2 (environment)"
