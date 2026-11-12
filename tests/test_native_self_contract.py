# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-382: each rule of the self-contract fails on a violation planted in a copy of native/.

Consumer: `make native-check`. Two self-checks run with the Rust collector, each on its own copy
of `native/` without `target/`. The first copy holds each chain rule in two code forms (a `use`,
and a qualified path without `use`), each in a file of its own, and the external and assignment
plants. The second copy adds a matching `requires` entry for each chain rule. A rule that does
not fail at its planted file fails here.
"""

from __future__ import annotations

import io
import json
import shutil
from contextlib import redirect_stdout
from functools import partial
from pathlib import Path
from typing import Any
from unittest import mock

import pytest
from collector_pin import pin_of
from graph_report_support import commit_tree

from archkeel import cli
from archkeel.cli import main

ROOT = Path(__file__).parents[1]
DEPENDENCY = "[dependencies]\n"
CARGO = {
    "report": 'archkeel-report = { path = "../report" }',
    "eval": 'archkeel-eval = { path = "../eval" }',
    "model": 'archkeel-model = { path = "../model" }',
    "core": 'archkeel-core = { path = "../core" }',
    "facts": "archkeel-facts.workspace = true",
    "toml": "toml.workspace = true",
    "syn": "syn.workspace = true",
    "tree": "tree-sitter.workspace = true",
    "ruff": "ruff_python_parser.workspace = true",
    "sha2": "sha2.workspace = true",
    "regex": 'regex = "1"',
}
ITEM = {
    "report": "archkeel_report::problems",
    "eval": "archkeel_eval::evaluate",
    "model": "archkeel_model::Model",
    "core": "archkeel_core::run",
}
CHAIN_RULES = [
    ("eval", "report"),
    ("model", "eval"),
    ("model", "report"),
    ("contract", "model"),
    ("contract", "eval"),
    ("contract", "report"),
    ("contract", "core"),
    ("model", "core"),
    ("eval", "core"),
    ("report", "core"),
]
# (crate, Cargo key, file text, rule): plants of the external and requires rules.
OTHER = [
    ("eval", "toml", "pub use toml::Table;\n", "NATIVE-EXTERNAL-TOML"),
    ("eval", "syn", "pub use syn::File;\n", "NATIVE-EXTERNAL-SYN"),
    ("report", "tree", "pub use tree_sitter::Parser;\n", "NATIVE-EXTERNAL-TREE-SITTER"),
    ("model", "ruff", "pub use ruff_python_parser::Mode;\n", "NATIVE-EXTERNAL-RUFF-PYTHON-PARSER"),
    ("eval", "sha2", "pub use sha2::Sha256;\n", "NATIVE-EXTERNAL-SHA2"),
    ("report", "regex", "pub use regex::Regex;\n", "NATIVE-EXTERNAL-COMPLETE"),
    ("contract", "facts", "pub use archkeel_facts::Record;\n", "NATIVE-REQUIRES-COMPLETE"),
    ("typescript", "model", "pub use archkeel_model::Model;\n", "NATIVE-REQUIRES-COMPLETE"),
]
Plant = tuple[str, str]  # (rule, planted file below the copy root)


def _rule(source: str, target: str) -> str:
    return f"NATIVE-NO-{source.upper()}-TO-{target.upper()}"


def _plant(native: Path, crate: str, cargo: str, name: str, text: str) -> str:
    manifest = native / crate / "Cargo.toml"
    line = CARGO[cargo]
    if line not in manifest.read_text():
        manifest.write_text(manifest.read_text().replace(DEPENDENCY, f"{DEPENDENCY}{line}\n", 1))
    root = native / crate / "src" / ("main.rs" if crate in {"core", "typescript"} else "lib.rs")
    if crate == "typescript":  # a new module of a collector has no owner: plant in the entry
        root.write_text(f"{root.read_text()}\n{text}")
        return f"native/{crate}/src/main.rs"
    root.write_text(f"{root.read_text()}\nmod {name};\n")
    (native / crate / "src" / f"{name}.rs").write_text(text)
    return f"native/{crate}/src/{name}.rs"


def _code_forms(native: Path) -> list[Plant]:
    plants = []
    for number, (source, target) in enumerate(CHAIN_RULES):
        use = f"pub use {ITEM[target]} as planted;\n"
        path = f"pub fn planted() {{\n    let _ = {ITEM[target]};\n}}\n"
        for form, text in (("use", use), ("path", path)):
            name = f"planted_{form}_{number}"
            plants.append((_rule(source, target), _plant(native, source, target, name, text)))
    for number, (crate, cargo, text, rule) in enumerate(OTHER):
        plants.append((rule, _plant(native, crate, cargo, f"planted_other_{number}", text)))
    members = native / "Cargo.toml"
    members.write_text(members.read_text().replace('"report"]', '"report", "planted"]', 1))
    (native / "planted/src").mkdir(parents=True)
    (native / "planted/Cargo.toml").write_text(
        '[package]\nname = "archkeel-planted"\nversion = "0.0.0"\nedition = "2021"\n'
    )
    (native / "planted/src/lib.rs").write_text("pub fn planted() {}\n")
    plants.append(("NATIVE-ASSIGNMENT-COMPLETE", "native/planted/src/lib.rs"))
    return plants


def _with_requires(native: Path) -> list[Plant]:
    path = native / "architecture-contract.json"
    contract = json.loads(path.read_text())
    parts = {part["label"]: part for part in contract["components"]}
    plants = []
    for number, (source, target) in enumerate(CHAIN_RULES):
        parts[source].setdefault("requires", []).append({"component": target, "rationale": "x"})
        text = f"pub use {ITEM[target]} as planted;\n"
        plants.append((_rule(source, target), _plant(native, source, target, f"p_{number}", text)))
    path.write_text(json.dumps(contract, indent=2))
    return plants


def _run(root: Path, binary: Path) -> dict[str, Any]:
    config = (root / "native/archkeel.toml").read_text()
    (root / "archkeel.toml").write_text(f"{config}collector_argv = {json.dumps([str(binary)])}\n")
    commit_tree(root)
    build, out = cli.observer_for, io.StringIO()
    # A config has no pin (AD-344): the test pins the binary that it configured.
    pinned = partial(build, pinned_digest=pin_of(str(binary)))
    with mock.patch.object(cli, "observer_for", pinned), redirect_stdout(out):
        main(["report", "--root", str(root), "--output", str(root / "out/a.json"), "--json"])
    return json.loads(out.getvalue())  # type: ignore[no-any-return]


def _found(result: dict[str, Any]) -> set[Plant]:
    return {
        (rule, at["path"])
        for item in result["findings"]
        if item["kind"] == "violation"
        for rule in item["rules"]
        for at in item.get("locations") or ()
    }


@pytest.fixture(scope="module")
def runs(rust_binary: Path, tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    found: dict[str, Any] = {}
    for name, plant in (("code", _code_forms), ("requires", _with_requires)):
        root = tmp_path_factory.mktemp(name)
        shutil.copytree(ROOT / "native", root / "native", ignore=shutil.ignore_patterns("target"))
        plants = plant(root / "native")
        found[name] = (plants, _run(root, rust_binary))
    return found


@pytest.mark.parametrize("name", ["code", "requires"])
def test_each_rule_fails_at_each_planted_file(runs: dict[str, Any], name: str) -> None:
    plants, result = runs[name]
    statuses = {item["id"]: item["status"] for item in result["rule_assessments"]}
    assert [plant for plant in plants if plant not in _found(result)] == []
    assert {statuses[rule] for rule, _ in plants} == {"FAIL"}


def test_a_matching_requires_hides_each_chain_edge_from_complete_requires(
    runs: dict[str, Any],
) -> None:
    plants, result = runs["requires"]
    found = _found(result)
    assert [path for _, path in plants if ("NATIVE-REQUIRES-COMPLETE", path) in found] == []


def test_the_code_forms_cover_each_chain_rule_twice(runs: dict[str, Any]) -> None:
    plants, _ = runs["code"]
    rules = [rule for rule, _ in plants if rule.startswith("NATIVE-NO-")]
    assert sorted(set(rules)) == sorted(_rule(s, t) for s, t in CHAIN_RULES)
    assert len(rules) == 2 * len(CHAIN_RULES)
