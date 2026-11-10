# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-351: the Rust collector reports definitions and the host reads them as symbols.

Consumer: the report of a Rust crate (`ir/source_graph.py`). A `pub` item is `public`; `pub(crate)`
and `pub(super)` are `package`; the rest is `private`. A trait is an interface, a `macro_rules!`
is a macro, and an `impl` gives methods to its type. The inventory is never complete (a macro can
generate items, and an `impl` can sit in another module), so the graph says `partial`.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest import mock

import pytest
from collector_pin import pin_of
from rust_repository import repository, statuses, validate

from archkeel import cli
from archkeel.cli import main
from archkeel.ir.architecture_graph import ArchitectureGraph, CoverageStatus, EntityKind
from archkeel.ir.codec import decode_canonical_model, parse_observation
from archkeel.ir.source_graph import observed_graph

SOURCE = """\
pub trait Shape { fn area(&self) -> u8; }
pub struct Square(u8);
pub(crate) enum Mode { Fast, Slow }
impl Square {
    pub fn new(side: u8) -> Square { Square(side) }
    fn secret(&self) -> u8 { self.0 }
}
impl Shape for Square { fn area(&self) -> u8 { self.secret() } }
pub(super) const LIMIT: u8 = 3;
static COUNT: u8 = 0;
pub type Side = u8;
macro_rules! local { () => {}; }
#[macro_export]
macro_rules! shown { () => {}; }
make_items! { pub struct Generated; }
fn helper() {}
"""


def graph(root: Path, capsys: pytest.CaptureFixture[str], binary: Path) -> ArchitectureGraph:
    """The observed graph of the fixture, built from the `architecture.json` of `report`."""
    capsys.readouterr()
    build = cli.observer_for
    with mock.patch.object(
        cli, "observer_for", lambda *a, **k: build(*a, **k, pinned_digest=pin_of(str(binary)))
    ):
        main(["report", "--root", str(root), "--output", str(root / "out/architecture.json")])
    saved = json.loads((root / "out/architecture.json").read_text())
    return observed_graph(parse_observation(decode_canonical_model(saved)))


@pytest.fixture
def repo(tmp_path: Path, rust_binary: Path) -> Path:
    return repository(tmp_path, rust_binary, files={"crates/base/src/lib.rs": SOURCE})


def test_each_definition_is_a_symbol_with_its_kind_and_visibility(
    repo: Path, capsys: pytest.CaptureFixture[str], rust_binary: Path
) -> None:
    found = {
        entity.qualified_name.removeprefix("native.base_crate."): (
            entity.kind,
            entity.visibility.kind.value,
        )
        for entity in graph(repo, capsys, rust_binary).entities
        if entity.qualified_name.startswith("native.base_crate.")
    }
    assert found["Shape"] == (EntityKind.INTERFACE, "public")
    assert found["Shape.area"] == (EntityKind.METHOD, "public")
    assert found["Square"] == (EntityKind.CLASS, "public")
    assert found["Square.new"] == (EntityKind.METHOD, "public")
    assert found["Square.secret"] == (EntityKind.METHOD, "private")
    assert found["Mode"] == (EntityKind.ENUM, "package")
    assert found["LIMIT"] == (EntityKind.CONSTANT, "package")
    assert found["COUNT"] == (EntityKind.CONSTANT, "private")
    assert found["Side"] == (EntityKind.TYPE_ALIAS, "public")
    assert found["local"] == (EntityKind.MACRO, "package")
    assert found["shown"] == (EntityKind.MACRO, "public")
    assert found["helper"] == (EntityKind.FUNCTION, "private")


def test_an_item_that_a_macro_generates_is_not_invented(
    repo: Path, capsys: pytest.CaptureFixture[str], rust_binary: Path
) -> None:
    names = {entity.qualified_name for entity in graph(repo, capsys, rust_binary).entities}
    assert "native.base_crate.Generated" not in names
    assert "native.base_crate.Square.area" not in names, "a trait impl declares no method"


def test_the_graph_says_that_the_symbol_inventory_is_partial(
    repo: Path, capsys: pytest.CaptureFixture[str], rust_binary: Path
) -> None:
    coverage = [
        item
        for item in graph(repo, capsys, rust_binary).coverage
        if EntityKind.CLASS in item.entity_kinds
    ]
    assert coverage
    assert {item.status for item in coverage} == {CoverageStatus.PARTIAL}


def test_the_rules_are_decided_with_the_symbols_section(
    tmp_path: Path, rust_binary: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # An exported macro is UNKNOWN for its edges (AD-335), so this source exports none.
    source = SOURCE.replace("#[macro_export]\n", "")
    root = repository(tmp_path, rust_binary, files={"crates/base/src/lib.rs": source})
    result: dict[str, Any] = validate(root, capsys)
    assert result["diagnostics"] == []
    assert result["exit_code"] == 0
    assert set(statuses(result).values()) == {"PASS"}
