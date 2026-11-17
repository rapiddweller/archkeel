# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The README shows the hero, the mission and live reports that the gallery really writes."""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import unquote, urlparse

from test_report_gallery import _build, _matrix, _run

ROOT = Path(__file__).parents[1]
README = (ROOT / "README.md").read_text()
SITE = "https://rapiddweller.github.io/archkeel/"
MAX_BADGES = 10
MAX_HERO_BYTES = 300_000


def test_the_hero_comes_first_then_the_mission_line() -> None:
    lines = [line for line in README.splitlines() if line.strip()]
    assert lines[0] == "# ArchKeel"
    assert 'src="docs/assets/archkeel-hero.png"' in lines[2]
    assert 'alt="ArchKeel: deterministic architecture checks. PASS, FAIL or UNKNOWN."' in lines[2]
    assert lines[4] == "**See what your code really does. Check it against what you decided.**"
    assert "archkeel-mark.svg" not in README


def test_the_hero_files_exist_and_stay_small() -> None:
    png = ROOT / "docs/assets/archkeel-hero.png"
    assert png.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
    assert png.stat().st_size <= MAX_HERO_BYTES
    assert (ROOT / "docs/assets/archkeel-hero.svg").read_text().startswith("<svg")


def test_the_badges_are_few_in_two_rows_and_use_the_dark_label() -> None:
    top = README.split("**See it live.**")[0]
    badges = re.findall(r"!\[[^\]]*\]\((https://[^)]+)\)", top)
    assert 0 < len(badges) <= MAX_BADGES
    assert len([row for row in top.split("\n\n") if row.startswith(("![", "[!["))]) == 2
    assert all("labelColor=141414" in url for url in badges if "img.shields.io" in url)
    # One self badge: the verdict of the system, from the generated file (never a fixed PASS).
    assert sum("endpoint?url=" in url for url in badges) == 1
    assert SITE + "self/badge.json" in top
    assert "checks-Rust" not in top and "engine-Rust" not in top


def test_the_state_of_main_follows_the_pitch() -> None:
    assert README.index("**See it live.**") < README.index("## Why ArchKeel?")
    assert README.index("## Why ArchKeel?") < README.index("## State of `main`")
    assert README.index("## State of `main`") < README.index("## Install")


def test_each_link_to_the_site_names_a_path_that_the_gallery_writes(tmp_path: Path) -> None:
    code, out = _build(tmp_path, _matrix(tmp_path / "m.json", [_run("served-a", "served-a")]))
    assert code == 0
    written = {path.relative_to(out).as_posix() for path in out.rglob("*") if path.is_file()}
    urls = {
        unquote(url).rstrip(").,") for url in re.findall(re.escape(SITE) + r'[^\s)\]&"]*', README)
    }
    endpoint = re.findall(r"endpoint\?url=" + re.escape(SITE) + r"([^&)]+)", README)
    assert len(urls) >= 4 and endpoint == ["self/badge.json"]
    assert SITE + "self/index.html" in urls
    assert any(url.endswith("/showcase/index.html") for url in urls)
    for url in urls:
        path = urlparse(url).path.removeprefix("/archkeel/")
        assert (path or "index.html") in written, url


def test_the_first_screen_orders_meaning_verdict_picture_and_start() -> None:
    first = README.split("## Why ArchKeel?")[0]
    order = [
        "checks it against the boundaries you declare",
        "**UNKNOWN is not a pass.**",
        "docs/assets/archkeel-report.png",
        "**What each language decides today.**",
        "uv tool install git+https://github.com/rapiddweller/archkeel",
    ]
    positions = [first.index(text) for text in order]
    assert positions == sorted(positions)
    picture = ROOT / "docs/assets/archkeel-report.png"
    assert picture.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
    assert picture.stat().st_size <= 200_000


def test_the_readme_pins_no_count_and_does_not_announce_an_unreleased_version() -> None:
    first = README.split("## Why ArchKeel?")[0]
    # The counts live in the generated badge and page. A fixed count here would go stale.
    assert not re.search(r"\b\d+ (?:PASS|FAIL|UNKNOWN|rules)\b", first)
    assert "5.0.0" not in README
    assert "4.0.1" in README


TIERS = re.compile(r"<!-- tiers:start -->\n(.*?)\n<!-- tiers:end -->", re.S)


def test_the_language_tiers_of_the_readme_are_the_block_of_the_known_limits() -> None:
    limits = (ROOT / "docs/known-limits.md").read_text()
    (block,) = TIERS.findall(limits)
    assert len(TIERS.findall(README)) >= 2
    assert all(found == block for found in TIERS.findall(README))
    # Outside the block, the known limits say what the block says, so that one cannot change alone.
    body = TIERS.sub("", limits).replace("\n", " ")
    assert "`interface_boundary` and symbol-level" in body and "(AD-504)" in body
    flat = re.sub(r"\s+", " ", body)
    assert "cycle rule (`no_component_cycles`) has its receipt when the package map" in flat
    for sentence in block.splitlines():
        assert sentence.endswith(".")
    # The README names no tier of its own outside the block.
    outside = TIERS.sub("", README)
    assert "only for the rules that read the import graph" not in outside
    assert "four languages" not in outside.lower()
