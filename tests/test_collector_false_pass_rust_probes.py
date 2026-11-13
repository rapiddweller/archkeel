# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""#880: a Rust source that hides an edge must never give a PASS. The probes of the reviews of #916.

Consumer: the default `archkeel validate`, which the Rust core decides (AD-432). Each probe is a
small workspace whose source hid an edge in a review. The core runs its own Rust collector on it.
The expected verdict is FAIL (an edge) or UNKNOWN, never PASS.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from rust_repository import APP, CRATE_RULES, component, repository, rule, statuses, validate

# The false-PASS cases of the reviews of #916 (the Rust collector). The app crate does not require
# the crate `base_crate`, so a path that names it must be a FAIL (an edge) or UNKNOWN, never a PASS.
# The sources are the ones that hid an edge in a review: each family has its own list.
SHADOWED = {
    "module": "pub mod base_crate {}\n#[cfg(test)]\nmod tests { fn t() { base_crate::make(); } }\n",
    "type": "pub struct base_crate;\nmod m { fn t() { base_crate::make(); } }\n",
    "import of a function": "use crate::util::base_crate;\nfn t() { base_crate::make(); }\n",
    "function": "fn base_crate() {}\npub fn run() { base_crate::make(); }\n",
}
MACRO_BODY = {
    "macro argument": "pub fn run() { other::call!(base_crate); }\n",
    "path in a macro": 'pub fn run() { println!("{}", base_crate::make()); }\n',
    "macro_rules": (
        "macro_rules! m { ($c:ident) => { $c::make() }; }\npub fn run() { m!(base_crate); }\n"
    ),
    "raw identifier": "pub fn run() { r#base_crate::make(); }\n",
}
ATTRIBUTE = {
    "string with a path": '#[serde(getter = "base_crate::get")]\npub struct S;\n',
    "string with a name": '#[serde(with = "base_crate")]\npub struct S;\n',
    "attribute argument": "#[other::attr(base_crate)]\npub struct S;\n",
    "doc expression": "#![doc = base_crate::readme!()]\n",
}
RUST_PROBES = {**SHADOWED, **MACRO_BODY, **ATTRIBUTE}


@pytest.mark.parametrize("source", RUST_PROBES.values(), ids=RUST_PROBES.keys())
def test_a_rust_source_that_hides_a_crate_edge_gives_no_pass(
    tmp_path: Path, core_binary: Path, capsys: pytest.CaptureFixture[str], source: str
) -> None:
    parts = (component("base", "base_crate"), component("app", "app"))
    files = {"crates/app/src/lib.rs": source}
    result = validate(repository(tmp_path, core_binary, files, components=parts), capsys)

    assert statuses(result).get("REQUIRES") != "PASS"
    assert result["status"] in {"FAIL", "UNKNOWN"}


# 5b-2c: the module `a` of the app crate must not use the module `b`. Each source below uses `b`
# (a path, a name that hides it, a glob, a macro or a re-export), so the verdict is FAIL, or UNKNOWN
# when the scan cannot say. It is never PASS.
MODULE_LIB = "mod a;\nmod b;\nmod c;\n"
MODULE_FILES = {"crates/app/src/b.rs": "pub fn make() {}\n", "crates/app/src/c.rs": ""}
MODULE_PROBES = {
    "a path in a body": {"a.rs": "pub fn run() { crate::b::make(); }\n"},
    "a use group": {"a.rs": "use crate::{b::make};\npub fn run() { make(); }\n"},
    "a local name": {"a.rs": "use crate::b as local;\npub fn run() { local::make(); }\n"},
    "a glob import": {"a.rs": "use crate::b::*;\npub fn run() { make(); }\n"},
    "a glob of the parent": {"a.rs": "use super::*;\npub fn run() { b::make(); }\n"},
    "a self import": {"a.rs": "use crate::b::{self};\npub fn run() { b::make(); }\n"},
    "super in an inline module": {
        "a.rs": "mod inner { pub fn run() { super::super::b::make(); } }\n"
    },
    "extern crate self": {"a.rs": "extern crate self as me;\npub fn run() { me::b::make(); }\n"},
    "a macro body": {
        "a.rs": "macro_rules! m { () => { crate::b::make() }; }\npub fn run() { m!(); }\n"
    },
    "a macro body of the parent": {
        "lib.rs": "macro_rules! m { () => { crate::b::make() }; }\n" + MODULE_LIB,
        "a.rs": "pub fn run() { m!(); }\n",
    },
    "a relative path in a macro": {
        "a.rs": "macro_rules! m { () => { super::b::make() }; }\npub fn run() { m!(); }\n"
    },
    "a path module": {
        "lib.rs": '#[path = "x.rs"]\nmod a;\nmod b;\nmod c;\n',
        "x.rs": "use crate::b::make;\n",
    },
    "a name declared twice": {"a.rs": "mod b {}\nuse crate::b;\npub fn run() { b::make(); }\n"},
    # A re-exporting module is the dependency (AD-335): the forbidden target of these two is `c`.
    "a re-exporting module is the dependency": {
        "a.rs": "pub use crate::c::make;\n",
        "c.rs": "pub use crate::b::make;\n",
    },
    "a glob of a re-exporting module is the dependency": {
        "a.rs": "use crate::c::*;\npub fn run() { make(); }\n",
        "c.rs": "pub use crate::b::*;\n",
    },
    "edition 2015 use path": {
        "crates/app/Cargo.toml": APP.replace('edition = "2021"\n', ""),
        "a.rs": "use b::make;\n",
    },
    "edition 2015 colon path": {
        "crates/app/Cargo.toml": APP.replace('edition = "2021"\n', ""),
        "a.rs": "pub fn run() { ::b::make(); }\n",
    },
}
RE_EXPORTED = {
    "a re-exporting module is the dependency",
    "a glob of a re-exporting module is the dependency",
}


