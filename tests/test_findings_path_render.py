# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-263: the HTML row and the terminal summary both show a cycle finding's path steps."""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import replace
from html import unescape
from pathlib import Path

import pytest
from test_cycle_levels import _component
from test_findings import HUB_FILES, Run, _page, _run
from test_module_explore import _sample

from archkeel.ir.model import FindingKind
from archkeel.render.summary import report_summary


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


def test_the_html_row_of_a_cycle_shows_each_step_with_its_site(run: Run) -> None:
    row = _text(_rows(_page(run))[_index(run, FindingKind.MODULE_CYCLE)])

    assert "sample.core.c1 → sample.core.c2 sample/core/c1.py:1" in row
    assert "sample.core.c2 → sample.core.c3 sample/core/c2.py:1" in row
    assert "sample.core.c3 → sample.core.c1 sample/core/c3.py:1" in row


def test_a_hub_row_has_no_path_block(run: Run) -> None:
    rows = _rows(_page(run))

    assert 'class="finding-path"' not in rows[_index(run, FindingKind.FAN_IN_HUB)]
    assert 'class="finding-path"' in rows[_index(run, FindingKind.MODULE_CYCLE)]


def test_the_html_row_names_the_edges_a_path_leaves_out(run: Run) -> None:
    assert run.result.findings is not None
    cycle = run.result.findings[_index(run, FindingKind.MODULE_CYCLE)]
    assert cycle.path is not None
    shortened = replace(cycle, path=replace(cycle.path, omitted_edges=2))
    rendered = replace(run.result, findings=(shortened,))

    row = _text(_rows(_page(Run(rendered, run.observation, run.architecture)))[0])
    assert "2 other cycle edges not on this path" in row


def test_the_terminal_prints_each_step_indented_under_its_finding(run: Run) -> None:
    assert run.result.findings is not None
    cycle = run.result.findings[_index(run, FindingKind.MODULE_CYCLE)]
    lines = report_summary(run.result).claims.splitlines()
    start = next(
        i for i, line in enumerate(lines) if line.endswith(cycle.title + "  sample/core/c1.py:1")
    )

    assert lines[start + 1 : start + 4] == [
        "     sample.core.c1 → sample.core.c2  sample/core/c1.py:1",
        "     sample.core.c2 → sample.core.c3  sample/core/c2.py:1",
        "     sample.core.c3 → sample.core.c1  sample/core/c3.py:1",
    ]


def test_the_terminal_names_the_edges_a_path_leaves_out(run: Run) -> None:
    assert run.result.findings is not None
    cycle = run.result.findings[_index(run, FindingKind.MODULE_CYCLE)]
    assert cycle.path is not None
    shortened = replace(cycle, path=replace(cycle.path, omitted_edges=1))

    lines = report_summary(replace(run.result, findings=(shortened,))).claims.splitlines()

    assert lines[-1] == "     1 other cycle edge not on this path"


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


def test_the_html_row_of_a_component_cycle_shows_its_steps(component_run: Run) -> None:
    assert component_run.result.findings is not None
    index = next(
        i
        for i, item in enumerate(component_run.result.findings)
        if item.kind is FindingKind.VIOLATION
    )
    row = _text(_rows(_page(component_run))[index])

    assert "alpha → beta sample/alpha/x.py:1" in row
    assert "beta → gamma sample/beta/y.py:1" in row
    assert "gamma → alpha sample/gamma/z.py:1" in row


def test_the_terminal_prints_a_component_cycle_path_under_its_violation(
    component_run: Run,
) -> None:
    lines = report_summary(component_run.result).claims.splitlines()
    start = next(
        i for i, line in enumerate(lines) if "Component cycle: alpha ↔ beta ↔ gamma" in line
    )

    assert lines[start + 1 : start + 4] == [
        "     alpha → beta  sample/alpha/x.py:1",
        "     beta → gamma  sample/beta/y.py:1",
        "     gamma → alpha  sample/gamma/z.py:1",
    ]
