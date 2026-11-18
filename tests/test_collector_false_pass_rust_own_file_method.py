# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""#1571: a method in the file of its type, called on a value that the caller does not name.

Consumer: `archkeel validate`. `c` holds `pub struct S` and `impl S { fn m }`. `a` gets a value of
type `S` without naming `c` (a field of a parameter, a chain of fields, the return value of a
function of `d`) and calls `m`. rustc compiles each plant, and the program prints `c`: the call is a
dependency `a -> c`. So `NO-A-TO-C` is FAIL (the edge) or UNKNOWN (a pair gap), never PASS.
Before #1571 the scan gave no record that names `c`, and the rule was PASS (AD-418,
`docs/known-limits.md`).
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest
from rust_repository import CRATE_RULES, component, repository, rule, statuses, validate
from test_cli_native_rust_interface import _rustc_accepts

pytestmark = pytest.mark.skipif(shutil.which("cargo") is None, reason="rustc is the oracle")

SRC = "crates/app/src/"
STR = "&'static str"
TYPE = f'pub struct S;\nimpl S {{\n    pub fn m(&self) -> {STR} {{\n        "c"\n    }}\n}}\n'
HOLDER = (
    "pub struct W {\n    pub s: crate::c::S,\n}\npub struct V {\n    pub w: W,\n}\n"
    "pub fn make() -> W {\n    W { s: crate::c::S }\n}\n"
    "pub fn nest() -> V {\n    V { w: make() }\n}\n"
    "pub fn value() -> crate::c::S {\n    crate::c::S\n}\n"
    "pub static ONE: crate::c::S = crate::c::S;\n"
    "pub fn shared() -> &'static crate::c::S {\n    &ONE\n}\n"
)
CALLERS = {
    "a field of a typed parameter": (
        f"pub fn g(w: &crate::d::W) -> {STR} {{\n    w.s.m()\n}}\n"
        f"pub fn run() -> {STR} {{\n    g(&crate::d::make())\n}}\n"
    ),
    "a chain of two fields": (
        f"pub fn g(v: &crate::d::V) -> {STR} {{\n    v.w.s.m()\n}}\n"
        f"pub fn run() -> {STR} {{\n    g(&crate::d::nest())\n}}\n"
    ),
    "the field of a return value": f"pub fn run() -> {STR} {{\n    crate::d::make().s.m()\n}}\n",
    "a return value": f"pub fn run() -> {STR} {{\n    crate::d::value().m()\n}}\n",
    "a local of a return value": (
        f"pub fn run() -> {STR} {{\n    let w = crate::d::make();\n    w.s.m()\n}}\n"
    ),
}


def _plant(root: Path, core: Path, caller: str, ty: str = TYPE, holder: str = HOLDER) -> Path:
    files = {
        SRC + "lib.rs": "pub mod a;\nmod c;\nmod d;\n",
        SRC + "c.rs": ty,
        SRC + "d.rs": holder,
        SRC + "a.rs": caller,
    }
    to_c = rule(
        "NO-A-TO-C",
        "forbidden_dependency",
        source="native.app.a",
        target="native.app.c",
        include_type_checking=True,
    )
    return repository(root, core, files, rules=(*CRATE_RULES, to_c))


def _real_target(root: Path) -> str:
    """The module of the member that Rust calls: the output of `app::a::run()`."""
    out = root / "out"
    out.mkdir()
    common = ["rustc", "--edition", "2021", "-A", "warnings", "--out-dir", str(out)]
    library = [*common, "--crate-type", "lib", "--crate-name", "app", str(root / SRC / "lib.rs")]
    done = subprocess.run(library, capture_output=True, text=True)
    assert done.returncode == 0, done.stderr
    main = root / "main.rs"
    main.write_text('fn main() {\n    print!("{}", app::a::run());\n}\n')
    program = [*common, "--extern", f"app={out / 'libapp.rlib'}", str(main)]
    done = subprocess.run(program, capture_output=True, text=True)
    assert done.returncode == 0, done.stderr
    return subprocess.run([str(out / "main")], capture_output=True, text=True, check=True).stdout


