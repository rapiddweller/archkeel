# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""A trait impl runs in a module that reaches its module, without a name (#1515, #1516, AD-806).

`b` defines `Y` and a trait impl for it; `c` gives `a` a value of `Y` (`c::make()`). `a` runs the
impl by a form that writes no name of `b`: a format macro, `*` through `Deref`, an index, a method
of a foreign trait that a glob brings in. `a` reaches `b` over `c`, so the rule that forbids
`a -> b` is never PASS. The 17 forms of `rust_orphan_plants` (`OPEN_VALUE_FORMS`,
`OPEN_TRAIT_FORMS`) are checked in `test_collector_false_pass_rust_orphan_impl.py`; here `cargo
check` accepts each of them too. Controls: a module that does not reach `b`, and an impl that
holds only an associated type, keep PASS.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest
from corpus_support import commit_tree
from rust_orphan_plants import OPEN_TRAIT_FORMS, OPEN_VALUE_FORMS
from rust_repository import APP, BASE, CRATE_RULES, component, repository, rule, statuses, validate

pytestmark = pytest.mark.skipif(shutil.which("cargo") is None, reason="rustc is the oracle")

NO_A_TO_B = rule(
    "NO-A-TO-B",
    "forbidden_dependency",
    source="native.app.a",
    target="native.app.b",
    include_type_checking=True,
)

STORED_VALUE = """
use std::sync::Mutex;
static SLOT: Mutex<Option<Box<dyn Send>>> = Mutex::new(None);
pub fn put(value: Box<dyn Send>) { *SLOT.lock().unwrap() = Some(value); }
pub fn take() -> Option<Box<dyn Send>> { SLOT.lock().unwrap().take() }
"""
HOOK_VALUE = """
use std::sync::Mutex;
pub fn put(value: Box<dyn Send>) {
    let payload = Mutex::new(value);
    std::panic::set_hook(Box::new(move |_| { let _ = &payload; }));
}
pub fn take() -> Box<dyn Send> { Box::new(std::panic::take_hook()) }
"""
DISCARDED_VALUE = """
pub fn put(value: Box<dyn Send>) { drop(value); }
pub fn take() -> Option<Box<dyn Send>> { None }
"""


