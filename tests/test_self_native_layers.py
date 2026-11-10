# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-327: the native workspace keeps the crate direction and adds no module cycle.

`native/layers.toml` declares each crate, its role and the crates it may use. The check reads
`cargo metadata` and the `crate::` paths of each source file. It needs no Rust toolchain for the
fixture tests; the tests of the real workspace skip without `cargo`.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tomllib
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).parents[1]
NATIVE = ROOT / "native"
UNCHECKED = {"main", "lib", "test_tree", "dump"}
# Comments, raw strings, strings and characters (a lifetime has no closing quote).
NOISE = re.compile(
    r"//[^\n]*|/\*.*?\*/|(?<![\w])b?r(#*)\".*?\"\1|\"(?:\\.|[^\"\\])*\"|'(?:\\.[^']*|[^\\'\n])'",
    re.S,
)
CFG_TEST_MODULE = re.compile(r"#\[cfg\(test\)\]\s*(?:#\[path[^\]]*\]\s*)?mod\s+\w+\s*[;{]")
CHILD = re.compile(r'#\[path = "([\w]+\.rs)"\]\s*mod\s+\w+;')


def crate_problems(layers: Mapping[str, Any], dependencies: Mapping[str, list[str]]) -> list[str]:
    """Return one line for each crate edge that the layer file does not allow."""
    crates: Mapping[str, Mapping[str, Any]] = layers["crates"]
    parsers: list[str] = layers["parser_prefixes"]
    problems: list[str] = []
    for name, entry in sorted(crates.items()):
        if name not in dependencies and not entry.get("planned"):
            problems.append(f"{name} is declared but has no crate; mark it planned")
        if name in dependencies and entry.get("planned"):
            problems.append(f"{name} exists now; remove planned from its entry")
        for allowed in entry["may_use"]:
            if allowed not in crates:
                problems.append(f"{name} may use {allowed}, which has no entry")
            elif entry["role"] == "library" and crates[allowed]["role"] == "collector":
                problems.append(f"{name} is a library and must not be allowed to use {allowed}")
    for name, used in sorted(dependencies.items()):
        if name not in crates:
            problems.append(f"{name} has no entry in native/layers.toml")
            continue
        for dep in used:
            if dep.startswith(tuple(parsers)):
                if crates[name]["role"] != "collector":
                    problems.append(f"{name} is not a collector and must not use {dep}")
            elif dep in dependencies and dep not in crates[name]["may_use"]:
                problems.append(f"{name} must not use {dep}")
    return problems


def _strip(text: str) -> str:
    """Blank the comments, strings and characters, so that a path in them is not an edge."""
    return NOISE.sub(" ", text)


def _block_end(text: str, start: int) -> int:
    """Return the index after the `}` that closes the `{` at or after `start`."""
    depth = 0
    for index in range(text.index("{", start), len(text)):
        depth += {"{": 1, "}": -1}.get(text[index], 0)
        if depth == 0:
            return index + 1
    return len(text)


def _drop_test_modules(text: str) -> str:
    """Remove each `#[cfg(test)] mod`: a test-only edge is not a production cycle."""
    while match := CFG_TEST_MODULE.search(text):
        end = match.end() if match.group(0).endswith(";") else _block_end(text, match.start())
        text = text[: match.start()] + text[end:]
    return text


def _first_names(group: str) -> set[str]:
    """Return the first path segment of each top-level item of a `{...}` use group."""
    items, depth, current = [], 0, ""
    for char in group:
        depth += {"{": 1, "}": -1}.get(char, 0)
        if char == "," and depth == 0:
            items.append(current)
            current = ""
        else:
            current += char
    return {m.group(0) for item in [*items, current] if (m := re.search(r"\w+", item))}


def _used(text: str, roots: set[str]) -> set[str]:
    prefix = "|".join(sorted(roots))
    used: set[str] = set()
    for match in re.finditer(rf"(?<![\w:])(?:{prefix})::(\{{|\w+)", text):
        if match.group(1) == "{":
            used |= _first_names(text[match.end() : _block_end(text, match.end() - 1)])
        else:
            used.add(match.group(1))
    return used


