# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-496: the report page of the default CLI. Each test writes a page with `report --output` and
reads the file, as a user does."""

import base64
import hashlib
import html
import json
import re
from pathlib import Path

import pytest
from core_support import ROOT, pinned_self_status, run
from frozen_native import frozen_root as frozen_root
from planted_cycle import cycle_root as cycle_root

from archkeel.cli import core_only

ASSETS = ROOT / "native/report/assets"
# AD-606: the Explorer scripts and style are about 2.1 MB of the page.
BUDGET = 3_500_000
RUNS = {
    # AD-670: the shell pin holds the known FAIL rows of its self-contract.
    "shell": (
        None,
        "docs/architecture/shell.toml",
        pinned_self_status(ROOT / "docs/architecture/target/shell-expected.json")[1],
    ),
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
    assert (code, found["status"]) == pinned_self_status()
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


def test_the_theme_script_is_the_file_of_the_design_system_and_its_hash_is_in_the_policy(
    self_page: str,
) -> None:
    script = (ASSETS / "archkeel-theme.js").read_bytes()
    digest = base64.b64encode(hashlib.sha256(script).digest()).decode()
    assert f"script-src 'sha256-{digest}'" in self_page
    assert self_page.count("<script>") == 1
    assert f"<script>{script.decode()}</script>" in self_page
    assert "default-src 'none'" in self_page and "unsafe-eval" not in self_page


def markup(page: str) -> str:
    """The page without the bodies of its scripts: the scripts are checked by their hashes."""
    return re.sub(r"(<script[^>]*>).*?</script>", r"\1</script>", page, flags=re.S)


def test_the_page_loads_nothing_and_links_only_inside_itself(self_page: str) -> None:
    page = markup(self_page)
    assert "src=" not in page and "<link" not in page and "@import" not in page
    assert not re.findall(r'href="(?!#)', page)
    # `url(#...)` names an SVG marker of the page itself.
    assert not re.findall(r"url\((?!data:|#)", page)
    assert "http://" not in page and "https://" not in page
    # A script cannot request anything either: the policy admits no source.
    assert "default-src 'none'" in self_page and "connect-src" not in self_page


def test_each_script_of_the_page_is_admitted_by_its_hash(self_page: str) -> None:
    policy = re.search(r'Content-Security-Policy" content="([^"]+)"', self_page)
    assert policy
    bodies = re.findall(r"<script(?![^>]*application/json)[^>]*>(.*?)</script>", self_page, re.S)
    assert len(bodies) == 9, "the theme switch and the eight scripts of the Explorer"
    for body in bodies:
        digest = base64.b64encode(hashlib.sha256(body.encode()).digest()).decode()
        assert f"'sha256-{digest}'" in policy.group(1)


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
    assert int(count.group(1)) == len(real) > 12
    assert all(c["language"] == "rust" for c in real if c["observed_modules"])


@pytest.mark.parametrize("name", sorted(RUNS))
def test_the_page_stays_below_the_budget_and_keeps_its_verdict(
    release_core: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, name: str
) -> None:
    folder, config, status = RUNS[name]
    root = ROOT / folder if folder else ROOT
    _, text, found = write_page(release_core, monkeypatch, root, config, tmp_path / "p.html")
    size = len(text.encode())
    print(f"page {name}: {size} bytes")
    assert found["status"] == status and f"<h1>Verdict: {status}</h1>" in text
    assert size < BUDGET


def test_the_core_self_page_stays_below_the_budget(self_page: str) -> None:
    print(f"page core self run: {len(self_page.encode())} bytes")
    assert len(self_page.encode()) < BUDGET


def test_a_page_request_adds_no_topology_to_the_output_of_the_run(
    release_core: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(core_only, "locate_core", lambda: release_core)
    config = ("--root", str(ROOT), "--config", "docs/architecture/shell.toml")
    _, plain = run("report", *config)
    _, paged = run("report", *config, "--output", str(tmp_path / "p.html"))
    assert "topology" not in paged["frame"] and paged == plain


# AD-496: the design-system files are copies. The hashes pin their bytes, so that a change of the
# copy is a reviewed change of the hash too.
DESIGN_SYSTEM = {
    "tokens.css": "782f1a7ac43a20875d3b36e7d614138634cb60fb19ca682aa586d9f2b4a46c36",
    "bundle.css": "88cf31f2cc4c3d830ab611bcd49f92c67131b2b996e9e8de4132a31443974389",
    "Geist-Variable.woff2": "19f9c92546aa300c312235e3125af1b81394d8db9a4bc4a425cd5b641d2d54e1",
    "JetBrainsMono-Variable.woff2": (
        "18be452724bfdc236c074ca94a249a7f41a86752c7d04ab258ce9ed5651f6a7e"
    ),
    "archkeel-theme.js": "ecdc6971d6bc31aff76fd6bdb557f38b69eaec35bcf35bd8bf1ec1f2459d3944",
}


@pytest.mark.parametrize("name", sorted(DESIGN_SYSTEM))
def test_the_design_system_copy_has_its_pinned_bytes(name: str) -> None:
    digest = hashlib.sha256((ASSETS / name).read_bytes()).hexdigest()
    assert digest == DESIGN_SYSTEM[name], f"{name} changed: review it and update the pin"


def test_the_local_style_has_no_rule_that_no_page_uses() -> None:
    assert "rp-ring" not in (ASSETS / "report.css").read_text()


def visible_text(page: str) -> str:
    """The text that a reader sees: no style, no script, the body of a closed fold left out."""
    page = re.sub(r"<style>.*?</style>|<script[^>]*>.*?</script>", "", page, flags=re.S)
    fold = r"<details(?![^>]*\bopen\b)[^>]*>\s*<summary[^>]*>(.*?)</summary>.*?</details>"
    page = re.sub(fold, r"\1", page, flags=re.S)
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", page))).strip()


WORD_BUDGET = 6_000
# AD-668: the self page shows each violated place of the self-contract (honesty rule); each block
# adds its own text to the budget, and no more than this.
PLACE_BUDGET = 400


def test_the_word_budget_of_the_core_self_page_and_no_json_block(self_page: str) -> None:
    """The page is a report for people: its visible text stays short, and it holds no JSON dump.
    Before (main at e65cbe009): 83,356 characters and 46,862 px."""
    words = visible_text(self_page)
    places = self_page.count('class="rp-dos"')
    print(f"visible characters of the core self page: {len(words)} with {places} places")
    assert len(words) < WORD_BUDGET + PLACE_BUDGET * places
    page = markup(self_page)
    assert "<pre" not in page and '"kind":' not in page and "&quot;kind&quot;" not in page


@pytest.mark.parametrize("name", sorted(RUNS))
def test_the_word_budget_and_the_links_hold_on_each_dogfood_page(
    release_core: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, name: str
) -> None:
    folder, config, _ = RUNS[name]
    root = ROOT / folder if folder else ROOT
    _, text, _ = write_page(release_core, monkeypatch, root, config, tmp_path / "p.html")
    places = text.count('class="rp-dos"')
    assert len(visible_text(text)) < WORD_BUDGET + PLACE_BUDGET * places
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