@pytest.mark.parametrize(
    ("store", "external", "destructor", "runs_in_reader"),
    [
        (STORED_VALUE, False, True, True),
        (HOOK_VALUE, False, True, True),
        (STORED_VALUE, True, True, True),
        (DISCARDED_VALUE, True, True, False),
        (STORED_VALUE, False, False, False),
        (HOOK_VALUE, False, False, False),
        (STORED_VALUE, True, False, False),
    ],
    ids=[
        "sibling",
        "no-counter",
        "unread-stores",
        "unread-discards",
        "sibling-other-trait",
        "no-counter-other-trait",
        "unread-other-trait",
    ],
)
def test_a_value_from_shared_state_can_run_its_destructor(
    tmp_path: Path,
    release_core: Path,
    store: str,
    external: bool,
    destructor: bool,
    runs_in_reader: bool,
) -> None:
    access = "vault" if external else "crate::slot"
    body = f"""
        use std::sync::{{Arc, atomic::{{AtomicBool, Ordering}}}};
        struct Y(Arc<AtomicBool>);
        pub fn drive() -> bool {{
            let hit = Arc::new(AtomicBool::new(false));
            {access}::put(Box::new(Y(hit.clone())));
            hit.store(false, Ordering::SeqCst);
            crate::a::run();
            hit.load(Ordering::SeqCst)
        }}
    """
    if destructor:
        body += """
            use std::ops::Drop as Destructor;
            impl Destructor for Y {
                fn drop(&mut self) { self.0.store(true, Ordering::SeqCst); }
            }
        """
    else:
        body += "trait Other { fn other(); } impl Other for Y { fn other() {} }"
    files = _app(
        {
            "lib.rs": "pub mod b; mod a;" + ("" if external else "mod slot;"),
            "a.rs": f"pub fn run() {{ let _value = {access}::take(); }}",
            "b.rs": body,
        }
    )
    parts = [component("base", "base_crate")]
    for label, modules, needs in (
        ("app", ["native.app", "native.app.cargo_toml"], ("base",)),
        ("a", ["native.app.a"], () if external else ("slot",)),
        ("b", ["native.app.b"], ("a",) if external else ("a", "slot")),
    ):
        parts.append({**component(label, "app", needs), "packages": [], "exact_modules": modules})
    if external:
        files["crates/app/Cargo.toml"] = APP + 'vault = { path = "../../vendor/vault" }\n'
        files["vendor/vault/Cargo.toml"] = BASE.replace('"base-crate"', '"vault"') + "[workspace]\n"
        files["vendor/vault/src/lib.rs"] = store
    else:
        files["crates/app/src/slot.rs"] = store
        parts.append(component("slot", "app.slot"))
    rules = (
        *CRATE_RULES,
        rule("MODULE-CYCLE", "no_component_cycles", level="module"),
        {**NO_A_TO_B, "target_match": "exact"},
    )
    root = repository(tmp_path / "repo", release_core, files, tuple(parts), rules)
    path = root / "architecture-contract.json"
    contract = json.loads(path.read_text())
    if "declarations" not in contract:  # a contract with the type-reach premise needs 3.22.0
        contract["schema_version"] = "3.4.0"
    path.write_text(json.dumps(contract))
    commit_tree(root)
    compile_lib = ["rustc", "--edition=2021", "--crate-type", "rlib"]
    extra = []
    if external:
        vault = tmp_path / "libvault.rlib"
        subprocess.run(
            [*compile_lib, "--crate-name", "vault", root / "vendor/vault/src/lib.rs", "-o", vault],
            check=True,
        )
        extra = ["--extern", f"vault={vault}"]
    app = tmp_path / "libprobe.rlib"
    subprocess.run(
        [*compile_lib, "--crate-name", "probe", root / "crates/app/src/lib.rs", "-o", app, *extra],
        check=True,
    )
    exe = tmp_path / ("witness.exe" if os.name == "nt" else "witness")
    expected = str(runs_in_reader).lower()
    subprocess.run(
        ["rustc", "-L", f"dependency={tmp_path}", "--extern", f"probe={app}", "-", "-o", exe],
        input=f"extern crate probe; fn main() {{ assert_eq!(probe::b::drive(), {expected}); }}",
        text=True,
        check=True,
    )
    subprocess.run([exe], check=True)
    result = validate(root)
    actual = statuses(result)
    assert actual["ASSIGNED"] == "PASS"
    for name in ("NO-A-TO-B", "MODULE-CYCLE", "NO-CYCLES"):
        assert actual[name] == ("UNKNOWN" if destructor else "PASS")
        if destructor:
            holds = result["frame"]["explain"]["holds"]["rules"]
            assert {"source": "native.app.a", "target": "native.app.b"} in holds[name]["pairs"]


LIB = "mod a;\nmod b;\nmod c;\n"
MAKE = "pub fn make() -> crate::b::Y {\n    crate::b::Y\n}\n"


def _form(impl: str, caller: str) -> dict[str, str]:
    return {"lib.rs": LIB, "b.rs": f"pub struct Y;\n{impl}", "c.rs": MAKE, "a.rs": caller}


