# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""One fact has one table: two literal tables that share most names are one table written twice.

The clone gate skips tables of literals by design (`tests/test_rust_clones.py`), so a list of names
can be copied into a second file without a finding. The hygiene audit found a door list and a
builtin list written twice in the Python collector. A new name added to one copy and not to the
other is a wrong-PASS route.

This test reads each table of string literals at the top level of a production file: a Rust
`const` or `static` array in `native/*/src`, and a Python tuple, list or set (also inside a
`frozenset(...)` call) in `src/`. Two tables of different files overlap when they share at least
`MIN_SHARED` names and at least `MIN_SHARE` of the smaller table. A subset counts too: derive the
smaller table from the larger in code, or state both from one table.

Each overlap on main is listed in `tests/table_overlap_expected.json` with its issue, so it stays
visible until the code is fixed. A new overlap fails, a gone overlap asks to remove its entry, and
a pinned overlap must not grow.
"""

from __future__ import annotations

import ast
import itertools
import json
import re
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).parents[1]
EXPECTED = ROOT / "tests/table_overlap_expected.json"
MIN_ENTRIES = 3
MIN_SHARED = 5
MIN_SHARE = 0.6
TEST_MODULE = re.compile(
    r"^#\[cfg\(test\)\]\s*\n(?:#\[[^\n]*\]\s*\n)*\s*mod\s+\w+\s*\{", re.MULTILINE
)
COMMENT = re.compile(r"//[^\n]*")
RUST_TABLE = re.compile(
    r"\b(?:const|static)\s+([A-Z][A-Z0-9_]*)\s*:[^=]*?=\s*&?\s*\[(.*?)\]\s*;", re.DOTALL
)
STRING = re.compile(r'"((?:\\.|[^"\\])*)"')


@dataclass(frozen=True)
class Table:
    """One table of string literals: its file, its name and its names."""

    path: str
    name: str
    names: frozenset[str]

    @property
    def key(self) -> str:
        return f"{self.path}:{self.name}"


def rust_tables(root: Path, path: Path) -> list[Table]:
    """The `const` and `static` arrays of a Rust file that hold only string literals."""
    text = path.read_text(encoding="utf-8")
    test_module = TEST_MODULE.search(text)
    text = COMMENT.sub("", text[: test_module.start()] if test_module else text)
    found = []
    for name, body in RUST_TABLE.findall(text):
        names = STRING.findall(body)
        rest = STRING.sub("", body).replace(",", "").split()
        if len(names) >= MIN_ENTRIES and not rest:
            found.append(Table(path.relative_to(root).as_posix(), name, frozenset(names)))
    return found


def python_tables(root: Path, path: Path) -> list[Table]:
    """The module-level tuples, lists and sets of a Python file that hold only strings."""
    found = []
    for node in ast.parse(path.read_text(encoding="utf-8")).body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target, value = node.targets[0], node.value
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            target, value = node.target, node.value
        else:
            continue
        if isinstance(value, ast.Call) and len(value.args) == 1:
            value = value.args[0]
        if not isinstance(target, ast.Name) or not isinstance(
            value, ast.Tuple | ast.List | ast.Set
        ):
            continue
        items = value.elts
        if len(items) >= MIN_ENTRIES and all(
            isinstance(item, ast.Constant) and isinstance(item.value, str) for item in items
        ):
            names = frozenset(str(item.value) for item in items if isinstance(item, ast.Constant))
            found.append(Table(path.relative_to(root).as_posix(), target.id, names))
    return found


def is_production_rust(relative: str) -> bool:
    return "/src/" in relative and not relative.endswith(("_tests.rs", "/tests.rs"))


def tables(root: Path) -> list[Table]:
    """Every table of the production code of `native/*/src` and `src/`."""
    found: list[Table] = []
    native = root / "native"
    for path in sorted(native.glob("*/src/**/*.rs")):
        if is_production_rust(path.relative_to(root).as_posix()):
            found += rust_tables(root, path)
    for path in sorted((root / "src").rglob("*.py")):
        found += python_tables(root, path)
    return found


def overlaps(found: list[Table]) -> dict[tuple[str, str], int]:
    """Each pair of tables of different files that share most names, with the shared count."""
    pairs = {}
    for one, other in itertools.combinations(sorted(found, key=lambda t: t.key), 2):
        shared = len(one.names & other.names)
        smaller = min(len(one.names), len(other.names))
        if one.path != other.path and shared >= MIN_SHARED and shared >= MIN_SHARE * smaller:
            pairs[(one.key, other.key)] = shared
    return pairs


def problems(found: dict[tuple[str, str], int], pinned: list[dict]) -> list[str]:
    """The difference between the overlaps and the pinned list: the list only shrinks."""
    known = {(entry["tables"][0], entry["tables"][1]): entry for entry in pinned}
    lines = [
        f"new overlap: {one} and {other} share {count} names: state them in one table"
        for (one, other), count in sorted(found.items())
        if (one, other) not in known
    ]
    for pair, entry in sorted(known.items()):
        count = found.get(pair)
        if count is None:
            lines.append(f"gone overlap: {pair[0]} and {pair[1]}: remove its entry")
        elif count > entry["shared"]:
            lines.append(f"grown overlap: {pair[0]} and {pair[1]} share {count} names")
        elif count < entry["shared"]:
            lines.append(f"shrunk overlap: {pair[0]} and {pair[1]}: lower its count to {count}")
        if not (isinstance(entry.get("issue"), int) and entry["issue"] > 0):
            lines.append(f"overlap without an issue number: {pair[0]} and {pair[1]}")
    return lines


def test_each_literal_table_of_main_is_one_table_or_a_visible_overlap() -> None:
    pinned = json.loads(EXPECTED.read_text(encoding="utf-8"))
    found = overlaps(tables(ROOT))
    assert problems(found, pinned) == []


def test_the_scan_reads_the_tables_of_both_languages() -> None:
    keys = {table.key for table in tables(ROOT)}
    assert "native/contract/src/component.rs:REQUIRED" in keys
    assert any(key.startswith("src/archkeel/") for key in keys)


def _write(root: Path, files: dict[str, str]) -> None:
    for name, text in files.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(text)


DOORS = '"exec", "eval", "compile", "globals", "locals", "vars"'


def test_a_copied_table_fails_and_a_derived_or_test_table_does_not(tmp_path: Path) -> None:
    _write(
        tmp_path,
        {
            "native/a/src/one.rs": f"pub const DOORS: &[&str] = &[{DOORS}];\n",
            "native/a/src/two.rs": f"const DOOR_KEYS: [&str; 6] = [{DOORS}];\n",
            "native/a/src/three.rs": "const SOME: &[&str] = &DOORS[..3];\n"
            f"#[cfg(test)]\nmod tests {{\n    const COPY: &[&str] = &[{DOORS}];\n}}\n",
            "native/a/src/four_tests.rs": f"const COPY: &[&str] = &[{DOORS}];\n",
            "native/a/src/five.rs": f"// const COPY: &[&str] = &[{DOORS}];\n",
            "src/pkg/doors.py": f"DOORS = frozenset({{{DOORS}}})\n",
        },
    )
    found = overlaps(tables(tmp_path))
    assert found == {
        ("native/a/src/one.rs:DOORS", "native/a/src/two.rs:DOOR_KEYS"): 6,
        ("native/a/src/one.rs:DOORS", "src/pkg/doors.py:DOORS"): 6,
        ("native/a/src/two.rs:DOOR_KEYS", "src/pkg/doors.py:DOORS"): 6,
    }


def test_a_small_or_a_partial_share_is_no_overlap(tmp_path: Path) -> None:
    _write(
        tmp_path,
        {
            "native/a/src/one.rs": 'const A: &[&str] = &["a", "b", "c", "d", "e", "f", "g", '
            '"h", "i"];\n',
            "native/a/src/two.rs": 'const B: &[&str] = &["a", "b", "c", "d", "x", "y", "z"];\n',
            "native/a/src/three.rs": 'const C: &[&str] = &["a", "b", "c", "d", "e", '
            '"p", "q", "r", "s"];\n',
        },
    )
    assert overlaps(tables(tmp_path)) == {}


def test_the_pin_only_shrinks_and_each_entry_names_an_issue() -> None:
    pair = ("x.rs:A", "y.rs:B")
    entry = {"tables": list(pair), "shared": 6, "issue": 1}
    assert problems({pair: 6}, [entry]) == []
    assert problems({pair: 7}, [entry]) == ["grown overlap: x.rs:A and y.rs:B share 7 names"]
    assert problems({pair: 5}, [entry]) == [
        "shrunk overlap: x.rs:A and y.rs:B: lower its count to 5"
    ]
    assert problems({}, [entry]) == ["gone overlap: x.rs:A and y.rs:B: remove its entry"]
    assert problems({pair: 6}, []) == [
        "new overlap: x.rs:A and y.rs:B share 6 names: state them in one table"
    ]
    assert problems({pair: 6}, [{**entry, "issue": None}]) == [
        "overlap without an issue number: x.rs:A and y.rs:B"
    ]
