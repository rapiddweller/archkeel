# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The product page copies two runs and joins none (AD-462): a small page, links that resolve."""

from __future__ import annotations

import html
import re
from pathlib import Path
from typing import Any

import pytest
from core_support import run as run_cli
from planted_cycle import cycle_root as cycle_root

from archkeel.cli import core_only
from tools import report_gallery
from tools.report_product import (
    ALL_NAMED_LIMIT,
    MAX_PLACES,
    Contract,
    Part,
    contract_of,
    judge,
    part_of,
    summed,
    system,
    system_line,
    weakest,
    worst,
)
from tools.report_product_page import headline_of, product_page, system_note
from tools.system_parts import load

NAME = load().name
SHELL, CORE = report_gallery.SELF_RUNS[:2]


def _frame(*, cycles: int = 2, imports: int = 1, comps: int = 4, gaps: int = 1) -> dict[str, Any]:
    components = [{"id": f"C{i}", "name": f"comp-{i}"} for i in range(comps)]
    modules = [{"name": f"m{i}", "component": f"C{i}"} for i in range(comps)]
    details = [
        {"source": "m0", "target": "m1", "cause": "forbidden import", "evidence": []}
        for _ in range(imports)
    ]
    details += [
        {"source": "m2 -> m3", "target": "m2", "cause": "dependency cycle", "evidence": []}
        for _ in range(cycles)
    ]
    items = [
        {
            "index": imports + n,
            "members": ["m2", "m3"],
            "path": [{"from_component": "C2", "to_component": "C3"}],
        }
        for n in range(cycles)
    ]
    return {
        "status": "FAIL",
        "engine": "archkeel-core " + "a" * 64,
        "contract_digest": "b" * 64,
        "rules": {"R1": ["x", "FAIL"], "R2": ["x", "PASS"], "R3": ["x", "UNKNOWN"]},
        "topology": {"components": components, "modules": modules, "total": {"modules": 99}},
        "details": {"R1": details},
        "explain": {"cycles": {"R1": {"items": items}}},
        "collection_gaps": [{"subjects": ["m1"]}] * gaps,
    }


def _part(entry: dict[str, str], frame: dict[str, Any] | None, status: str = "FAIL") -> Part:
    envelope = None if frame is None else {"status": status, "frame": frame}
    return part_of(envelope, entry, f"self/{entry['name']}.html", "boom")


def _visible(text: str) -> str:
    body = re.sub(r"<script.*?</script>|<style.*?</style>", "", text, flags=re.S)
    return html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", body))).strip()


def _page(parts: list[Part], ids: frozenset[str] = frozenset()) -> str:
    return product_page(NAME, parts, {part.key: ids for part in parts}, "abc1234567", "now")


def test_the_places_follow_the_numbering_of_the_part_report_imports_first_then_cycles() -> None:
    part = _part(CORE, _frame(cycles=2, imports=1))
    assert [place.number for place in part.places] == [1, 2, 3]
    assert part.places[0].text == "comp-0 imports comp-1"
    assert part.places[1].text == "Cycle of 2 modules in comp-2"
    assert part.places_total == 3 and part.failing == 3


def test_a_component_with_a_violation_is_named_and_an_unknown_one_after_it() -> None:
    part = _part(CORE, _frame(comps=5))
    states = [(tile.label, tile.state) for tile in part.tiles]
    assert states == [
        ("comp-0", "FAIL"),
        ("comp-2", "FAIL"),
        ("comp-3", "FAIL"),
        ("comp-1", "UNKNOWN"),
        ("comp-4", ""),
    ]
    assert part.tiles[0].place == 1


def test_a_large_state_is_one_count_and_never_a_row_of_names() -> None:
    frame = _frame(comps=ALL_NAMED_LIMIT + 8, cycles=0, imports=0, gaps=0)
    frame["collection_gaps"] = [{"subjects": [f"m{i}"]} for i in range(2, ALL_NAMED_LIMIT + 8)]
    part = _part(CORE, frame)
    assert [tile.label for tile in part.tiles] == [
        f"{ALL_NAMED_LIMIT + 6} with gaps",
        "2 without an exception",
    ]


def test_the_list_of_places_is_cut_where_the_part_report_cuts_it() -> None:
    part = _part(CORE, _frame(cycles=MAX_PLACES + 5, imports=0))
    assert len(part.places) == MAX_PLACES and part.places_total == MAX_PLACES + 5


