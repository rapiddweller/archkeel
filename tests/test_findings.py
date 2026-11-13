# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-258: the report opens with one ranked list that terminal, HTML and JSON all read."""

from __future__ import annotations

import json
import re
from dataclasses import replace
from html import unescape
from pathlib import Path
from typing import NamedTuple

import pytest
from browser_report_support import _browser_page
from test_cycle_levels import _CLI_CYCLE, _observe
from test_module_explore import _sample

from archkeel.check.ports import ScanConfig
from archkeel.check.report import run_report
from archkeel.cli.observe import observe
from archkeel.ir.architecture_graph import AssessmentStatus
from archkeel.ir.codec import (
    decode_canonical_model,
    parse_observation,
)
from archkeel.ir.findings import findings
from archkeel.ir.model import (
    Finding,
    FindingKind,
    Observation,
    Record,
    RunResult,
)
from archkeel.ir.module_explore import (
    ModuleExploreLevel,
    ModuleStatistic,
    module_exploration,
)
from archkeel.render.html import render_architecture_html
from archkeel.render.summary import report_summary

REMEDY = "Change the code or amend the contract with owner approval."
CONFIG = ScanConfig(("sample",), "sample", "contract.json", "0" * 64)

# One violation (peer imports core twice), a 3-edge and a 2-edge module cycle, a fan-in hub
# (24 importers) and a fan-out hub (12 imports). The cycle files carry no cross-component import.
HUB_FILES = {
    **{f"sample/core/item_{i}.py": "import sample.core.shared\n" for i in range(24)},
    "sample/core/shared.py": "VALUE = 1\n",
    "sample/core/hub.py": "".join(f"import sample.core.item_{i}\n" for i in range(12)),
    "sample/core/c1.py": "import sample.core.c2\n",
    "sample/core/c2.py": "import sample.core.c3\n",
    "sample/core/c3.py": "import sample.core.c1\n",
    "sample/core/d1.py": "import sample.core.d2\n",
    "sample/core/d2.py": "import sample.core.d1\n",
}


class Run(NamedTuple):
    result: RunResult
    observation: Observation
    architecture: bytes


def _run(root: Path) -> Run:
    result, encoded = run_report(root, config=CONFIG, analyzer=observe)
    assert encoded is not None, result.diagnostics
    return Run(result, parse_observation(decode_canonical_model(json.loads(encoded))), encoded)


@pytest.fixture(scope="module")
def run(tmp_path_factory: pytest.TempPathFactory) -> Run:
    tmp_path = tmp_path_factory.mktemp("findings")
    _sample(tmp_path, extra_files=HUB_FILES)
    return _run(tmp_path / "repo")


def _identity(item: Finding) -> tuple[str, tuple[str, ...], tuple[str, ...]]:
    return item.kind, item.rules, item.subjects


def _core(*names: str) -> tuple[str, ...]:
    return tuple(f"sample.core.{name}" for name in names)


def _cycle_run(tmp_path: Path, sources: dict[str, str], **rule: object) -> list[Finding]:
    observation = _observe(tmp_path, sources, **rule)
    return list(findings(observation, module_exploration(observation), violation_remedy=REMEDY))


_THREE_CYCLE = {
    "core/a.py": "from sample.core import b\n",
    "core/b.py": "from sample.core import c\n",
    "core/c.py": "from sample.core import a\n",
    **_CLI_CYCLE,
}


def _with_violations(run: Run, *extra: Record) -> list[Finding]:
    sections = tuple(
        replace(section, records=(*section.records, *extra))
        if section.name == "violations"
        else section
        for section in run.observation.sections
    )
    observation = replace(run.observation, sections=sections)
    return list(findings(observation, module_exploration(observation), violation_remedy=REMEDY))


def _statistic(name: str, fan_in: int | None, fan_out: int | None = 0) -> ModuleStatistic:
    return ModuleStatistic(
        f"MOD-{name}",
        name,
        f"{name}.py",
        None,
        (),
        AssessmentStatus.UNKNOWN,
        "",
        None,
        fan_in,
        fan_out,
        None,
        (),
        (),
    )


def _level(parent: str | None, *modules: ModuleStatistic) -> ModuleExploreLevel:
    return ModuleExploreLevel(
        parent, (), modules, (), AssessmentStatus.PASS, "Complete module import evidence."
    )


def _hubs(run: Run, *levels: ModuleExploreLevel) -> list[tuple[str, str, int]]:
    return [
        (item.kind, item.subjects[0], item.size)
        for item in findings(run.observation, levels, violation_remedy=REMEDY)
        if item.kind in {FindingKind.FAN_IN_HUB, FindingKind.FAN_OUT_HUB}
    ]


def _terminal_titles(result: RunResult) -> list[str]:
    # AD-263: a cycle's path lines sit under its numbered line; only numbered lines are titles.
    return [
        re.sub(r"^\s*\d+\. ", "", line).split("  ")[0]
        for line in report_summary(result).claims.splitlines()[1:]
        if re.match(r"^\s*\d+\. ", line)
    ]


