# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).parents[1]


def test_make_demo_reproduces_all_three_outcomes(tmp_path: Path) -> None:
    output = tmp_path / "demo"
    run = subprocess.run(
        ["make", "demo", f"OUTPUT={output}"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )

    assert run.returncode == 0, (run.stdout, run.stderr)
    results = json.loads((output / "results.json").read_bytes())
    assert {case: results[case]["exit_code"] for case in ("A", "B", "C")} == {
        "A": 1,
        "B": 1,
        "C": 0,
    }
    for case, expected in (("A", 1), ("B", 1), ("C", 0)):
        result_path = output / f"{case}-check.stdout.json"
        html = output / f"{case}-check.stdout.check.html"
        result = json.loads(result_path.read_bytes())
        assert result["exit_code"] == expected
        assert f"{case} · {expected} · {expected} ·" in run.stdout
        assert str(result_path) in run.stdout
        assert str(html) in run.stdout
        assert html.is_file()
    assert len(list(output.glob("*.check.html"))) == 3
