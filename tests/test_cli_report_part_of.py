# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The page of one part names its system and links up (Wave 2 of #1451, E4).

`archkeel report --part-of <system document> --system-href <url>` writes the page of one part of a
system. The core reads the titles of the system and of the part from the system document, so the
Explorer root reads "<part> of <system>" and links to the page of the system.
"""

import json
import re
import shutil
from pathlib import Path

import pytest
from core_support import ROOT, run

from archkeel.cli import core_arguments, core_only

SYSTEM = "docs/architecture/architecture-system.json"
SHELL = "docs/architecture/shell.toml"


def navigation(page: Path) -> dict[str, object]:
    data = re.search(r'id="flow-data" type="application/json">(.*?)</script>', page.read_text())
    assert data, "the page has no Explorer"
    return json.loads(data.group(1))["navigation"]


@pytest.mark.parametrize(
    ("arguments", "words"),
    [
        (["--system-href", "index.html", "--output", "o.html"], "--system-href needs --part-of"),
        (["--part-of", SYSTEM], "--part-of needs an HTML --output"),
        (["--part-of", SYSTEM, "--output", "o.json", "--format", "json"], "HTML --output"),
        (["--part-of", "../system.json", "--output", "o.html"], "below the root"),
    ],
)
def test_a_part_of_option_without_its_page_is_refused_by_name(
    arguments: list[str], words: str
) -> None:
    with pytest.raises(ValueError, match=re.escape(words)):
        core_arguments.parse(["report", *arguments])


def test_the_page_of_a_part_names_its_system_and_links_up(
    release_core: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(core_only, "locate_core", lambda: release_core)
    page = tmp_path / "shell.html"
    run(*("report", "--config", SHELL, "--part-of", SYSTEM, "--system-href", "index.html"),
        *("--output", str(page)))  # fmt: skip
    title = json.loads(Path(SYSTEM).read_text())["title"]
    assert navigation(page) == {
        "repository": f"Python shell of {title}",
        "main_href": "",
        "part_title": "Python shell",
        "system_title": title,
        "system_href": "index.html",
    }
    plain = tmp_path / "plain.html"
    run("report", "--config", SHELL, "--output", str(plain))
    assert navigation(plain) == {"repository": "System", "main_href": ""}


@pytest.mark.parametrize(
    ("document", "words"),
    [
        ("system.json", "no part names the configuration archkeel.toml"),
        ("archkeel.toml", "not a system document"),
    ],
)
def test_a_part_of_document_that_does_not_name_the_part_is_a_refusal(
    release_core: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    document: str,
    words: str,
) -> None:
    monkeypatch.setattr(core_only, "locate_core", lambda: release_core)
    root = tmp_path / "project"
    shutil.copytree(ROOT / "fixtures" / "H-typescript", root)
    system = json.loads((ROOT / SYSTEM).read_text())
    other = {**system["parts"][0], "id": "other", "config": "other.toml"}
    (root / "system.json").write_text(
        json.dumps({**system, "parts": [other], "interfaces": [], "rules": []})
    )
    code, found = run(
        *("report", "--root", str(root), "--config", "archkeel.toml", "--part-of", document),
        *("--output", str(tmp_path / "page.html")),
    )
    assert (code, found["status"]) == (2, "UNKNOWN")
    assert f"--part-of {document}: {words}" in json.dumps(found)
