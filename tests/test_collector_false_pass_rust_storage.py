# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Compiler-backed storage controls for erased destructor dispatch (#1811)."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest
from core_support import NATIVE
from corpus_support import commit_tree
from rust_repository import CRATE_RULES, component, repository, rule, statuses, validate

pytestmark = pytest.mark.skipif(shutil.which("cargo") is None, reason="rustc is the oracle")

NO_A_TO_B = rule(
    "NO-A-TO-B",
    "forbidden_dependency",
    source="native.app.a",
    target="native.app.b",
    include_type_checking=True,
)

HOOK_STORE = """
    use std::sync::{Mutex, atomic::{AtomicBool, Ordering}};
    static READY: AtomicBool = AtomicBool::new(false);
    pub fn set(v: Box<dyn Send>) {
        let payload = Mutex::new(v);
        std::panic::set_hook(Box::new(move |_| { let _ = &payload; }));
        READY.store(true, Ordering::Release);
    }
    pub fn take() -> Box<dyn Send> {
        assert!(READY.swap(false, Ordering::AcqRel));
        Box::new(std::panic::take_hook())
    }
"""


def _app(files: dict[str, str]) -> dict[str, str]:
    return {f"crates/app/src/{name}": text for name, text in files.items()}


def _rustc_asserts(tmp_path: Path, root: Path, expression: str) -> None:
    rustc = ["rustc", "--edition=2021"]
    library = tmp_path / "libprobe.rlib"
    subprocess.run(
        [
            *rustc,
            "--crate-name",
            "probe",
            "--crate-type",
            "rlib",
            root / "crates/app/src/lib.rs",
            "-o",
            library,
        ],
        cwd=NATIVE,
        check=True,
    )
    exe = tmp_path / ("witness.exe" if os.name == "nt" else "witness")
    subprocess.run(
        [*rustc, "--extern", f"probe={library}", "-", "-o", exe],
        input=f"extern crate probe; fn main() {{ assert!({expression}); }}",
        cwd=NATIVE,
        text=True,
        check=True,
    )
    subprocess.run([exe], check=True)


@pytest.mark.parametrize(
    ("case", "status"),
    [("allowed", "PASS"), ("named-import", "FAIL"), ("opaque-hold", "UNKNOWN")],
)
def test_destructor_origin_controls(
    tmp_path: Path, release_core: Path, case: str, status: str
) -> None:
    """Check a named import and a conservative hold, not a collector proof of value flow."""
    files = {
        "lib.rs": "pub mod a; pub mod b; mod slot;",
        "b.rs": """
            use std::sync::{Arc, atomic::{AtomicBool, Ordering}};
            pub struct Guard(Arc<AtomicBool>);
            impl Drop for Guard {
                fn drop(&mut self) { self.0.store(true, Ordering::SeqCst); }
            }
            pub fn make() -> (Arc<AtomicBool>, Guard) {
                let hit = Arc::new(AtomicBool::new(false));
                (hit.clone(), Guard(hit))
            }
        """,
    }
    entry = "probe::a::run()"
    if case == "allowed":
        files["slot.rs"] = """
            pub struct Guard<'a>(pub &'a mut bool);
            impl Drop for Guard<'_> {
                fn drop(&mut self) { *self.0 = true; }
            }
        """
        files["a.rs"] = """
            pub fn run() -> bool {
                let mut hit = false;
                { let _guard = crate::slot::Guard(&mut hit); }
                hit
            }
        """
    elif case == "named-import":
        files["slot.rs"] = ""
        files["a.rs"] = """
            pub fn run() -> bool {
                let (hit, guard) = crate::b::make();
                std::mem::forget(guard);
                !hit.load(std::sync::atomic::Ordering::SeqCst)
            }
        """
    else:
        files["slot.rs"] = HOOK_STORE
        files["a.rs"] = "pub fn run() { let _guard = crate::slot::take(); }"
        files["b.rs"] += """
            pub fn drive() -> bool {
                let (hit, guard) = make();
                crate::slot::set(Box::new(guard));
                assert!(!hit.load(Ordering::SeqCst));
                crate::a::run();
                hit.load(Ordering::SeqCst)
            }
        """
        entry = "probe::b::drive()"
    root = repository(tmp_path / "repo", release_core, _app(files), rules=(NO_A_TO_B,))
    _rustc_asserts(tmp_path, root, entry)
    result = validate(root)
    frame = result["frame"]
    assert statuses(result)["NO-A-TO-B"] == status, frame["explained"]
    if case == "named-import":
        assert [(row["source"], row["target"]) for row in frame["details"]["NO-A-TO-B"]] == [
            ("native.app.a", "native.app.b")
        ]
    elif case == "opaque-hold":
        assert {"source": "native.app.a", "target": "native.app.b"} in frame["explain"]["holds"][
            "rules"
        ]["NO-A-TO-B"]["pairs"]
        assert any(
            gap["subjects"] == ["native.app.a"]
            and gap["reason"] == "An unproved value origin may run a destructor in native.app.b"
            for gap in frame["collection_gaps"]
        )


