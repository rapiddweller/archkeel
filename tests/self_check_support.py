# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Helpers of the tests of `tools/self_check_gate.py`: real result files and the tool process."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).parents[1]
FIXTURES = Path(__file__).parent / "selfcheck_fixtures"
TOOL = ROOT / "tools/self_check_gate.py"
RULE = "TINY-INTERFACE-BOUNDARY"


def real(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def save(tmp_path: Path, name: str, result: dict[str, Any] | str) -> str:
    path = tmp_path / name
    path.write_text(result if isinstance(result, str) else json.dumps(result), encoding="utf-8")
    return str(path)


def gate(path: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(TOOL), path], capture_output=True, text=True, timeout=60
    )


def worse(status: str, result: dict[str, Any]) -> None:
    result["frame"]["rules"][RULE][1] = status


def violation(result: dict[str, Any], count: int = 1) -> None:
    worse("FAIL", result)
    row = {"source": "a", "target": "b", "cause": "forbidden", "evidence": []}
    result["frame"]["details"] = {RULE: [{**row, "source": f"s{i}"} for i in range(count)]}
    result["frame"]["violations"] = {RULE: count}
    result["exit_code"] = 1