@pytest.mark.parametrize(("name", "probe"), MODULE_PROBES.items(), ids=MODULE_PROBES.keys())
def test_a_rust_source_that_hides_a_module_edge_gives_no_pass(
    tmp_path: Path,
    core_binary: Path,
    capsys: pytest.CaptureFixture[str],
    name: str,
    probe: dict[str, str],
) -> None:
    files = {"crates/app/src/lib.rs": MODULE_LIB, **MODULE_FILES}
    files.update(
        {
            (file if file.startswith("crates/") else f"crates/app/src/{file}"): text
            for file, text in probe.items()
        }
    )
    # The module `a` uses `c`, which re-exports `b`: the forbidden edge is the one to `c`.
    target = "native.app.c" if name in RE_EXPORTED else "native.app.b"
    forbidden = rule(
        "NO-A-TO-B",
        "forbidden_dependency",
        source="native.app.a",
        target=target,
        include_type_checking=True,
    )
    rules = (*CRATE_RULES, forbidden)
    result = validate(repository(tmp_path, core_binary, files, rules=rules), capsys)

    # An UNKNOWN rule has no status: it is never PASS.
    assert statuses(result).get("NO-A-TO-B") != "PASS"
    assert result["status"] in {"FAIL", "UNKNOWN"}


# #954: a macro defined in `macros` names `b` in its body, and the module `a` calls it. The path
# is a use of `b` by `a`, so a rule that forbids the edge is FAIL. A call that the scan cannot
# place (inside another macro, or by a module path) must give UNKNOWN, never PASS.
EXPANDS = "macro_rules! m { () => { $crate::b::make() }; }\n"
EXPANSION_LIB = "mod macros;\nmod a;\nmod b;\nmod c;\n"
UNPLACED = {
    "a call inside another macro": "pub fn run() { other::wrap! { m!(); } }\n",
    "a call by a module path": "pub fn run() { macros::m!(); }\n",
}
# The body names `b` by a path from the crate name: it needs `extern crate self as app`.
ABSOLUTE_BODY = "extern crate self as app;\nmacro_rules! m { () => { ::app::b::make() }; }\n"


def _expansion(
    tmp_path: Path, binary: Path, capsys: pytest.CaptureFixture[str], files: dict[str, str], *rules
) -> dict[str, object]:
    sources = {"crates/app/src/lib.rs": EXPANSION_LIB, "crates/app/src/macros.rs": EXPANDS}
    sources.update({f"crates/app/src/{name}": text for name, text in files.items()})
    sources.setdefault("crates/app/src/b.rs", "pub fn make() {}\n")
    sources.setdefault("crates/app/src/c.rs", "")
    return validate(repository(tmp_path, binary, sources, rules=(*CRATE_RULES, *rules)), capsys)