FORMS: dict[str, dict[str, str]] = {
    "Debug through a format macro": _form(
        "impl std::fmt::Debug for Y {\n    fn fmt(&self, _f: &mut std::fmt::Formatter) "
        "-> std::fmt::Result {\n        Ok(())\n    }\n}\n",
        'pub fn f() -> String {\n    format!("{:?}", crate::c::make())\n}\n',
    ),
    "Deref through *": _form(
        "impl std::ops::Deref for Y {\n    type Target = u8;\n"
        "    fn deref(&self) -> &u8 {\n        &1\n    }\n}\n",
        "pub fn f() -> u8 {\n    *crate::c::make()\n}\n",
    ),
    "Index through []": _form(
        "impl std::ops::Index<usize> for Y {\n    type Output = u8;\n"
        "    fn index(&self, _i: usize) -> &u8 {\n        &1\n    }\n}\n",
        "pub fn f() -> u8 {\n    crate::c::make()[0]\n}\n",
    ),
}
CONTROLS: dict[str, dict[str, str]] = {
    "a does not reach b": _form(
        "impl std::fmt::Display for Y {\n    fn fmt(&self, _f: &mut std::fmt::Formatter) "
        "-> std::fmt::Result {\n        Ok(())\n    }\n}\n",
        "pub fn f() -> u8 {\n    1\n}\n",
    ),
    "the impl holds only an associated type": {
        **_form(
            "pub trait K {\n    type T;\n}\nimpl K for Y {\n    type T = u8;\n}\n",
            "pub fn f() {\n    let _y = crate::c::make();\n}\n",
        ),
    },
}
VENDOR = {
    "vendor/trait-ext/Cargo.toml": '[package]\nname = "trait-ext"\nversion = "0.0.0"\n'
    'edition = "2021"\n[workspace]\n',
    "vendor/trait-ext/src/lib.rs": "pub trait T {\n    fn m(&self) -> u8;\n}\n",
}
GLOB = {
    "crates/app/Cargo.toml": APP + 'trait-ext = { path = "../../vendor/trait-ext" }\n',
    "crates/app/src/lib.rs": LIB,
    "crates/app/src/a.rs": "use trait_ext::*;\npub fn f() -> u8 {\n    crate::c::make().m()\n}\n",
    "crates/app/src/b.rs": "pub struct Y;\nimpl trait_ext::T for Y {\n"
    "    fn m(&self) -> u8 {\n        1\n    }\n}\n",
    "crates/app/src/c.rs": MAKE,
    **VENDOR,
}


def _rustc_accepts(root: Path) -> None:
    env = {**os.environ, "CARGO_TARGET_DIR": str(root.parent / "target")}
    manifest = root / "crates/Cargo.toml"
    command = ["cargo", "check", "--quiet", "--offline", "--manifest-path", str(manifest)]
    done = subprocess.run(command, capture_output=True, text=True, env=env, check=False)
    assert done.returncode == 0, done.stderr


def _verdict(tmp_path: Path, core: Path, files: dict[str, str]) -> str:
    root = repository(tmp_path / "repo", core, files, rules=(*CRATE_RULES, NO_A_TO_B))
    verdict = statuses(validate(root))["NO-A-TO-B"]
    _rustc_accepts(root)
    return verdict


def _app(files: dict[str, str]) -> dict[str, str]:
    return {f"crates/app/src/{name}": text for name, text in files.items()}


@pytest.mark.parametrize("name", list(FORMS))
def test_an_implicit_call_through_another_module_never_passes(
    tmp_path: Path, release_core: Path, name: str
) -> None:
    assert _verdict(tmp_path, release_core, _app(FORMS[name])) in {"FAIL", "UNKNOWN"}


def test_a_foreign_trait_that_a_glob_brings_in_never_passes(
    tmp_path: Path, release_core: Path
) -> None:
    assert _verdict(tmp_path, release_core, GLOB) in {"FAIL", "UNKNOWN"}


@pytest.mark.parametrize("name", list(CONTROLS))
def test_a_module_that_cannot_run_the_impl_keeps_its_verdict(
    tmp_path: Path, release_core: Path, name: str
) -> None:
    assert _verdict(tmp_path, release_core, _app(CONTROLS[name])) == "PASS"


OPEN = {**OPEN_VALUE_FORMS, **OPEN_TRAIT_FORMS}


@pytest.mark.parametrize("name", list(OPEN))
def test_rustc_accepts_each_dispatch_form_of_the_audit(
    tmp_path: Path, release_core: Path, name: str
) -> None:
    assert _verdict(tmp_path, release_core, _app(OPEN[name])) in {"FAIL", "UNKNOWN"}


