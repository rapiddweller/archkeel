# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""#2107, AD-772, AD-1085: code of `m` runs through a facade that re-exports an item of `m`.

`f` holds `pub use crate::m::T;` (or the function, or a glob). `c` uses the item through `f` and
never writes `m`. Rust runs the code of `m` (the counter is 101). The import edge names the facade
`f`, as AD-772 decides (the facade semantics of an item re-export do not change). So a direct
`forbidden_dependency` `c -> m` is PASS by design, and the contract that wants the facade to be
the only way adds `indirect: true` (AD-1085): that rule is FAIL. A method call on a value of `T`
is a pair gap `c -> m` (UNKNOWN). A path that writes `m` is FAIL in both modes.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest
from corpus_support import commit_tree
from rust_repository import component, repository, rule, statuses, validate

pytestmark = pytest.mark.skipif(shutil.which("cargo") is None, reason="rustc is the oracle")

ATOMIC = "std::sync::atomic"
COUNTER = f"pub static COUNTER: {ATOMIC}::AtomicUsize = {ATOMIC}::AtomicUsize::new(100);\n"
BUMP = f"crate::api::COUNTER.fetch_add(1, {ATOMIC}::Ordering::SeqCst);"
LIB = "pub mod api; pub mod m; pub mod f; pub mod c;\n"
WITNESS = (
    "extern crate probe; fn main() { probe::c::run(); "
    f'println!("{{}}", probe::api::COUNTER.load({ATOMIC}::Ordering::SeqCst)); }}'
)
NEW = f"pub struct T;\nimpl T {{ pub fn new() -> T {{ {BUMP} T }} }}\n"

# The sources of m, f and c.
FORMS = {
    "associated function": (
        NEW,
        "pub use crate::m::T;\n",
        "use crate::f::T;\npub fn run() { let _t = T::new(); }\n",
    ),
    "function": (
        f"pub fn helper() {{ {BUMP} }}\n",
        "pub use crate::m::helper;\n",
        "use crate::f::helper;\npub fn run() { helper(); }\n",
    ),
    "glob": (
        NEW,
        "pub use crate::m::*;\n",
        "use crate::f::*;\npub fn run() { let _t = T::new(); }\n",
    ),
    "method call": (
        f"pub struct T;\nimpl T {{ pub fn hit(&self) {{ {BUMP} }} }}\n",
        "pub use crate::m::T;\npub fn make() -> T { T }\n",
        "pub fn run() { crate::f::make().hit(); }\n",
    ),
    "written m": (f"pub fn helper() {{ {BUMP} }}\n", "", "pub fn run() { crate::m::helper(); }\n"),
}
# The status of the direct rule and of the indirect rule.
VERDICTS = {
    "associated function": ("PASS", "FAIL"),
    "function": ("PASS", "FAIL"),
    "glob": ("PASS", "FAIL"),
    "method call": ("UNKNOWN", "FAIL"),
    "written m": ("FAIL", "FAIL"),
}
LAYOUT = (
    ("app", ["native.app", "native.app.cargo_toml", "native.app.api"], ()),
    ("m", ["native.app.m"], ("app",)),
    ("f", ["native.app.f"], ("m", "app")),
    ("c", ["native.app.c"], ("f", "m", "app")),
)


def _root(tmp_path: Path, binary: Path, form: str, indirect: bool) -> Path:
    m, f, c = FORMS[form]
    sources = {"lib.rs": LIB, "api.rs": COUNTER, "m.rs": m, "f.rs": f, "c.rs": c}
    files = {f"crates/app/src/{name}": text for name, text in sources.items()}
    parts = tuple(
        {**component(label, "app", needs), "packages": [], "exact_modules": modules}
        for label, modules, needs in LAYOUT
    )
    forbidden = rule(
        "NO-C-TO-M",
        "forbidden_dependency",
        source="native.app.c",
        target="native.app.m",
        target_match="exact",
        include_type_checking=True,
        **({"indirect": True} if indirect else {}),
    )
    root = repository(tmp_path / "repo", binary, files, parts, (forbidden,), type_reach=False)
    path = root / "architecture-contract.json"
    contract = json.loads(path.read_text())
    contract["schema_version"] = "3.21.0"
    path.write_text(json.dumps(contract))
    commit_tree(root)
    return root


def _counter(tmp_path: Path, root: Path) -> str:
    """The counter after `c::run()` in a program that rustc built from the plant."""
    library = tmp_path / "libprobe.rlib"
    source = root / "crates/app/src/lib.rs"
    build = ["rustc", "--edition=2021", "--crate-type", "rlib", "--crate-name", "probe"]
    subprocess.run([*build, source, "-o", library], check=True)
    exe = tmp_path / "witness"
    link: list[str | Path] = [
        "rustc",
        "-L",
        f"dependency={tmp_path}",
        "--extern",
        f"probe={library}",
        "-",
        "-o",
        exe,
    ]
    subprocess.run(link, input=WITNESS, text=True, check=True)
    return subprocess.run([str(exe)], capture_output=True, text=True, check=True).stdout.strip()


@pytest.mark.parametrize("indirect", [False, True], ids=["direct", "indirect"])
@pytest.mark.parametrize("form", list(FORMS))
def test_code_of_m_runs_through_a_facade_and_only_the_indirect_rule_fails(
    tmp_path: Path, release_core: Path, form: str, indirect: bool
) -> None:
    root = _root(tmp_path, release_core, form, indirect)
    assert _counter(tmp_path, root) == "101", "the plant must run the code of m"
    assert statuses(validate(root))["NO-C-TO-M"] == VERDICTS[form][indirect]
