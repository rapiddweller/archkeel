# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-263: the HTML row and the terminal summary both show a cycle finding's path steps."""

from __future__ import annotations

import json
import re
import subprocess
from html import unescape
from pathlib import Path

import pytest
from test_cycle_levels import _component
from test_findings import HUB_FILES, Run, _run
from test_module_explore import _sample

from archkeel.ir.model import FindingKind


@pytest.fixture(scope="module")
def run(tmp_path_factory: pytest.TempPathFactory) -> Run:
    tmp_path = tmp_path_factory.mktemp("findings-path-render")
    _sample(tmp_path, extra_files=HUB_FILES)
    return _run(tmp_path / "repo")


def _rows(page: str) -> list[str]:
    """One chunk of HTML per list row, in the order the findings are listed."""
    return page.split('<li data-finding-identity="')[1:]


def _text(markup: str) -> str:
    return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", markup))).strip()


def _index(run: Run, kind: FindingKind) -> int:
    assert run.result.findings is not None
    return next(i for i, item in enumerate(run.result.findings) if item.kind is kind)


_COMPONENT_CYCLE = {
    "alpha/x.py": "from sample.beta import y\n",
    "beta/y.py": "from sample.gamma import z\n",
    "gamma/z.py": "from sample.alpha import x\n",
}


def _component_run(root: Path) -> Run:
    """A three-component cycle that no_component_cycles reports, through the real report path."""
    root.mkdir(parents=True)
    contract = {
        "schema_version": "2.1.0",
        "components": [_component(label) for label in ("alpha", "beta", "gamma")],
        "rules": [
            {
                "id": "RULE",
                "kind": "no_component_cycles",
                "rationale": "Probe.",
                "provenance": ["docs/architecture/sample.md"],
                "decided_by": "architect",
            }
        ],
    }
    (root / "pyproject.toml").write_text('[project]\nrequires-python = ">=3.11"\n')
    (root / "contract.json").write_text(json.dumps(contract))
    for name, text in _COMPONENT_CYCLE.items():
        path = root / "sample" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    # The report resolves HEAD, so the sample must be a committed repository.
    for args in (
        ("init", "-q", "-b", "main"),
        ("config", "user.email", "demo@example.invalid"),
        ("config", "user.name", "Demo"),
        ("add", "-A"),
        ("-c", "commit.gpgsign=false", "commit", "-q", "-m", "sample"),
    ):
        subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)
    return _run(root)


@pytest.fixture(scope="module")
def component_run(tmp_path_factory: pytest.TempPathFactory) -> Run:
    return _component_run(tmp_path_factory.mktemp("component-path") / "repo")