def test_a_module_that_calls_a_macro_uses_the_module_that_its_body_names(
    tmp_path: Path, core_binary: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    forbidden = rule(
        "NO-A-TO-B",
        "forbidden_dependency",
        source="native.app.a",
        target="native.app.b",
        include_type_checking=True,
    )
    result = _expansion(
        tmp_path, core_binary, capsys, {"a.rs": "pub fn run() { m!(); }\n"}, forbidden
    )

    assert statuses(result)["NO-A-TO-B"] == "FAIL"


def test_a_cycle_through_the_expansion_of_a_macro_is_found(
    tmp_path: Path, core_binary: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    cycles = rule("MODULE-CYCLES", "no_component_cycles", level="module")
    files = {"a.rs": "pub fn run() { m!(); }\n", "b.rs": "use crate::a;\npub fn make() {}\n"}
    result = _expansion(tmp_path, core_binary, capsys, files, cycles)

    assert statuses(result)["MODULE-CYCLES"] == "FAIL"


def test_the_template_of_a_macro_is_no_edge_of_its_module_in_a_cycle_rule(
    tmp_path: Path, core_binary: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`macros` holds a template: only a call puts the path in a module that compiles it."""
    cycles = rule("MODULE-CYCLES", "no_component_cycles", level="module")
    files = {"a.rs": "", "b.rs": "pub fn make() {}\nfn t() { m!(); }\n"}
    result = _expansion(tmp_path, core_binary, capsys, files, cycles)

    assert statuses(result)["MODULE-CYCLES"] == "PASS"


def test_a_macro_body_path_from_the_crate_name_gives_no_pass(
    tmp_path: Path, core_binary: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    forbidden = rule(
        "NO-A-TO-B",
        "forbidden_dependency",
        source="native.app.a",
        target="native.app.b",
        include_type_checking=True,
    )
    files = {"macros.rs": ABSOLUTE_BODY, "a.rs": "pub fn run() { m!(); }\n"}
    result = _expansion(tmp_path, core_binary, capsys, files, forbidden)

    assert statuses(result).get("NO-A-TO-B") != "PASS"
    assert result["status"] in {"FAIL", "UNKNOWN"}


@pytest.mark.parametrize("source", UNPLACED.values(), ids=UNPLACED.keys())
def test_a_macro_call_that_the_scan_cannot_place_gives_no_pass(
    tmp_path: Path, core_binary: Path, capsys: pytest.CaptureFixture[str], source: str
) -> None:
    forbidden = rule(
        "NO-A-TO-B",
        "forbidden_dependency",
        source="native.app.a",
        target="native.app.b",
        include_type_checking=True,
    )
    result = _expansion(tmp_path, core_binary, capsys, {"a.rs": source}, forbidden)

    assert statuses(result).get("NO-A-TO-B") != "PASS"
    assert result["status"] in {"FAIL", "UNKNOWN"}


# The review of head 1114d663: three ways to use the crate `base_crate` that a path in source does
# not show. Each compiles, and the app crate declares the dependency on `base` but its contract
# does not require it. A crate can use another crate only if its Cargo.toml declares it, so the
# declared dependency is an edge, and the verdict is FAIL.
MANIFEST = '[package]\nname = "{name}"\nversion = "0.0.0"\nedition = "2021"\n{rest}'
BASE_DEP = 'base-crate = { path = "../base" }\n'
PROC_MACRO = (
    "use proc_macro::TokenStream;\n"
    "#[proc_macro_derive(D)]\n"
    "pub fn d(_: TokenStream) -> TokenStream {\n"
    '    "fn g() { ::base_crate::make() }".parse().unwrap()\n'
    "}\n"
)
EXPORTED_MACRO = "#[macro_export]\nmacro_rules! call_b { () => { ::base_crate::make() } }\n"


def _crate(name: str, rest: str = "") -> dict[str, str]:
    return {f"crates/{name}/Cargo.toml": MANIFEST.format(name=name, rest=rest)}


def _app(manifest: str, **sources: str) -> dict[str, str]:
    """The app crate: its manifest, and its sources by name (`src__lib` is `src/lib.rs`)."""
    files = {"crates/app/Cargo.toml": MANIFEST.format(name="app", rest=manifest)}
    files.update({f"crates/app/{key.replace('__', '/')}.rs": text for key, text in sources.items()})
    return files


PROC_FILES = {
    "crates/Cargo.toml": '[workspace]\nmembers = ["base", "app", "d"]\n',
    **_crate("d", "[lib]\nproc-macro = true\n"),
    "crates/d/src/lib.rs": PROC_MACRO,
    **_app(
        f'[dependencies]\n{BASE_DEP}d = {{ path = "../d" }}\n',
        src__lib="#[derive(d::D)]\npub struct S;\n",
    ),
}
VENDOR_DEPS = f'[dependencies]\n{BASE_DEP}c = {{ path = "../../../vendor/c" }}\n'
VENDOR_FILES = {
    "vendor/c/Cargo.toml": MANIFEST.format(name="c", rest=""),
    "vendor/c/src/lib.rs": EXPORTED_MACRO,
}
NO_BASE = ("[dev_dependencies]\n", "[build_dependencies]\n")
HIDDEN_DEPENDENCY = {
    "a proc-macro crate builds the path from a string": (PROC_FILES, ("base", "d", "app"), ("d",)),
    "an exported macro of a crate outside the scan": (
        {**VENDOR_FILES, **_app(VENDOR_DEPS, src__lib="pub fn f() { c::call_b!(); }\n")},
        ("base", "app"),
        (),
    ),
    "a derive helper of a crate outside the scan": (
        {
            **VENDOR_FILES,
            **_app(VENDOR_DEPS, src__lib="#[derive(c::D)]\n#[base_crate]\npub struct S;\n"),
        },
        ("base", "app"),
        (),
    ),
    "dev_dependencies with an underscore": (
        _app(
            f"[dev_dependencies]\n{BASE_DEP}",
            src__lib="",
            tests__t="fn t() { base_crate::make(); }\n",
        ),
        ("base", "app"),
        (),
    ),
    "build_dependencies with an underscore": (
        _app(
            f"[build_dependencies]\n{BASE_DEP}",
            src__lib="",
            build="fn main() { base_crate::make(); }\n",
        ),
        ("base", "app"),
        (),
    ),
    "a declared dependency that no source uses": (
        _app(f"[dependencies]\n{BASE_DEP}", src__lib="pub fn f() {}\n"),
        ("base", "app"),
        (),
    ),
}


@pytest.mark.parametrize(
    ("files", "labels", "app_requires"),
    HIDDEN_DEPENDENCY.values(),
    ids=HIDDEN_DEPENDENCY.keys(),
)
def test_a_dependency_that_source_hides_is_a_declared_edge_and_fails(
    tmp_path: Path,
    core_binary: Path,
    capsys: pytest.CaptureFixture[str],
    files: dict[str, str],
    labels: tuple[str, ...],
    app_requires: tuple[str, ...],
) -> None:
    crates = {"base": "base_crate", "d": "d", "app": "app"}
    parts = tuple(
        component(label, crates[label], app_requires if label == "app" else ()) for label in labels
    )
    result = validate(repository(tmp_path, core_binary, files, components=parts), capsys)

    assert statuses(result)["REQUIRES"] == "FAIL"


# Review of #916 (issue #946): each manifest compiles with `cargo build`, and the app crate uses
# `base` without a `requires` entry. A string form that the reader decoded wrongly or dropped hid
# the dependency. The reader now decodes it as Cargo does, so the verdict is FAIL.
ESCAPED = "base\\u002dcrate"
BASE_PATH = 'path = "../base"'
USES_BASE = {"src__lib": "use base_crate::make;\npub fn r() { make(); }\n"}
USES_FOO = {"src__lib": "pub fn r() { foo::make(); }\n"}
STRING_FORMS = {
    "a unicode escape in the key": _app(
        f'[dependencies]\n"{ESCAPED}" = {{ {BASE_PATH} }}\n', **USES_BASE
    ),
    "a unicode escape in package": _app(
        f'[dependencies]\nfoo = {{ package = "{ESCAPED}", {BASE_PATH} }}\n', **USES_FOO
    ),
    "a unicode escape in a workspace rename": {
        "crates/Cargo.toml": (
            '[workspace]\nmembers = ["base", "app"]\n'
            f'[workspace.dependencies]\nfoo = {{ package = "{ESCAPED}", path = "base" }}\n'
        ),
        **_app("[dependencies]\nfoo.workspace = true\n", **USES_FOO),
    },
    "a multi-line basic string in package": _app(
        f'[dependencies]\nfoo = {{ package = """base-crate""", {BASE_PATH} }}\n', **USES_FOO
    ),
    "a multi-line literal string in package": _app(
        f"[dependencies.foo]\npackage = '''base-crate'''\n{BASE_PATH}\n", **USES_FOO
    ),
}
NO_REQUIRES = (component("base", "base_crate"), component("app", "app"))


@pytest.mark.parametrize("files", STRING_FORMS.values(), ids=STRING_FORMS.keys())
def test_a_string_form_of_a_dependency_is_decoded_as_cargo_does_and_fails(
    tmp_path: Path, core_binary: Path, capsys: pytest.CaptureFixture[str], files: dict[str, str]
) -> None:
    result = validate(repository(tmp_path, core_binary, files, components=NO_REQUIRES), capsys)

    assert statuses(result)["REQUIRES"] == "FAIL"


PATH_OUT = '#[path = "../../base/src/lib.rs"]\nmod b;\npub fn r() { b::make(); }\n'


def test_a_path_attribute_into_a_file_of_another_crate_gives_no_pass(
    tmp_path: Path, core_binary: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    files = _app("", src__lib=PATH_OUT)
    result = validate(repository(tmp_path, core_binary, files, components=NO_REQUIRES), capsys)

    assert statuses(result).get("REQUIRES") != "PASS"
    assert result["status"] in {"FAIL", "UNKNOWN"}
