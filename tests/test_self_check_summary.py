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
from self_check_diff import condense  # noqa: E402

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


def repository(tmp_path: Path, files: dict[str, int], baseline: dict[str, int]) -> Path:
    root = tmp_path / "repo"
    (root / "tests").mkdir(parents=True)
    (root / "tests/file_size_baseline.json").write_text(json.dumps(baseline), encoding="utf-8")
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
    write(tmp_path, "native", envelope(big))
    write(tmp_path, "shell", envelope(big))
    write(tmp_path, "system", big)
    base = condense(envelope(frame(status="PASS", causes=0)), "b" * 40, "t")
    base["gaps"] = []
    compared = tmp_path / "selfcheck/compared-base.json"
    compared.parent.mkdir()
    compared.write_text(json.dumps(base), encoding="utf-8")
    files = {f"src/over{i}.py": 520 for i in range(6)}
    files |= {f"src/near{i}.py": 500 for i in range(70)}
    root = repository(tmp_path, files, {"src/legacy.py": 900})
    lines = tool.summary(tmp_path, root, 1, "x.log")
    assert len(lines) <= tool.MAX_LINES, "\n".join(lines)
    assert sum(line.startswith("  next:") for line in lines) == 6
    assert (
        lines[0] == "self-check: native FAIL (exit 1) | shell FAIL (exit 1) | system FAIL (exit 1)"
    )
    assert "new violations: 24 (the base has none)" in lines
    assert "  and 20 more" in lines  # the violations of the two frames, 4 shown
    assert any(line.startswith("size (measured") and "6 files over it" in line for line in lines)
    assert any("70 files at 450 to 500 lines; 70 at 500: src/near0.py" in line for line in lines)
    assert any(" and 40 more" in line for line in lines)
    assert any("cycle: native R-CYCLES: 2 members" in line for line in lines)
    assert lines[-1] == "self-validate exit 1 (the gate); full output: x.log"


def test_the_counts_equal_the_counts_of_the_result_files(tmp_path: Path) -> None:
    inner = frame(status="UNKNOWN", causes=3, violations=2, modules=4)
    inner["explained"] = {"R-A": "w", "R-B": "w"}
    write(tmp_path, "native", envelope(inner))
    root = repository(tmp_path, {}, {})
    lines = tool.summary(tmp_path, root, 0, "x.log")
    assert "new violations: 2 (the base has none)" in lines
    assert "  2 x cause 1 (first: native/a/src/lib.rs:7)" in lines
    assert "  3 x cause 0 (first: native/a/src/lib.rs:7)" in lines
    total = len(inner["collection_gaps"])
    assert (
        f"unknown causes (measured, gaps per cause; top 3 of 3 causes, {total} gaps; 2 rules wait):"
        in lines
    )
    assert "  native fan-in: m3 3, m2 2, m1 1" in lines
    assert "  native fan-out: m0 3, m1 2, m2 1" in lines
    assert lines[0].startswith("self-check: native UNKNOWN (exit 2) | shell has no result")


def test_a_file_over_the_limit_is_listed_and_a_file_at_the_limit_is_near(tmp_path: Path) -> None:
    root = repository(
        tmp_path,
        {
            "src/clean.py": 3,
            "src/big.py": 520,
            "src/edge.py": 500,
            "src/old.py": 700,
            "x/y.py": 900,
        },
        {"src/old.py": 700},
    )
    lines = tool.sizes(root)
    assert lines[0] == "size (measured, limit 500): 1 files over it, not in the baseline"
    assert lines[1] == "  over: src/big.py (520 lines)"
    assert lines[2] == "  1 files at 450 to 500 lines; 1 at 500: src/edge.py"
    removed = repository(tmp_path / "again", {"src/big.py": 500}, {})
    assert tool.sizes(removed)[0].endswith("0 files over it, not in the baseline")


def test_the_ratchet_is_told_in_words(tmp_path: Path) -> None:
    own = envelope(frame(status="UNKNOWN", causes=0))
    own["frame"]["collection_gaps"] = [gap("one"), gap("two")]
    base = condense(own, "a" * 40, "t")
    base["gaps"] = [base["gaps"][0], ["collection_gap", "gone", "old"]]
    path = tmp_path / "base.json"
    path.write_text(json.dumps(base), encoding="utf-8")
    lines, new = tool.ratchet(own, path)
    assert new == 1
    assert lines[0] == "native vs base aaaaaaaaaaaa: 1 new items, 1 gaps gone"
    assert tool.ratchet(own, tmp_path / "missing.json")[1] == 0


def test_ratchet_uses_the_gate_scan_table(tmp_path: Path) -> None:
    own = envelope(frame(status="UNKNOWN", causes=0))
    before = condense(own, "a" * 40, "t", {"roots": ["native"]})
    path = tmp_path / "base.json"
    path.write_text(json.dumps(before), encoding="utf-8")
    (tmp_path / "native").mkdir()
    (tmp_path / "native/archkeel.toml").write_text('[scan]\nroots = ["native"]\n')
    assert tool.ratchet(own, path, tmp_path)[1] == 0


def test_summary_uses_the_base_result_override(tmp_path: Path, monkeypatch: Any) -> None:
    own = envelope(frame(status="UNKNOWN"))
    write(tmp_path, "native", own)
    base = condense(own, "a" * 40, "t")
    base["gaps"] = [["collection_gap", "gone", "old"]]
    path = tmp_path / "base.json"
    path.write_text(json.dumps(base))
    monkeypatch.setenv("BASE_RESULT", str(path))
    root = repository(tmp_path, {}, {})
    assert "native vs base aaaaaaaaaaaa: 0 new items, 1 gaps gone" in tool.summary(
        tmp_path, root, 0, "x.log"
    )
