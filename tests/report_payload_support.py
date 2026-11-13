# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Shared runs of the current report for the report v2 payload tests (AD-361)."""

from __future__ import annotations

import contextlib
import io
import json
import tomllib
from dataclasses import dataclass
from functools import cache
from pathlib import Path

from archkeel.cli import main

ROOT = Path(__file__).resolve().parents[1]
CONFIGS = sorted(
    str(path.relative_to(ROOT))
    for pattern in ("fixtures/*/archkeel*.toml", "fixtures/*/*/archkeel*.toml")
    for path in ROOT.glob(pattern)
    if tomllib.loads(path.read_text())["scan"].get("language", "python") in {"rust", "typescript"}
)
EXPLORE = "explore:fixtures/H-uml-typescript"
CASES = (*CONFIGS, EXPLORE)
EXPLORE_ARGS = (
    "explore",
    "--language",
    "typescript",
    "--source",
    "src",
    "--namespace",
    "demo",
    "--tsconfig",
    "tsconfig.json",
)


@dataclass(frozen=True)
class Run:
    """One run of the current report: architecture.json, its printed result and its projection."""

    path: Path
    raw: bytes
    line: str
    projection: str

    @property
    def document(self) -> dict[str, object]:
        loaded: dict[str, object] = json.loads(self.raw)
        return loaded

    @property
    def result(self) -> dict[str, object]:
        loaded: dict[str, object] = json.loads(self.line)
        return loaded


def _main(argv: list[str]) -> str:
    stdout = io.StringIO()
    with contextlib.redirect_stdout(stdout):
        main(argv)
    return stdout.getvalue().splitlines()[-1]


@cache
def run_case(case: str, workdir: str) -> Run:
    """Run the current report once per case, then `report --input ... --only architecture`."""
    output = Path(workdir) / case.replace("/", "_").replace(":", "_") / "architecture.json"
    if case == EXPLORE:
        argv = [*EXPLORE_ARGS, "--root", str(ROOT / case.split(":", 1)[1])]
        line = _main([*argv, "--output", str(output.parent), "--json"])
    else:
        config = ROOT / case
        argv = ["report", "--root", str(config.parent), "--config", config.name]
        line = _main([*argv, "--output", str(output), "--json"])
    projection = _main(["report", "--input", str(output), "--only", "architecture", "--json"])
    return Run(output, output.read_bytes(), line, projection)
