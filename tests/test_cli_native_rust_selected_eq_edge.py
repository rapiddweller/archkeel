# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-1136: a `PartialEq::eq` call with a compiler-selected impl is an edge.

`a` compares two values with `==`. The factory `c` makes the values. `b` defines the type and its
`PartialEq`, which counts its calls. `a` writes no name of `b`. The compiler resolves the call to
the `eq` of `b`, so `a -> b` is a proven dependency. A contract that does not allow it fails.

A site that the driver does not resolve stays a gap. Here it is a `Display` impl in `d`, and the
pair `a -> d` stays UNKNOWN. The oracle is `cargo run`: the counter shows that the impl runs.
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

NO_A_TO_B = rule(
    "NO-A-TO-B",
    "forbidden_dependency",
    source="native.app.a",
    target="native.app.b",
    include_type_checking=True,
)
NO_NAME_Y = {
    **NO_A_TO_B,
    "id": "NO-NAME-Y",
    "target_symbol": "Y",
    "source_symbol_only": True,
}
NO_A_TO_D = {**NO_A_TO_B, "id": "NO-A-TO-D", "target": "native.app.d"}
MODULE_CYCLE = rule("MODULE-CYCLE", "no_component_cycles", level="module")

LIB = "pub mod a;\npub mod b;\npub mod c;\npub mod d;\n"
B = """use std::sync::atomic::{AtomicUsize, Ordering};

static HITS: AtomicUsize = AtomicUsize::new(0);

pub struct Y;

impl PartialEq for Y {
    fn eq(&self, _other: &Y) -> bool {
        HITS.fetch_add(1, Ordering::SeqCst);
        true
    }
}

pub fn hits() -> usize {
    HITS.load(Ordering::SeqCst)
}
"""
D = """pub struct Z;

impl std::fmt::Display for Z {
    fn fmt(&self, f: &mut std::fmt::Formatter) -> std::fmt::Result {
        write!(f, "z")
    }
}
"""
C = """pub fn make() -> crate::b::Y {
    crate::b::Y
}

pub fn made() -> crate::d::Z {
    crate::d::Z
}
"""
A = """pub fn same() -> bool {
    crate::c::make() == crate::c::make()
}

pub fn shown() -> String {
    format!("{}", crate::c::made())
}
"""
BACK = A + "\npub fn back() -> bool {\n    crate::a::same()\n}\n"
# The oracle is outside the scan roots: it only runs the code of the fixture.
ORACLE = {
    "oracle/Cargo.toml": '[package]\nname = "oracle"\nversion = "0.0.0"\nedition = "2021"\n'
    '[dependencies]\napp = { path = "../crates/app" }\n[workspace]\n',
    "oracle/src/main.rs": "fn main() {\n    assert!(app::a::same());\n"
    '    println!("{}", app::b::hits());\n}\n',
}


def _app(files: dict[str, str]) -> dict[str, str]:
    return {f"crates/app/src/{name}": text for name, text in files.items()}


SOURCES = {
    **_app({"lib.rs": LIB, "b.rs": B, "c.rs": C, "d.rs": D, "a.rs": A}),
    **ORACLE,
}


def _parts(
    a_needs: tuple[str, ...], ports: dict[str, list[str]] | None = None
) -> tuple[dict[str, Any], ...]:
    """Each module of the app is a component, so each crossing needs a `requires`."""

    def part(label: str, modules: list[str], needs: tuple[str, ...]) -> dict[str, Any]:
        found = {**component(label, "app", needs), "packages": [], "exact_modules": modules}
        if label == "a":
            for entry in found["requires"]:
                if entry["component"] in (ports or {}):
                    entry["through"] = ports[entry["component"]] if ports else []
        return found

    return (
        component("base", "base_crate"),
        part("root", ["native.app", "native.app.cargo_toml"], ("base", "a", "b", "c", "d")),
        part("a", ["native.app.a"], a_needs),
        part("b", ["native.app.b"], ()),
        part("c", ["native.app.c"], ("b", "d")),
        part("d", ["native.app.d"], ()),
    )


