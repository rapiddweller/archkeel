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
    assert sum("endpoint?url=" in url for url in badges) == 2


def test_the_state_of_main_follows_the_pitch() -> None:
    assert README.index("**See it live.**") < README.index("## Why ArchKeel?")
    assert README.index("## Why ArchKeel?") < README.index("## State of `main`")
    assert README.index("## State of `main`") < README.index("## Install")


def test_each_link_to_the_site_names_a_path_that_the_gallery_writes(tmp_path: Path) -> None:
    code, out = _build(tmp_path, _matrix(tmp_path / "m.json", [_run("served-a", "served-a")]))
    assert code == 0
    written = {path.relative_to(out).as_posix() for path in out.rglob("*") if path.is_file()}
    urls = {
        unquote(url).rstrip(").,") for url in re.findall(re.escape(SITE) + r"[^\s)\]&]*", README)
    }
    endpoint = re.findall(r"endpoint\?url=" + re.escape(SITE) + r"([^&)]+)", README)
    assert len(urls) >= 3 and len(endpoint) == 2
    for url in urls:
        path = urlparse(url).path.removeprefix("/archkeel/")
        assert (path or "index.html") in written, url
