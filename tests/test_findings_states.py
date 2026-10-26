# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-272: every equivalence class of the ranked list, on every render, from one table.

The table `CLASSES` is the oracle. `docs/architecture/findings-path.md` carries the same table for
a human reviewer, and `test_the_page_and_the_tests_name_the_same_classes` fails when they differ.
"""

from __future__ import annotations

import itertools
import re
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path

import pytest
from test_cycle_levels import _CORE_CYCLE, _observe
from test_findings import HUB_FILES, REMEDY, Run, _page, _run
from test_findings_path_render import _component_run
from test_module_explore import _sample

from archkeel.check.report import _ranked_findings
from archkeel.ir.architecture_graph import AssessmentStatus
from archkeel.ir.codec import result_payload
from archkeel.ir.findings import findings, findings_note, findings_state
from archkeel.ir.model import (
    FindingKind,
    FindingsState,
    Observation,
    ReportFilter,
    RunResult,
)
from archkeel.ir.module_explore import module_exploration
from archkeel.ir.report_graph import architecture_report
from archkeel.render.summary import report_summary

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


def _ranked(case: Case, runs: dict[str, Run]) -> tuple[Run, Observation, RunResult]:
    run = runs[case.base]
    observation = case.edit(run.observation)
    ranked = _ranked_findings(observation, architecture_report(observation), case.complete, None)
    status = PASS if case.complete else UNKNOWN
    result = replace(run.result, observation_complete=status, findings=ranked)
    return run, observation, result


@pytest.fixture
def runs(full: Run, plain: Run) -> dict[str, Run]:
    return {"full": full, "plain": plain}


@pytest.mark.parametrize("case", CLASSES, ids=lambda case: case.id)
def test_the_ranking_of_each_class(case: Case, runs: dict[str, Run]) -> None:
    _, _, result = _ranked(case, runs)
    assert findings_state(result) is case.state
    if case.kinds is None:
        assert result.findings is None
    else:
        assert result.findings is not None
        assert tuple(item.kind for item in result.findings) == case.kinds


@pytest.mark.parametrize("case", CLASSES, ids=lambda case: case.id)
def test_an_incomplete_run_never_ranks_a_hub_or_an_empty_list(
    case: Case, runs: dict[str, Run]
) -> None:
    _, _, result = _ranked(case, runs)
    if not case.complete:
        assert result.findings != ()
        assert all(item.kind not in {FAN_IN, FAN_OUT} for item in result.findings or ())


@pytest.mark.parametrize("case", CLASSES, ids=lambda case: case.id)
def test_the_terminal_says_what_the_state_says(case: Case, runs: dict[str, Run]) -> None:
    _, _, result = _ranked(case, runs)
    claims = report_summary(result).claims
    note = findings_note(result)
    if case.state is FindingsState.COMPLETE and case.kinds:
        assert claims.startswith("Findings, ranked (")
        assert note is None
    elif case.state is FindingsState.COMPLETE:
        assert claims == "No ranked findings: no violation, dependency cycle or hub."
    elif case.state is FindingsState.PARTIAL:
        assert claims.startswith("Findings, ranked (")
        assert claims.endswith(note or "?")
    else:
        assert claims == note
    if not case.complete:
        assert "No ranked findings:" not in claims


@pytest.mark.parametrize("case", CLASSES, ids=lambda case: case.id)
def test_the_html_says_what_the_state_says(case: Case, runs: dict[str, Run]) -> None:
    run, _, result = _ranked(case, runs)
    page = _page(Run(result, run.observation, run.architecture))
    markup = re.sub(r"<(style|script)\b.*?</\1>", "", page, flags=re.S)
    note = findings_note(result)
    listed = markup.count("data-finding-identity=")
    assert listed == len(result.findings or ())
    if note is not None:
        assert f'<p class="findings-note">{note}</p>' in markup
    else:
        assert 'class="findings-note"' not in markup
    if case.complete and not case.kinds:
        assert "No violation, dependency cycle or hub." in markup
    else:
        assert "No violation, dependency cycle or hub." not in markup


@pytest.mark.parametrize("case", CLASSES, ids=lambda case: case.id)
def test_the_three_renders_name_the_same_findings(case: Case, runs: dict[str, Run]) -> None:
    run, _, result = _ranked(case, runs)
    payload = result_payload(result)
    expected = [item.title for item in result.findings or ()]
    assert ("findings" in payload) is (result.findings is not None)
    assert [item["title"] for item in payload.get("findings", [])] == expected
    page = _page(Run(result, run.observation, run.architecture))
    titles = re.findall(r'<strong class="finding-title">(?:<a [^>]*>)?([^<]*)', page)
    assert [title.replace("&amp;", "&") for title in titles][: len(expected)] == expected[
        : len(titles)
    ]
    numbered = [
        line for line in report_summary(result).claims.splitlines() if re.match(r"^\s*\d+\. ", line)
    ]
    assert len(numbered) == min(len(expected), 5)


def test_the_proven_violation_keeps_its_size_and_sentence_on_an_incomplete_run(
    runs: dict[str, Run],
) -> None:
    case = next(item for item in CLASSES if item.id == "C5")
    _, _, result = _ranked(case, runs)
    assert result.findings is not None
    [violation] = result.findings
    # Twice at one pair is one finding of size 2, as on a complete run (the reverse direction
    # is pinned in test_findings.py).
    assert violation.size == 2
    assert violation.sentence == f"dependencies is broken 2 times. {REMEDY}"


def _rank(observation: Observation, complete: bool) -> tuple[FindingKind, ...] | None:
    ranked = _ranked_findings(observation, architecture_report(observation), complete, None)
    return None if ranked is None else tuple(item.kind for item in ranked)


def test_a_module_cycle_rule_and_its_cycle_are_listed_once_on_every_run(tmp_path: Path) -> None:
    """C17: the violation hides its own cycle only while the violation is proven."""
    observation = _observe(tmp_path, _CORE_CYCLE, level="module")
    assert _rank(observation, True) == (V,)
    assert _rank(observation, False) == (V,)
    # Without a complete trace the violation is not ranked, and it must not hide the cycle.
    assert _rank(_untraced(observation), False) == (MC,)


def test_a_component_cycle_violation_keeps_its_path_on_an_incomplete_run(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    """C16: the path of a component-cycle violation is the same on a partial run."""
    run = _component_run(tmp_path_factory.mktemp("states-component") / "repo")
    kinds = {}
    for complete in (True, False):
        ranked = _ranked_findings(
            run.observation, architecture_report(run.observation), complete, None
        )
        assert ranked is not None
        [violation] = [item for item in ranked if item.kind is V]
        assert violation.path is not None
        kinds[complete] = [(step.source, step.target) for step in violation.path.steps]
    assert kinds[True] == kinds[False]
    assert len(kinds[True]) == 3


def test_a_complete_run_ranks_exactly_what_it_ranked_before(full: Run) -> None:
    again = findings(
        full.observation,
        module_exploration(full.observation),
        violation_remedy=REMEDY,
    )
    assert full.result.findings == again


def test_a_run_with_no_observation_has_no_findings_and_says_so(full: Run) -> None:
    result = replace(
        full.result, observation_complete=UNKNOWN, coverage=None, findings=None, claims=None
    )
    assert findings_state(result) is FindingsState.NO_OBSERVATION
    assert findings_note(result) == "Findings are not ranked: no observation was produced."
    assert report_summary(result).claims == ""
    assert "findings" not in result_payload(result)


@pytest.mark.parametrize("report_filter", FILTERS, ids=FILTER_NAMES)
def test_every_filter_ranks_nothing_whatever_the_observation(
    report_filter: ReportFilter, full: Run
) -> None:
    for complete in (True, False):
        assert (
            _ranked_findings(
                full.observation, architecture_report(full.observation), complete, report_filter
            )
            is None
        )
        result = replace(
            full.result,
            report_filter=report_filter,
            observation_complete=PASS if complete else UNKNOWN,
            findings=None,
        )
        assert findings_state(result) is FindingsState.FILTERED
        assert findings_note(result) == (
            "A filtered result lists no findings. Run report without a filter."
        )
        assert "findings" not in result_payload(result)


def test_a_complete_result_without_findings_is_an_older_result(full: Run) -> None:
    result = replace(full.result, findings=None)
    assert findings_state(result) is FindingsState.NONE_RECORDED
    assert findings_note(result) == "This result carries no ranked findings."


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


@pytest.mark.parametrize("combination", TRUTH, ids=lambda item: "-".join(item))
def test_the_truth_table_of_the_state(combination: tuple[str, str, str, str], full: Run) -> None:
    observation, coverage, found, filtered = combination
    result = replace(
        full.result,
        observation_complete=PASS if observation == "PASS" else UNKNOWN,
        coverage=full.result.coverage if coverage == "cov" else None,
        findings={"list": full.result.findings, "empty": (), "absent": None}[found],
        report_filter=FILTERS[0] if filtered == "set" else None,
    )
    assert findings_state(result) is TRUTH[combination]


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


def test_a_note_counts_the_coverage_failures_it_names(full: Run) -> None:
    class _Coverage:
        failures = tuple(range(30))

    partial = replace(full.result, observation_complete=UNKNOWN, coverage=_Coverage())  # type: ignore[arg-type]
    assert findings_note(partial) == (
        "Hubs are not ranked: the observation is incomplete (30 coverage failures)."
    )
    one = replace(partial, coverage=type("C", (), {"failures": (1,)})(), findings=None)  # type: ignore[arg-type]
    assert "(1 coverage failure)" in (findings_note(one) or "")


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


def test_the_page_and_the_code_use_the_same_sentences(full: Run) -> None:
    _, sentences = _page_rows()

    class _Coverage:
        failures = tuple(range(30))

    base = replace(full.result, coverage=_Coverage())  # type: ignore[arg-type]
    results = {
        FindingsState.PARTIAL: replace(base, observation_complete=UNKNOWN),
        FindingsState.NOT_RANKED: replace(base, observation_complete=UNKNOWN, findings=None),
        FindingsState.NO_OBSERVATION: replace(
            base, observation_complete=UNKNOWN, findings=None, coverage=None
        ),
        FindingsState.FILTERED: replace(base, report_filter=FILTERS[0], findings=None),
        FindingsState.NONE_RECORDED: replace(base, findings=None),
    }
    assert set(sentences) == {state.name for state in results}
    for state, result in results.items():
        assert findings_state(result) is state
        assert _normal(findings_note(result) or "") == _normal(sentences[state.name])


PACKAGE_CYCLE = "Package cycle with 23 members, roll-up only: no module cycle crosses them"


# ----- the report that Tung reviewed ------------------------------------------------------------


@pytest.mark.parametrize(
    ("variant", "titles"),
    [
        ("compass-project", ["Module cycle with 2 members", PACKAGE_CYCLE]),
        (
            "compass-forbidden-edge",
            [
                "Bundled local data imports HTTP API clients without requiring it",
                "Module cycle with 2 members",
                PACKAGE_CYCLE,
            ],
        ),
    ],
)
def test_the_compass_report_ranks_what_the_partial_observation_proves(
    variant: str, titles: list[str], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from test_compass_project_report import replay

    output = tmp_path / f"{variant}.json"
    assert replay(variant, output) == 2
    capsys.readouterr()
    page = output.with_suffix(".report.html").read_text(encoding="utf-8")
    markup = re.sub(r"<(style|script)\b.*?</\1>", "", page, flags=re.S)
    listed = re.findall(r'<strong class="finding-title">(?:<a [^>]*>)?([^<]*)', markup)
    assert [item.strip() for item in listed] == titles
    assert (
        '<p class="findings-note">Hubs are not ranked: the observation is incomplete '
        "(30 coverage failures).</p>"
    ) in markup
    assert "No ranked findings are recorded" not in markup
    assert f"Findings · {len(titles)}" in markup
