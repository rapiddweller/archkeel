# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-496: the report page of the default CLI. Each test writes a page with `report --output` and
reads the file, as a user does."""

import html
import json
import re
from pathlib import Path

import pytest
from core_support import ROOT, run
from frozen_native import frozen_root as frozen_root
from planted_cycle import cycle_root as cycle_root

from archkeel.cli import core_only

RUNS = {
    # AD-1260: a self run has no pinned status; the page must show the status of its own result.
    "shell": (None, "docs/architecture/shell.toml", None),
    "H-typescript": ("fixtures/H-typescript", "archkeel.toml", "UNKNOWN"),
    "L-nest-realworld": ("fixtures/L-nest-realworld", "archkeel.toml", "UNKNOWN"),
    "I-flutter-shop": ("fixtures/I-flutter-shop", "archkeel.toml", "UNKNOWN"),
}


def write_page(
    core: Path, monkeypatch: pytest.MonkeyPatch, root: Path, config: str, target: Path
) -> tuple[int, str, dict]:
    monkeypatch.setattr(core_only, "locate_core", lambda: core)
    code, found = run("report", "--root", str(root), "--config", config, "--output", str(target))
    return code, target.read_text(), found


@pytest.fixture(scope="module")
def self_page(
    release_core: Path, frozen_root: Path, tmp_path_factory: pytest.TempPathFactory
) -> str:
    """The page of the core self run, on the frozen copy of `native/`."""
    with pytest.MonkeyPatch.context() as patch:
        target = tmp_path_factory.mktemp("page") / "core.html"
        code, text, found = write_page(
            release_core, patch, frozen_root, "native/archkeel.toml", target
        )
    assert code in (0, 2) and found["status"] in ("PASS", "UNKNOWN"), found["status"]
    return text


@pytest.fixture(scope="module")
def cycle_page(
    release_core: Path, cycle_root: Path, tmp_path_factory: pytest.TempPathFactory
) -> str:
    """The page of the planted project with one module cycle: a rule fails."""
    with pytest.MonkeyPatch.context() as patch:
        target = tmp_path_factory.mktemp("page") / "cycle.html"
        code, text, found = write_page(release_core, patch, cycle_root, "archkeel.toml", target)
    assert (code, found["status"]) == (1, "FAIL")
    return text


def markup(page: str) -> str:
    """The page without the bodies of its scripts: the scripts are checked by their hashes."""
    return re.sub(r"(<script[^>]*>).*?</script>", r"\1</script>", page, flags=re.S)


def test_the_page_loads_nothing_and_links_to_its_gap_file(self_page: str) -> None:
    page = markup(self_page)
    assert "src=" not in page and "<link" not in page and "@import" not in page
    links = re.findall(r'href="(?!#)([^"]+)"', page)
    assert len(links) == 1
    assert re.fullmatch(r"archkeel-gaps-[0-9a-f]{64}\.json", links[0])
    # `url(#...)` names an SVG marker of the page itself.
    assert not re.findall(r"url\((?!data:|#)", page)
    assert "http://" not in page and "https://" not in page
    # A script cannot request anything either: the policy admits no source.
    assert "default-src 'none'" in self_page and "connect-src" not in self_page


def test_the_verdict_heading_is_the_one_exact_line_that_the_shell_checks(cycle_page: str) -> None:
    assert cycle_page.count("<h1>Verdict: FAIL</h1>") == 1
    assert len(re.findall(r"<h1\b", cycle_page)) == 1


def test_a_cycle_page_shows_one_block_for_its_cycle(cycle_page: str) -> None:
    # The first two places are open blocks; the others are folds with the same id (AD-510).
    blocks = re.findall(
        r'<(?:article|details) class="rp-(?:dos|fold rp-place)" id="x(\d+)"', cycle_page
    )
    assert blocks == ["1"]
    assert cycle_page.count('<article class="rp-dos"') == 1
    assert "1 place in the code, 1 rule broken" in cycle_page
    # Each step names a file and a line of the frame: `path.py:line`.
    cycle = cycle_page.split('id="x1"', 1)[1].split("</article>", 1)[0]
    assert re.search(r'<span class="rp-code">app/[a-z_/]+\.py:\d+</span>', cycle)
    assert re.search(r"Step \d+ imports .*, where step 1 starts\.", cycle)
    assert "members are in this cycle. Shortest closed path shown:" in cycle


def test_the_self_run_page_holds_the_explorer_with_the_components_of_its_line(
    self_page: str,
) -> None:
    # AD-606: the line of counts and the Explorer read the same data.
    count = re.search(r"(\d+) components, \d+ modules", self_page)
    data = re.search(r'<script id="flow-data" type="application/json">(.*?)</script>', self_page)
    assert count and data
    components = json.loads(data.group(1))["atlas"]["components"]
    real = [c for c in components if not c["id"].startswith(("LAYER:", "GROUP:"))]
    assert int(count.group(1)) == len(real)
    assert all(c["language"] == "rust" for c in real if c["observed_modules"])


@pytest.mark.parametrize("name", sorted(RUNS))
def test_the_page_keeps_its_verdict(
    release_core: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, name: str
) -> None:
    folder, config, status = RUNS[name]
    root = ROOT / folder if folder else ROOT
    _, text, found = write_page(release_core, monkeypatch, root, config, tmp_path / "p.html")
    causes = [
        found.get("scope"),
        list(found.get("explained", {}).items())[:3],
        [g["reason"][:200] for g in found.get("gaps", [])][:4],
        [s for s in __import__("json").dumps(found).split('"') if "outside_file" in s][:3],
    ]
    if status is None:
        status = found["status"]
        assert status != "FAIL", causes
    assert found["status"] == status and f"<h1>Verdict: {status}</h1>" in text, causes


def test_a_page_request_adds_no_topology_to_the_output_of_the_run(
    release_core: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(core_only, "locate_core", lambda: release_core)
    config = ("--root", str(ROOT), "--config", "docs/architecture/shell.toml")
    _, plain = run("report", *config)
    _, paged = run("report", *config, "--output", str(tmp_path / "p.html"))
    assert "topology" not in paged["frame"] and paged == plain


def test_the_core_self_page_holds_no_json_block(self_page: str) -> None:
    """The page is a report for people: it holds no JSON dump."""
    page = markup(self_page)
    assert "<pre" not in page and '"kind":' not in page and "&quot;kind&quot;" not in page


@pytest.mark.parametrize("name", sorted(RUNS))
def test_the_links_hold_on_each_dogfood_page(
    release_core: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, name: str
) -> None:
    folder, config, _ = RUNS[name]
    root = ROOT / folder if folder else ROOT
    _, text, _ = write_page(release_core, monkeypatch, root, config, tmp_path / "p.html")
    assert "<pre" not in markup(text)
    ids = set(re.findall(r' id="([^"]+)"', text))
    links = set(re.findall(r'href="#([^"]+)"', text))
    assert not (links - ids), sorted(links - ids)[:5]


def test_every_link_inside_the_core_self_page_has_its_target(
    self_page: str, cycle_page: str
) -> None:
    # A PASS page has no violation or cause to link to; the page of a failing run does, so the
    # check is not empty: it sees links there, and none of either page is dangling.
    for page in (self_page, cycle_page):
        ids = set(re.findall(r' id="([^"]+)"', page))
        links = re.findall(r'href="#([^"]+)"', page)
        assert not (set(links) - ids), sorted(set(links) - ids)[:5]
    assert re.findall(r'href="#([^"]+)"', cycle_page)
    assert re.findall(r' id="([^"]+)"', self_page)


@pytest.mark.parametrize("name", ["H-typescript", "L-nest-realworld"])
def test_the_page_of_an_unknown_run_names_its_cause_and_at_most_five_held_rules(
    release_core: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, name: str
) -> None:
    folder, config, _ = RUNS[name]
    _, text, found = write_page(
        release_core, monkeypatch, ROOT / folder, config, tmp_path / "p.html"
    )
    assert found["status"] == "UNKNOWN"
    held = [rule for rule, row in found["frame"]["rules"].items() if row[1] == "UNKNOWN"]
    cards = text.split('id="unknown"', 1)[1].split("</section>", 1)[0]
    assert 'class="rp-cause"' in cards
    # Each card names at most five rule ids; with at most five held rules, each is named.
    named = [rule for rule in held if html.escape(rule, quote=True) in cards]
    assert named
    if len(held) <= 5:
        assert len(named) == len(held)


@pytest.mark.parametrize("name", ["H-typescript", "L-nest-realworld", "I-flutter-shop"])
def test_no_box_cell_or_edge_of_an_unknown_run_shows_pass(
    release_core: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, name: str
) -> None:
    """AD-730 (#1468): a run that does not decide every rule draws no PASS in the Explorer."""
    folder, config, _ = RUNS[name]
    _, text, found = write_page(
        release_core, monkeypatch, ROOT / folder, config, tmp_path / "p.html"
    )
    assert found["status"] == "UNKNOWN"
    data = re.search(r'<script id="flow-data" type="application/json">(.*?)</script>', text)
    assert data
    atlas = json.loads(data.group(1))["atlas"]
    shown = [c["status"] for c in atlas["components"]]
    shown += [cell[3] for cell in atlas["cells"]]
    shown += [edge["status"] for level in atlas["levels"] for edge in level["edges"]]
    assert shown and "PASS" not in shown


@pytest.mark.parametrize(("unported", "expected"), [(True, "UNKNOWN"), (False, "PASS")])
def test_a_fail_beside_an_unported_rule_draws_no_pass_box(
    release_core: Path,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    unported: bool,
    expected: str,
) -> None:
    """#1507: the client imports the forbidden secret (FAIL) and the contract has a
    `source_ownership` rule that the core does not port. That rule has no row and may break in
    any box, so the boxes without a violated place show UNKNOWN. Without it the run decides every
    rule and those boxes keep PASS."""
    from test_cli_native_python_imports import RULE, project
    from test_cli_python_gap_effects import FILES, RULES

    ownership = {
        **RULE,
        "id": "UNPORTED-OWNER",
        "kind": "source_ownership",
        "source": "app",
        "mode": "confined",
        "symbols": ["app.client.page.helper"],
        "owner": "app.client.page",
        "roles": ["definition", "read"],
    }
    files = {**FILES, "src/app/client/page.py": "import app.service.secret\n"}
    root = project(tmp_path / "p", files, contract_rules=[*RULES, *([ownership] * unported)])
    contract_path = root / "architecture-contract.json"
    contract = json.loads(contract_path.read_text())
    contract["schema_version"] = "3.12.0"
    contract_path.write_text(json.dumps(contract))
    _, text, found = write_page(release_core, monkeypatch, root, "archkeel.toml", tmp_path / "r")
    assert found["status"] == "FAIL"
    assert ("UNPORTED-OWNER" in found["frame"]["unsupported"]["rules"]) is unported
    data = re.search(r'<script id="flow-data" type="application/json">(.*?)</script>', text)
    assert data
    boxes = {c["id"]: c["status"] for c in json.loads(data.group(1))["atlas"]["components"]}
    assert boxes == {"COMP-CLIENT": "FAIL", "COMP-ROOT": expected, "COMP-SERVICE": expected}
