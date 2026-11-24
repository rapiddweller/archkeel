# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Helpers of the tests of `tools/self_check_diff.py`: real result files and the tool process."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

ROOT = Path(__file__).parents[1]
FIXTURES = Path(__file__).parent / "selfcheck_fixtures"
TOOL = Path(os.environ.get("SELF_CHECK_DIFF_TOOL", ROOT / "tools/self_check_diff.py"))
RULE = "TINY-INTERFACE-BOUNDARY"
LINE = "Ratchet growth: {n} items: the scan reads a new public name"


def real(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def save(tmp_path: Path, name: str, result: dict[str, Any] | str) -> str:
    path = tmp_path / name
    path.write_text(result if isinstance(result, str) else json.dumps(result), encoding="utf-8")
    return str(path)


def run(
    tmp_path: Path,
    base: str,
    pr: str,
    *,
    labels: str = "",
    body: str = "",
    extra: tuple[str, ...] = (),
) -> subprocess.CompletedProcess[str]:
    args = [sys.executable, str(TOOL), base, pr, "--labels", labels, *extra]
    if body:
        args += ["--body-file", save(tmp_path, "body.txt", body)]
    return subprocess.run(args, capture_output=True, text=True, timeout=60)


def worse(status: str) -> Callable[[dict[str, Any]], None]:
    def edit(result: dict[str, Any]) -> None:
        result["frame"]["rules"][RULE][1] = status

    return edit


def unknown_reason(result: dict[str, Any]) -> None:
    worse("UNKNOWN")(result)
    result["frame"]["unknown_kinds"] = {RULE: "scope_incomplete"}


def violation(result: dict[str, Any]) -> None:
    worse("FAIL")(result)
    row = {"source": "a", "target": "b", "cause": "forbidden", "evidence": []}
    result["frame"]["details"] = {RULE: [row]}
    result["frame"]["violations"] = {RULE: 1}
    result["exit_code"] = 1


def red(done: subprocess.CompletedProcess[str], *named: str) -> None:
    assert done.returncode == 1, done.stdout + done.stderr
    for text in named:
        assert text in done.stdout, done.stdout
