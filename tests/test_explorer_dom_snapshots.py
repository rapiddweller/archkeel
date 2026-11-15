# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The DOM that the Explorer runtime builds, in Chromium, for the page fixtures (AD-492).

Each fixture is a page of the deleted report renderer (see `tools/dom_snapshot.py`). The scenario
clicks the views and the first elements of each page. The snapshot is the serialized DOM after the
clicks; `sinks.json` lists the markup sinks of the runtime that the scenarios reach, so that a
rewrite of a sink is checked only where a snapshot sees it. Refresh both with
`ARCHKEEL_UPDATE_SNAPSHOTS=1 uv run pytest -m browser tests/test_explorer_dom_snapshots.py`.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import dom_snapshot  # noqa: E402

SNAPSHOTS = Path(__file__).parent / "browser_snapshots"
FIXTURES = ("ts-report", "ts-detail", "story-report", "story-detail")
VIEWS = [f'button[data-flow-view="{view}"]' for view in ("target", "diff", "review", "actual")]
SCENARIO = [
    *VIEWS,
    'button[data-flow-view="diagram"]',
    *[f"svg g.node@{index}" for index in range(4)],
    "button[data-uml-detail]",
    "button[data-flow-details-toggle]",
    *[f"button.flow-legend-item@{index}" for index in range(3)],
]


def _update() -> bool:
    return os.environ.get("ARCHKEEL_UPDATE_SNAPSHOTS") == "1"


@pytest.fixture(scope="module")
def runs() -> dict[str, tuple[str, set[tuple[int, int]]]]:
    if dom_snapshot.chromium() is None:
        pytest.skip("no Chromium: set ARCHKEEL_CHROMIUM")
    found = {}
    for name in FIXTURES:
        dom, sites = dom_snapshot.run(name, SCENARIO)
        found[name] = (dom, dom_snapshot.reached(sites))
    return found


@pytest.mark.browser
@pytest.mark.parametrize("name", FIXTURES)
def test_the_dom_of_a_fixture_is_the_snapshot(
    name: str, runs: dict[str, tuple[str, set[tuple[int, int]]]]
) -> None:
    path = SNAPSHOTS / f"{name}.html"
    dom = runs[name][0]
    if _update():
        path.write_text(dom, encoding="utf-8")
    assert dom == path.read_text(encoding="utf-8")


@pytest.mark.browser
def test_the_scenarios_reach_the_pinned_markup_sinks(
    runs: dict[str, tuple[str, set[tuple[int, int]]]],
) -> None:
    reached = sorted(set().union(*(sites for _, sites in runs.values())))
    pinned = SNAPSHOTS / "sinks.json"
    report = {"reached": [list(at) for at in reached], "all": len(dom_snapshot.sinks())}
    if _update():
        pinned.write_text(json.dumps(report, indent=1) + "\n", encoding="utf-8")
    assert report == json.loads(pinned.read_text(encoding="utf-8"))