def test_a_part_without_an_envelope_shows_its_error_and_no_verdict() -> None:
    part = _part(SHELL, None)
    page = _page([part, _part(CORE, _frame())])
    assert not part.decided and "No result: boom" in page
    assert worst([part]) == "UNKNOWN"
    # The system is as weak as its weakest part: a part without a result is UNKNOWN, not PASS.
    passing = {**_frame(), "rules": {"R": ["x", "PASS"]}}
    assert worst([part, _part(CORE, passing, "PASS")]) == "UNKNOWN"
    assert f"{NAME}: FAIL" in page


def test_a_refused_part_shows_the_reason_of_the_core_escaped() -> None:
    envelope = {"status": "UNKNOWN", "refusal": {"message": "<b>no</b>"}, "frame": {}}
    part = part_of(envelope, CORE, "self/core.html")
    page = _page([_part(SHELL, _frame(), "PASS"), part])
    assert "No result: &lt;b&gt;no&lt;/b&gt;" in page and "<b>no</b>" not in page


def test_a_link_into_a_part_report_exists_only_for_an_id_that_the_report_holds() -> None:
    parts = [_part(SHELL, _frame(), "PASS"), _part(CORE, _frame())]
    holding = _page(parts, frozenset({"x1", "x2", "x3", "arch", "violations"}))
    missing = _page(parts, frozenset())
    assert 'href="self/core.html#x3"' in holding and 'href="self/core.html#x3"' not in missing
    assert 'href="self/core.html"' in missing


def test_every_link_of_the_gallery_page_has_a_target_that_the_tool_writes(tmp_path: Path) -> None:
    out = tmp_path / "site"
    stub = tmp_path / "stub.py"
    stub.write_text(_STUB.replace("FRAME", repr(_frame())))
    code = report_gallery.main(
        ["--out", str(out), "--archkeel", f"python3 {stub}", "--sha", "abc", "--built-at", "t"]
    )
    page = (out / "index.html").read_text()
    assert code == 0
    links = set(re.findall(r'href="([^"]+)"', page))
    # The entry is the report of the system: a bar of links to the fixtures and to each part.
    assert {"self/core.html", "self/shell.html", "showcase/index.html"} <= links
    for link in links:
        path, _, anchor = link.partition("#")
        target = out / path
        assert target.is_file(), link
        if anchor:
            assert f'id="{anchor}"' in target.read_text(), link


_STUB = """
import json, sys
args = sys.argv[1:]
out = args[args.index("--output") + 1]
html = '<main id="arch"><section id="violations"><article id="x1"></article><article id="x2">'
html += '</article><article id="x3"></article></section></main>'
open(out, "w").write(html if "html" in args else "{}")
envelope = {"command": "report", "status": "FAIL", "exit_code": 1, "gaps": [], "frame": FRAME}
print(json.dumps(envelope))
"""


