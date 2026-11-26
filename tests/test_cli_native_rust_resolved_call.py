# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-1185: a method call that rustc resolves is an edge and closes the other receiver candidates.

`c::make()` gives a `d::U`. `a` calls it through a local, so the scan cannot type it.
The scan reads no types, so `a -> b` was a held pair. The compiler resolves the call to the `m`
of `d`: the counter that `cargo run` prints shows that only `d` runs. A call that the compiler
cannot resolve (a trait object) keeps the gap. So does a call that a configuration changes.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest
from rust_repository import CRATE_RULES, component, repository, rule, statuses, validate
from rustc_dev_support import needs_rustc_dev

pytestmark = [
    pytest.mark.skipif(shutil.which("cargo") is None, reason="cargo is the oracle"),
    needs_rustc_dev,
]


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


def test_a_resolved_call_closes_the_other_candidate_and_is_a_proven_use(
    tmp_path: Path, release_core: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, found = _scan(tmp_path, release_core, monkeypatch, A_D)
    assert _cargo_run(root) == "0 1", "only the `m` of `d` runs"
    assert found["NO-A-TO-B"] == "PASS", "the compiler excludes `b`"
    assert found["NO-A-TO-D"] == "FAIL", "the resolved call is a use of `d`"


def test_a_call_that_runs_the_candidate_is_a_proven_use_of_it(
    tmp_path: Path, release_core: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, found = _scan(tmp_path, release_core, monkeypatch, A_B)
    assert _cargo_run(root) == "1 0", "the `m` of `b` runs"
    assert found["NO-A-TO-B"] == "FAIL"
    assert found["NO-A-TO-D"] == "PASS", "the compiler excludes `d`"


def test_a_call_through_a_trait_object_is_not_resolved_and_keeps_both_gaps(
    tmp_path: Path, release_core: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, found = _scan(tmp_path, release_core, monkeypatch, A_DYN)
    assert _cargo_run(root) == "0 1", "the impl of `d` runs through the vtable"
    assert found["NO-A-TO-B"] == "UNKNOWN"
    assert found["NO-A-TO-D"] != "PASS"


def test_a_call_that_a_feature_changes_keeps_the_gap(
    tmp_path: Path, release_core: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Without the feature `d` runs, with it `b` runs: no callee holds in every configuration."""
    _, found = _scan(tmp_path, release_core, monkeypatch, A_FEATURE, MANIFEST)
    assert found["NO-A-TO-B"] != "PASS"
    assert found["NO-A-TO-D"] != "PASS"


def test_a_std_adapter_that_runs_a_closure_of_b_keeps_the_gap(
    tmp_path: Path, release_core: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`Map::next` is in `core`, but its type argument is a closure of `b`: `b` runs."""
    root, found = _scan(tmp_path, release_core, monkeypatch, A_CLOSURE_B)
    assert _cargo_run(root) == "1 0", "the closure of `b` runs"
    assert found["NO-A-TO-B"] != "PASS"


def test_a_std_adapter_with_a_function_pointer_into_b_keeps_the_gap(
    tmp_path: Path, release_core: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A function pointer hides its target: the type argument is `fn(()) -> usize`, and `b` runs."""
    closure = (
        "pub fn mk() -> impl FnMut(()) -> usize {\n    |_| HITS.fetch_add(1, Ordering::SeqCst)\n}"
    )
    pointer = (
        "fn hit(_: ()) -> usize {\n    HITS.fetch_add(1, Ordering::SeqCst)\n}\n\n"
        "pub fn mk() -> fn(()) -> usize {\n    hit\n}"
    )
    assert closure in B
    files = {
        "crates/app/src/b.rs": B.replace(closure, pointer),
        "crates/app/src/c.rs": C.replace("-> impl FnMut(()) -> usize", "-> fn(()) -> usize"),
    }
    monkeypatch.setenv("ARCHKEEL_FACTS_CACHE", str(tmp_path / "cache"))
    root = repository(
        tmp_path / "repo",
        release_core,
        {**_sources(A_CLOSURE_B), **files},
        components=_parts(),
        rules=(*CRATE_RULES[1:], _forbid("b"), _forbid("d")),
        type_reach=True,
    )
    assert _cargo_run(root) == "1 0", "the function of `b` runs"
    assert statuses(validate(root))["NO-A-TO-B"] != "PASS"


def test_a_std_adapter_over_a_type_that_holds_a_callback_into_b_keeps_the_gap(
    tmp_path: Path, release_core: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The callback is a function pointer in a field of `d::Iter`; no type argument shows it."""
    iterator = COUNTER.format(
        body="pub struct Iter {\n    pub callback: fn(()) -> usize,\n    pub done: bool,\n}\n\n"
        "impl Iterator for Iter {\n    type Item = usize;\n\n"
        "    fn next(&mut self) -> Option<usize> {\n"
        "        if self.done {\n            return None;\n        }\n"
        "        self.done = true;\n        Some((self.callback)(()))\n    }\n}"
    )
    files = {
        "crates/app/src/d.rs": iterator,
        "crates/app/src/b.rs": B
        + "\npub fn hit(_: ()) -> usize {\n    HITS.fetch_add(1, Ordering::SeqCst)\n}\n",
        "crates/app/src/c.rs": "pub fn other() -> crate::b::S {\n    crate::b::S\n}\n\n"
        "pub fn make() -> crate::d::Iter {\n"
        "    crate::d::Iter { callback: crate::b::hit, done: false }\n}\n",
        "crates/app/src/a.rs": "pub fn run() {\n    let _held = crate::c::other();\n"
        "    crate::c::make().map(|x| x).next();\n}\n",
    }
    monkeypatch.setenv("ARCHKEEL_FACTS_CACHE", str(tmp_path / "cache"))
    root = repository(
        tmp_path / "repo",
        release_core,
        {**_sources(A_CLOSURE_B), **files},
        components=_parts(),
        rules=(*CRATE_RULES[1:], _forbid("b"), _forbid("d")),
        type_reach=True,
    )
    assert _cargo_run(root) == "1 0", "the callback of `b` runs"
    assert statuses(validate(root))["NO-A-TO-B"] != "PASS"


def test_an_inherent_method_of_a_type_that_holds_a_callback_into_b_keeps_the_gap(
    tmp_path: Path, release_core: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No generics: the receiver is no type argument, but a field holds the callback."""
    iterator = COUNTER.format(
        body="pub struct Iter {\n    pub callback: fn(()) -> usize,\n    pub done: bool,\n}\n\n"
        "impl Iter {\n"
        "    pub fn next(&mut self) -> Option<usize> {\n"
        "        if self.done {\n            return None;\n        }\n"
        "        self.done = true;\n        Some((self.callback)(()))\n    }\n}"
    )
    files = {
        "crates/app/src/d.rs": iterator,
        "crates/app/src/b.rs": B
        + "\npub fn hit(_: ()) -> usize {\n    HITS.fetch_add(1, Ordering::SeqCst)\n}\n",
        "crates/app/src/c.rs": "pub fn other() -> crate::b::S {\n    crate::b::S\n}\n\n"
        "pub fn make() -> crate::d::Iter {\n"
        "    crate::d::Iter { callback: crate::b::hit, done: false }\n}\n",
        "crates/app/src/a.rs": "pub fn run() {\n    let _held = crate::c::other();\n"
        "    let make = crate::c::make;\n    make().next();\n}\n",
    }
    monkeypatch.setenv("ARCHKEEL_FACTS_CACHE", str(tmp_path / "cache"))
    root = repository(
        tmp_path / "repo",
        release_core,
        {**_sources(A_CLOSURE_B), **files},
        components=_parts(),
        rules=(*CRATE_RULES[1:], _forbid("b"), _forbid("d")),
        type_reach=True,
    )
    assert _cargo_run(root) == "1 0", "the callback of `b` runs"
    assert statuses(validate(root))["NO-A-TO-B"] != "PASS"


def test_a_method_of_a_std_type_that_holds_a_callback_into_b_keeps_the_gap(
    tmp_path: Path, release_core: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`Waker` holds a vtable of functions of `b` in a field of a std type."""
    waker = (
        "\nfn vtable_clone(data: *const ()) -> std::task::RawWaker {\n"
        "    std::task::RawWaker::new(data, &VTABLE)\n}\n\n"
        "fn vtable_wake(_: *const ()) {\n    HITS.fetch_add(1, Ordering::SeqCst);\n}\n\n"
        "fn vtable_drop(_: *const ()) {}\n\n"
        "static VTABLE: std::task::RawWakerVTable =\n"
        "    std::task::RawWakerVTable::new(\n"
        "        vtable_clone, vtable_wake, vtable_wake, vtable_drop\n    );\n\n"
        "pub fn waker() -> std::task::Waker {\n"
        "    let raw = std::task::RawWaker::new(std::ptr::null(), &VTABLE);\n"
        "    unsafe { std::task::Waker::from_raw(raw) }\n}\n"
    )
    files = {
        "crates/app/src/b.rs": B.replace("pub fn next(&self)", "pub fn wake(&self)") + waker,
        "crates/app/src/c.rs": "pub fn other() -> crate::b::S {\n    crate::b::S\n}\n\n"
        "pub fn make() -> std::task::Waker {\n    crate::b::waker()\n}\n",
        "crates/app/src/a.rs": "pub fn run() {\n    let _held = crate::c::other();\n"
        "    let make = crate::c::make;\n    make().wake();\n}\n",
    }
    monkeypatch.setenv("ARCHKEEL_FACTS_CACHE", str(tmp_path / "cache"))
    root = repository(
        tmp_path / "repo",
        release_core,
        {**_sources(A_CLOSURE_B), **files},
        components=_parts(),
        rules=(*CRATE_RULES[1:], _forbid("b"), _forbid("d")),
        type_reach=True,
    )
    assert _cargo_run(root) == "1 0", "the vtable function of `b` runs"
    assert statuses(validate(root))["NO-A-TO-B"] != "PASS"


def test_a_std_adapter_whose_item_type_holds_a_callback_into_b_keeps_the_gap(
    tmp_path: Path, release_core: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`Peekable<Outer>` holds `Outer::Item`, an associated type: its drop calls `b`."""
    outer = COUNTER.format(
        body="pub struct Inner {\n    pub callback: fn(),\n}\n\n"
        "impl Drop for Inner {\n    fn drop(&mut self) {\n        (self.callback)();\n    }\n}\n\n"
        "pub struct Outer {\n    pub done: bool,\n    pub callback: fn(),\n}\n\n"
        "impl Iterator for Outer {\n    type Item = Inner;\n\n"
        "    fn next(&mut self) -> Option<Inner> {\n"
        "        if self.done {\n            return None;\n        }\n"
        "        self.done = true;\n        Some(Inner { callback: self.callback })\n    }\n}"
    )
    files = {
        "crates/app/src/d.rs": outer,
        "crates/app/src/b.rs": B
        + "\npub fn hit0() {\n    HITS.fetch_add(1, Ordering::SeqCst);\n}\n",
        "crates/app/src/c.rs": "pub fn other() -> crate::b::S {\n    crate::b::S\n}\n\n"
        "pub fn make() -> std::iter::Peekable<crate::d::Outer> {\n"
        "    crate::d::Outer { done: false, callback: crate::b::hit0 }.peekable()\n}\n",
        "crates/app/src/a.rs": "pub fn run() {\n    let _held = crate::c::other();\n"
        "    let make = crate::c::make;\n    make().next();\n}\n",
    }
    monkeypatch.setenv("ARCHKEEL_FACTS_CACHE", str(tmp_path / "cache"))
    root = repository(
        tmp_path / "repo",
        release_core,
        {**_sources(A_CLOSURE_B), **files},
        components=_parts(),
        rules=(*CRATE_RULES[1:], _forbid("b"), _forbid("d")),
        type_reach=True,
    )
    assert _cargo_run(root) == "1 0", "the drop of the item runs the function of `b`"
    assert statuses(validate(root))["NO-A-TO-B"] != "PASS"


def test_a_type_that_grows_without_end_is_walked_with_a_bound(
    tmp_path: Path, release_core: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`R<T>` holds `R<Vec<T>>`: the walk ends, and the scan gives a verdict."""
    grows = (
        "pub struct R<T> {\n    pub value: T,\n    pub next: Option<Box<R<Vec<T>>>>,\n}\n\n"
        "impl<T> R<T> {\n    pub fn len(&self) -> usize {\n        1\n    }\n}\n"
    )
    files = {
        "crates/app/src/c.rs": C + grows,
        "crates/app/src/a.rs": "pub fn run() {\n    let _held = crate::c::other();\n"
        "    let r = crate::c::R { value: 1u32, next: None };\n    r.len();\n}\n",
    }
    monkeypatch.setenv("ARCHKEEL_FACTS_CACHE", str(tmp_path / "cache"))
    root = repository(
        tmp_path / "repo",
        release_core,
        {**_sources(A_CLOSURE_B), **files},
        components=_parts(),
        rules=(*CRATE_RULES[1:], _forbid("b"), _forbid("d")),
        type_reach=True,
    )
    assert "NO-A-TO-B" in statuses(validate(root))


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


def test_a_receiver_adjustment_that_runs_a_callback_of_b_keeps_the_gap(
    tmp_path: Path, release_core: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`make().m()` goes through `Wrapper::deref`, which calls `b::hit0` before it returns `&U`."""
    deref = COUNTER.format(
        body="pub struct U;\n\nimpl U {\n    pub fn m(&self) -> usize {\n        0\n    }\n}\n\n"
        "pub struct Wrapper {\n    pub inner: U,\n    pub callback: fn(),\n}\n\n"
        "impl std::ops::Deref for Wrapper {\n    type Target = U;\n\n"
        "    fn deref(&self) -> &U {\n        (self.callback)();\n        &self.inner\n    }\n}"
    )
    files = {
        "crates/app/src/d.rs": deref,
        "crates/app/src/c.rs": "pub fn other() -> crate::b::S {\n    crate::b::S\n}\n\n"
        "pub fn make() -> crate::d::Wrapper {\n"
        "    crate::d::Wrapper { inner: crate::d::U, callback: crate::b::hit0 }\n}\n",
        "crates/app/src/a.rs": "pub fn run() {\n    let _held = crate::c::other();\n"
        "    let make = crate::c::make;\n    make().m();\n}\n",
    }
    root, found = _hit0_scan(tmp_path, release_core, monkeypatch, files)
    assert _cargo_run(root) == "1 0", "the deref of `d` runs the function of `b`"
    assert found["NO-A-TO-B"] != "PASS"


def test_a_method_that_returns_a_callback_of_b_keeps_the_gap(
    tmp_path: Path, release_core: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`d::U::m` returns a function pointer into `b`, and `a` runs it."""
    returns = COUNTER.format(
        body="pub struct U {\n    pub callback: fn(),\n}\n\n"
        "impl U {\n    pub fn m(&self) -> fn() {\n        self.callback\n    }\n}"
    )
    files = {
        "crates/app/src/d.rs": returns,
        "crates/app/src/c.rs": "pub fn other() -> crate::b::S {\n    crate::b::S\n}\n\n"
        "pub fn make() -> crate::d::U {\n    crate::d::U { callback: crate::b::hit0 }\n}\n",
        "crates/app/src/a.rs": "pub fn run() {\n    let _held = crate::c::other();\n"
        "    let make = crate::c::make;\n    make().m()();\n}\n",
    }
    root, found = _hit0_scan(tmp_path, release_core, monkeypatch, files)
    assert _cargo_run(root) == "1 0", "the returned function of `b` runs"
    assert found["NO-A-TO-B"] != "PASS"


def test_a_std_adapter_with_a_closure_of_the_caller_closes_the_candidate(
    tmp_path: Path, release_core: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The control: the closure is written in `a`, so no type argument can run code of `b`."""
    root, found = _scan(tmp_path, release_core, monkeypatch, A_CLOSURE_A)
    assert _cargo_run(root) == "0 0", "nothing of `b` runs"
    assert found["NO-A-TO-B"] == "PASS"
