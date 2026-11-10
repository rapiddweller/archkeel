# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-335: a crate name that the scan can hide is an edge or UNKNOWN, and never a PASS.

Consumer: `archkeel validate` with `[scan] language = "rust"`. The app crate does not require
`base_crate`, so each path that names it must FAIL or be UNKNOWN. Each list is a family of
sources that hid an edge in a review: a local name equal to a crate name, an import from the
crate itself, a name in a macro body or an attribute, and the safety net over those places.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from rust_repository import component, repository, statuses, validate

Capsys = pytest.CaptureFixture[str]


def _verdict(
    tmp_path: Path, binary: Path, capsys: Capsys, files: dict[str, str] | None = None, **kwargs: Any
) -> dict[str, Any]:
    return validate(repository(tmp_path, binary, files, **kwargs), capsys)


def _claims(result: dict[str, Any]) -> list[str]:
    return [item["unknown_claim"] for item in result["diagnostics"]]


OWN_IMPORT = [
    "use base_crate::base_crate;\npub fn run() { base_crate::make(); }\n",
    "use base_crate::{Other, base_crate};\npub fn run() { base_crate::make(); }\n",
    "use base_crate::Error as base_crate;\npub fn run() { base_crate::make(); }\n",
]
FOREIGN_IMPORT = [
    "use other::base_crate;\npub fn run() { base_crate::make(); }\n",
    "use other::Error as base_crate;\npub fn run() { base_crate::make(); }\n",
    "mod base_crate {}\nuse base_crate::base_crate;\npub fn run() { base_crate::make(); }\n",
]


@pytest.mark.parametrize("source", OWN_IMPORT, ids=range(len(OWN_IMPORT)))
def test_a_name_that_only_its_own_crate_provides_keeps_the_edge(
    tmp_path: Path, rust_binary: Path, capsys: Capsys, source: str
) -> None:
    parts = (component("base", "base_crate"), component("app", "app"))
    result = _verdict(
        tmp_path, rust_binary, capsys, {"crates/app/src/lib.rs": source}, components=parts
    )

    assert statuses(result)["REQUIRES"] == "FAIL"
    assert not any("A local name equals a crate name" in claim for claim in _claims(result))


@pytest.mark.parametrize("source", FOREIGN_IMPORT, ids=range(len(FOREIGN_IMPORT)))
def test_a_name_from_another_source_stays_unknown(
    tmp_path: Path, rust_binary: Path, capsys: Capsys, source: str
) -> None:
    parts = (component("base", "base_crate"), component("app", "app"))
    result = _verdict(
        tmp_path, rust_binary, capsys, {"crates/app/src/lib.rs": source}, components=parts
    )

    assert statuses(result).get("REQUIRES") != "PASS"
    assert any("A local name equals a crate name: base_crate" in c for c in _claims(result))


HIDDEN = [
    "pub fn run() { r#base_crate::make(); }\n",
    "use r#base_crate::make;\n",
    '#[serde(with = "base_crate")]\npub struct S;\n',
    '#[serde(crate = "base_crate")]\npub struct S;\n',
    "macro_rules! m { ($c:ident) => { $c::make() }; }\n"
    "pub fn run() { other::call!(base_crate); }\n",
    "#[other::attr(base_crate)]\npub struct S;\n",
    "#![doc = base_crate::readme!()]\n",
]
NET_ONLY = [
    "macro_rules! m { ($c:ident) => { $c::make() }; }\n"
    "pub fn run() { other::call!(base_crate); }\n",
    "#[other::attr(base_crate)]\npub struct S;\n",
    "pub fn run() { mac!(base_crate); }\n",
    'pub const A: &str = "base_crate::make";\n',
]
QUIET = [
    "pub fn run() { let base_crate = 1; let _ = base_crate + 1; }\n",
    "pub struct S { base_crate: String }\n",
    "pub fn run(base_crate: u8) -> u8 { base_crate }\n",
    "// base_crate in a comment\n/* base_crate */\npub fn run() {}\n",
    "/// base_crate::make in a doc comment\npub fn run() {}\n",
    '#[deprecated(note = "base_crate")]\npub fn run() {}\n',
]


@pytest.mark.parametrize("source", HIDDEN, ids=range(len(HIDDEN)))
def test_a_hidden_use_of_a_crate_name_is_an_edge_or_unknown_never_pass(
    tmp_path: Path, rust_binary: Path, capsys: Capsys, source: str
) -> None:
    parts = (component("base", "base_crate"), component("app", "app"))
    result = _verdict(
        tmp_path, rust_binary, capsys, {"crates/app/src/lib.rs": source}, components=parts
    )

    assert statuses(result).get("REQUIRES") != "PASS"


@pytest.mark.parametrize("source", NET_ONLY, ids=range(len(NET_ONLY)))
def test_a_crate_name_in_a_place_nobody_reads_is_unknown_with_the_net_reason(
    tmp_path: Path, rust_binary: Path, capsys: Capsys, source: str
) -> None:
    parts = (component("base", "base_crate"), component("app", "app"))
    result = _verdict(
        tmp_path, rust_binary, capsys, {"crates/app/src/lib.rs": source}, components=parts
    )

    reason = "The crate name base_crate appears in a place the collector does not read"
    assert any(reason in claim for claim in _claims(result))


@pytest.mark.parametrize("source", QUIET, ids=range(len(QUIET)))
def test_a_crate_name_in_a_comment_or_a_message_gives_no_unknown(
    tmp_path: Path, rust_binary: Path, capsys: Capsys, source: str
) -> None:
    parts = (component("base", "base_crate"), component("app", "app"))
    result = _verdict(
        tmp_path, rust_binary, capsys, {"crates/app/src/lib.rs": source}, components=parts
    )

    assert not any("appears in a place" in claim for claim in _claims(result))


def test_a_closure_parameter_named_like_a_crate_keeps_the_edge_of_its_path(
    tmp_path: Path, rust_binary: Path, capsys: Capsys
) -> None:
    parts = (component("base", "base_crate"), component("app", "app"))
    source = "pub fn run() { let f = |base_crate: u8| base_crate::x(base_crate); f(1); }\n"
    result = _verdict(
        tmp_path, rust_binary, capsys, {"crates/app/src/lib.rs": source}, components=parts
    )

    assert statuses(result).get("REQUIRES") != "PASS"
    assert not any("appears in a place" in claim for claim in _claims(result))
