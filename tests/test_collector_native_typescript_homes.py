# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Keep the shared TypeScript literal sets in one production source location."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

SOURCE = Path(__file__).parents[1] / "native/typescript/src"
HOMES = (
    ("walk roots", ("window", "globalThis", "self", "frames"), "source_input.rs"),
    ("frame roots", ("top", "parent"), "source_input.rs"),
    ("config directory", ("${configDir}",), "layer.rs"),
    ("visibility names", ("public", "protected", "private"), "members.rs"),
    ("site kind names", ("call", "new", "reference"), "site_types.rs"),
    (
        "host names",
        ("exports", "module", "define", "window", "global", "self"),
        "source_input.rs",
    ),
)


def _literal_groups(text: str) -> list[set[str]]:
    # Read strings before block delimiters, so `${configDir}` stays one token.
    text = re.sub(r"//[^\n]*", "", text)
    groups: list[set[str]] = []
    names: set[str] = set()
    for match in re.finditer(r'b?"(?:\\.|[^"\\])*"|[;{}]', text):
        token = match.group()
        if token in (";", "{", "}"):
            groups.append(names)
            names = set()
        else:
            names.add(token.removeprefix("b")[1:-1])
    groups.append(names)
    return groups


@pytest.mark.parametrize(("label", "names", "owner"), HOMES, ids=[row[0] for row in HOMES])
def test_literal_set_has_one_home(label: str, names: tuple[str, ...], owner: str) -> None:
    found = [
        path.name
        for path in sorted(SOURCE.rglob("*.rs"))
        if not path.stem.endswith("_tests")
        for group in _literal_groups(path.read_text())
        if set(names) <= group
    ]
    assert found == [owner], f"{label}: expected only {owner}, found {found}"
