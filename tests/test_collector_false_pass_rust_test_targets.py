# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""#880: the Rust collector reads test targets and the macros of function bodies, and hides no edge.

Consumer: `archkeel validate`. A forbidden edge in an integration test, a bench or an example
is FAIL, or the request leaves the target out and says so. A forbidden path in a macro of a
function body is FAIL. A call that sees two macros of one name is never PASS.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from core_support import core_binary
from rust_repository import CRATE_RULES, claims, repository, rule, statuses, validate

__all__ = ["core_binary"]

USE_BASE = "use base_crate::make;\n"
NO_BASE = "NO-TEST-TO-BASE"
NO_B = "NO-A-TO-B"

TEST_TARGETS = {
    "an integration test with its own directory": "crates/app/tests/it/main.rs",
    "a module of that integration test": "crates/app/tests/it/helper.rs",
    "an integration test file": "crates/app/tests/single.rs",
    "a bench": "crates/app/benches/speed.rs",
    "an example in its own directory": "crates/app/examples/demo/main.rs",
}
MODULE_OF = {
    "crates/app/tests/it/main.rs": "native.app.test_it",
    "crates/app/tests/it/helper.rs": "native.app.test_it.helper",
    "crates/app/tests/single.rs": "native.app.test_single",
    "crates/app/benches/speed.rs": "native.app.bench_speed",
    "crates/app/examples/demo/main.rs": "native.app.example_demo",
}


def _files(path: str) -> dict[str, str]:
    files = {path: USE_BASE}
    if path.endswith("helper.rs"):
        files["crates/app/tests/it/main.rs"] = "mod helper;\n"
    return files


def _exclude_tests(root: Path) -> None:
    with (root / "archkeel.toml").open("a") as config:
        config.write("exclude_test_sources = true\n")
    for args in (["add", "-A"], ["-c", "commit.gpgsign=false", "commit", "-q", "-m", "exclude"]):
        subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)


@pytest.mark.parametrize("path", TEST_TARGETS.values(), ids=TEST_TARGETS.keys())
def test_a_forbidden_edge_in_a_test_target_is_fail(
    tmp_path: Path, core_binary: Path, capsys: pytest.CaptureFixture[str], path: str
) -> None:
    forbidden = rule(
        NO_BASE,
        "forbidden_dependency",
        source=MODULE_OF[path],
        target="native.base_crate",
        include_type_checking=True,
    )
    root = repository(tmp_path, core_binary, _files(path), rules=(*CRATE_RULES, forbidden))
    result = validate(root, capsys)

    assert statuses(result).get(NO_BASE) == "FAIL", claims(result)
    reasons = [gap["reason"] for gap in result["frame"]["collection_gaps"]]
    assert not [reason for reason in reasons if "no module tree" in reason], reasons


@pytest.mark.parametrize("path", TEST_TARGETS.values(), ids=TEST_TARGETS.keys())
def test_a_request_that_excludes_tests_leaves_a_test_target_out_without_a_gap(
    tmp_path: Path, core_binary: Path, capsys: pytest.CaptureFixture[str], path: str
) -> None:
    forbidden = rule(
        NO_BASE,
        "forbidden_dependency",
        source=MODULE_OF[path],
        target="native.base_crate",
        include_type_checking=True,
    )
    root = repository(tmp_path, core_binary, _files(path), rules=(*CRATE_RULES, forbidden))
    _exclude_tests(root)
    result = validate(root, capsys)

    # The rule names a module that the request left out: the core decides nothing, never PASS.
    assert set(statuses(result).values()) == {"UNKNOWN"}
    assert f"{NO_BASE}: incomplete scope: the rule {NO_BASE} selects no module" in claims(result)
    reasons = [gap["reason"] for gap in result["frame"]["collection_gaps"]]
    assert not [reason for reason in reasons if "no module tree" in reason], reasons


LOCAL_MACRO = "fn t() {{\n    macro_rules! m {{ () => {{ {body} }}; }}\n    m!();\n}}\n"
MACRO_PROBES = {
    "a macro of a function body names a forbidden path": (
        {"lib.rs": "mod a;\nmod b;\n", "a.rs": LOCAL_MACRO.format(body="crate::b::make()")},
        "FAIL",
    ),
    "a second function holds a macro of the same name": (
        {
            "lib.rs": "mod a;\nmod b;\nmod c;\n",
            "a.rs": LOCAL_MACRO.format(body="crate::b::make()")
            + LOCAL_MACRO.format(body="crate::c::make()").replace("fn t()", "fn u()"),
            "c.rs": "pub fn make() {}\n",
        },
        "FAIL",
    ),
    "a nested function of the body calls the macro": (
        {
            "lib.rs": "mod a;\nmod b;\n",
            "a.rs": "fn f() {\n    macro_rules! m { () => { crate::b::make() }; }\n"
            "    fn g() { m!(); }\n}\n",
        },
        "FAIL",
    ),
    "a closure of the body calls the macro": (
        {
            "lib.rs": "mod a;\nmod b;\n",
            "a.rs": "fn f() {\n    macro_rules! m { () => { crate::b::make() }; }\n"
            "    let c = || { m!(); };\n    c();\n}\n",
        },
        "FAIL",
    ),
    "a later definition of the name does not hide the earlier one": (
        {
            "lib.rs": "mod a;\nmod b;\nmod c;\n",
            "a.rs": "fn f() {\n    macro_rules! m { () => { crate::b::make() }; }\n    m!();\n"
            "    macro_rules! m { () => { crate::c::make() }; }\n}\n",
            "c.rs": "pub fn make() {}\n",
        },
        "FAIL",
    ),
    "a crate-wide macro of the same name is also in scope": (
        {
            "lib.rs": "mod a;\nmod b;\n",
            "a.rs": LOCAL_MACRO.format(body="crate::b::make()"),
            "b.rs": "pub fn make() {}\nmacro_rules! m { () => {}; }\n",
        },
        "",
    ),
}


@pytest.mark.parametrize(("files", "expected"), MACRO_PROBES.values(), ids=MACRO_PROBES.keys())
def test_a_macro_of_a_function_body_never_hides_its_path(
    tmp_path: Path,
    core_binary: Path,
    capsys: pytest.CaptureFixture[str],
    files: dict[str, str],
    expected: str,
) -> None:
    sources = {f"crates/app/src/{name}": text for name, text in files.items()}
    sources.setdefault("crates/app/src/b.rs", "pub fn make() {}\n")
    forbidden = rule(
        NO_B,
        "forbidden_dependency",
        source="native.app.a",
        target="native.app.b",
        include_type_checking=True,
    )
    root = repository(tmp_path, core_binary, sources, rules=(*CRATE_RULES, forbidden))
    result = validate(root, capsys)

    status = statuses(result).get(NO_B)
    assert status != "PASS", claims(result)
    assert (status == expected) if expected else result["status"] in {"FAIL", "UNKNOWN"}
