# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""#1346: a `pub use` that a macro writes never gives a silent PASS.

Consumer: `archkeel validate`. In each plant the module `y` gets `b` only from a macro call, and
`x` takes it through `use crate::y::*;` and calls `b::g()`. rustc accepts each plant, so the edge
`x -> b` is real: the rule that forbids it is UNKNOWN or FAIL, never PASS. The forms reach the
`pub use` through a repetition, a macro that calls a macro, a macro that defines a macro, a crate
macro named like a `std` macro, `$crate`, and a macro of another crate (by its path, by a `use`
and by `#[macro_use]`).
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from rust_repository import APP, CRATE_RULES, claims, repository, statuses, validate
from test_cli_native_rust_interface import _rustc_accepts
from test_collector_false_pass_rust_extern_self import SRC, B, forbid

pytestmark = pytest.mark.skipif(shutil.which("cargo") is None, reason="rustc is the oracle")

LIB = "pub mod b;\npub mod x;\npub mod y;\npub mod z;\n"
GLOB_X = "use crate::y::*;\npub fn f() {\n    b::g();\n}\n"
FILL = "#[macro_export]\nmacro_rules! fill {\n    ($p:path) => {\n        pub use $p;\n    };\n}\n"
DEP = {
    "crates/app/Cargo.toml": APP + 'dep = { path = "../../vendor/dep" }\n',
    "vendor/dep/Cargo.toml": '[package]\nname = "dep"\nversion = "0.0.0"\nedition = "2021"\n',
    "vendor/dep/src/lib.rs": FILL,
}
CASES = {
    "a repetition": {
        "y.rs": "macro_rules! mk {\n    ($($t:ident)*) => { $(pub use crate::$t;)* };\n}\nmk!(b);\n"
    },
    "a macro that calls a macro": {
        "y.rs": "macro_rules! inner {\n    () => { pub use crate::b; };\n}\n"
        "macro_rules! outer {\n    () => { inner!(); };\n}\nouter!();\n"
    },
    "a macro that defines a macro": {
        "y.rs": "macro_rules! gen {\n    () => {\n"
        "        macro_rules! mk { () => { pub use crate::b; }; }\n        mk!();\n    };\n}\n"
        "gen!();\n"
    },
    "a crate macro named like a std macro": {
        "y.rs": "macro_rules! format {\n    () => { pub use crate::b; };\n}\nformat!();\n"
    },
    "an exported macro with $crate": {
        "z.rs": "#[macro_export]\nmacro_rules! mk {\n    () => { pub use $crate::b; };\n}\n",
        "y.rs": "crate::mk!();\n",
    },
    "a macro of another crate by its path": {"y.rs": "dep::fill!(crate::b);\n"},
    "a macro of another crate through a use": {"y.rs": "use dep::fill;\nfill!(crate::b);\n"},
    "a macro of another crate through macro_use": {
        "lib.rs": "#[macro_use]\nextern crate dep;\n" + LIB,
        "y.rs": "fill!(crate::b);\n",
    },
    "a glob of a glob over a macro call": {
        "z.rs": "macro_rules! mk {\n    () => { pub use crate::b; };\n}\nmk!();\n",
        "y.rs": "pub use crate::z::*;\n",
    },
}


@pytest.mark.parametrize("name", sorted(CASES))
def test_a_pub_use_that_a_macro_writes_never_passes(
    tmp_path: Path, core_binary: Path, capsys: pytest.CaptureFixture[str], name: str
) -> None:
    files = {"lib.rs": LIB, "b.rs": B, "x.rs": GLOB_X, "y.rs": "", "z.rs": "", **CASES[name]}
    sources = {SRC + path: text for path, text in files.items()}
    rules = (*CRATE_RULES, forbid("native.app.x", "native.app.b"))
    root = repository(tmp_path, core_binary, {**DEP, **sources}, rules=rules)
    _rustc_accepts(root)
    result = validate(root, capsys)

    assert statuses(result).get("NO-X-TO-B") in {"UNKNOWN", "FAIL"}, (name, claims(result))