def test_the_anchors_of_a_real_core_report_exist_and_match_the_number_of_places(
    release_core: Path,
    cycle_root: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The numbers of the page are the ids `x1..xN` of the report that the same run writes."""
    monkeypatch.setattr(core_only, "locate_core", lambda: release_core)
    target = tmp_path / "core.html"
    arguments = ["--root", str(cycle_root), "--config", "archkeel.toml"]
    code, envelope = run_cli("report", *arguments, "--output", str(target), "--topology")
    assert code == 1
    part = part_of(envelope, CORE, "self/core.html")
    ids = re.findall(r'\sid="(x\d+)"', target.read_text())
    assert part.places_total > 0
    assert sorted(ids, key=lambda name: int(name[1:])) == [
        f"x{place.number}" for place in part.places
    ]
    assert part.tiles and part.counts["FAIL"] > 0


def test_a_part_of_at_most_twelve_components_names_each_one_and_a_larger_one_counts() -> None:
    small = _part(SHELL, _frame(comps=ALL_NAMED_LIMIT, cycles=0, imports=0, gaps=0), "PASS")
    assert [tile.label for tile in small.tiles] == [f"comp-{i}" for i in range(ALL_NAMED_LIMIT)]
    assert not any(tile.count or tile.state for tile in small.tiles)
    large = _part(SHELL, _frame(comps=ALL_NAMED_LIMIT + 1, cycles=0, imports=0, gaps=0), "PASS")
    assert [tile.label for tile in large.tiles] == [f"{ALL_NAMED_LIMIT + 1} without an exception"]


def test_another_contract_is_one_line_with_its_counts_and_a_failure_shows_no_counts() -> None:
    rules = {"R": ["x", "UNKNOWN"]}
    ok = contract_of({"status": "UNKNOWN", "frame": {"rules": rules}}, "Studio UI")
    bad = contract_of(None, "Browser assets", "boom")
    parts = [_part(SHELL, _frame(), "PASS"), _part(CORE, _frame())]
    ids = {part.key: frozenset[str]() for part in parts}
    text = _visible(product_page(NAME, parts, ids, "abc", "now", [ok, bad]))
    assert "UNKNOWN Studio UI 0/0/1" in text
    assert "NO RESULT Browser assets boom" in text


def test_the_system_is_the_weakest_verdict_of_its_parts_with_the_counts_added_up() -> None:
    assert weakest(["PASS", "UNKNOWN"]) == "UNKNOWN"
    assert weakest(["UNKNOWN", "FAIL", "PASS"]) == "FAIL"
    assert weakest(["PASS", "PASS"]) == "PASS"
    assert weakest(["PASS", ""]) == "UNKNOWN" and weakest([]) == "UNKNOWN"
    assert summed([{"PASS": 63, "UNKNOWN": 20}, {"PASS": 22}]) == {
        "PASS": 85,
        "FAIL": 0,
        "UNKNOWN": 20,
    }
    line = system_line(
        NAME,
        [
            Contract("a", "PASS", {"PASS": 22}),
            Contract("b", "UNKNOWN", {"PASS": 63, "UNKNOWN": 20}),
        ],
    )
    assert line == f"{NAME}: UNKNOWN: 85 PASS · 0 FAIL · 20 UNKNOWN"


def test_the_card_of_the_system_comes_first_and_is_never_a_green_pass_over_an_unknown() -> None:
    unknown = _part(CORE, {**_frame(), "rules": {"R": ["x", "UNKNOWN"]}}, "UNKNOWN")
    passing = _part(SHELL, {**_frame(), "rules": {"R": ["x", "PASS"]}}, "PASS")
    page = _page([passing, unknown])
    first = page.split("Verdict of the system")[1][:600]
    assert "ak-verdict--unknown" in page.split("Verdict of the system")[0][-120:]
    assert "cannot be decided" in first and "UNKNOWN is not a pass" in first


def _mk(key: str, status: str, counts: dict[str, int]) -> Part:
    return Part(key, key, "py", "s", f"{key}.html", status=status, counts=counts)


def test_the_note_follows_the_verdict_when_a_part_fails_and_another_has_no_result() -> None:
    failing = _mk("a", "FAIL", {"PASS": 1, "FAIL": 1, "UNKNOWN": 0})
    missing = Part("b", "b", "rs", "s", "b.html", error="no envelope")
    note = system_note(system([failing, missing]), [failing, missing])
    assert note.startswith("No result for b.") and "A violation is a fact of this run" in note
    assert "No violation found" not in note
    only_missing = system_note(system([missing]), [missing])
    assert "No violation found" in only_missing and "UNKNOWN is not a pass" in only_missing
    assert headline_of(system([missing])) == "The system cannot be decided"


def test_the_badge_shows_the_fail_of_one_part_when_another_part_has_no_result() -> None:
    failing = _mk("a", "FAIL", {"PASS": 1, "FAIL": 1, "UNKNOWN": 0})
    missing = Part("b", "b", "rs", "s", "b.html", error="no envelope")
    badge = report_gallery.system_badge([failing, missing])
    assert badge["color"] == "f2606b" and badge["message"].endswith("1 no result")
    assert badge["color"] == report_gallery.COLORS[worst([failing, missing])]
    ok = _mk("c", "PASS", {"PASS": 5, "FAIL": 0, "UNKNOWN": 0})
    assert report_gallery.system_badge([ok, missing])["color"] == "ecb64a"


def test_the_join_does_not_trust_the_word_of_an_envelope() -> None:
    row = {"R": ["x", "FAIL"]}
    assert judge({"status": "PASS", "exit_code": 0, "frame": {"rules": row}}).status == "FAIL"
    assert judge({"status": "PASS", "exit_code": 2, "frame": {}}).status == "UNKNOWN"
    assert judge({"status": "PASS", "exit_code": 0, "frame": {}}).status == "PASS"
    for bad in (None, {}, [], "x", {"status": None}, {"status": "MAYBE"}):
        assert judge(bad) is None
    one = Part("a", "a", "x", "s", "a.html", status="PASS", counts={}, commit="1")
    two = Part("b", "b", "x", "s", "b.html", status="PASS", counts={}, commit="2")
    assert system([one, two]).status == "UNKNOWN"
    assert system([one, two]).cause == "parts are from different commits"
    assert system([one, one]).status == "PASS"


def test_a_part_card_labels_the_unit_of_its_exception_counts() -> None:
    part = _part(CORE, _frame())
    page = _page([_part(SHELL, _frame(), "PASS"), part])
    text = _visible(page)
    assert re.search(r"\d+ components? with a violation · \d+ components? with gaps", text)
