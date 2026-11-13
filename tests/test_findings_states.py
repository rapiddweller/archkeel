# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-272: every equivalence class of the ranked list, on every render, from one table.

The table `CLASSES` is the oracle. `docs/architecture/findings-path.md` carries the same table for
a human reviewer, and `test_the_page_and_the_tests_name_the_same_classes` fails when they differ.
"""

from __future__ import annotations

import itertools
import json
import re
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path

import pytest
from test_findings import HUB_FILES, Run, _run
from test_module_explore import _sample

from archkeel.check.report import _ranked_findings, run_saved_report
from archkeel.ir.architecture_graph import AssessmentStatus
from archkeel.ir.codec import canonical_report_bytes, decode_canonical_model
from archkeel.ir.model import (
    Finding,
    FindingKind,
    FindingsState,
    Observation,
    ReportFilter,
    RunResult,
)
from archkeel.ir.report_graph import architecture_report

PASS, UNKNOWN = AssessmentStatus.PASS, AssessmentStatus.UNKNOWN
V, MC, FAN_IN, FAN_OUT = (
    FindingKind.VIOLATION,
    FindingKind.MODULE_CYCLE,
    FindingKind.FAN_IN_HUB,
    FindingKind.FAN_OUT_HUB,
)
PAGE = Path(__file__).parents[1] / "docs/architecture/findings-path.md"


@pytest.fixture(scope="module")
def full(tmp_path_factory: pytest.TempPathFactory) -> Run:
    """One violation, two module cycles and two hubs."""
    root = tmp_path_factory.mktemp("states-full")
    _sample(root, extra_files=HUB_FILES)
    return _run(root / "repo")


@pytest.fixture(scope="module")
def plain(tmp_path_factory: pytest.TempPathFactory) -> Run:
    """One violation and nothing else."""
    root = tmp_path_factory.mktemp("states-plain")
    _sample(root)
    return _run(root / "repo")


def _without(observation: Observation, *names: str) -> Observation:
    return replace(
        observation,
        sections=tuple(
            replace(section, records=()) if section.name in names else section
            for section in observation.sections
        ),
    )


def _untraced(observation: Observation) -> Observation:
    """The violation records stay, but none carries the facts that prove it."""
    return replace(
        observation,
        sections=tuple(
            replace(section, records=tuple(replace(item, fact_ids=()) for item in section.records))
            if section.name == "violations"
            else section
            for section in observation.sections
        ),
    )


@dataclass(frozen=True)
class Case:
    id: str
    base: str
    edit: Callable[[Observation], Observation]
    complete: bool
    kinds: tuple[FindingKind, ...] | None
    state: FindingsState


def _same(observation: Observation) -> Observation:
    return observation


CLASSES = (
    Case("C1", "plain", lambda o: _without(o, "violations"), True, (), FindingsState.COMPLETE),
    Case("C2", "plain", _same, True, (V,), FindingsState.COMPLETE),
    Case(
        "C3",
        "full",
        lambda o: _without(o, "violations"),
        True,
        (MC, MC, FAN_IN, FAN_OUT),
        FindingsState.COMPLETE,
    ),
    Case("C4", "full", _same, True, (V, MC, MC, FAN_IN, FAN_OUT), FindingsState.COMPLETE),
    Case("C5", "plain", _same, False, (V,), FindingsState.PARTIAL),
    Case("C6", "full", lambda o: _without(o, "violations"), False, (MC, MC), FindingsState.PARTIAL),
    Case("C7", "full", _same, False, (V, MC, MC), FindingsState.PARTIAL),
    Case(
        "C8",
        "full",
        lambda o: _without(o, "violations", "cycles"),
        False,
        None,
        FindingsState.NOT_RANKED,
    ),
    Case("C9", "plain", _untraced, False, None, FindingsState.NOT_RANKED),
    Case(
        "C10", "plain", lambda o: _without(o, "violations"), False, None, FindingsState.NOT_RANKED
    ),
    Case(
        "C11",
        "full",
        lambda o: _without(o, "violations", "imports"),
        False,
        None,
        FindingsState.NOT_RANKED,
    ),
)
RESULT_ONLY = {
    "C12": FindingsState.NO_OBSERVATION,
    "C13": FindingsState.FILTERED,
    "C14": FindingsState.NONE_RECORDED,
}
FILTERS = (
    ReportFilter(only_violations=True),
    ReportFilter(only_architecture=True),
    ReportFilter(component="core"),
    ReportFilter(rule="dependencies"),
    ReportFilter(only_calls=True),
)
FILTER_NAMES = ("only_violations", "only_architecture", "component", "rule", "only_calls")


def _ranked_for(
    observation: Observation,
    complete: bool,
    report_filter: ReportFilter | None = None,
) -> tuple[Finding, ...] | None:
    """Rank through the real function, which reads only the status and the diagnostics."""
    result = RunResult("report", 0, observation_complete=PASS if complete else UNKNOWN)
    return _ranked_findings(observation, architecture_report(observation), result, report_filter)


def _ranked(case: Case, runs: dict[str, Run]) -> tuple[Run, Observation, RunResult]:
    run = runs[case.base]
    observation = case.edit(run.observation)
    ranked = _ranked_for(observation, case.complete)
    status = PASS if case.complete else UNKNOWN
    result = replace(run.result, observation_complete=status, findings=ranked)
    return run, observation, result


@pytest.fixture
def runs(full: Run, plain: Run) -> dict[str, Run]:
    return {"full": full, "plain": plain}


def _rank(observation: Observation, complete: bool) -> tuple[FindingKind, ...] | None:
    ranked = _ranked_for(observation, complete)
    return None if ranked is None else tuple(item.kind for item in ranked)


def _saved(full: Run, tmp_path: Path, runtime_required: str | None) -> RunResult:
    raw = decode_canonical_model(json.loads(full.architecture))
    if runtime_required is not None:
        raw["runtime"]["required"] = runtime_required
    path = tmp_path / "saved.json"
    path.write_bytes(canonical_report_bytes(raw))
    return run_saved_report(path)


# The truth table of `findings_state`: every combination of the four fields it reads.
# (observation, coverage record, findings, filter) -> state
TRUTH = {
    ("PASS", "cov", "list", "none"): FindingsState.COMPLETE,
    ("PASS", "cov", "empty", "none"): FindingsState.COMPLETE,
    ("PASS", "cov", "absent", "none"): FindingsState.NONE_RECORDED,
    ("PASS", "none", "list", "none"): FindingsState.COMPLETE,
    ("PASS", "none", "empty", "none"): FindingsState.COMPLETE,
    ("PASS", "none", "absent", "none"): FindingsState.NONE_RECORDED,
    ("UNKNOWN", "cov", "list", "none"): FindingsState.PARTIAL,
    ("UNKNOWN", "cov", "empty", "none"): FindingsState.NOT_RANKED,
    ("UNKNOWN", "cov", "absent", "none"): FindingsState.NOT_RANKED,
    ("UNKNOWN", "none", "list", "none"): FindingsState.PARTIAL,
    ("UNKNOWN", "none", "empty", "none"): FindingsState.NO_OBSERVATION,
    ("UNKNOWN", "none", "absent", "none"): FindingsState.NO_OBSERVATION,
    **{
        (obs, cov, found, "set"): FindingsState.FILTERED
        for obs, cov, found in itertools.product(
            ("PASS", "UNKNOWN"), ("cov", "none"), ("list", "empty", "absent")
        )
    },
}


def test_the_truth_table_covers_every_combination() -> None:
    every = set(
        itertools.product(
            ("PASS", "UNKNOWN"),
            ("cov", "none"),
            ("list", "empty", "absent"),
            ("none", "set"),
        )
    )
    assert set(TRUTH) == every


# ----- the page and the tests must name the same classes ---------------------------------------


def _page_rows() -> tuple[dict[str, str], dict[str, str]]:
    text = PAGE.read_text(encoding="utf-8")
    classes = {
        match.group(1): match.group(2).strip("`")
        for match in re.finditer(r"^\| (C\d+) \| .*? \| .*? \| (.+?) \|$", text, re.M)
    }
    sentences = {
        match.group(1): match.group(2)
        for match in re.finditer(r"^\| `([A-Z_]+)` \| `(.+)` \|$", text, re.M)
    }
    return classes, sentences


def _normal(sentence: str) -> str:
    return re.sub(r"\d+ coverage failures?", "N coverage failures", sentence)


def test_the_page_and_the_tests_name_the_same_classes() -> None:
    classes, _ = _page_rows()
    expected = {case.id: case.state.name for case in CLASSES} | {
        key: value.name for key, value in RESULT_ONLY.items()
    }
    for number in ("C15", "C16"):
        # Grouping and path are pinned in test_findings.py and test_findings_path_render.py.
        assert number in classes
    assert {key: value for key, value in classes.items() if key in expected} == expected
