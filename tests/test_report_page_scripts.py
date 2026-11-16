# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The scripts of a report page run: the policy admits each one, and the Explorer starts (#1312).

#1312 changed `report-scene.js` without its hash in the policy of the page. The browser then
refused the script, the Explorer ran on no page, and no test failed. These tests read the real
pages of the self run, the system run and a fixture run: each script body must have its hash in the
policy, and a headless Chrome must show the marker that the Explorer writes when its layout is done.
"""

import base64
import hashlib
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest
from core_support import ROOT, run

from archkeel.cli import core_only

PAGES = {
    "shell": (None, "docs/architecture/shell.toml"),
    "system": (None, "docs/architecture/architecture-system.json"),
    "fixture-typescript": ("fixtures/H-typescript", "archkeel.toml"),
}
SCRIPT = re.compile(r"<script(?![^>]*application/json)[^>]*>(.*?)</script>", re.S)
POLICY = re.compile(r'Content-Security-Policy" content="([^"]+)"')
READY = 'data-layout-state="ready"'
CHROME_NAMES = ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser")
CHROME_APP = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"


def unadmitted(page: str) -> list[str]:
    """The start of each script body of the page whose hash the policy of the page lacks."""
    policy = POLICY.search(page)
    assert policy, "the page has no Content-Security-Policy"
    bodies = SCRIPT.findall(page)
    assert bodies, "the page has no script"
    found = []
    for body in bodies:
        digest = base64.b64encode(hashlib.sha256(body.encode()).digest()).decode()
        if f"'sha256-{digest}'" not in policy.group(1):
            found.append(body[:60])
    return found


@pytest.fixture(scope="module")
def pages(release_core: Path, tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    """One written page for each run of PAGES."""
    folder = tmp_path_factory.mktemp("pages")
    written = {}
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(core_only, "locate_core", lambda: release_core)
        for name, (root, config) in PAGES.items():
            target = folder / f"{name}.html"
            run(
                "report",
                *("--root", str(ROOT / root if root else ROOT)),
                *("--config", config, "--output", str(target)),
            )
            written[name] = target
    return written


@pytest.mark.parametrize("name", sorted(PAGES))
def test_the_policy_of_each_page_admits_each_of_its_scripts(
    pages: dict[str, Path], name: str
) -> None:
    assert unadmitted(pages[name].read_text(encoding="utf-8")) == []


def test_the_script_check_fails_on_a_script_that_changed_after_its_hash() -> None:
    page = (
        '<meta http-equiv="Content-Security-Policy" content="script-src \'sha256-AAAA\'">'
        "<script>one()</script>"
    )
    assert unadmitted(page) == ["one()"]
    digest = base64.b64encode(hashlib.sha256(b"one()").digest()).decode()
    assert unadmitted(page.replace("AAAA", digest)) == []


def chrome() -> str:
    found = os.environ.get("CHROME") or next(
        (path for name in CHROME_NAMES if (path := shutil.which(name))), None
    )
    found = found or (CHROME_APP if Path(CHROME_APP).is_file() else None)
    if found is None:
        if os.environ.get("CI"):
            pytest.fail("no Chrome on this runner: the Explorer cannot be started")
        pytest.skip("no Chrome on this machine; set CHROME to its path")
    return found


def dom_of(page: Path, tmp_path: Path) -> str:
    """The DOM of the page after its scripts ran in headless Chrome."""
    command = [
        chrome(),
        "--headless=new",
        "--disable-gpu",
        "--no-sandbox",
        f"--user-data-dir={tmp_path / 'profile'}",
        "--virtual-time-budget=20000",
        "--dump-dom",
        page.as_uri(),
    ]
    done = subprocess.run(command, capture_output=True, text=True, timeout=120, check=True)
    return done.stdout


@pytest.mark.parametrize("name", sorted(PAGES))
def test_the_explorer_starts_on_each_page(
    pages: dict[str, Path], tmp_path: Path, name: str
) -> None:
    dom = dom_of(pages[name], tmp_path)
    assert READY in dom, "the Explorer did not finish its layout: a script may be refused"
    assert 'data-layout-state="error"' not in dom


def test_the_explorer_does_not_start_when_a_script_has_no_hash(
    pages: dict[str, Path], tmp_path: Path
) -> None:
    page = pages["shell"].read_text(encoding="utf-8")
    hashes = re.findall(r"'sha256-[^']+'", POLICY.search(page).group(1))
    broken = tmp_path / "broken.html"
    broken.write_text(
        page.replace(hashes[3], "'sha256-AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA='")
    )
    assert unadmitted(broken.read_text(encoding="utf-8"))
    assert READY not in dom_of(broken, tmp_path)