def test_a_foreign_return_type_can_carry_a_private_impl(tmp_path: Path, release_core: Path) -> None:
    files = {
        "crates/Cargo.toml": '[workspace]\nmembers = ["base", "app", "carrier"]\n',
        "crates/base/Cargo.toml": BASE + '[dependencies]\ncarrier = { path = "../carrier" }\n',
        "crates/base/src/lib.rs": (
            "mod hidden;\n"
            "pub fn make() -> carrier::Handle { carrier::Handle(Box::new(hidden::Y)) }\n"
        ),
        "crates/base/src/hidden.rs": ("#[derive(Debug)]\npub(super) struct Y;\n"),
        "crates/carrier/Cargo.toml": BASE.replace('"base-crate"', '"carrier"'),
        "crates/carrier/src/lib.rs": (
            "#[derive(Debug)]\npub struct Handle(pub Box<dyn std::fmt::Debug>);\n"
        ),
        "crates/app/src/lib.rs": (
            'pub fn run() -> String { format!("{:?}", base_crate::make()) }\n'
        ),
    }
    no_private_dispatch = rule(
        "NO-PRIVATE-DISPATCH",
        "forbidden_dependency",
        source="native.app",
        target="native.base_crate.hidden",
        include_type_checking=True,
    )
    root = repository(
        tmp_path / "repo",
        release_core,
        files,
        components=(
            component("base", "base_crate", ("carrier",)),
            component("app", "app", ("base",)),
            component("carrier", "carrier"),
        ),
        rules=(*CRATE_RULES, no_private_dispatch),
    )
    _rustc_accepts(root)
    assert statuses(validate(root))["NO-PRIVATE-DISPATCH"] in {"FAIL", "UNKNOWN"}


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        pytest.param(
            "pub fn f() -> u8 { trait_ext::T::m(&crate::c::make()) }\n",
            {"FAIL"},
            id="direct",
        ),
        pytest.param(
            "macro_rules! to_u8 { ($path:path) => { $path(&crate::c::make()) }; }\n"
            "pub fn f() -> u8 { to_u8!(trait_ext::T::m) }\n",
            {"FAIL", "UNKNOWN"},
            id="opaque-macro",
        ),
    ],
)
def test_a_lexical_external_path_never_passes(
    tmp_path: Path, release_core: Path, source: str, expected: set[str]
) -> None:
    files = {**GLOB, "crates/app/src/a.rs": source}
    scope = rule(
        "NO-EXTERNAL-IN-A",
        "external_dependency_scope",
        dependency="trait_ext",
        exact_sources=["native.app.b", "native.app.cargo_toml"],
    )
    root = repository(tmp_path / "repo", release_core, files, rules=(*CRATE_RULES, scope))
    _rustc_accepts(root)
    assert statuses(validate(root))["NO-EXTERNAL-IN-A"] in expected


def test_an_internal_dispatch_does_not_add_a_lexical_external_path(
    tmp_path: Path, release_core: Path
) -> None:
    files = {
        **GLOB,
        "crates/app/src/a.rs": "pub fn f() { drop(crate::c::make()); }\n",
        "crates/app/src/b.rs": GLOB["crates/app/src/b.rs"]
        + "impl Drop for Y { fn drop(&mut self) {} }\n",
    }
    package = rule(
        "NO-EXTERNAL-IN-A",
        "external_dependency_scope",
        dependency="trait_ext",
        exact_sources=["native.app.b", "native.app.cargo_toml"],
    )
    complete = rule("EXTERNALS-DECLARED", "complete_external_scope", source="native")
    local = rule(
        "NO-LOCAL-IN-A",
        "external_dependency_scope",
        dependency="native.app.b",
        exact_sources=["native.app", "native.app.c", "native.app.b"],
    )
    root = repository(
        tmp_path / "repo", release_core, files, rules=(*CRATE_RULES, package, complete, local)
    )
    _rustc_accepts(root)
    verdicts = statuses(validate(root))
    assert verdicts["NO-EXTERNAL-IN-A"] == "PASS"
    assert verdicts["EXTERNALS-DECLARED"] == "PASS"
    assert verdicts["NO-LOCAL-IN-A"] == "UNKNOWN"