@pytest.mark.parametrize(
    "case",
    [
        "stored",
        "stored-named",
        "stored-unread",
        "atomic-handle",
        "table-handle",
        "opaque-store",
        "different-trait",
        "no-read",
    ],
)
def test_drop_from_sibling_storage(tmp_path: Path, release_core: Path, case: str) -> None:
    home = """
        use std::sync::{Arc, atomic::{AtomicBool, Ordering}};
        pub struct Y(Arc<AtomicBool>);
        pub fn drive() -> bool {
            let hit = Arc::new(AtomicBool::new(false));
            crate::slot::set(Box::new(Y(hit.clone())));
            crate::a::run();
            hit.load(Ordering::SeqCst)
        }
    """
    if case == "different-trait":
        home += """
            trait Other { fn other(); fn generated(); }
            macro_rules! method { () => { fn generated() {} }; }
            impl Other for Y { fn other() {} method!(); }
        """
    else:
        home += """
            use std::ops::Drop as Destructor;
            impl Destructor for Y { fn drop(&mut self) { self.0.store(true, Ordering::SeqCst); } }
        """
    files = {
        "lib.rs": "pub mod a; pub mod b; pub mod slot;",
        "b.rs": home,
        "slot.rs": """
            use std::sync::Mutex;
            type Value = Box<dyn Send>;
            fn slot() -> &'static Mutex<Option<Value>> {
                static SLOT: Mutex<Option<Value>> = Mutex::new(None);
                &SLOT
            }
            pub fn set(v: Value) { *slot().lock().unwrap() = Some(v); }
            pub fn take() -> Value { slot().lock().unwrap().take().unwrap() }
        """,
        "a.rs": "pub fn run() { let _v = crate::slot::take(); }"
        if case != "no-read"
        else "pub fn run() {}",
    }
    if case == "opaque-store":
        files["slot.rs"] = HOOK_STORE
    if case == "stored-named":
        files["b.rs"] += "pub fn secret() {}"
        files["a.rs"] = "pub fn run() { let _v = crate::slot::take(); crate::b::secret(); }"
    if case == "stored-unread":
        files["b.rs"] += "impl Y { pub fn touch(&self) {} }"
        files["a.rs"] = """
            trait Touch { fn touch(&self) {} }
            impl Touch for u8 {}
            pub fn run() {
                let _v = crate::slot::take();
                (if true { 1u8 } else { 2u8 }).touch();
            }
        """
    if case in {"atomic-handle", "table-handle"}:
        carrier = (
            """
            use std::sync::atomic::{AtomicU64, Ordering};
            static SLOT: AtomicU64 = AtomicU64::new(0);
            fn put(n: u64) { SLOT.store(n, Ordering::Release); }
            fn get() -> u64 { SLOT.load(Ordering::Acquire) }
            """
            if case == "atomic-handle"
            else """
            use std::sync::OnceLock;
            static SLOT: OnceLock<Vec<(u32, u32)>> = OnceLock::new();
            fn put(n: u64) { SLOT.set(vec![(n as u32, (n >> 32) as u32)]).unwrap(); }
            fn get() -> u64 {
                let &(lo, hi) = SLOT.get().unwrap().first().unwrap();
                u64::from(lo) | (u64::from(hi) << 32)
            }
            """
        )
        files["slot.rs"] = (
            carrier
            + """
            type Value = Box<dyn Send>;
            type Cell = std::sync::Mutex<Option<Value>>;
            pub fn set(v: Value) {
                let cell: &'static Cell = Box::leak(Box::new(Cell::new(Some(v))));
                put(std::ptr::from_ref(cell).expose_provenance() as u64);
            }
            pub fn take() -> Value {
                let n = get();
                assert_ne!(n, 0);
                // Only set publishes an address, and the cell lives for the process.
                let cell = unsafe { &*std::ptr::with_exposed_provenance::<Cell>(n as usize) };
                cell.lock().unwrap().take().unwrap()
            }
        """
        )
    parts = [component("base", "base_crate")]
    for label, modules, needs in (
        ("app", ["native.app", "native.app.cargo_toml"], ("base",)),
        ("a", ["native.app.a"], ("slot",)),
        ("b", ["native.app.b"], ("slot", "a")),
        ("slot", ["native.app.slot"], ()),
    ):
        ports = {
            "a": ["native.app.a:run"],
            "b": ["native.app.b:drive"],
            "slot": ["native.app.slot:set", "native.app.slot:take"],
        }
        parts.append(
            {
                **component(label, "app", needs),
                "packages": [],
                "exact_modules": modules,
                "public": ports.get(label, []),
            }
        )
    rules = (
        *CRATE_RULES,
        rule("INTERFACE", "interface_boundary"),
        rule("MODULE-CYCLE", "no_component_cycles", level="module"),
    )
    if case != "stored-named":
        rules += ({**NO_A_TO_B, "target_match": "exact"},)
    root = repository(tmp_path / "repo", release_core, _app(files), tuple(parts), rules)
    path = root / "architecture-contract.json"
    contract = json.loads(path.read_text())
    if "declarations" not in contract:  # a contract with the type-reach premise needs 3.21.0
        contract["schema_version"] = "3.4.0"
    path.write_text(json.dumps(contract))
    commit_tree(root)
    runs_drop = case not in {"different-trait", "no-read"}
    _rustc_asserts(tmp_path, root, f"probe::b::drive() == {str(runs_drop).lower()}")
    result = validate(root)
    actual = statuses(result)
    assert actual["ASSIGNED"] == "PASS"
    interface = {"stored": "PASS", "stored-named": "FAIL", "stored-unread": "UNKNOWN"}
    if case in interface:
        assert actual["INTERFACE"] == interface[case], result["frame"]["explained"]
    checked = ("NO-A-TO-B", "MODULE-CYCLE", "NO-CYCLES")
    results = {key: actual[key] for key in checked if key in actual}
    if runs_drop:
        assert set(results.values()) <= {"UNKNOWN", "FAIL"}, results
        pair = {"source": "native.app.a", "target": "native.app.b"}
        holds = result["frame"]["explain"]["holds"]["rules"]
        for name, status in results.items():
            if status == "UNKNOWN":
                assert pair in holds[name]["pairs"]
    elif case == "different-trait":
        assert set(results.values()) == {"PASS"}, results
    else:
        assert results["NO-A-TO-B"] == "PASS"
