# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""#984: the Rust collector completes a run on the layouts that it once refused.

Consumer: `archkeel validate`. The layouts are a module directory named `target`, `cfg`
alternatives of one `mod`, and a crate root in a skipped directory. A hidden edge is never PASS.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from rust_repository import (
    APP,
    CRATE_RULES,
    claims,
    component,
    repository,
    rule,
    statuses,
    validate,
)

NO_REQUIRES = (component("base", "base_crate"), component("app", "app"))

# #984: a run must not refuse a module directory named `target` or two `cfg` alternatives of one
# `mod`. The forbidden edge in the `target` module is FAIL. The `cfg` on an alternative stays a gap,
# so a rule about the module is never PASS, whichever file holds the edge (the module of the second
# file is not the module of the rule, and a path to the name reaches only the first file).
ALTERNATIVES = (
    '#[cfg(unix)]\n#[path = "a1.rs"]\nmod a;\n'
    '#[cfg(not(unix))]\n#[path = "a2.rs"]\nmod a;\n'
    "mod b;\nmod c;\n"
)
USE_B = "use crate::b::make;\n"
USE_BASE = "use base_crate::make;\n"
ALT_LIB = {"lib.rs": ALTERNATIVES, "a1.rs": "", "a2.rs": USE_B}
REFUSAL_PROBES = {
    "a module directory named target": (
        {"lib.rs": "mod target;\nmod b;\n", "target/mod.rs": USE_B},
        "native.app.target",
        "native.app.b",
        "FAIL",
    ),
    "the edge is in the first alternative": (
        {**ALT_LIB, "a1.rs": USE_B, "a2.rs": ""},
        "native.app.a",
        "native.app.b",
        "",
    ),
    "the edge is in the second alternative": (ALT_LIB, "native.app.a", "native.app.b", ""),
    "a crate edge is in the second alternative": (
        {**ALT_LIB, "a2.rs": USE_BASE},
        "native.app.a",
        "native.base_crate",
        "",
    ),
    "a path reaches an item that only the second alternative has": (
        {**ALT_LIB, "a2.rs": "pub struct Y;\n", "c.rs": "pub use crate::a::Y;\n"},
        "native.app.c",
        "native.app.a",
        "",
    ),
    "a real module has the name of the second alternative": (
        {**ALT_LIB, "lib.rs": ALTERNATIVES + "mod a_alt2;\n", "a_alt2.rs": USE_B},
        "native.app.a_alt2",
        "native.app.b",
        "",
    ),
}


@pytest.mark.parametrize(
    ("files", "source", "target", "expected"), REFUSAL_PROBES.values(), ids=REFUSAL_PROBES.keys()
)
def test_a_run_that_once_refused_completes_and_never_passes_a_hidden_edge(
    tmp_path: Path,
    core_binary: Path,
    capsys: pytest.CaptureFixture[str],
    files: dict[str, str],
    source: str,
    target: str,
    expected: str,
) -> None:
    sources = {f"crates/app/src/{name}": text for name, text in files.items()}
    sources["crates/app/src/b.rs"] = "pub fn make() {}\n"
    forbidden = rule(
        "NO-A-TO-B",
        "forbidden_dependency",
        source=source,
        target=target,
        include_type_checking=True,
    )
    rules = (*CRATE_RULES, forbidden)
    result = validate(repository(tmp_path, core_binary, sources, rules=rules), capsys)

    status = statuses(result).get("NO-A-TO-B")
    assert status != "PASS", claims(result)
    assert (status == expected) if expected else result["status"] in {"FAIL", "UNKNOWN"}


def test_a_crate_root_in_a_skipped_directory_gives_a_gap_and_no_pass(
    tmp_path: Path, core_binary: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    files = {
        "crates/app/Cargo.toml": APP + '[lib]\npath = "target/lib.rs"\n',
        "crates/app/target/CACHEDIR.TAG": "",
        "crates/app/target/lib.rs": "use base_crate::make;\n",
        "crates/app/src/lib.rs": "",
    }
    result = validate(repository(tmp_path, core_binary, files, components=NO_REQUIRES), capsys)

    assert statuses(result).get("REQUIRES") != "PASS"
    assert result["status"] in {"FAIL", "UNKNOWN"}


# FP-28: `extern crate` of a crate that no manifest declares compiles only through a link that a
# `build.rs` prints. The collector does not read that link, so the name is a gap and never PASS.
UNDECLARED = "extern crate base_crate;\npub fn run() { base_crate::make(); }\n"
UNDECLARED_PROBES = {
    "plain": UNDECLARED,
    "renamed": UNDECLARED.replace("base_crate;", "base_crate as b;"),
}


@pytest.mark.parametrize("source", UNDECLARED_PROBES.values(), ids=UNDECLARED_PROBES.keys())
def test_an_extern_crate_that_no_manifest_declares_gives_no_pass(
    tmp_path: Path, core_binary: Path, capsys: pytest.CaptureFixture[str], source: str
) -> None:
    files = {
        "crates/app/Cargo.toml": APP.split("[dependencies]")[0],
        "crates/app/build.rs": 'fn main() { println!("cargo:rustc-link-search=crate=x"); }\n',
        "crates/app/src/lib.rs": source,
    }
    result = validate(repository(tmp_path, core_binary, files, components=NO_REQUIRES), capsys)

    assert statuses(result).get("REQUIRES") != "PASS", claims(result)
    assert result["status"] in {"FAIL", "UNKNOWN"}
