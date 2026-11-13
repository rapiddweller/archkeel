# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The H1–H5 compiler rules apply to source families, not only review examples."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from python_compile_review_families import RULES, families, outcome
from test_collector_native_python_parse import _minor, _native, _write

ROOT = Path(__file__).parents[1]
SOURCES = families()
PINS = json.loads((ROOT / "tests/python_compile_review_families.json").read_text())


def compare(binary: Path, root: Path) -> dict[str, dict[str, object]]:
    sources = {name: source for cases in SOURCES.values() for name, source in cases.items()}
    rels = _write(root, {f"{name}.py": source for name, source in sources.items()})
    found = _native(binary, root, rels)
    return {
        name: {"compiler": outcome(source), "native": found[f"{name}.py"]}
        for name, source in sources.items()
    }


@pytest.fixture(scope="module")
def family_results(python_dump_binary: Path, tmp_path_factory: pytest.TempPathFactory):
    return compare(python_dump_binary, tmp_path_factory.mktemp("review-families"))


@pytest.mark.parametrize("family", RULES)
def test_a_review_rule_holds_in_each_source_position(family: str, family_results) -> None:
    assert set(PINS) == {name for cases in SOURCES.values() for name in cases}
    rows = {name: family_results[name] for name in SOURCES[family]}
    for name, row in rows.items():
        assert row["compiler"] == PINS[name][str(_minor())], (name, SOURCES[family][name])
    unsafe = [
        name for name, row in rows.items() if row["compiler"] is not None and row["native"] is None
    ]
    stricter = [
        (name, row["native"])
        for name, row in rows.items()
        if row["compiler"] is None and row["native"] is not None
    ]
    assert not unsafe, (family, RULES[family], unsafe)
    assert not stricter, (family, RULES[family], stricter)


@pytest.mark.parametrize(
    ("source", "accepted", "reason"),
    [
        (f"x = '\\N{{TANGUT IDEOGRAPH-{point:X}}}'", {13, 14}, "Got unexpected unicode")
        for point in (0x17000, 0x17FFF, 0x187F7)
    ]
    + [
        (
            "x = f'{a:\n}'",
            {12},
            "f-string: newlines are not allowed in format specifiers when using single quotes",
        )
    ],
)
def test_the_two_remaining_parser_false_refusal_classes_are_named(
    source: str, accepted: set[int], reason: str, python_dump_binary: Path, tmp_path: Path
) -> None:
    assert (outcome(source) is None) == (_minor() in accepted)
    found = _native(python_dump_binary, tmp_path, _write(tmp_path, {"limit.py": source}))[
        "limit.py"
    ]
    assert found is not None and found["message"] == reason
