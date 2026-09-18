# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The PyPI description is this README with its local paths rewritten, or it is broken links.

PyPI serves the description with no repository around it, so every `docs/...` path in the
README resolves against pypi.org and 404s. `hatch-fancy-pypi-readme` rewrites them at build
time; this applies the very same substitutions and fails if one path is left behind, which is
how four images shipped broken after the substitution list was kept per file.
"""

import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).parents[1]
# Anchors are the one local reference that is correct on PyPI: they point within the page.
_LOCAL_ATTRIBUTE = re.compile(r'(?:src|href)="(?!https?:|#|mailto:)[^"]*"')
_LOCAL_LINK = re.compile(r"\]\((?!https?:|#|mailto:)[^)]+\)")


def _rendered_description() -> str:
    config = tomllib.loads((ROOT / "pyproject.toml").read_text())
    hook = config["tool"]["hatch"]["metadata"]["hooks"]["fancy-pypi-readme"]
    text = (ROOT / "README.md").read_text()
    for substitution in hook["substitutions"]:
        text = re.sub(substitution["pattern"], substitution["replacement"], text)
    return text


def test_no_local_path_survives_into_the_pypi_description() -> None:
    rendered = _rendered_description()
    assert _LOCAL_ATTRIBUTE.findall(rendered) == []
    assert _LOCAL_LINK.findall(rendered) == []


def test_every_rewritten_asset_exists_in_the_repository() -> None:
    """A rewritten URL is only as good as the file it points at on the default branch."""
    prefix = "https://raw.githubusercontent.com/rapiddweller/archkeel/main/"
    referenced = {
        url.removeprefix(prefix)
        for url in re.findall(
            r'src="(https://raw\.githubusercontent\.com[^"]*)"', _rendered_description()
        )
    }
    assert referenced
    missing = sorted(path for path in referenced if not (ROOT / path).is_file())
    assert missing == []