def module_graph(sources: Mapping[str, str]) -> dict[str, set[str]]:
    """Return the production module edges of one crate.

    `sources` maps a file stem to its text. A `#[path = "x.rs"] mod x;` child is part of its
    parent: its `crate::` edges belong to the parent, and its `super::` is the parent itself.
    """
    production = {name: _drop_test_modules(text) for name, text in sources.items()}
    texts = {name: _strip(text) for name, text in production.items()}
    children = {
        name: {c for c in CHILD.findall(text) if c.removesuffix(".rs") in texts}
        for name, text in production.items()
    }
    folded = {c.removesuffix(".rs") for kids in children.values() for c in kids}
    graph: dict[str, set[str]] = {}
    for name in texts.keys() - folded:
        body = texts[name]
        roots = {"crate"} | set(re.findall(r"\buse crate as (\w+)", body))
        used = _used(body, roots | {"super"})
        for child in children[name]:
            used |= _used(texts[child.removesuffix(".rs")], {"crate"})
        graph[name] = used
    return {name: (used & graph.keys()) - {name} for name, used in graph.items()}


def declared_cycles(layers: Mapping[str, Any], crate: str) -> list[list[str]]:
    """Return the module cycles that the layer file allows for `crate` (none when absent)."""
    entries = layers.get("cycles", {}).get(crate, [])
    return [sorted(entry["modules"]) for entry in entries if entry["modules"]]


def _components(graph: Mapping[str, set[str]]) -> list[list[str]]:
    """Return the strongly connected sets of two or more modules (Tarjan)."""
    index: dict[str, int] = {}
    low: dict[str, int] = {}
    stack: list[str] = []
    found: list[list[str]] = []

    def visit(node: str) -> None:
        index[node] = low[node] = len(index)
        stack.append(node)
        for nxt in sorted(graph[node]):
            if nxt not in index:
                visit(nxt)
                low[node] = min(low[node], low[nxt])
            elif nxt in stack:
                low[node] = min(low[node], index[nxt])
        if low[node] == index[node]:
            members = [stack.pop()]
            while members[-1] != node:
                members.append(stack.pop())
            if len(members) > 1:
                found.append(sorted(members))

    for node in sorted(graph):
        if node not in index:
            visit(node)
    return sorted(found)


def cycle_problems(graph: Mapping[str, set[str]], allowed: list[list[str]]) -> list[str]:
    """Compare the strongly connected sets of `graph` with the allowed list."""
    current = _components(graph)
    problems = [f"new module cycle: {', '.join(c)}" for c in current if c not in allowed]
    problems += [
        f"not a cycle any more, remove it: {', '.join(c)}" for c in allowed if c not in current
    ]
    return problems


LAYERS: dict[str, Any] = {
    "parser_prefixes": ["tree-sitter"],
    "crates": {
        "wire": {"role": "library", "may_use": []},
        "ts": {"role": "collector", "may_use": ["wire"]},
    },
}


def test_the_allowed_direction_has_no_problem() -> None:
    deps = {"wire": ["serde"], "ts": ["wire", "tree-sitter", "tree-sitter-typescript"]}
    assert crate_problems(LAYERS, deps) == []


def test_a_library_that_uses_a_collector_is_a_problem() -> None:
    problems = crate_problems(LAYERS, {"wire": ["ts"], "ts": ["wire"]})
    assert problems == ["wire must not use ts"]


def test_a_library_that_uses_a_parser_crate_is_a_problem() -> None:
    problems = crate_problems(LAYERS, {"wire": ["tree-sitter-python"], "ts": ["wire"]})
    assert problems == ["wire is not a collector and must not use tree-sitter-python"]


def test_a_planned_crate_needs_no_crate_and_a_present_crate_is_not_planned() -> None:
    layers = {
        **LAYERS,
        "crates": {
            **LAYERS["crates"],
            "facts": {"role": "library", "may_use": [], "planned": True},
        },
    }
    deps = {"wire": [], "ts": ["wire"]}
    assert crate_problems(layers, deps) == []
    assert crate_problems(layers, {**deps, "facts": []}) == [
        "facts exists now; remove planned from its entry"
    ]


def test_a_declared_crate_that_is_missing_and_not_planned_is_a_problem() -> None:
    assert crate_problems(LAYERS, {"wire": []}) == [
        "ts is declared but has no crate; mark it planned"
    ]


def test_an_entry_must_not_allow_what_has_no_entry_or_lets_a_library_use_a_collector() -> None:
    layers = {
        **LAYERS,
        "crates": {
            "wire": {"role": "library", "may_use": ["ts", "ghost"]},
            "ts": {"role": "collector", "may_use": ["wire"]},
        },
    }
    assert crate_problems(layers, {"wire": [], "ts": ["wire"]}) == [
        "wire is a library and must not be allowed to use ts",
        "wire may use ghost, which has no entry",
    ]


def test_a_crate_without_an_entry_is_a_problem() -> None:
    problems = crate_problems(LAYERS, {"wire": [], "ts": ["wire"], "new": ["wire"]})
    assert problems == ["new has no entry in native/layers.toml"]


