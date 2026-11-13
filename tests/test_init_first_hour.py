# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-266: the first hour. `init` reads its own observation aloud, and `--adopt` takes it in."""

import json
import re
import subprocess
from pathlib import Path

import pytest
from test_onboarding import _repository

from archkeel.check import onboarding
from archkeel.check.onboarding import CONTRACT_PATH
from archkeel.cli import main
from archkeel.cli.guide import GUIDE_PATH
from archkeel.ir.model import FirstLook, RunResult
from archkeel.render.summary import init_summary

_JUDGEMENT = re.compile(r"\b(good|bad|healthy|large|small|too)\b", re.IGNORECASE)
_NEXT_STEPS = (
    "1. archkeel report            # read the overview and the first findings",
    "2. open test-artifacts/architecture/architecture.report.html   "
    "# the Explorer; click a name to select a component",
    "3. archkeel init --force --adopt   # or write the target yourself "
    "(see docs/getting-started.md)",
)


def _cyclic_repository(root: Path) -> Path:
    """The same project as `_repository`, with `ir.model` importing `cli.app` back."""
    _repository(root)
    model = root / "src" / "archkeel" / "ir" / "model.py"
    model.write_text("from archkeel.cli.app import VALUE as CLI_VALUE\n" + model.read_text())
    subprocess.run(["git", "add", "."], cwd=root, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-qm", "cycle"], cwd=root, check=True, capture_output=True)
    return root


def _first_look_lines(sentence: str) -> list[str]:
    start = sentence.index("First look:")
    end = sentence.index("Next steps:")
    return [line.strip() for line in sentence[start:end].splitlines()[1:] if line.strip()]


def _init_json(root: Path, capsys: pytest.CaptureFixture, *extra: str) -> tuple[int, dict]:
    code = main(["init", "--root", str(root), "--json", "--full", *extra])
    return code, json.loads(capsys.readouterr().out)


def _observed_pairs(payload: dict) -> set[tuple[str, str]]:
    return {
        (item["source"], item["target"]) for item in payload["open_decisions"] if item["observed"]
    }


def _contract(root: Path) -> dict:
    return json.loads((root / CONTRACT_PATH).read_bytes())


def test_first_look_wording_for_one_importer_a_tie_and_no_measured_calls() -> None:
    look = FirstLook(
        files_parsed=2,
        files_discovered=2,
        call_resolution_percent=None,
        module_cycles=0,
        largest_module_cycle=0,
        most_imported_module="pkg.one",
        most_importers=1,
        largest_component="alpha",
        largest_component_ties=2,
        largest_component_modules=5,
        unknown_positions=0,
    )
    result = RunResult(
        "init",
        0,
        observation_complete="PASS",
        expectation_fulfilled="n/a",
        artifact="architecture-contract.json",
        first_look=look,
    )

    lines = _first_look_lines(init_summary(result).sentence)
    isolated = init_summary(
        RunResult(
            "init",
            0,
            observation_complete="PASS",
            expectation_fulfilled="n/a",
            artifact="architecture-contract.json",
            first_look=FirstLook(2, 2, 0.0, 0, 0, None, 0, None, 0, 0, 0),
        )
    )

    assert lines == [
        "Files parsed: 2 of 2",
        "Calls resolved: not measured",
        "Module cycles: none",
        "Most imported module: pkg.one (1 module imports it)",
        "Largest component: tie of 2 components (5 modules each)",
        "Positions left UNKNOWN: 0",
    ]
    assert "Most imported module: none" in _first_look_lines(isolated.sentence)
    assert "Largest component: none" in _first_look_lines(isolated.sentence)


def _tree(root: Path) -> dict[Path, bytes]:
    return {
        path: path.read_bytes()
        for path in root.rglob("*")
        if path.is_file() and ".git" not in path.relative_to(root).parts
    }


def test_init_guard_and_guide_command_name_the_same_path() -> None:
    # init guards the path it never writes itself, so the two copies must stay equal.
    assert onboarding.GUIDE_PATH == GUIDE_PATH
