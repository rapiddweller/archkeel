# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-382: the rules of native/ that stay tests until a Rust rule kind can say them.

Each rule has its pin on main and a planted violation in a copy of `native/`. A new use fails,
and a use that goes away fails too, so the pin shrinks with the code.
"""

from __future__ import annotations

import json
import shutil
from collections import Counter
from pathlib import Path

import pytest
from native_rules_support import (
    CORE_SIDE,
    language_names,
    production_sources,
    requires_problems,
    system_uses,
)
from rust_source import inline_test_mask, tokenize

ROOT = Path(__file__).parents[1]
NATIVE = ROOT / "native"
CONTRACT = NATIVE / "architecture-contract.json"
# The core binary reads its arguments and standard input, writes standard output and sets its
# exit code; no other production code of the core side names a system path of the scan.
SYSTEM_USES = Counter(
    {
        "core/src/main.rs: std::env": 1,
        "core/src/main.rs: std::process": 1,
        "core/src/main.rs: std::io::stdin": 1,
        "core/src/main.rs: std::io::stdout": 1,
    }
)
# (planted text in native/model/src/lib.rs, the hit that the scan must give)
SYSTEM_FORMS = [
    ('pub fn p() -> bool {\n    std::fs::read("x").is_ok()\n}\n', "std::fs"),
    ("use std::{fs, io};\n", "std::fs"),
    ("use std::{fs as f};\n", "std::fs"),
    ('pub fn p() -> bool {\n    ::std::fs::read("x").is_ok()\n}\n', "std::fs"),
    ('use std;\npub fn p() -> bool {\n    std::fs::read("x").is_ok()\n}\n', "std::fs"),
    ('use std as s;\npub fn p() -> bool {\n    s::env::var("x").is_ok()\n}\n', "std::env"),
    ("extern crate std as k;\npub fn p() {\n    k::process::exit(0);\n}\n", "std::process"),
    ("use std::net::TcpStream;\n", "std::net"),
    ("use std::os::unix::fs::MetadataExt;\n", "std::os"),
    ('pub fn p() -> bool {\n    std::path::Path::new("x").exists()\n}\n', "Path::exists"),
    (
        "pub fn p(x: &std::path::Path) -> bool {\n    x.try_exists().is_ok()\n}\n",
        "Path::try_exists",
    ),
    ("pub fn p(x: &std::path::Path) -> bool {\n    x.is_file()\n}\n", "Path::is_file"),
    ("pub fn p(x: &std::path::Path) -> bool {\n    x.is_dir()\n}\n", "Path::is_dir"),
    ("pub fn p(x: &std::path::Path) -> bool {\n    x.is_symlink()\n}\n", "Path::is_symlink"),
    ("pub fn p(x: &std::path::Path) -> bool {\n    x.metadata().is_ok()\n}\n", "Path::metadata"),
    (
        "pub fn p(x: &std::path::Path) -> bool {\n    x.symlink_metadata().is_ok()\n}\n",
        "Path::symlink_metadata",
    ),
    ("pub fn p(x: &std::path::Path) -> bool {\n    x.read_dir().is_ok()\n}\n", "Path::read_dir"),
    ("pub fn p(x: &std::path::Path) -> bool {\n    x.read_link().is_ok()\n}\n", "Path::read_link"),
    (
        "pub fn p(x: &std::path::PathBuf) -> bool {\n    x.canonicalize().is_ok()\n}\n",
        "Path::canonicalize",
    ),
    (
        "pub fn p(x: &std::path::Path) -> bool {\n    std::path::Path::is_file(x)\n}\n",
        "Path::is_file",
    ),
    ("use std::io;\npub fn p() {\n    let _ = io::stdin();\n}\n", "std::io::stdin"),
    ("pub fn p() {\n    let _ = std::io::stderr();\n}\n", "std::io::stderr"),
    ("use std::io::stdout;\n", "std::io::stdout"),
    ("use std::time::Instant;\n", "std::time::Instant"),
    ("pub fn p() {\n    let _ = std::time::SystemTime::now();\n}\n", "std::time::SystemTime"),
]


def _core_side(tmp_path: Path) -> Path:
    copy = tmp_path / "native"
    for crate in CORE_SIDE:
        shutil.copytree(NATIVE / crate / "src", copy / crate / "src")
    return copy


def test_the_core_side_names_only_the_pinned_system_paths_and_file_methods() -> None:
    assert system_uses(NATIVE) == SYSTEM_USES


@pytest.mark.parametrize(
    ("planted", "hit"), SYSTEM_FORMS, ids=[f[1] + str(i) for i, f in enumerate(SYSTEM_FORMS)]
)
def test_a_planted_system_access_in_model_fails(tmp_path: Path, planted: str, hit: str) -> None:
    copy = _core_side(tmp_path)
    lib = copy / "model/src/lib.rs"
    lib.write_text(lib.read_text() + "\n" + planted)
    assert system_uses(copy) - SYSTEM_USES == Counter({f"model/src/lib.rs: {hit}": 1})


@pytest.mark.parametrize("crate", ["eval", "report", "core"])
def test_a_planted_system_access_fails_in_each_core_crate(tmp_path: Path, crate: str) -> None:
    copy = _core_side(tmp_path)
    root = copy / crate / "src" / ("main.rs" if crate == "core" else "lib.rs")
    root.write_text(
        root.read_text() + '\npub fn p() -> bool {\n    std::fs::read("x").is_ok()\n}\n'
    )
    assert system_uses(copy) - SYSTEM_USES == Counter({f"{crate}/src/{root.name}: std::fs": 1})


def test_a_system_use_in_a_test_file_or_an_inline_test_is_not_a_violation(tmp_path: Path) -> None:
    copy = _core_side(tmp_path)
    lib = copy / "eval/src/lib.rs"
    lib.write_text(lib.read_text() + "\n#[cfg(test)]\nmod planted {\n    use std::fs;\n}\n")
    (copy / "eval/src/eval_tests.rs").write_text('fn t() { let _ = std::fs::read("x"); }\n')
    assert system_uses(copy) == SYSTEM_USES


def test_a_planted_language_name_in_a_subdirectory_of_report_fails(tmp_path: Path) -> None:
    copy = _core_side(tmp_path)
    before = language_names(copy)
    lib = copy / "report/src/lib.rs"
    lib.write_text(lib.read_text() + "\nmod planted;\n")
    (copy / "report/src/planted").mkdir()
    (copy / "report/src/planted/mod.rs").write_text('pub const NAME: &str = "Dart";\n')
    assert language_names(copy) - before == Counter({"report/src/planted/mod.rs: dart": 1})


def test_the_declared_requires_follow_the_crate_chain() -> None:
    assert requires_problems(json.loads(CONTRACT.read_text())) == []


# (source component, target component): one or more planted cases for each direction class.
AGAINST_THE_ORDER = [
    ("facts", "ts-entry"),  # base -> collector
    ("snapshot", "py-survey"),  # base -> collector
    ("store", "model"),  # base -> core chain
    ("facts", "contract"),  # base -> core chain
    ("facts", "snapshot"),  # base -> higher base
    ("snapshot", "wire"),  # base -> base of the same level
    ("contract", "facts"),  # contract -> anything
    ("contract", "store"),
    ("model", "eval"),  # chain upward
    ("eval", "report"),
    ("model", "report"),
    ("report", "core"),  # anything -> core
    ("py-reply", "core"),
    ("eval", "model-barrier"),  # anything -> the test crate
    ("ts-flow", "model"),  # collector -> core chain
    ("rs-flow", "eval"),
    ("dart-entry", "contract"),
    ("rs-flow", "py-survey"),  # collector -> another collector
    ("model", "ts-flow"),  # chain -> collector
    ("core", "rs-flow"),
    ("eval", "py-survey"),
    ("core", "ts-entry"),  # AD-406: only collect requires a collector
    ("report", "ts-entry"),
    ("eval", "collect"),  # AD-406: only the core requires collect
    ("model", "collect"),
    ("report", "collect"),
    ("collect", "model"),  # collect -> core chain
    ("collect", "core"),
    ("ts-flow", "collect"),  # collector -> collect
    ("collect", "snapshot"),  # collect -> a base crate outside facts, store and wire
    ("collect", "pytext"),
    ("ts-entry", "store"),  # collector -> store
    ("rs-flow", "store"),
    ("py-reply", "store"),
    ("dart-entry", "store"),
]


@pytest.mark.parametrize(("source", "target"), AGAINST_THE_ORDER)
def test_a_planted_requires_against_the_crate_order_fails(source: str, target: str) -> None:
    contract = json.loads(CONTRACT.read_text())
    part = next(item for item in contract["components"] if item["label"] == source)
    part.setdefault("requires", []).append({"component": target, "rationale": "planted"})
    assert requires_problems(contract) == [f"{source} requires {target}"]


def test_report_may_require_eval_and_a_base_crate_a_lower_base_crate() -> None:
    contract = json.loads(CONTRACT.read_text())
    parts = {item["label"]: item for item in contract["components"]}
    parts["report"]["requires"].append({"component": "eval", "rationale": "the report seam"})
    parts["wire"]["requires"].append({"component": "pytext", "rationale": "lower base"})
    assert requires_problems(contract) == []


def test_a_crate_without_a_place_in_the_order_fails() -> None:
    contract = json.loads(CONTRACT.read_text())
    contract["components"].append({"label": "x", "packages": ["native.archkeel_planted"]})
    assert requires_problems(contract) == ["crate planted has no place in the crate order"]


def test_the_python_future_feature_list_has_one_production_home() -> None:
    features = {
        json.dumps(name)
        for name in (
            "nested_scopes",
            "generators",
            "division",
            "absolute_import",
            "with_statement",
            "print_function",
            "unicode_literals",
            "barry_as_FLUFL",
            "generator_stop",
            "annotations",
        )
    }
    found: Counter[str] = Counter()
    for crate in NATIVE.iterdir():
        if not (crate / "src").is_dir():
            continue
        for path, text in production_sources(NATIVE, crate.name).items():
            tokens = tokenize(text)
            arrays: list[set[str]] = []
            for token, test in zip(tokens, inline_test_mask(tokens), strict=True):
                if test:
                    continue
                if token.text == "[":
                    arrays.append(set())
                elif token.text == "]" and arrays:
                    found[path] += int(features <= arrays.pop())
                elif arrays:
                    arrays[-1].add(token.text)
    assert +found == Counter({"python/src/parse.rs": 1})
