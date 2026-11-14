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


WINDOW_HOMES = (
    ("other windows", ("opener", "global"), "source_input.rs"),
    (
        "window members",
        ("defaultView", "contentWindow", "parentWindow", "view", "source"),
        "script_window.rs",
    ),
    ("text timers", ("setTimeout", "setInterval", "setImmediate"), "script_window.rs"),
)


@pytest.mark.parametrize(
    ("label", "names", "owner"), WINDOW_HOMES, ids=[r[0] for r in WINDOW_HOMES]
)
def test_window_name_set_has_one_home(label: str, names: tuple[str, ...], owner: str) -> None:
    test_literal_set_has_one_home(label, names, owner)


# AD-460: each place that decides a script global reads a gate, and each gate reads the writes
# that the one check gives. A new decision site fails this test until it names its gate here.
PROOF_SITES = {
    ("script_depend.rs", "dependency"): "stable_publication(",
    ("script_depend.rs", "source_target"): "source_origin(",
    ("script_global.rs", "external_dependency"): "standard_global(",
    ("script_global.rs", "namespace_dependency"): "bound_or_written_elsewhere(",
}
DECISION = re.compile(r"Target::(Local|Builtin|External) \{|\.resolution\s*$|\.resolution\.")
FUNCTION = re.compile(r"^\s*(?:pub(?:\(crate\))? )?fn ([a-z_0-9]+)")


def _decision_sites() -> dict[tuple[str, str], str]:
    """Each function of a script file that decides a target or a resolution, with its body."""
    found: dict[tuple[str, str], str] = {}
    for path in sorted(SOURCE.glob("script*.rs")):
        if path.stem.endswith("_tests"):
            continue
        text = path.read_text()
        function = ""
        for line in text.splitlines():
            match = FUNCTION.match(line)
            function = match.group(1) if match else function
            if DECISION.search(line):
                start = text.index(f"fn {function}(")
                found[(path.name, function)] = text[start : text.find("\n    }\n", start)]
    return found


def test_each_script_global_decision_reads_the_one_write_check() -> None:
    sites = _decision_sites()
    assert set(sites) == set(PROOF_SITES), "a new decision site must name its gate here"
    for site, gate in PROOF_SITES.items():
        assert gate in sites[site], (site, gate)
    # The gates read the script writes, the source writes and the write paths.
    project = (SOURCE / "script_project.rs").read_text()
    stable = (SOURCE / "script_global.rs").read_text()
    assert "writes.sole(name)" in project
    assert "paths.any_empty" in stable and "paths.singles.contains_key(name)" in stable
    # The one check fills all three: one helper pushes each written name to each of them.
    declarations = (SOURCE / "script_declarations.rs").read_text()
    for call in ("self.global_write(", "self.changed_global(", "self.node_write("):
        assert f"found.check({call}" in declarations, call
    check = declarations[declarations.index("fn check(") :]
    check = check[: check.index("\n    }\n")]
    for field in ("self.writes.push(", "self.checked.push(", "self.paths.push("):
        assert field in check, field
    script = re.sub(r"\s+", "", (SOURCE / "script.rs").read_text())
    assert "declared.checked.iter()" in script and "writes.extend(checked)" in script