def test_the_terminal_names_five_findings_and_an_empty_list_is_not_a_missing_one() -> None:
    many = tuple(
        Finding(FindingKind.FAN_IN_HUB, (), (f"m{i}",), 10, f"m{i} is a hub", "", (), ())
        for i in range(7)
    )
    complete = AssessmentStatus.PASS
    lines = report_summary(
        RunResult("report", 0, observation_complete=complete, findings=many)
    ).claims.splitlines()

    assert lines[0] == "Findings, ranked (5 of 7):"
    assert [line.strip() for line in lines[1:]] == [f"{i + 1}. m{i} is a hub" for i in range(5)]
    empty = RunResult("report", 0, observation_complete=complete, findings=())
    assert report_summary(empty).claims.startswith("No ranked")
    assert report_summary(RunResult("report", 0)).claims == ""


def _page(run: Run) -> str:
    return render_architecture_html(
        run.result, run.architecture, repository="One target", architecture_href="architecture.json"
    ).decode()


def _html_identities(page: str) -> list[tuple[str, list[str], list[str]]]:
    return [
        tuple(json.loads(unescape(value)))
        for value in re.findall(r'<li data-finding-identity="([^"]*)"', page)
    ]


@pytest.mark.browser
def test_the_report_in_a_browser_lists_what_the_json_lists(tmp_path: Path, run: Run) -> None:
    api = pytest.importorskip("playwright.sync_api")
    report = tmp_path / "report.html"
    report.write_text(_page(run))
    assert run.result.findings is not None
    errors: list[str] = []
    playwright, browser, page = _browser_page(api, "", errors=errors)
    try:
        page.on(
            "console",
            lambda message: errors.append(message.text) if message.type == "error" else None,
        )
        page.goto(report.as_uri())
        items = page.locator(".findings-list > li")
        api.expect(items).to_have_count(len(run.result.findings))
        assert items.first.inner_text().startswith(run.result.findings[0].title)
        # A violation opens its entry in the explorer's own findings panel.
        link = items.first.locator("a")
        link.click()
        entry = page.locator(f'[id="{(link.get_attribute("href") or "")[1:]}"]')
        api.expect(entry).to_be_visible()
        # A cycle selects its first module: the route names it and the inspector shows it.
        items.nth(1).locator("a").click()
        api.expect(page.locator(".flow-inspector")).to_contain_text("sample.core.c1")
        assert "selected=" in page.url
        assert not errors
    finally:
        browser.close()
        playwright.stop()


# AD-263: a cycle finding carries one concrete path, the shortest closed walk through it.
_TRIANGLE = {
    "core/a.py": "from sample.core import b\n",
    "core/b.py": "from sample.core import c\n",
    "core/c.py": "from sample.core import a\n",
}
# Two shortest cycles run through a: a-b-d-a and a-c-d-a. The walk takes the smaller next name, b.
_DIAMOND = {
    "core/a.py": "from sample.core import b\nfrom sample.core import c\n",
    "core/b.py": "from sample.core import d\n",
    "core/c.py": "from sample.core import d\n",
    "core/d.py": "from sample.core import a\n",
}
_TYPE_CHECKED_BACK = {
    "core/a.py": (
        "from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n    from sample.core import b\n"
    ),
    "core/b.py": "from sample.core import a\n",
}


def _walk(item: Finding) -> list[tuple[str, str, str, int, bool]]:
    """Each step as (source, target, file, line, type_checking_only); a site must exist."""
    assert item.path is not None
    steps = []
    for step in item.path.steps:
        assert step.location is not None
        steps.append(
            (
                step.source,
                step.target,
                step.location.path,
                step.location.line,
                step.type_checking_only,
            )
        )
    return steps


# AD-263 follow-up: a no_component_cycles violation is a cycle too, so it carries the same path.
_COMPONENTS = ("alpha", "beta", "gamma")
_COMPONENT_TRIANGLE = {
    "alpha/x.py": "from sample.beta import y\n",
    "beta/y.py": "from sample.gamma import z\n",
    "gamma/z.py": "from sample.alpha import x\n",
}
# alpha also imports gamma, so the shortest cycle through alpha is alpha -> gamma -> alpha.
_COMPONENT_CHORD = {
    **_COMPONENT_TRIANGLE,
    "alpha/x.py": "from sample.beta import y\nfrom sample.gamma import z\n",
}
_COMPONENT_TYPE_CHECKED = {
    **_COMPONENT_TRIANGLE,
    "alpha/x.py": (
        "from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n    from sample.beta import y\n"
    ),
}


def _component_violation(tmp_path: Path, sources: dict[str, str]) -> Finding:
    cycles = _cycle_run(tmp_path, sources, labels=_COMPONENTS)
    [violation] = [item for item in cycles if item.kind is FindingKind.VIOLATION]
    return violation
