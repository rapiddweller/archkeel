# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-1088: `make self-check` prints at most 40 lines from the results of `make self-validate`."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from core_support import ROOT

sys.path.insert(0, str(ROOT / "tools"))
import self_check_summary as tool  # noqa: E402

PLACE = {"path": "native/a/src/lib.rs", "line": 7}


def gap(cause: str, subject: str = "native.a") -> dict[str, Any]:
    return {"kind": "collection_gap", "subjects": [subject], "reason": cause, "evidence": ["EVD-1"]}


def frame(
    *,
    status: str,
    modules: int = 0,
    violations: int = 0,
    causes: int = 0,
    cycle_sizes: tuple[int, ...] = (),
    rules: dict[str, list[str]] | None = None,
) -> dict[str, Any]:
    names = [f"m{i}" for i in range(modules)]
    edges = [{"source": a, "target": b} for i, a in enumerate(names) for b in names[i + 1 :]]
    rows = [
        {"source": f"s{i}", "target": f"t{i}", "cause": "c", "evidence": ["EVD-1"]}
        for i in range(violations)
    ]
    return {
        "status": status,
        "rules": rules if rules is not None else {"R-ONE": ["forbidden_dependency", "PASS"]},
        "explained": {},
        "violations": {},
        "details": {"R-ONE": rows} if rows else {},
        "unknown_kinds": {},
        "locations": {"EVD-1": PLACE},
        "collection_gaps": [
            gap(f"cause {i}: detail") for i in range(causes) for _ in range(causes - i)
        ],
        "topology": {
            "modules": [{"name": name} for name in names],
            "edges": edges + [{"source": "m0", "target": "external-crate"}],
            "total": {"edges": len(edges) + 1},
        },
        "explain": {
            "cycles": {
                "R-CYCLES": {
                    "total": len(cycle_sizes),
                    "items": [{"members": ["x"] * size} for size in cycle_sizes],
                }
            }
        },
    }


def write(directory: Path, name: str, document: dict[str, Any]) -> None:
    path = directory / f"validation-{name}" / "result.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document), encoding="utf-8")


def envelope(inner: dict[str, Any]) -> dict[str, Any]:
    return {"command": "report", "status": inner["status"], "exit_code": 2, "frame": inner}


def repository(tmp_path: Path, files: dict[str, int]) -> Path:
    root = tmp_path / "repo"
    (root / "tests").mkdir(parents=True)
    for name, lines in files.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text("x = 1\n" * lines, encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    return root


def test_the_text_stays_within_40_lines_for_the_largest_input(tmp_path: Path) -> None:
    """Each group has a cap: 12 violations, 20 causes, 70 files at the limit, 5 cycles."""
    rules = {"R-ONE": ["forbidden_dependency", "FAIL"], "R-CYCLES": ["no_component_cycles", "FAIL"]}
    big = frame(
        status="FAIL",
        modules=12,
        violations=12,
        causes=20,
        cycle_sizes=(2, 3, 4, 5, 6),
        rules=rules,
    )
    big["system"] = {"parts": [{"id": "core", "status": "FAIL"}, {"id": "shell", "status": "FAIL"}]}
    write(tmp_path, "system", big)
    files = {f"src/over{i}.py": 520 for i in range(6)}
    files |= {f"src/near{i}.py": 500 for i in range(70)}
    root = repository(tmp_path, files)
    lines = tool.summary(tmp_path, root, 1, "x.log")
    assert len(lines) <= tool.MAX_LINES, "\n".join(lines)
    assert sum(line.startswith("  next:") for line in lines) == 5
    assert lines[0] == "self-check: system FAIL (exit 1) | core FAIL | shell FAIL"
    assert "violations: 12" in lines
    assert "  and 8 more" in lines  # 4 shown
    assert any(line.startswith("size (measured") and "6 files over it" in line for line in lines)
    assert any("70 files at 450 to 500 lines; 70 at 500: src/near0.py" in line for line in lines)
    assert any(" and 40 more" in line for line in lines)
    assert any("cycle: system R-CYCLES: 2 members" in line for line in lines)
    assert lines[-1] == "self-validate exit 1 (the gate); full output: x.log"


def test_the_counts_equal_the_counts_of_the_result_files(tmp_path: Path) -> None:
    inner = frame(status="UNKNOWN", causes=3, violations=2, modules=4)
    inner["explained"] = {"R-A": "w", "R-B": "w"}
    write(tmp_path, "system", inner)
    root = repository(tmp_path, {})
    lines = tool.summary(tmp_path, root, 0, "x.log")
    assert "violations: 2" in lines
    assert "  2 x cause 1 (first: native/a/src/lib.rs:7)" in lines
    assert "  3 x cause 0 (first: native/a/src/lib.rs:7)" in lines
    total = len(inner["collection_gaps"])
    assert (
        f"unknown causes (measured, gaps per cause; top 3 of 3 causes, {total} gaps; 2 rules wait):"
        in lines
    )
    assert "  system fan-in: m3 3, m2 2, m1 1" in lines
    assert "  system fan-out: m0 3, m1 2, m2 1" in lines
    assert lines[0] == "self-check: system UNKNOWN (exit 2)"


def test_a_gap_without_subjects_keeps_its_cause_and_gate_result(tmp_path: Path) -> None:
    inner = frame(status="UNKNOWN")
    inner["collection_gaps"] = [
        {"kind": "collection_gap", "subjects": [], "reason": "no place", "evidence": []},
        {"kind": "collection_gap", "subjects": [], "reason": "has place", "evidence": ["EVD-1"]},
    ]
    write(tmp_path, "system", inner)
    root = repository(tmp_path, {})
    lines = tool.summary(tmp_path, root, 1, "x.log")
    assert "  1 x no place (first: no subject)" in lines
    assert "  1 x has place (first: native/a/src/lib.rs:7)" in lines
    assert lines[-1] == "self-validate exit 1 (the gate); full output: x.log"


def test_a_file_over_the_limit_is_listed_and_a_file_at_the_limit_is_near(tmp_path: Path) -> None:
    root = repository(
        tmp_path,
        {
            "src/clean.py": 3,
            "src/big.py": 520,
            "src/edge.py": 500,
            "x/y.py": 900,
        },
    )
    lines = tool.sizes(root)
    assert lines[0] == "size (measured, limit 500): 1 files over it"
    assert lines[1] == "  over: src/big.py (520 lines)"
    assert lines[2] == "  1 files at 450 to 500 lines; 1 at 500: src/edge.py"
    removed = repository(tmp_path / "again", {"src/big.py": 500})
    assert tool.sizes(removed)[0].endswith("0 files over it")
