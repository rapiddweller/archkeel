# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-382: each rule of the self-contract fails on a violation planted in a copy of native/.

Consumer: `make native-check`. Two self-checks run through `archkeel validate`, each on its own
copy of `native/` without `target/`. The first copy holds each chain rule in two code forms (a
`use`, and a qualified path without `use`), each in a file of its own, and the external and
assignment plants. The second copy adds a matching `requires` entry for each chain rule. A rule
that does not fail at its planted file fails here.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from core_support import copy_native, run
from corpus_support import commit_tree
from frozen_native import frozen_root as frozen_root

from archkeel.cli import core_only

ROOT = Path(__file__).parents[1]
DEPENDENCY = "[dependencies]\n"
CARGO = {
    "report": 'archkeel-report = { path = "../report" }',
    "eval": 'archkeel-eval = { path = "../eval" }',
    "model": 'archkeel-model = { path = "../model" }',
    "core": 'archkeel-core = { path = "../core" }',
    "typescript": 'archkeel-typescript-collector = { path = "../typescript" }',
    "rust": 'archkeel-rust-collector = { path = "../rust" }',
    "collect": 'archkeel-collect = { path = "../collect" }',
    "contract": 'archkeel-contract = { path = "../contract" }',
    "store": 'archkeel-store = { path = "../store" }',
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
    "typescript": "archkeel_typescript_collector::provenance",
    "rust": "archkeel_rust_collector::provenance",
    "collect": "archkeel_collect::scan",
    "contract": "archkeel_contract::parse",
    "store": "archkeel_store::ingest_reply",
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
    # AD-406: only archkeel-collect links a collector, and only the core uses archkeel-collect.
    ("core", "typescript"),
    ("eval", "typescript"),
    ("model", "typescript"),
    ("report", "typescript"),
    *[(source, "rust") for source in ("core", "eval", "model", "report")],
    ("eval", "collect"),
    ("model", "collect"),
    ("report", "collect"),
    # AD-406 review F4: collect uses only facts, store, wire and the collectors; a collector uses
    # no store and no crate of the core side.
    *[("collect", target) for target in ("contract", "model", "eval", "report", "core")],
    *[
        (collector, target)
        for collector in ("typescript", "rust", "python", "dart")
        for target in ("store", "model", "eval", "report", "core", "collect")
    ],
]
COLLECTORS = ("typescript", "rust", "python", "dart")
# The component label of a planted target crate whose label is not its crate name.
LABEL = {"typescript": "ts-entry", "rust": "rs-entry", "python": "py-entry", "dart": "dart-entry"}
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

# The guarded collection spine: survey -> symbols -> unparse -> module, tree and parse.
PYTHON_LAYERS = [("survey",), ("symbols",), ("unparse",), ("module", "tree", "parse")]
PYTHON_MODULE = {"tree": "pyast"}
PYTHON_ITEM = {"survey": "Survey", "symbols": "Table", "unparse": "TextFailure"}


def _python_plants(native: Path, matching_requires: bool) -> list[Plant]:
    path = native / "architecture-contract.json"
    contract = json.loads(path.read_text())
    parts = {part["label"]: part for part in contract["components"]}
    plants = []
    for layer, sources in enumerate(PYTHON_LAYERS):
        for source in sources:
            module = PYTHON_MODULE.get(source, source)
            file = (
                native
                / "python/src"
                / (
                    f"{module}/mod.rs"
                    if source in {"tree", "unparse", "symbols", "survey"}
                    else f"{module}.rs"
                )
            )
            for targets in PYTHON_LAYERS[:layer]:
                for target in targets:
                    rule = f"NATIVE-PY-{source.upper()}-NO-{target.upper()}"
                    if matching_requires:
                        parts[f"py-{source}"]["requires"].append(
                            {"component": f"py-{target}", "rationale": "planted"}
                        )
                    item = f"crate::{target}::{PYTHON_ITEM[target]}"
                    for form in ["use"] if matching_requires else ["use", "path"]:
                        name = f"planted_{target}_{form}"
                        text = (
                            f"pub use {item} as {name};"
                            if form == "use"
                            else f"pub fn {name}() {{ let _ = std::mem::size_of::<{item}>(); }}"
                        )
                        file.write_text(file.read_text() + "\n" + text + "\n")
                        plants.append(
                            (
                                rule,
                                f"native/{file.relative_to(native).as_posix()}",
                            )
                        )
    path.write_text(json.dumps(contract, indent=2) + "\n")
    return plants