def _scan(
    tmp_path: Path,
    core: Path,
    monkeypatch: pytest.MonkeyPatch,
    a_needs: tuple[str, ...] = ("c",),
    files: dict[str, str] | None = None,
    rules: tuple[dict[str, Any], ...] = (),
    ports: dict[str, list[str]] | None = None,
) -> tuple[Path, dict[str, Any]]:
    monkeypatch.setenv("ARCHKEEL_FACTS_CACHE", str(tmp_path / "cache"))
    root = repository(
        tmp_path / "repo",
        core,
        {**SOURCES, **(files or {})},
        components=_parts(a_needs, ports),
        rules=(*CRATE_RULES[1:], *rules),
        type_reach=True,
    )
    return root, validate(root)


def _cargo_run(root: Path) -> str:
    env = {**os.environ, "CARGO_TARGET_DIR": str(root.parent / "target")}
    manifest = root / "oracle/Cargo.toml"
    command = ["cargo", "run", "--quiet", "--offline", "--manifest-path", str(manifest)]
    done = subprocess.run(command, capture_output=True, text=True, env=env, check=False)
    assert done.returncode == 0, done.stderr
    return done.stdout.strip()


def test_the_selected_eq_runs_and_the_contract_that_forbids_it_fails(
    tmp_path: Path, release_core: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, result = _scan(tmp_path, release_core, monkeypatch, rules=(NO_A_TO_B,))
    assert _cargo_run(root) == "1", "the selected impl of b runs once"
    found = statuses(result)
    assert found["NO-A-TO-B"] == "FAIL", result["frame"]["collection_gaps"]
    assert found["REQUIRES"] == "FAIL", "a -> b crosses components with no requires"


def test_the_violation_cites_the_call_of_the_compiler(
    tmp_path: Path, release_core: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, result = _scan(tmp_path, release_core, monkeypatch, rules=(NO_A_TO_B,))
    rows = result["frame"]["details"]["NO-A-TO-B"]
    assert {(row["source"], row["target"]) for row in rows} == {("native.app.a", "native.app.b")}
    [row] = rows
    cited = {
        result["frame"]["locations"][evidence]["path"]: result["frame"]["locations"][evidence][
            "line"
        ]
        for evidence in row["evidence"]
    }
    assert cited == {"crates/app/src/a.rs": 2}, "the call `==` in a.rs, line 2"


def test_a_contract_that_allows_the_edge_passes(
    tmp_path: Path, release_core: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, result = _scan(tmp_path, release_core, monkeypatch, a_needs=("c", "b", "d"))
    assert statuses(result)["REQUIRES"] == "PASS", result["frame"]["collection_gaps"]


def test_a_rule_that_counts_written_names_ignores_the_compiler_edge(
    tmp_path: Path, release_core: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AD-924: execution alone is no name. `a` never writes `Y`, so a rule of names passes."""
    _, result = _scan(tmp_path, release_core, monkeypatch, rules=(NO_NAME_Y,))
    assert statuses(result)["NO-NAME-Y"] == "PASS"


def test_a_symbol_port_keeps_the_edge_unknown(
    tmp_path: Path, release_core: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The compiler names the module of the impl, not a symbol. A symbol port can permit it."""
    ports = {"b": ["native.app.b:Y"]}
    _, result = _scan(tmp_path, release_core, monkeypatch, a_needs=("c", "b", "d"), ports=ports)
    assert statuses(result)["REQUIRES"] == "UNKNOWN"


def test_a_symbol_port_at_a_parent_module_keeps_the_edge_unknown(
    tmp_path: Path, release_core: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A name can be published by a parent module and defined in the module of the impl."""
    ports = {"b": ["native.app:Y"]}
    _, result = _scan(tmp_path, release_core, monkeypatch, a_needs=("c", "b", "d"), ports=ports)
    assert statuses(result)["REQUIRES"] == "UNKNOWN"


def test_a_facade_port_keeps_the_impl_in_another_module_unknown(
    tmp_path: Path, release_core: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The entry for `b` has a port that misses the impl module: a facade can publish the type."""
    ports = {"b": ["native.app.c"]}
    _, result = _scan(tmp_path, release_core, monkeypatch, a_needs=("c", "b", "d"), ports=ports)
    assert statuses(result)["REQUIRES"] == "UNKNOWN"


def test_a_module_port_that_covers_the_impl_passes(
    tmp_path: Path, release_core: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ports = {"b": ["native.app.b"], "d": ["native.app.d"]}
    _, result = _scan(tmp_path, release_core, monkeypatch, a_needs=("c", "b", "d"), ports=ports)
    assert statuses(result)["REQUIRES"] == "PASS"


def test_a_site_that_the_compiler_did_not_resolve_stays_unknown(
    tmp_path: Path, release_core: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`a` formats a value of `d` with `Display`: no compiler fact, so the pair `a -> d` is open."""
    _, result = _scan(tmp_path, release_core, monkeypatch, rules=(NO_A_TO_B, NO_A_TO_D))
    found = statuses(result)
    assert found["NO-A-TO-B"] == "FAIL"
    assert found["NO-A-TO-D"] == "UNKNOWN"


def test_a_return_edge_closes_a_cycle_with_the_edge_of_the_compiler(
    tmp_path: Path, release_core: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    files = {
        "crates/app/src/b.rs": B + "\npub fn back() -> bool {\n    crate::a::same()\n}\n",
    }
    _, result = _scan(
        tmp_path,
        release_core,
        monkeypatch,
        a_needs=("c", "b", "d"),
        files=files,
        rules=(MODULE_CYCLE,),
    )
    assert statuses(result)["MODULE-CYCLE"] == "FAIL", result["frame"]["collection_gaps"]


def test_a_derived_partial_eq_is_selected_like_a_written_one(
    tmp_path: Path, release_core: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    derived = "#[derive(PartialEq)]\npub struct Y;\n\npub fn hits() -> usize {\n    0\n}\n"
    files = {"crates/app/src/b.rs": derived}
    _, result = _scan(tmp_path, release_core, monkeypatch, files=files, rules=(NO_A_TO_B,))
    assert statuses(result)["NO-A-TO-B"] == "FAIL"


def test_a_call_behind_one_feature_stays_open(
    tmp_path: Path, release_core: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One configuration builds the call and another does not. Two edges of a cycle need one
    configuration, so a site that the matrix does not hold everywhere gives no edge."""
    gated = '#[cfg(feature = "hot")]\n' + A.split("\n\n")[0] + "\n"
    manifest = (
        '[package]\nname = "app"\nversion = "0.0.0"\nedition = "2021"\n'
        '[features]\nhot = []\n[dependencies]\nbase-crate = { path = "../base" }\n'
    )
    files = {"crates/app/src/a.rs": gated, "crates/app/Cargo.toml": manifest}
    _, result = _scan(tmp_path, release_core, monkeypatch, files=files, rules=(NO_A_TO_B,))
    assert statuses(result)["NO-A-TO-B"] == "UNKNOWN"


NO_SITE = {
    "a value that is only held": {
        "a.rs": "pub fn same() -> bool {\n    let _y = crate::c::make();\n    true\n}\n"
    },
    "a comparison through references": {
        "a.rs": "pub fn same() -> bool {\n    &crate::c::make() == &crate::c::make()\n}\n"
    },
    "a generic helper": {
        "a.rs": "fn eq_of<T: PartialEq>(x: &T, y: &T) -> bool {\n    x == y\n}\n\n"
        "pub fn same() -> bool {\n    eq_of(&crate::c::make(), &crate::c::make())\n}\n"
    },
    "a comparison in an inline test module": {
        "a.rs": "pub fn same() -> bool {\n    true\n}\n\n#[cfg(test)]\nmod tests {\n"
        "    #[test]\n    fn same_values() {\n"
        "        assert!(crate::c::make() == crate::c::make());\n    }\n}\n"
    },
    "a drop": {
        "b.rs": B + "\nimpl Drop for Y {\n    fn drop(&mut self) {}\n}\n",
        "a.rs": "pub fn same() -> bool {\n    let _y = crate::c::make();\n    true\n}\n",
    },
    "a boxed trait object": {
        "c.rs": C + "\npub trait Same {\n    fn same(&self) -> bool;\n}\n\n"
        "impl Same for crate::b::Y {\n    fn same(&self) -> bool {\n"
        "        *self == crate::b::Y\n    }\n}\n\n"
        "pub fn boxed() -> Box<dyn Same> {\n    Box::new(crate::b::Y)\n}\n",
        "a.rs": "pub fn same() -> bool {\n    crate::c::boxed().same()\n}\n",
    },
}


@pytest.mark.parametrize("name", list(NO_SITE))
def test_a_form_without_a_resolved_site_is_no_proven_dependency(
    tmp_path: Path, release_core: Path, monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    """The driver reads a concrete `eq` call only. A form that it cannot resolve stays a gap."""
    files = _app(NO_SITE[name])
    _, result = _scan(tmp_path, release_core, monkeypatch, files=files, rules=(NO_A_TO_B,))
    assert statuses(result)["NO-A-TO-B"] != "FAIL"


FACADE_SOURCES = {
    **ORACLE,
    **_app(
        {
            "lib.rs": "pub mod a;\npub mod b;\npub mod d;\n",
            "d.rs": B,
            "b.rs": "pub use crate::d::{hits, Y};\n\npub fn make() -> Y {\n    Y\n}\n",
            "a.rs": "pub fn same() -> bool {\n    crate::b::make() == crate::b::make()\n}\n",
        }
    ),
}


def _facade_parts(a_entries: tuple[str, ...]) -> tuple[dict[str, Any], ...]:
    def part(label: str, modules: list[str], needs: tuple[str, ...]) -> dict[str, Any]:
        return {**component(label, "app", needs), "packages": [], "exact_modules": modules}

    found = (
        component("base", "base_crate"),
        part("root", ["native.app", "native.app.cargo_toml"], ("base", "a", "b", "d")),
        part("a", ["native.app.a"], a_entries),
        part("b", ["native.app.b"], ("d",)),
        part("d", ["native.app.d"], ()),
    )
    for entry in found[2]["requires"]:
        entry["through"] = ["native.app.b"]
    return found


def test_an_impl_of_a_type_that_an_allowed_facade_re_exports_is_unknown(
    tmp_path: Path, release_core: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`Y` and its `eq` live in `d`. The facade `b` re-exports `Y`; `a` may use `b` only (#2069)."""
    monkeypatch.setenv("ARCHKEEL_FACTS_CACHE", str(tmp_path / "cache"))
    root = repository(
        tmp_path / "repo",
        release_core,
        FACADE_SOURCES,
        components=_facade_parts(("b",)),
        rules=(*CRATE_RULES[1:],),
        type_reach=True,
    )
    assert _cargo_run(root) == "1", "the selected impl of d runs"
    assert statuses(validate(root))["REQUIRES"] == "UNKNOWN"


def test_an_impl_that_no_allowed_route_publishes_still_fails(
    tmp_path: Path, release_core: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The same code, but `a` has no entry for `b`: no allowed facade re-exports the type."""
    monkeypatch.setenv("ARCHKEEL_FACTS_CACHE", str(tmp_path / "cache"))
    root = repository(
        tmp_path / "repo",
        release_core,
        FACADE_SOURCES,
        components=_facade_parts(()),
        rules=(*CRATE_RULES[1:],),
        type_reach=True,
    )
    assert statuses(validate(root))["REQUIRES"] == "FAIL"