def test_a_fake_use_edge_is_a_module_edge() -> None:
    graph = module_graph(
        {"a": "use crate::b::X;\nfn f() { crate::c::g() }", "b": "", "c": "use crate::{a, b};"}
    )
    assert graph == {"a": {"b", "c"}, "b": set(), "c": {"a", "b"}}


def test_a_module_edge_to_itself_or_to_a_non_module_is_ignored() -> None:
    assert module_graph({"a": "use crate::a::X; use crate::PROFILE;"}) == {"a": set()}


def test_the_listed_cycle_passes_and_a_new_cycle_fails() -> None:
    graph = {"a": {"b"}, "b": {"a"}, "c": {"d"}, "d": {"c"}, "e": set()}
    assert cycle_problems(graph, [["a", "b"], ["c", "d"]]) == []
    assert cycle_problems(graph, [["a", "b"]]) == ["new module cycle: c, d"]


def test_a_cycle_that_grows_fails_and_a_cycle_that_shrinks_must_leave_the_list() -> None:
    grown = {"a": {"b"}, "b": {"c"}, "c": {"a"}}
    assert cycle_problems(grown, [["a", "b"]]) == [
        "new module cycle: a, b, c",
        "not a cycle any more, remove it: a, b",
    ]
    gone = {"a": {"b"}, "b": set()}
    assert cycle_problems(gone, [["a", "b"]]) == ["not a cycle any more, remove it: a, b"]


def _edges(sources: dict[str, str]) -> dict[str, set[str]]:
    return module_graph(sources)


def test_nested_braces_in_a_use_group_keep_every_module() -> None:
    graph = _edges({"a": "use crate::{x::{P, Q}, b};", "b": "", "x": ""})
    assert graph["a"] == {"b", "x"}


def test_super_in_a_module_file_is_an_edge_to_a_sibling() -> None:
    assert _edges({"a": "use super::b::T;", "b": ""})["a"] == {"b"}


def test_a_path_in_a_comment_or_a_string_is_not_an_edge() -> None:
    text = (
        '/// see crate::b\n// crate::b\n/* crate::b */ let s = "crate::b"; let r = r#"crate::b"#;'
    )
    assert _edges({"a": text, "b": ""})["a"] == set()


def test_an_edge_inside_a_cfg_test_module_is_not_a_production_edge() -> None:
    text = "#[cfg(test)]\nmod tests {\n    use crate::b;\n}\nfn f() {}"
    assert _edges({"a": text, "b": ""})["a"] == set()


def test_an_alias_of_the_crate_root_is_an_edge() -> None:
    assert _edges({"a": "use crate as root;\nfn f() { root::b::g() }", "b": ""})["a"] == {"b"}


def test_a_path_child_folds_into_its_parent_and_super_means_the_parent() -> None:
    # collect -> imports (a #[path] child) -> parse -> collect is a real cycle.
    sources = {
        "collect": '#[path = "imports.rs"]\nmod imports;\nuse crate::parse;',
        "imports": "use super::Thing;\nuse crate::parse;",
        "parse": "use crate::collect;",
    }
    graph = _edges(sources)
    assert set(graph) == {"collect", "parse"}
    assert graph["collect"] == {"parse"}
    assert cycle_problems(graph, []) == ["new module cycle: collect, parse"]


def test_a_layer_file_without_cycles_passes_on_a_graph_without_cycles() -> None:
    assert cycle_problems({"a": {"b"}, "b": set()}, declared_cycles(LAYERS, "ts")) == []


def test_a_layer_file_without_cycles_fails_on_a_graph_with_a_cycle() -> None:
    graph = {"a": {"b"}, "b": {"a"}}
    assert cycle_problems(graph, declared_cycles(LAYERS, "ts")) == ["new module cycle: a, b"]


