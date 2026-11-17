# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""A path through a re-exported module or crate root names the module at its end (#1517, AD-772).

In `crate::c::other::b::g()`, `other` can be a `use` of `c` that names a module, the crate root
(`crate`, an alias of `extern crate self`), another crate of the workspace, or a name that a glob
of `c` brings in. rustc then resolves the path into `b`, so a rule that forbids `a -> b` may never
PASS. Before AD-772, the module resolver stopped at `c` and each form below gave a false PASS.
`cargo check` accepts each plant.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest
from rust_repository import CRATE_RULES, repository, rule, statuses, validate

pytestmark = pytest.mark.skipif(shutil.which("cargo") is None, reason="rustc is the oracle")

LIB = "pub mod a; pub mod b; pub mod c;\n"
ALIAS = LIB + "pub extern crate self as name;\n"
G = "pub fn g() {}\n"
HIDDEN = {"crates/base/src/lib.rs": "pub mod hidden;\n", "crates/base/src/hidden.rs": G}


def _app(lib: str, a: str, c: str, **more: str) -> dict[str, str]:
    files = {"crates/app/src/lib.rs": lib, "crates/app/src/a.rs": a, "crates/app/src/c.rs": c}
    files.update({f"crates/app/src/{name}.rs": text for name, text in more.items()})
    return files


def _in_app(a: str, c: str, lib: str = LIB, **more: str) -> dict[str, str]:
    return {**_app(lib, a, c, **more), "crates/app/src/b.rs": G}


def _in_base(a: str, c: str) -> dict[str, str]:
    return {**HIDDEN, **_app("pub mod a; pub mod c;\n", a, c)}


IN_APP = "native.app.b"
IN_BASE = "native.base_crate.hidden"
VIA_C = "pub fn f() { crate::c::other::b::g(); }\n"

# Each form names `g` in the forbidden module through `c`: the core follows the route (FAIL).
FOLLOWED = {
    "module-renamed": (
        _in_app("pub fn f() { crate::c::other::g(); }\n", "pub use crate::b as other;\n"),
        IN_APP,
    ),
    "module-plain": (_in_app("pub fn f() { crate::c::b::g(); }\n", "pub use crate::b;\n"), IN_APP),
    "extern-self-alias": (_in_app(VIA_C, "pub use crate::name as other;\n", ALIAS), IN_APP),
    "crate-root": (_in_app(VIA_C, "pub use crate as other;\n"), IN_APP),
    "second-re-export": (
        _in_app(VIA_C, "pub use crate::name as first;\npub use self::first as other;\n", ALIAS),
        IN_APP,
    ),
    "re-export-in-another-module": (
        _in_app(
            "pub fn f() { crate::c::module::other::b::g(); }\n",
            "pub use crate::d as module;\n",
            ALIAS + "pub mod d;\n",
            d="pub use crate::name as other;\n",
        ),
        IN_APP,
    ),
    "use-leaf-of-the-re-export": (
        _in_app(
            "use crate::c::other;\npub fn f() { other::b::g(); }\n",
            "pub use crate::name as other;\n",
            ALIAS,
        ),
        IN_APP,
    ),
    "glob-of-the-root": (
        _in_app("pub fn f() { crate::c::b::g(); }\n", "pub use crate::*;\n"),
        IN_APP,
    ),
    "glob-of-the-root-alias": (
        _in_app("pub fn f() { crate::c::name::b::g(); }\n", "pub use crate::*;\n", ALIAS),
        IN_APP,
    ),
    "dependency-root-renamed": (
        _in_base(
            "pub fn f() { crate::c::other::hidden::g(); }\n", "pub use base_crate as other;\n"
        ),
        IN_BASE,
    ),
    "dependency-root-plain": (
        _in_base("pub fn f() { crate::c::base_crate::hidden::g(); }\n", "pub use base_crate;\n"),
        IN_BASE,
    ),
    "dependency-module": (
        _in_base(
            "pub fn f() { crate::c::other::g(); }\n", "pub use base_crate::hidden as other;\n"
        ),
        IN_BASE,
    ),
    "dependency-glob-re-export": (
        _in_base("pub fn f() { crate::c::hidden::g(); }\n", "pub use base_crate::*;\n"),
        IN_BASE,
    ),
    "dependency-glob-bare-path": (
        {
            **HIDDEN,
            "crates/app/src/lib.rs": "pub mod a;\n",
            "crates/app/src/a.rs": "use base_crate::*;\npub fn f() { hidden::g(); }\n",
        },
        IN_BASE,
    ),
}

# The scan cannot follow these routes: the rule must not PASS (UNKNOWN with a gap, or FAIL).
KEPT = {
    "macro-writes-the-re-export": _in_app(
        VIA_C,
        "macro_rules! publish { () => { pub use crate::name as other; }; }\npublish!();\n",
        ALIAS,
    ),
    "alias-chain-over-the-hop-limit": _in_app(
        VIA_C,
        "pub use crate::name as n0;\n"
        + "".join(f"pub use self::n{i} as n{i + 1};\n" for i in range(10))
        + "pub use self::n10 as other;\n",
        ALIAS,
    ),
}


def _rustc_accepts(root: Path) -> None:
    env = {**os.environ, "CARGO_TARGET_DIR": str(root.parent / "target")}
    manifest = root / "crates/Cargo.toml"
    command = ["cargo", "check", "--quiet", "--offline", "--manifest-path", str(manifest)]
    done = subprocess.run(command, capture_output=True, text=True, env=env, check=False)
    assert done.returncode == 0, done.stderr


def _verdict(tmp_path: Path, core: Path, files: dict[str, str], target: str) -> str:
    forbidden = rule(
        "NO-HIDDEN",
        "forbidden_dependency",
        source="native.app.a",
        target=target,
        include_type_checking=True,
    )
    root = repository(tmp_path / "repo", core, files, rules=(*CRATE_RULES, forbidden))
    verdict = statuses(validate(root))["NO-HIDDEN"]
    _rustc_accepts(root)
    return verdict


@pytest.mark.parametrize("name", list(FOLLOWED))
def test_a_path_through_a_re_export_names_the_module_at_its_end(
    tmp_path: Path, release_core: Path, name: str
) -> None:
    files, target = FOLLOWED[name]
    assert _verdict(tmp_path, release_core, files, target) == "FAIL"


@pytest.mark.parametrize("name", list(KEPT))
def test_a_route_that_the_scan_cannot_follow_never_passes(
    tmp_path: Path, release_core: Path, name: str
) -> None:
    assert _verdict(tmp_path, release_core, KEPT[name], IN_APP) in {"FAIL", "UNKNOWN"}


def test_a_re_exported_type_does_not_become_a_module(tmp_path: Path, release_core: Path) -> None:
    """A path through a re-exported enum names a variant: no module of the crate is reached."""
    files = _in_app(
        "pub fn f() { let _ = crate::c::Other::V; }\n",
        "pub use crate::b::S as Other;\n",
        LIB + "pub mod d;\n",
        d="pub fn unused() {}\n",
    )
    files["crates/app/src/b.rs"] = "pub enum S { V }\n"
    assert _verdict(tmp_path, release_core, files, "native.app.d") == "PASS"
