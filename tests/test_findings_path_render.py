# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-263: the HTML row and the terminal summary both show a cycle finding's path steps."""

from __future__ import annotations

import re
from dataclasses import replace
from html import unescape

import pytest
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
