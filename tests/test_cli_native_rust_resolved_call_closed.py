# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-1185: a resolved call closes a candidate only when nothing that the call touches can run `b`.

Each test hides a callback of `b` in another place: a closure, a function pointer, a field, an
associated type, a returned value, a `Deref` of the receiver, an erased pointer, a `Waker`.
The counter
that `cargo run` prints is `1 0` (`b` runs), so the candidate must stay. The control closes it.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from rust_repository import CRATE_RULES, repository, statuses, validate
from rust_resolved_support import (
    A_CLOSURE_A,
    A_CLOSURE_B,
    COUNTER,
    B,
    C,
    _cargo_run,
    _forbid,
    _hit0_scan,
    _parts,
    _scan,
    _sources,
)
from rustc_dev_support import needs_rustc_dev

pytestmark = [
    pytest.mark.skipif(shutil.which("cargo") is None, reason="cargo is the oracle"),
    needs_rustc_dev,
]


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


def test_a_receiver_that_a_closure_makes_does_not_stop_the_facts(
    tmp_path: Path, release_core: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A closure call in the receiver has no function signature: the driver must not fail on it."""
    files = {
        "crates/app/src/a.rs": "use crate::t::Tr;\n\npub fn run() {\n"
        "    let _held = crate::c::other();\n"
        "    let make = || crate::c::make();\n    make().m();\n}\n",
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
    result = validate(root)
    reasons = [gap["reason"] for gap in result["frame"]["collection_gaps"]]
    assert not any("type-reach facts are unavailable" in reason for reason in reasons), reasons
    assert _cargo_run(root) == "0 1"


def test_an_erased_callback_pointer_keeps_the_gap(
    tmp_path: Path, release_core: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`d::U` holds `*const ()`: its type is erased, and `m` calls the function of `b` behind it."""
    erased = COUNTER.format(
        body="pub struct U {\n    pub callback: *const (),\n}\n\n"
        "impl U {\n    pub fn m(&self) -> usize {\n"
        "        let call: fn() = unsafe { std::mem::transmute(self.callback) };\n"
        "        call();\n        0\n    }\n}"
    )
    files = {
        "crates/app/src/d.rs": erased,
        "crates/app/src/c.rs": "pub fn other() -> crate::b::S {\n    crate::b::S\n}\n\n"
        "pub fn make() -> crate::d::U {\n"
        "    crate::d::U { callback: crate::b::hit0 as fn() as *const () }\n}\n",
        "crates/app/src/a.rs": "pub fn run() {\n    let _held = crate::c::other();\n"
        "    let make = crate::c::make;\n    make().m();\n}\n",
    }
    root, found = _hit0_scan(tmp_path, release_core, monkeypatch, files)
    assert _cargo_run(root) == "1 0", "the erased function of `b` runs"
    assert found["NO-A-TO-B"] != "PASS"


@pytest.mark.parametrize(
    ("fields", "store", "load"),
    [
        (
            "pub padding: Vec<u8>,\n    pub callback: *const u8,",
            "padding: Vec::new(),\n        callback: crate::b::hit0 as fn() as *const u8,",
            "self.callback",
        ),
        (
            "pub callback: std::ptr::NonNull<()>,",
            "callback: std::ptr::NonNull::new(crate::b::hit0 as fn() as *mut ()).unwrap(),",
            "self.callback.as_ptr()",
        ),
        (
            "pub callback: std::ptr::NonNull<u8>,",
            "callback: std::ptr::NonNull::new(crate::b::hit0 as fn() as *mut u8).unwrap(),",
            "self.callback.as_ptr()",
        ),
    ],
    ids=["a bytes buffer beside an erased pointer", "NonNull of unit", "NonNull of bytes"],
)
def test_an_erased_pointer_beside_or_inside_a_container_keeps_the_gap(
    tmp_path: Path,
    release_core: Path,
    monkeypatch: pytest.MonkeyPatch,
    fields: str,
    store: str,
    load: str,
) -> None:
    """A container keeps bytes behind raw pointers. That does not clear the pointer of the user."""
    erased = COUNTER.format(
        body=f"pub struct U {{\n    {fields}\n}}\n\n"
        "impl U {\n    pub fn m(&self) -> usize {\n"
        f"        let call: fn() = unsafe {{ std::mem::transmute({load}) }};\n"
        "        call();\n        0\n    }\n}"
    )
    files = {
        "crates/app/src/d.rs": erased,
        "crates/app/src/c.rs": "pub fn other() -> crate::b::S {\n    crate::b::S\n}\n\n"
        f"pub fn make() -> crate::d::U {{\n    crate::d::U {{\n        {store}\n    }}\n}}\n",
        "crates/app/src/a.rs": "pub fn run() {\n    let _held = crate::c::other();\n"
        "    let make = crate::c::make;\n    make().m();\n}\n",
    }
    root, found = _hit0_scan(tmp_path, release_core, monkeypatch, files)
    assert _cargo_run(root) == "1 0", "the erased function of `b` runs"
    assert found["NO-A-TO-B"] != "PASS"


def test_an_argument_adjustment_that_runs_a_callback_of_b_keeps_the_gap(
    tmp_path: Path, release_core: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`make().n(&arg())` coerces `&Wrapper` to `&str` with `Deref`, which calls `b::hit0`."""
    deref = COUNTER.format(
        body="pub struct U;\n\n"
        "impl U {\n    pub fn n(&self, _text: &str) -> usize {\n        0\n    }\n}\n\n"
        "pub struct Wrapper {\n    pub inner: String,\n    pub callback: fn(),\n}\n\n"
        "impl std::ops::Deref for Wrapper {\n    type Target = str;\n\n"
        "    fn deref(&self) -> &str {\n        (self.callback)();\n        &self.inner\n    }\n}"
    )
    hit0 = "\npub fn hit0() {\n    HITS.fetch_add(1, Ordering::SeqCst);\n}\n"
    in_b = "\nimpl S {\n    pub fn n(&self, _text: &str) -> usize {\n        1\n    }\n}\n"
    files = {
        "crates/app/src/b.rs": B + hit0 + in_b,
        "crates/app/src/d.rs": deref,
        "crates/app/src/c.rs": "pub fn other() -> crate::b::S {\n    crate::b::S\n}\n\n"
        "pub fn make() -> crate::d::U {\n    crate::d::U\n}\n\n"
        "pub fn arg() -> crate::d::Wrapper {\n    crate::d::Wrapper {\n"
        "        inner: String::new(),\n        callback: crate::b::hit0,\n    }\n}\n",
        "crates/app/src/a.rs": "pub fn run() {\n    let _held = crate::c::other();\n"
        "    let make = crate::c::make;\n    let arg = crate::c::arg;\n"
        "    make().n(&arg());\n}\n",
    }
    root, found = _hit0_scan(tmp_path, release_core, monkeypatch, files)
    assert _cargo_run(root) == "1 0", "the deref of the argument runs the function of `b`"
    assert found["NO-A-TO-B"] != "PASS"


def test_a_std_adapter_with_a_closure_of_the_caller_closes_the_candidate(
    tmp_path: Path, release_core: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The control: the closure is written in `a`, so no type argument can run code of `b`."""
    root, found = _scan(tmp_path, release_core, monkeypatch, A_CLOSURE_A)
    assert _cargo_run(root) == "0 0", "nothing of `b` runs"
    assert found["NO-A-TO-B"] == "PASS"
