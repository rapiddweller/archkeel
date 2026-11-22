# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-1048: an oracle test does not skip in CI, and each oracle that a run selects has run.

An oracle test compares a verdict with a real program: python3.12, cargo, node or dart. The test
skips when the tool is missing. A skip hides a false PASS, so in CI (`CI` is set) the skip is a
failure. The plugin also records which oracles a run selected and which one passed. A run that
selected an oracle and ran none of its tests fails at the end. The plugin marks each oracle test
with `oracle_<tool>`; the mark comes from the reason of its `skipif` mark.
"""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from typing import Any

import pytest

# A skip reason names an oracle tool as a word, in any case: `Node.js is required`, `no node on this
# machine`, `rustc is not on PATH`, `python3.14`. The tool of the first pattern that matches wins.
REASONS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bpython ?(3)\.(\d+)\b|\b(?:CPython|Python) is the oracle", re.I), "python"),
    (re.compile(r"\b(?:cargo|rustc)\b|\bRust runs\b", re.I), "cargo"),
    (re.compile(r"\bnode(?:\.?js)?\b", re.I), "node"),
    (re.compile(r"\bdart\b", re.I), "dart"),
)
MARK = "oracle_"
SELECTED: set[str] = set()
RAN: set[str] = set()


def tool_of(reason: str) -> str | None:
    """The oracle tool that a skip reason names, or None for another reason."""
    for pattern, tool in REASONS:
        found = pattern.search(reason)
        if found and tool == "python":
            return "python" + "".join(found.groups("")) if found.group(1) else "python312"
        if found:
            return tool
    return None


def in_ci(environ: Mapping[str, str] = os.environ) -> bool:
    """True when the run is a CI run."""
    return bool(environ.get("CI"))


def tools_of(keywords: Any) -> set[str]:
    """The oracle tools that the marks of a test or of its report name."""
    return {name[len(MARK) :] for name in keywords if name.startswith(MARK)}


def unran(selected: set[str], ran: set[str]) -> set[str]:
    """The oracles that a run selected and that no passed test ran."""
    return selected - ran


def skip_reason(report: Any) -> str | None:
    """The reason of a plain skip, or None for a pass, a failure or an expected failure."""
    if not report.skipped or hasattr(report, "wasxfail"):
        return None
    shown = report.longrepr
    return str(shown[2]) if isinstance(shown, tuple) and len(shown) == 3 else str(shown)


def fail_skip(report: Any, environ: Mapping[str, str] = os.environ) -> bool:
    """Turn the skip of an oracle test into a failure in CI. True when it did."""
    reason = skip_reason(report)
    tool = tool_of(reason) if reason is not None else None
    if tool is None or not in_ci(environ):
        return False
    report.outcome = "failed"
    report.longrepr = f"CI must provide the oracle `{tool}`; the test skipped: {reason}"
    return True


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        for mark in item.iter_markers("skipif"):
            tool = tool_of(str(mark.kwargs.get("reason", "")))
            if tool is not None:
                item.add_marker(getattr(pytest.mark, MARK + tool))


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo[None]):
    outcome = yield
    fail_skip(outcome.get_result())


def pytest_runtest_logreport(report: pytest.TestReport) -> None:
    tools = tools_of(report.keywords)
    SELECTED.update(tools)
    if report.when == "call" and report.passed:
        RAN.update(tools)


def pytest_sessionfinish(session: pytest.Session) -> None:
    if hasattr(session.config, "workerinput") or not in_ci():
        return
    missing = unran(SELECTED, RAN)
    if missing:
        session.exitstatus = pytest.ExitCode.TESTS_FAILED
        reporter = session.config.pluginmanager.get_plugin("terminalreporter")
        if reporter is not None:
            reporter.write_line(f"oracle never ran in CI: {', '.join(sorted(missing))}", red=True)
