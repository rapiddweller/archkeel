# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-335, AD-313: a 9.0.0 request makes the Rust collector leave test code out.

Consumer: the host. It sends `scope.exclude_test_sources` and refuses a reply that selects a test
source by its path. The collector owns the `cfg(test)` rule, so the sources below cover each form
of test code of Rust: a sibling file, a `path` file, an inline module with a file, a `#[test]`
function, the `tests/`, `benches/` and `examples/` targets and a production file that only has a
name like a test. A build script stays in scope.
"""

from __future__ import annotations

import json
import subprocess
import zlib
from pathlib import Path
from typing import Any

import pytest

from archkeel.ir.profiles import TEST_SCOPE_LANGUAGES, Language, is_test_source

SOURCES = {
    "crates/Cargo.toml": '[package]\nname = "app"\nbuild = "build.rs"\n'
    '[dev-dependencies]\nserde_json = "1"\n',
    "crates/src/lib.rs": "mod prod_tests;\n#[cfg(test)] mod tests;\n"
    '#[cfg(test)] #[path = "lib_cases.rs"] mod cases;\n#[cfg(test)] mod inline { mod deep; }\n'
    "#[test] fn alone() { let _ = serde_json::json!(1); }\n",
    "crates/src/prod_tests.rs": "pub fn p() {}\n",
    "crates/src/tests.rs": "fn t() { let _ = serde_json::json!(1); }\n",
    "crates/src/lib_cases.rs": "fn c() {}\n",
    "crates/src/inline/deep.rs": "fn d() {}\n",
    "crates/tests/it.rs": "fn i() {}\n",
    "crates/benches/b.rs": "fn b() {}\n",
    "crates/examples/e.rs": "fn e() {}\n",
    "crates/build.rs": "fn main() {}\n",
}
PRODUCTION = ["crates/build.rs", "crates/src/lib.rs", "crates/src/prod_tests.rs"]


def _reply(root: Path, binary: Path, *, exclude: bool) -> dict[str, Any]:
    for name, text in SOURCES.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(text)
    request = {
        "protocol_version": "9.0.0",
        "snapshot": {"root": str(root), "git_head": "a" * 40, "dirty": False},
        "scope": {"roots": ["crates"], "namespace": "native", "exclude_test_sources": exclude},
        "resolver": {"language": "rust"},
    }
    done = subprocess.run(
        [str(binary)], input=json.dumps(request).encode(), capture_output=True, check=True
    )
    reply: dict[str, Any] = json.loads(zlib.decompress(done.stdout))
    return reply


def test_an_excluding_request_selects_only_production_files(
    tmp_path: Path, rust_binary: Path
) -> None:
    facts = _reply(tmp_path, rust_binary, exclude=True)["facts"]

    selected = [rel for rel in facts["coverage"]["selected_files"] if rel.endswith(".rs")]
    assert selected == PRODUCTION
    assert [item["rel_path"] for item in facts["files"] if item["rel_path"].endswith(".rs")] == (
        PRODUCTION
    )
    assert facts["coverage"]["gaps"] == []
    # The host refuses a reply that selects a test source, so no selected file may be one.
    assert not [rel for rel in selected if is_test_source(rel, Language.RUST)]


def test_a_request_without_the_flag_keeps_the_test_files(tmp_path: Path, rust_binary: Path) -> None:
    facts = _reply(tmp_path, rust_binary, exclude=False)["facts"]

    selected = [rel for rel in facts["coverage"]["selected_files"] if rel.endswith(".rs")]
    assert selected == sorted(rel for rel in SOURCES if rel.endswith(".rs"))


def test_the_host_sends_the_flag_for_rust() -> None:
    assert Language.RUST in TEST_SCOPE_LANGUAGES


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("crates/tests/it.rs", True),
        ("crates/benches/b.rs", True),
        ("crates/examples/e.rs", True),
        ("crates/src/walk_tests.rs", False),
        ("crates/src/lib.rs", False),
    ],
)
def test_the_host_path_check_knows_the_test_directories_of_cargo(path: str, expected: bool) -> None:
    assert is_test_source(path, Language.RUST) is expected
    # Benches and examples are test scope of Rust only.
    assert is_test_source("a/benches/b.py", Language.PYTHON) is False