def _metadata() -> dict[str, list[str]]:
    out = subprocess.run(
        ["cargo", "metadata", "--format-version", "1", "--locked", "--no-deps"],
        cwd=NATIVE,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    packages = json.loads(out)["packages"]
    return {p["name"]: sorted({d["name"] for d in p["dependencies"]}) for p in packages}


def _sources(crate_dir: Path) -> dict[str, str]:
    return {
        p.stem: p.read_text()
        for p in (crate_dir / "src").glob("*.rs")
        if not p.stem.endswith("_tests") and p.stem not in UNCHECKED
    }


def _layers() -> dict[str, Any]:
    return tomllib.loads((NATIVE / "layers.toml").read_text())


def test_the_native_workspace_keeps_the_declared_layers() -> None:
    if shutil.which("cargo") is None:
        message = "the layer check needs a Rust toolchain"
        if os.environ.get("CI"):
            pytest.fail(message)  # CI always has cargo: a skip would hide the check
        pytest.skip(message)
    assert crate_problems(_layers(), _metadata()) == []


def test_each_declared_crate_adds_no_module_cycle() -> None:
    layers = _layers()
    for crate, entry in layers["crates"].items():
        graph = module_graph(_sources(NATIVE / entry["dir"]))
        assert cycle_problems(graph, declared_cycles(layers, crate)) == [], crate


# The rules of the contract, pinned: a change of a rule is a change of this test as well.
EXPECTED_RULES = [
    ("NATIVE-ASSIGNMENT-COMPLETE", "complete_assignment", None, None),
    ("NATIVE-REQUIRES-COMPLETE", "complete_requires", None, None),
    ("NATIVE-NO-CRATE-CYCLES", "no_component_cycles", None, None),
    (
        "NATIVE-EXTERNAL-TREE-SITTER",
        "external_dependency_scope",
        "tree_sitter",
        ["native.archkeel_typescript_collector"],
    ),
    (
        "NATIVE-EXTERNAL-TREE-SITTER-TYPESCRIPT",
        "external_dependency_scope",
        "tree_sitter_typescript",
        ["native.archkeel_typescript_collector"],
    ),
    (
        "NATIVE-EXTERNAL-SYN",
        "external_dependency_scope",
        "syn",
        ["native.archkeel_rust_collector"],
    ),
]


def contract_problems(
    layers: Mapping[str, Any],
    contract: Mapping[str, Any],
    expected_rules: list[tuple[Any, ...]] | None = None,
) -> list[str]:
    """Compare `layers.toml` with the contract: components, `requires` and the pinned rules."""
    by_label = {c["label"]: c for c in contract["components"]}
    package_of = {name: "native." + name.replace("-", "_") for name in layers["crates"]}
    label_of = {
        package: label for label, component in by_label.items() for package in component["packages"]
    }
    # A planned crate has no code: the contract names it when it gets code, not before.
    planned = {package_of[name] for name, entry in layers["crates"].items() if entry.get("planned")}
    problems: list[str] = []
    known = set(package_of.values())
    for label, component in sorted(by_label.items()):
        for package in component["packages"]:
            if package not in known:
                problems.append(f"component {label} names {package}, which has no crate entry")
    if expected_rules is not None:
        rules = [
            (r["id"], r["kind"], r.get("dependency"), r.get("allowed_sources"))
            for r in contract.get("rules", [])
        ]
        if rules != expected_rules:
            problems.append(f"the rules of the contract changed: {rules}")
    for name, entry in sorted(layers["crates"].items()):
        if entry.get("planned"):
            continue
        label = label_of.get(package_of[name])
        if label is None:
            problems.append(f"{name} has no component in the contract")
            continue
        wanted = sorted(
            label_of.get(package_of[used], "?")
            for used in entry["may_use"]
            if package_of[used] not in planned
        )
        declared = sorted(r["component"] for r in by_label[label].get("requires", []))
        if wanted != declared:
            problems.append(
                f"{name}: layers.toml allows {wanted}, the contract requires {declared}"
            )
    return problems


def test_the_contract_and_the_layer_file_state_the_same_directions() -> None:
    contract = json.loads((NATIVE / "architecture-contract.json").read_text())
    assert contract_problems(_layers(), contract, EXPECTED_RULES) == []


def test_a_direction_that_only_one_file_states_is_a_problem() -> None:
    contract = {
        "components": [
            {"label": "wire", "packages": ["native.wire"]},
            {"label": "ts", "packages": ["native.ts"], "requires": []},
        ]
    }
    assert contract_problems(LAYERS, contract) == [
        "ts: layers.toml allows ['wire'], the contract requires []"
    ]
    assert contract_problems(LAYERS, {"components": contract["components"][:1]}) == [
        "ts has no component in the contract"
    ]


def test_a_component_without_a_crate_and_a_changed_rule_are_problems() -> None:
    contract = {
        "components": [
            {"label": "wire", "packages": ["native.wire"]},
            {"label": "ts", "packages": ["native.ts"], "requires": [{"component": "wire"}]},
            {"label": "ghost", "packages": ["native.ghost"]},
        ],
        "rules": [{"id": "R", "kind": "complete_requires"}],
    }
    rules = [("R", "complete_requires", None, None)]
    assert contract_problems(LAYERS, contract, rules) == [
        "component ghost names native.ghost, which has no crate entry"
    ]
    contract["rules"] = []
    assert contract_problems(LAYERS, contract, rules) == [
        "component ghost names native.ghost, which has no crate entry",
        "the rules of the contract changed: []",
    ]