def _rule(source: str, target: str) -> str:
    return f"NATIVE-NO-{source.upper()}-TO-{target.upper()}"


def _plant(native: Path, crate: str, cargo: str, name: str, text: str) -> str:
    manifest = native / crate / "Cargo.toml"
    line = CARGO[cargo]
    if line not in manifest.read_text():
        manifest.write_text(manifest.read_text().replace(DEPENDENCY, f"{DEPENDENCY}{line}\n", 1))
    root = native / crate / "src" / ("main.rs" if crate in {"core", *COLLECTORS} else "lib.rs")
    if crate in COLLECTORS:  # a new module of a collector has no owner: plant in the entry
        root.write_text(f"{root.read_text()}\n{text}")
        return f"native/{crate}/src/main.rs"
    root.write_text(f"{root.read_text()}\nmod {name};\n")
    (native / crate / "src" / f"{name}.rs").write_text(text)
    return f"native/{crate}/src/{name}.rs"


def _code_forms(native: Path) -> list[Plant]:
    plants = _python_plants(native, False)
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
    python = _python_plants(native, True)
    path = native / "architecture-contract.json"
    contract = json.loads(path.read_text())
    parts = {part["label"]: part for part in contract["components"]}
    plants = []
    for number, (source, target) in enumerate(CHAIN_RULES):
        label = LABEL.get(target, target)
        part = parts[LABEL.get(source, source)]
        part.setdefault("requires", []).append({"component": label, "rationale": "x"})
        text = f"pub use {ITEM[target]} as planted;\n"
        plants.append((_rule(source, target), _plant(native, source, target, f"p_{number}", text)))
    path.write_text(json.dumps(contract, indent=2))
    return plants + python


def _run(root: Path, binary: Path) -> dict[str, Any]:
    commit_tree(root)
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(core_only, "locate_core", lambda: binary)
        _, document = run("validate", "--root", str(root), "--config", "native/archkeel.toml")
    frame: dict[str, Any] = document["frame"]
    return frame


def _found(frame: dict[str, Any]) -> set[Plant]:
    return {
        (rule, frame["locations"][evidence]["path"])
        for rule, rows in frame["details"].items()
        for row in rows
        for evidence in row["evidence"]
    }


@pytest.fixture(scope="module")
def runs(
    core_binary: Path, tmp_path_factory: pytest.TempPathFactory, frozen_root: Path
) -> dict[str, Any]:
    found: dict[str, Any] = {}
    for name, plant in (("code", _code_forms), ("requires", _with_requires)):
        root = tmp_path_factory.mktemp(name)
        copy_native(root, frozen_root)
        plants = plant(root / "native")
        found[name] = (plants, _run(root, core_binary))
    return found


@pytest.mark.parametrize("name", ["code", "requires"])
def test_each_rule_fails_at_each_planted_file(runs: dict[str, Any], name: str) -> None:
    plants, result = runs[name]
    statuses = {rule: row[1] for rule, row in result["rules"].items()}
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


def test_each_python_upward_pair_has_a_rule_and_a_plant(runs: dict[str, Any]) -> None:
    plants, _ = runs["code"]
    expected = {
        f"NATIVE-PY-{source.upper()}-NO-{target.upper()}"
        for layer, sources in enumerate(PYTHON_LAYERS)
        for source in sources
        for targets in PYTHON_LAYERS[:layer]
        for target in targets
    }
    contract = json.loads((ROOT / "native/architecture-contract.json").read_text())
    assert expected == {
        rule["id"] for rule in contract["rules"] if rule["id"].startswith("NATIVE-PY-")
    }
    assert expected == {rule for rule, _ in plants if rule.startswith("NATIVE-PY-")}