REEXPORT_CALL = "pub fn run() -> u32 { base_crate::Token::origin() }\n"
UNUSED_REEXPORT = "macro_rules! unused { () => { base_crate::Token::origin() }; }\n"


# AD-1048: in the two `VACUOUS` plants no import names `cc`, so the rule examined nothing: the
# verdict was PASS before and is UNKNOWN now, and the unread package gap is not the cause.
@pytest.mark.parametrize(
    ("bridge", "app", "direct", "answer", "expected"),
    [
        ("pub use foreign::Token;", REEXPORT_CALL, False, 42, "UNKNOWN"),
        ("pub use foreign::Token;", UNUSED_REEXPORT + REEXPORT_CALL, False, 42, "UNKNOWN"),
        ("pub use foreign::Token;", REEXPORT_CALL + UNUSED_REEXPORT, False, 42, "UNKNOWN"),
        (
            "pub use foreign::Token;",
            UNUSED_REEXPORT + "pub fn run() -> u32 { 0 }\n",
            False,
            0,
            "VACUOUS",
        ),
        (
            "pub struct Token; impl Token { pub fn origin() -> u32 { 42 } }",
            REEXPORT_CALL,
            False,
            42,
            "VACUOUS",
        ),
        ("pub use foreign::Token;", REEXPORT_CALL.replace("base_crate", "cc"), True, 42, "FAIL"),
    ],
    ids=[
        "foreign-reexport",
        "template-first",
        "template-last",
        "template-only",
        "local-definition",
        "direct-import",
    ],
)
def test_an_external_reexport_can_name_an_unread_package(
    tmp_path: Path,
    release_core: Path,
    bridge: str,
    app: str,
    direct: bool,
    answer: int,
    expected: str,
) -> None:
    cc = BASE.replace('"base-crate"', '"cc"') + "[workspace]\n"
    foreign = BASE.replace('"base-crate"', '"foreign"') + "[workspace]\n"
    files = {
        "crates/base/Cargo.toml": BASE
        + '[dependencies]\nforeign = { path = "../../vendor/foreign" }\n',
        "crates/base/src/lib.rs": bridge,
        "crates/app/src/lib.rs": app,
        "crates/app/src/main.rs": f"fn main() {{ assert_eq!(app::run(), {answer}); }}\n",
        "vendor/foreign/Cargo.toml": foreign + '[dependencies]\ncc = { path = "../cc" }\n',
        "vendor/foreign/src/lib.rs": "pub use cc::Token;\n",
        "vendor/cc/Cargo.toml": cc,
        "vendor/cc/src/lib.rs": "pub struct Token; impl Token { pub fn origin() -> u32 { 42 } }\n",
    }
    if direct:
        files["crates/app/Cargo.toml"] = APP + 'cc = { path = "../../vendor/cc" }\n'
    scope = rule(
        "NO-CC",
        "external_dependency_scope",
        dependency="cc",
        exact_sources=["native.app.cargo_toml"],
    )
    root = repository(tmp_path / "repo", release_core, files, rules=(scope,))
    command = [
        "cargo",
        "run",
        "--quiet",
        "--offline",
        "--package",
        "app",
        "--manifest-path",
        str(root / "crates/Cargo.toml"),
    ]
    env = {**os.environ, "CARGO_TARGET_DIR": str(tmp_path / "target")}
    done = subprocess.run(command, capture_output=True, text=True, env=env, check=False)
    assert done.returncode == 0, done.stderr
    result = validate(root)
    assert statuses(result)["NO-CC"] == ("UNKNOWN" if expected == "VACUOUS" else expected)
    gaps = result["frame"]["collection_gaps"]
    unread = [gap for gap in gaps if "unread package foreign" in gap["reason"]]
    if expected == "UNKNOWN":
        assert len(unread) == 1
        assert unread[0]["subjects"] == ["native.app"]
        [site] = unread[0]["evidence"]
        at = result["frame"]["locations"][site]
        assert at["path"] == "crates/app/src/lib.rs"
        assert app.splitlines()[at["line"] - 1] == REEXPORT_CALL.rstrip()
    else:
        assert not unread
