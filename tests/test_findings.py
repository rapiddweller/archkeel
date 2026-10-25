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
from test_cycle_levels import _CLI_CYCLE, _CORE_CYCLE, _observe
from test_module_explore import _sample
from test_result_schema import _validator

from archkeel.check.ports import ScanConfig
from archkeel.check.report import run_report, run_saved_report
from archkeel.cli.observe import observe
from archkeel.ir.architecture_graph import AssessmentStatus
from archkeel.ir.baseline import canonical_fingerprint
from archkeel.ir.codec import (
    decode_canonical_model,
    parse_observation,
    result_payload,
)
from archkeel.ir.findings import findings
from archkeel.ir.model import (
    Finding,
    FindingKind,
    Observation,
    Record,
    ReportFilter,
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


def test_findings_are_ranked_violations_then_cycles_then_hubs(run: Run) -> None:
    assert run.result.findings is not None
    assert [(_identity(item), item.size) for item in run.result.findings] == [
        ((FindingKind.VIOLATION, ("dependencies",), ("sample.core", "sample.peer")), 2),
        ((FindingKind.MODULE_CYCLE, (), _core("c1", "c2", "c3")), 3),
        ((FindingKind.MODULE_CYCLE, (), _core("d1", "d2")), 2),
        ((FindingKind.FAN_IN_HUB, (), _core("shared")), 24),
        ((FindingKind.FAN_OUT_HUB, (), _core("hub")), 12),
    ]


def test_identity_is_the_kind_and_the_canonical_fingerprint(run: Run) -> None:
    assert run.result.findings is not None
    violation = run.result.findings[0]
    # Subject order carries no direction (AD-106): the finding names the baseline's own key.
    assert canonical_fingerprint(violation.rules, reversed(violation.subjects)) == (
        canonical_fingerprint(("dependencies",), ("sample.peer", "sample.core"))
    )


def test_findings_name_their_locations_components_and_words(run: Run) -> None:
    assert run.result.findings is not None
    violation, cycle, _, fan_in, fan_out = run.result.findings
    assert [(item.path, item.line) for item in violation.locations] == [
        ("sample/peer.py", 1),
        ("sample/peer.py", 2),
    ]
    assert violation.title == "peer imports core without requiring it"
    assert violation.sentence == f"dependencies is broken 2 times. {REMEDY}"
    assert violation.component_ids == ("core", "peer")
    assert [item.path for item in cycle.locations] == [
        "sample/core/c1.py",
        "sample/core/c2.py",
        "sample/core/c3.py",
    ]
    assert cycle.sentence == (
        "sample.core.c1, sample.core.c2, sample.core.c3 import each other through 3 import edges."
    )
    assert [item.path for item in fan_in.locations] == ["sample/core/shared.py"]
    assert fan_in.title == "sample.core.shared is imported by 24 modules"
    assert fan_out.title == "sample.core.hub imports 12 modules"
    assert fan_in.component_ids == fan_out.component_ids == ("core",)


def test_a_comparison_free_run_carries_no_change(run: Run) -> None:
    assert run.result.findings is not None
    assert all(item.change is None and item.before is None for item in run.result.findings)
    payload = result_payload(run.result)
    items = payload["findings"]
    assert isinstance(items, list) and len(items) == len(run.result.findings)
    for item in items:
        assert isinstance(item, dict)
        assert "change" not in item and "before" not in item
    assert "findings" not in result_payload(RunResult("report", 0))


def test_two_runs_give_equal_findings(tmp_path: Path, run: Run) -> None:
    _sample(tmp_path, extra_files=HUB_FILES)
    again = _run(tmp_path / "repo")
    assert again.result.findings == run.result.findings
    assert findings(
        again.observation, module_exploration(again.observation), violation_remedy=REMEDY
    ) == findings(run.observation, module_exploration(run.observation), violation_remedy=REMEDY)


def test_a_filtered_report_ranks_nothing(tmp_path: Path, run: Run) -> None:
    root = tmp_path / "repo"
    _sample(tmp_path, extra_files=HUB_FILES)
    filtered, _ = run_report(root, config=CONFIG, analyzer=observe, only_violations=True)
    assert filtered.report_filter == ReportFilter(True, None, None)
    assert filtered.findings is None
    assert "findings" not in result_payload(filtered)


def test_a_saved_report_ranks_the_same_findings(tmp_path: Path, run: Run) -> None:
    saved = tmp_path / "architecture.json"
    saved.write_bytes(run.architecture)
    assert run_saved_report(saved).findings == run.result.findings


def _cycle_run(tmp_path: Path, sources: dict[str, str], **rule: object) -> list[Finding]:
    observation = _observe(tmp_path, sources, **rule)
    return list(findings(observation, module_exploration(observation), violation_remedy=REMEDY))


_THREE_CYCLE = {
    "core/a.py": "from sample.core import b\n",
    "core/b.py": "from sample.core import c\n",
    "core/c.py": "from sample.core import a\n",
    **_CLI_CYCLE,
}


def test_cycles_rank_by_size_then_name(tmp_path: Path) -> None:
    ranked = _cycle_run(tmp_path, {**_CORE_CYCLE, **_THREE_CYCLE})

    assert [(item.kind, item.size, item.subjects) for item in ranked] == [
        (FindingKind.MODULE_CYCLE, 3, ("sample.core.a", "sample.core.b", "sample.core.c")),
        (FindingKind.MODULE_CYCLE, 2, ("sample.cli.x", "sample.cli.y")),
    ]


def test_a_large_cycle_names_three_members_and_counts_the_rest(tmp_path: Path) -> None:
    ring = {f"core/r{i}.py": f"from sample.core import r{(i + 1) % 5}\n" for i in range(5)}
    (cycle,) = _cycle_run(tmp_path, ring)

    assert cycle.size == 5
    assert cycle.subjects == tuple(f"sample.core.r{i}" for i in range(5))
    assert cycle.sentence == (
        "sample.core.r0, sample.core.r1, sample.core.r2 and 2 others import each other "
        "through 5 import edges."
    )
    assert len(cycle.locations) == 3


def test_a_cycle_the_rule_reports_is_not_listed_again(tmp_path: Path) -> None:
    """AD-98: the module-level rule reports the whole SCC as one violation."""
    ranked = _cycle_run(tmp_path, _THREE_CYCLE, level="module")

    assert [(item.kind, item.subjects) for item in ranked] == [
        (FindingKind.VIOLATION, ("sample.cli.x", "sample.cli.y")),
        (FindingKind.VIOLATION, ("sample.core.a", "sample.core.b", "sample.core.c")),
    ]


def test_a_scoped_rule_leaves_the_other_cycle_to_the_cycle_list(tmp_path: Path) -> None:
    ranked = _cycle_run(tmp_path, _THREE_CYCLE, level="module", components=["core"])

    assert [(item.kind, item.subjects) for item in ranked] == [
        (FindingKind.VIOLATION, ("sample.core.a", "sample.core.b", "sample.core.c")),
        (FindingKind.MODULE_CYCLE, ("sample.cli.x", "sample.cli.y")),
    ]


def test_a_package_roll_up_follows_the_module_cycles(tmp_path: Path) -> None:
    """core.x -> cli.y and cli.z -> core.w close a package cycle that no module cycle closes."""
    sources = {
        "core/x.py": "from sample.cli import y\n",
        "core/w.py": "VALUE = 1\n",
        "cli/y.py": "VALUE = 1\n",
        "cli/z.py": "from sample.core import w\n",
        "core/a.py": "from sample.core import b\n",
        "core/b.py": "from sample.core import a\n",
    }
    ranked = _cycle_run(tmp_path, sources, labels=("core",))

    assert [(item.kind, item.subjects) for item in ranked] == [
        (FindingKind.MODULE_CYCLE, ("sample.core.a", "sample.core.b")),
        (FindingKind.PACKAGE_CYCLE, ("sample.cli", "sample.core")),
    ]
    assert ranked[1].title.endswith("roll-up only: no module cycle crosses them")
    # Review (#652): the roll-up names packages, yet it still points at source.
    assert ranked[1].locations


def _with_violations(run: Run, *extra: Record) -> list[Finding]:
    sections = tuple(
        replace(section, records=(*section.records, *extra))
        if section.name == "violations"
        else section
        for section in run.observation.sections
    )
    observation = replace(run.observation, sections=sections)
    return list(findings(observation, module_exploration(observation), violation_remedy=REMEDY))


def test_one_rule_broken_both_ways_names_neither_direction(run: Run) -> None:
    # Review (#652): a fingerprint sorts subjects, so A->B and B->A form one finding.
    original = (run.observation.records("violations") or ())[0]
    reverse = replace(
        original,
        id="VIO-reverse",
        title="sample.core imports sample.peer",
        subjects=tuple(reversed(original.subjects)),
    )
    [violation] = [
        item for item in _with_violations(run, reverse) if item.kind is FindingKind.VIOLATION
    ]

    assert violation.size == 3
    assert violation.title == "dependencies between sample.core and sample.peer"


def test_a_violation_on_a_symbol_is_owned_by_its_cited_module(run: Run) -> None:
    # Review (#652): construct rules name a function, not a module, as their subject.
    original = (run.observation.records("violations") or ())[0]
    on_symbol = replace(original, id="VIO-symbol", subjects=("sample.peer.client.call",))
    [symbol] = [
        item for item in _with_violations(run, on_symbol) if item.subjects == on_symbol.subjects
    ]

    assert symbol.component_ids


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


def test_a_hub_needs_ten_and_an_unknown_fan_is_not_ten(run: Run) -> None:
    level = _level(None, _statistic("nine", 9), _statistic("ten", 10), _statistic("unknown", None))

    assert _hubs(run, level) == [(FindingKind.FAN_IN_HUB, "ten", 10)]


def test_a_level_names_its_top_three_and_a_module_listed_twice_counts_once(run: Run) -> None:
    root = _level(None, *(_statistic(f"m{i}", 20 + i) for i in range(5)))
    inside = _level("core", *(_statistic(f"m{i}", 20 + i) for i in range(4)))

    assert _hubs(run, root, inside) == [
        (FindingKind.FAN_IN_HUB, "m4", 24),
        (FindingKind.FAN_IN_HUB, "m3", 23),
        (FindingKind.FAN_IN_HUB, "m2", 22),
        (FindingKind.FAN_IN_HUB, "m1", 21),
    ]


def test_hubs_rank_across_levels_by_size_and_stop_at_ten(run: Run) -> None:
    levels = [
        _level(
            None if index == 0 else f"c{index}",
            *(_statistic(f"l{index}m{i}", 10 + index * 3 + i, 10) for i in range(3)),
        )
        for index in range(5)
    ]

    assert _hubs(run, *levels) == [
        (FindingKind.FAN_IN_HUB, f"l{index}m{i}", 10 + index * 3 + i)
        for index, i in sorted(
            ((index, i) for index in range(5) for i in range(3)),
            key=lambda pair: -pair[0] * 3 - pair[1],
        )[:10]
    ]


def test_a_larger_fan_out_hub_still_follows_every_fan_in_hub(run: Run) -> None:
    # Review (#652): kinds rank before sizes, so a 40-module fan-out follows a 12-module fan-in.
    level = _level(None, _statistic("small_in", 12, 0), _statistic("big_out", 0, 40))

    assert [kind for kind, _, _ in _hubs(run, level)] == [
        FindingKind.FAN_IN_HUB,
        FindingKind.FAN_OUT_HUB,
    ]


def test_one_module_can_be_a_hub_both_ways_and_fan_in_is_named_first(run: Run) -> None:
    level = _level(None, _statistic("b", 12, 12), _statistic("a", 12, 11))

    assert _hubs(run, level) == [
        (FindingKind.FAN_IN_HUB, "a", 12),
        (FindingKind.FAN_IN_HUB, "b", 12),
        (FindingKind.FAN_OUT_HUB, "b", 12),
        (FindingKind.FAN_OUT_HUB, "a", 11),
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
    lines = report_summary(RunResult("report", 0, findings=many)).claims.splitlines()

    assert lines[0] == "Findings, ranked (5 of 7):"
    assert [line.strip() for line in lines[1:]] == [f"{i + 1}. m{i} is a hub" for i in range(5)]
    assert report_summary(RunResult("report", 0, findings=())).claims.startswith("No ranked")
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


def test_terminal_html_and_json_list_the_same_findings_in_the_same_order(run: Run) -> None:
    assert run.result.findings is not None
    payload = result_payload(run.result)
    items = payload["findings"]
    assert isinstance(items, list)
    from_json = [
        (item["kind"], item["rules"], item["subjects"]) for item in items if isinstance(item, dict)
    ]
    expected = [(item.kind, list(item.rules), list(item.subjects)) for item in run.result.findings]
    page = _page(run)

    assert from_json == expected
    assert _html_identities(page) == expected
    assert _terminal_titles(run.result) == [item.title for item in run.result.findings]
    assert '<ol class="findings-list">' in page
    # The explorer follows the list (AD-130): findings come before the diagram.
    assert page.index('class="findings-list"') < page.index('id="flow"')


def test_the_page_opens_with_one_verdict_line_and_no_rule_cards(run: Run) -> None:
    page = _page(run)
    line = re.search(r'<p class="verdict-line".*?</p>', page, re.S)

    assert line is not None
    text = re.sub(r"<[^>]+>", "", line.group())
    assert "Rules FAIL" in text
    assert re.search(r"\d+ PASS · \d+ UNKNOWN", text)
    assert re.search(r"Agent decisions \d+/\d+", text)
    assert "Source observation PASS" in text
    assert run.observation.source.git_head[:7] in text
    assert run.observation.source.git_head not in text
    markup = re.sub(r"<(style|script)\b.*?</\1>", "", page, flags=re.S)
    for gone in ("atlas-verdict-grid", "atlas-status", "decision-banner", "flow-how-to-read"):
        assert gone not in markup
    assert run.observation.source.git_head in page.split("Snapshot and audit")[1]


def test_five_findings_show_and_the_rest_open_on_request(run: Run) -> None:
    # The explorer must stay on the first screen, so the list shows five findings.
    assert run.result.findings
    many = (run.result.findings * 7)[:7]
    page = _page(Run(replace(run.result, findings=many), run.observation, run.architecture))
    markup = re.sub(r"<(style|script)\b.*?</\1>", "", page, flags=re.S)
    first, _, rest = markup.partition('<details class="findings-more">')

    assert first.count("data-finding-identity=") == 5
    assert "<summary>Show all 7 findings</summary>" in rest
    assert '<ol class="findings-list" start="6">' in rest
    assert rest.split("</details>")[0].count("data-finding-identity=") == 2


def test_a_result_without_findings_never_reads_as_a_clean_list(run: Run) -> None:
    page = _page(Run(replace(run.result, findings=None), run.observation, run.architecture))

    assert "No ranked findings are recorded in this result." in page
    assert "findings-list" not in re.sub(r"<(style|script)\b.*?</\1>", "", page, flags=re.S)


def test_every_finding_links_into_the_explorer_with_the_existing_route_grammar(run: Run) -> None:
    page = _page(run)
    hrefs = [
        unescape(href)
        for href in re.findall(r'<strong class="finding-title"><a href="([^"]*)"', page)
    ]
    assert run.result.findings is not None
    assert len(hrefs) == len(run.result.findings)
    violation_id = next(
        item.id
        for item in run.observation.records("violations") or ()
        if item.subjects == ("sample.core", "sample.peer")
    )
    assert hrefs[0] == f"#atlas-finding-{violation_id}-dependencies"
    module_ids = {
        str(item.data.get("qualified_name")): item.id
        for item in run.observation.records("modules") or ()
    }
    assert hrefs[1:] == [
        f"?content=modules&scope=core&selected={module_ids['sample.core.c1']}&view=diagram#flow",
        f"?content=modules&scope=core&selected={module_ids['sample.core.d1']}&view=diagram#flow",
        f"?content=modules&scope=core&selected={module_ids['sample.core.shared']}&view=diagram#flow",
        f"?content=modules&scope=core&selected={module_ids['sample.core.hub']}&view=diagram#flow",
    ]


def test_the_atlas_payload_carries_the_same_list(run: Run) -> None:
    page = _page(run)
    start = page.index('id="flow-data"')
    start = page.index(">", start) + 1
    atlas = json.loads(page[start : page.index("</script>", start)])["atlas"]

    assert run.result.findings is not None
    assert [item["subjects"] for item in atlas["ranked_findings"]] == [
        list(item.subjects) for item in run.result.findings
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


def test_a_three_module_cycle_walks_its_three_edges_with_their_import_sites(tmp_path: Path) -> None:
    [cycle] = _cycle_run(tmp_path, _TRIANGLE, labels=("core",))

    assert _walk(cycle) == [
        ("sample.core.a", "sample.core.b", "sample/core/a.py", 1, False),
        ("sample.core.b", "sample.core.c", "sample/core/b.py", 1, False),
        ("sample.core.c", "sample.core.a", "sample/core/c.py", 1, False),
    ]
    assert cycle.path is not None and cycle.path.omitted_edges == 0


def test_a_two_package_cycle_shows_one_module_site_per_package_edge(tmp_path: Path) -> None:
    sources = {
        "core/x.py": "from sample.cli import y\n",
        "cli/y.py": "VALUE = 1\n",
        "cli/z.py": "from sample.core import w\n",
        "core/w.py": "VALUE = 1\n",
    }
    [cycle] = [
        item for item in _cycle_run(tmp_path, sources) if item.kind is FindingKind.PACKAGE_CYCLE
    ]

    # The walk starts at the smaller package name, sample.cli.
    assert _walk(cycle) == [
        ("sample.cli", "sample.core", "sample/cli/z.py", 1, False),
        ("sample.core", "sample.cli", "sample/core/x.py", 1, False),
    ]


def test_the_same_repository_in_reversed_file_order_gives_the_same_path(tmp_path: Path) -> None:
    forward = _cycle_run(tmp_path / "forward", _DIAMOND, labels=("core",))
    backward = _cycle_run(tmp_path / "backward", dict(reversed(_DIAMOND.items())), labels=("core",))

    assert [item.path for item in forward] == [item.path for item in backward]
    [cycle] = forward
    assert [target for _, target, _, _, _ in _walk(cycle)] == [
        "sample.core.b",
        "sample.core.d",
        "sample.core.a",
    ]


def test_a_large_cycle_shows_a_short_path_and_counts_the_edges_it_leaves_out(
    tmp_path: Path,
) -> None:
    size = 30
    # A ring keeps all 30 modules in one SCC; every third module adds a chord: 40 edges.
    sources = {
        f"core/r{i}.py": "".join(
            f"from sample.core import r{target}\n"
            for target in [(i + 1) % size, *([(i + 5) % size] if i % 3 == 0 else [])]
        )
        for i in range(size)
    }
    [cycle] = _cycle_run(tmp_path, sources, labels=("core",))
    walk = _walk(cycle)

    assert cycle.size == 40
    assert len(walk) <= size
    assert cycle.path is not None
    assert cycle.path.omitted_edges == cycle.size - len(walk)
    # The steps form one closed walk: each target is the next source, and it returns to the start.
    assert all(step[1] == following[0] for step, following in zip(walk, walk[1:], strict=False))
    assert walk[-1][1] == walk[0][0]


def test_an_edge_whose_only_import_is_type_checking_is_marked(tmp_path: Path) -> None:
    [cycle] = _cycle_run(tmp_path, _TYPE_CHECKED_BACK, labels=("core",))

    assert _walk(cycle) == [
        ("sample.core.a", "sample.core.b", "sample/core/a.py", 3, True),
        ("sample.core.b", "sample.core.a", "sample/core/b.py", 1, False),
    ]


def test_a_hub_carries_no_path_and_the_result_validates_with_and_without(run: Run) -> None:
    validator = _validator("command-result-11.0.schema.json")
    assert run.result.findings is not None
    by_kind = {item.kind: item for item in run.result.findings}
    payload = result_payload(run.result)
    items = payload["findings"]
    assert isinstance(items, list)
    serialized = {item["kind"]: item for item in items if isinstance(item, dict)}

    assert by_kind[FindingKind.FAN_IN_HUB].path is None
    assert "path" not in serialized["fan_in_hub"]
    assert by_kind[FindingKind.MODULE_CYCLE].path is not None
    assert "path" in serialized["module_cycle"]
    assert validator.is_valid(payload)
    assert not validator.is_valid(
        {**payload, "findings": [{**serialized["fan_in_hub"], "path": 1}]}
    )
