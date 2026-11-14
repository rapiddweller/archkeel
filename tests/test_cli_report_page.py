# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-496: the report page of the default CLI. Each test writes a page with `report --output` and
reads the file, as a user does."""

import base64
import hashlib
import html
import re
from pathlib import Path

import pytest
from core_support import ROOT, run
from frozen_native import frozen_root as frozen_root

from archkeel.cli import core_only

ASSETS = ROOT / "native/report/assets"
BUDGET = 600_000
RUNS = {
    "shell": (None, "docs/architecture/shell.toml", "PASS"),
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


def test_the_page_loads_nothing_and_links_only_inside_itself(self_page: str) -> None:
    assert "src=" not in self_page and "<link" not in self_page and "@import" not in self_page
    assert not re.findall(r'href="(?!#)', self_page)
    assert not re.findall(r"url\((?!data:)", self_page)
    assert "http://" not in self_page and "https://" not in self_page


def test_the_verdict_heading_is_the_one_exact_line_that_the_shell_checks(self_page: str) -> None:
    assert self_page.count("<h1>Verdict: FAIL</h1>") == 1
    assert len(re.findall(r"<h1\b", self_page)) == 1


def test_the_self_run_page_shows_one_block_for_each_of_its_seven_cycles(self_page: str) -> None:
    blocks = re.findall(r'<article class="rp-dos" id="x(\d+)">', self_page)
    assert blocks == [str(number) for number in range(1, 8)]
    assert self_page.count("Cycle of ") == 7
    assert "7 places in the code, 1 rule broken" in self_page
    # Each step names a file and a line of the frame: `path.rs:line`.
    cycle = self_page.split('id="x1"', 1)[1].split("</article>", 1)[0]
    assert re.search(r'<span class="rp-code">native/[a-z_/-]+\.rs:\d+</span>', cycle)
    assert re.search(r"Step \d+ imports .*, where step 1 starts\.", cycle)
    assert "members are in this cycle. Shortest closed path shown:" in cycle
    # The count comes from the page, which copies the frame: more than 12 components draw a matrix.
    count = re.search(r"(\d+) components, \d+ modules", self_page)
    assert count and int(count.group(1)) > 12 and 'class="rp-mx"' in self_page
    # A matrix page has no drawn map: the run has more than 12 components.
    assert 'class="ak-diagram rp-map"' not in self_page


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
    "tokens.css": "5c19020e154a136f14a86103a117fcf46c7331b7a18d78a3dab0115afd6f26d2",
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
    page = re.sub(r"<style>.*?</style>|<script>.*?</script>", "", page, flags=re.S)
    fold = r"<details(?![^>]*\bopen\b)[^>]*>\s*<summary[^>]*>(.*?)</summary>.*?</details>"
    page = re.sub(fold, r"\1", page, flags=re.S)
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", page))).strip()


WORD_BUDGET = 6_000


def test_the_word_budget_of_the_core_self_page_and_no_json_block(self_page: str) -> None:
    """The page is a report for people: its visible text stays short, and it holds no JSON dump.
    Before (main at e65cbe009): 83,356 characters and 46,862 px."""
    words = visible_text(self_page)
    print(f"visible characters of the core self page: {len(words)}")
    assert len(words) < WORD_BUDGET
    assert (
        "<pre" not in self_page
        and '"kind":' not in self_page
        and "&quot;kind&quot;" not in self_page
    )


@pytest.mark.parametrize("name", sorted(RUNS))
def test_the_word_budget_and_the_links_hold_on_each_dogfood_page(
    release_core: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, name: str
) -> None:
    folder, config, _ = RUNS[name]
    root = ROOT / folder if folder else ROOT
    _, text, _ = write_page(release_core, monkeypatch, root, config, tmp_path / "p.html")
    assert len(visible_text(text)) < WORD_BUDGET and "<pre" not in text
    ids = set(re.findall(r' id="([^"]+)"', text))
    links = set(re.findall(r'href="#([^"]+)"', text))
    assert not (links - ids), sorted(links - ids)[:5]


def test_every_link_inside_the_core_self_page_has_its_target(self_page: str) -> None:
    ids = set(re.findall(r' id="([^"]+)"', self_page))
    links = re.findall(r'href="#([^"]+)"', self_page)
    assert links and not (set(links) - ids), sorted(set(links) - ids)[:5]


@pytest.mark.parametrize("name", ["H-typescript", "L-nest-realworld"])
def test_the_page_of_an_unknown_run_names_its_cause_and_at_most_five_held_rules(
    release_core: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, name: str
) -> None:
    folder, config, _ = RUNS[name]
    _, text, found = write_page(
        release_core, monkeypatch, ROOT / folder, config, tmp_path / "p.html"
    )
    assert found["status"] == "UNKNOWN" and "Unknown because of" in text
    held = [rule for rule, row in found["frame"]["rules"].items() if row[1] == "UNKNOWN"]
    line = text.split("Unknown because of", 1)[1].split("</p>", 1)[0]
    named = [rule for rule in held if html.escape(rule, quote=True) in line]
    assert named and len(named) <= 3 * 5
    if len(held) <= 5:
        assert len(named) == len(held)
