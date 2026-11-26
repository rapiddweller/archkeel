# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The fixture of the resolved-call tests (AD-1185): modules `a` to `d`, `cargo run` counters."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any

import pytest
from rust_repository import CRATE_RULES, component, repository, rule, statuses, validate


def _forbid(target: str) -> dict[str, Any]:
    return rule(
        f"NO-A-TO-{target.upper()}",
        "forbidden_dependency",
        source="native.app.a",
        target=f"native.app.{target}",
        include_type_checking=True,
    )


COUNTER = """use std::sync::atomic::{{AtomicUsize, Ordering}};

static HITS: AtomicUsize = AtomicUsize::new(0);

pub fn hits() -> usize {{
    HITS.load(Ordering::SeqCst)
}}

{body}
"""
LIB = "pub mod a;\npub mod b;\npub mod c;\npub mod d;\npub mod t;\n"
T = "pub trait Tr {\n    fn m(&self) -> usize;\n}\n"
B = COUNTER.format(
    body="pub struct S;\n\nimpl S {\n    pub fn m(&self) -> usize {\n"
    "        HITS.fetch_add(1, Ordering::SeqCst)\n    }\n\n"
    "    pub fn next(&self) -> usize {\n        0\n    }\n}\n\n"
    "pub fn mk() -> impl FnMut(()) -> usize {\n    |_| HITS.fetch_add(1, Ordering::SeqCst)\n}"
)
D = COUNTER.format(
    body="pub struct U;\n\nimpl crate::t::Tr for U {\n    fn m(&self) -> usize {\n"
    "        HITS.fetch_add(1, Ordering::SeqCst)\n    }\n}"
)
C = (
    "pub fn make() -> crate::d::U {\n    crate::d::U\n}\n\n"
    "pub fn other() -> crate::b::S {\n    crate::b::S\n}\n\n"
    "pub fn units() -> Vec<crate::d::U> {\n    vec![crate::d::U]\n}\n\n"
    "pub fn others() -> Vec<crate::b::S> {\n    vec![crate::b::S]\n}\n\n"
    "pub fn pass() -> impl FnMut(()) -> usize {\n    crate::b::mk()\n}\n\n"
    "pub fn boxed() -> Vec<Box<dyn crate::t::Tr>> {\n    vec![Box::new(crate::d::U)]\n}\n"
)
A_D = (
    "use crate::t::Tr;\n\npub fn run() {\n    let _held = crate::c::other();\n"
    "    let make = crate::c::make;\n    make().m();\n}\n"
)
A_CLOSURE_B = (
    "pub fn run() {\n    let _held = crate::c::other();\n"
    "    std::iter::once(()).map(crate::c::pass()).next();\n}\n"
)
A_CLOSURE_A = (
    "pub fn run() {\n    let _held = crate::c::other();\n"
    "    std::iter::once(()).map(|_| 1usize).next();\n}\n"
)
A_B = "pub fn run() {\n    crate::c::other().m();\n}\n"
A_DYN = (
    "use crate::t::Tr;\n\npub fn run() {\n    let _held = crate::c::other();\n"
    "    for one in crate::c::boxed().iter() {\n        one.m();\n    }\n}\n"
)
A_FEATURE = (
    "use crate::t::Tr;\n\npub fn run() {\n    let _held = crate::c::other();\n"
    '    #[cfg(feature = "hot")]\n    let make = crate::c::other;\n'
    '    #[cfg(not(feature = "hot"))]\n    let make = crate::c::make;\n    make().m();\n}\n'
)
MANIFEST = (
    '[package]\nname = "app"\nversion = "0.0.0"\nedition = "2021"\n'
    '[features]\nhot = []\n[dependencies]\nbase-crate = { path = "../base" }\n'
)
ORACLE = {
    "oracle/Cargo.toml": '[package]\nname = "oracle"\nversion = "0.0.0"\nedition = "2021"\n'
    '[dependencies]\napp = { path = "../crates/app" }\n[workspace]\n',
    "oracle/src/main.rs": "fn main() {\n    app::a::run();\n"
    '    println!("{} {}", app::b::hits(), app::d::hits());\n}\n',
}


def _sources(a: str, manifest: str | None = None) -> dict[str, str]:
    files = {"lib.rs": LIB, "t.rs": T, "b.rs": B, "d.rs": D, "c.rs": C, "a.rs": a}
    found = {f"crates/app/src/{name}": text for name, text in files.items()}
    if manifest:
        found["crates/app/Cargo.toml"] = manifest
    return {**found, **ORACLE}


def _parts() -> tuple[dict[str, Any], ...]:
    def part(label: str, module: str, needs: tuple[str, ...]) -> dict[str, Any]:
        return {**component(label, "app", needs), "packages": [], "exact_modules": [module]}

    return (
        component("base", "base_crate"),
        {
            **component("root", "app", ("base", "a", "b", "c", "d", "t")),
            "packages": [],
            "exact_modules": ["native.app", "native.app.cargo_toml"],
        },
        part("a", "native.app.a", ("c", "t")),
        part("b", "native.app.b", ()),
        part("c", "native.app.c", ("b", "d", "t")),
        part("d", "native.app.d", ("t",)),
        part("t", "native.app.t", ()),
    )


def _scan(
    tmp_path: Path,
    core: Path,
    monkeypatch: pytest.MonkeyPatch,
    a: str,
    manifest: str | None = None,
) -> tuple[Path, dict[str, str]]:
    monkeypatch.setenv("ARCHKEEL_FACTS_CACHE", str(tmp_path / "cache"))
    root = repository(
        tmp_path / "repo",
        core,
        _sources(a, manifest),
        components=_parts(),
        rules=(*CRATE_RULES[1:], _forbid("b"), _forbid("d")),
        type_reach=True,
    )
    return root, statuses(validate(root))


def _cargo_run(root: Path) -> str:
    env = {**os.environ, "CARGO_TARGET_DIR": str(root.parent / "target")}
    manifest = root / "oracle/Cargo.toml"
    command = ["cargo", "run", "--quiet", "--offline", "--manifest-path", str(manifest)]
    done = subprocess.run(command, capture_output=True, text=True, env=env, check=False)
    assert done.returncode == 0, done.stderr
    return done.stdout.strip()


def _hit0_scan(
    tmp_path: Path,
    core: Path,
    monkeypatch: pytest.MonkeyPatch,
    files: dict[str, str],
) -> tuple[Path, dict[str, str]]:
    """The fixture with `b::hit0` and the given `c`, `d` and `a`."""
    hit0 = "\npub fn hit0() {\n    HITS.fetch_add(1, Ordering::SeqCst);\n}\n"
    monkeypatch.setenv("ARCHKEEL_FACTS_CACHE", str(tmp_path / "cache"))
    root = repository(
        tmp_path / "repo",
        core,
        {**_sources(A_CLOSURE_B), "crates/app/src/b.rs": B + hit0, **files},
        components=_parts(),
        rules=(*CRATE_RULES[1:], _forbid("b"), _forbid("d")),
        type_reach=True,
    )
    return root, statuses(validate(root))