@pytest.mark.parametrize("name", sorted(CALLERS))
def test_a_call_into_the_file_of_the_type_is_never_silent(
    tmp_path: Path, core_binary: Path, capsys: pytest.CaptureFixture[str], name: str
) -> None:
    root = _plant(tmp_path, core_binary, CALLERS[name])
    _rustc_accepts(root)
    assert _real_target(root) == "c"
    found = statuses(validate(root, capsys))
    assert found.get("NO-A-TO-C") in {"FAIL", "UNKNOWN"}, (name, found)


def test_an_exact_field_and_an_exact_impl_give_the_edge(
    tmp_path: Path, core_binary: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Where the scan resolves the field to an exact type with one exact member of the `self` form
    of the field (AD-524), the call is the edge `a -> c` (FAIL), not only a gap. A `&self` member
    through a field of a value is an autoref: a trait method `m(self)` in scope would win, and the
    scan cannot see each trait in scope (std, a blanket impl of a dependency), so that call keeps
    the pair gap of the cases above."""
    copy = TYPE.replace("pub struct S;", "#[derive(Clone, Copy)]\npub struct S;").replace(
        "m(&self)", "m(self)"
    )
    root = _plant(tmp_path, core_binary, CALLERS["a field of a typed parameter"], copy)
    _rustc_accepts(root)
    assert _real_target(root) == "c"
    found = statuses(validate(root, capsys))
    assert found.get("NO-A-TO-C") == "FAIL", found


def test_requires_receipt_distinguishes_matching_and_wrong_ports(
    tmp_path: Path, release_core: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    files = {
        SRC + "lib.rs": "mod a;\nmod c;\nmod d;\n",
        SRC + "a.rs": CALLERS["a field of a typed parameter"],
        SRC + "c.rs": TYPE,
        SRC + "d.rs": HOLDER,
    }
    root_component = component("root", "app", ("a", "base", "c", "d"))
    root_component["packages"] = []
    root_component["exact_modules"] = ["native.app", "native.app.cargo_toml"]
    a = component("a", "app.a", ("c", "d"))
    parts = (
        component("base", "base_crate"),
        root_component,
        a,
        component("c", "app.c"),
        component("d", "app.d", ("c",)),
    )
    root = repository(tmp_path, release_core, files, components=parts)
    _rustc_accepts(root)
    allowed = validate(root, capsys)
    # A module port permits any symbol. A symbol port still needs a named edge.
    a["requires"][0]["through"] = ["native.app.c:S"]
    contract = root / "architecture-contract.json"
    contract.write_text(
        json.dumps({"schema_version": "2.1.0", "components": parts, "rules": CRATE_RULES})
    )
    matching = validate(root, capsys)
    a["requires"][0]["through"] = ["native.app.c.other"]
    contract.write_text(
        json.dumps({"schema_version": "2.1.0", "components": parts, "rules": CRATE_RULES})
    )
    wrong = validate(root, capsys)
    assert allowed["frame"]["collection_gaps"] == matching["frame"]["collection_gaps"]
    assert allowed["frame"]["collection_gaps"] == wrong["frame"]["collection_gaps"]
    assert len(allowed["frame"]["collection_gaps"]) == 1
    assert statuses(allowed)["REQUIRES"] == "PASS", allowed["frame"]["details"]
    assert statuses(matching)["REQUIRES"] == "PASS", matching
    assert statuses(wrong)["REQUIRES"] == "UNKNOWN", wrong
    assert "native.app.a -> native.app.c" in wrong["frame"]["explained"]["REQUIRES"]


# #1571 (AD-804): the receiver type comes from a written return type `&S`, or from the item of a
# fixed std adapter or loop over `&Vec<S>` / `&[S]` (`&S`): one exact member of the same `self`
# form, so the call is the edge `a -> c`.
TYPED = {
    "a written return type": f"pub fn run() -> {STR} {{\n    crate::d::shared().m()\n}}\n",
    "a closure of iter().map": (
        f"pub fn g(v: &Vec<crate::c::S>) -> {STR} {{\n"
        '    v.iter().map(|s| s.m()).next().unwrap_or("")\n}\n'
        f"pub fn run() -> {STR} {{\n    g(&vec![crate::d::value()])\n}}\n"
    ),
    "a for loop over a slice": (
        f"pub fn g(v: &[crate::c::S]) -> {STR} {{\n"
        '    for s in v {\n        return s.m();\n    }\n    ""\n}\n'
        f"pub fn run() -> {STR} {{\n    g(&[crate::d::value()])\n}}\n"
    ),
}


@pytest.mark.parametrize("name", sorted(TYPED))
def test_a_written_receiver_type_gives_the_edge(
    tmp_path: Path, core_binary: Path, capsys: pytest.CaptureFixture[str], name: str
) -> None:
    root = _plant(tmp_path, core_binary, TYPED[name])
    _rustc_accepts(root)
    assert _real_target(root) == "c"
    found = statuses(validate(root, capsys))
    assert found.get("NO-A-TO-C") == "FAIL", (name, found)


@pytest.mark.parametrize(
    ("first", "verdict"), [("", "FAIL"), ("#[cfg(any())] pub u8, ", "UNKNOWN")]
)
def test_a_tuple_struct_field_gives_the_edge_only_at_an_exact_position(
    tmp_path: Path, core_binary: Path, capsys: pytest.CaptureFixture[str], first: str, verdict: str
) -> None:
    caller = (
        f"pub fn g(w: &crate::d::Tuple) -> {STR} {{ w.0.m() }}\n"
        f"pub fn run() -> {STR} {{ g(&crate::d::Tuple(crate::d::shared())) }}\n"
    )
    holder = HOLDER + f"pub struct Tuple({first}pub &'static crate::c::S);\n"
    root = _plant(tmp_path, core_binary, caller, holder=holder)
    _rustc_accepts(root)
    assert _real_target(root) == "c"
    found = statuses(validate(root, capsys))
    assert found.get("NO-A-TO-C") == verdict, (first, found)


def test_a_std_receiver_reaches_no_member_of_the_workspace(
    tmp_path: Path, core_binary: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`String::from(..)` gives a `String`: its `len` is the one of std, never `S::len` in `c` (an
    inherent impl of a std type is E0116). rustc prints the length 2, not 999."""
    ty = "pub struct S;\nimpl S {\n    pub fn len(&self) -> usize {\n        999\n    }\n}\n"
    caller = 'pub fn run() -> usize {\n    let x = String::from("ab");\n    x.len()\n}\n'
    root = _plant(tmp_path, core_binary, caller, ty)
    _rustc_accepts(root)
    assert _real_target(root) == "2"
    found = statuses(validate(root, capsys))
    assert found.get("NO-A-TO-C") == "PASS", found


@pytest.mark.parametrize("profile_first", (False, True))
def test_same_call_text_keeps_both_proven_receivers(
    tmp_path: Path, release_core: Path, capsys: pytest.CaptureFixture[str], profile_first: bool
) -> None:
    clean = f"fn clean() -> {STR} {{ {{ let value = crate::d::clean(); value.label() }} }}\n"
    profile = f"fn profile() -> {STR} {{ {{ let value = crate::d::profile(); value.label() }} }}\n"
    calls = profile + clean if profile_first else clean + profile
    files = {
        SRC + "lib.rs": "pub mod a;\nmod c;\nmod d;\n",
        SRC + "a.rs": calls + 'pub fn run() -> String { [clean(), profile()].join("/") }\n',
        SRC + "c.rs": (
            f'pub struct Clean;\nimpl Clean {{ pub fn label(&self) -> {STR} {{ "clean" }} }}\n'
            "pub struct Profile;\n"
            f'impl Profile {{ pub fn label(&self) -> {STR} {{ "profile" }} }}\n'
        ),
        SRC + "d.rs": (
            "pub fn clean() -> &'static crate::c::Clean { &crate::c::Clean }\n"
            "pub fn profile() -> &'static crate::c::Profile { &crate::c::Profile }\n"
        ),
    }
    no_profile = rule(
        "NO-PROFILE",
        "forbidden_dependency",
        source="native.app.a",
        target="native.app.c",
        target_symbol="Profile",
        include_type_checking=True,
    )
    source_names = {**no_profile, "id": "SOURCE-NAMES", "source_symbol_only": True}
    root = repository(tmp_path, release_core, files, rules=(*CRATE_RULES, no_profile, source_names))
    path = root / "architecture-contract.json"
    contract = json.loads(path.read_text())
    contract["schema_version"] = "3.19.0"
    path.write_text(json.dumps(contract, indent=2))
    assert _real_target(root) == "clean/profile"
    found = statuses(validate(root, capsys))
    assert found.get("NO-PROFILE") == "FAIL", found
    assert found.get("SOURCE-NAMES") == "PASS", found
