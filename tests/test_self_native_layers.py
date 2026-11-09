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
MODULE_PATH = re.compile(r"crate::(\w+)")
MODULE_GROUP = re.compile(r"crate::\{([^}]*)\}")
UNCHECKED = {"main", "test_tree", "dump"}


def crate_problems(layers: Mapping[str, Any], dependencies: Mapping[str, list[str]]) -> list[str]:
    """Return one line for each crate edge that the layer file does not allow."""
    crates: Mapping[str, Mapping[str, Any]] = layers["crates"]
    parsers: list[str] = layers["parser_prefixes"]
    problems: list[str] = []
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


def module_graph(sources: Mapping[str, str]) -> dict[str, set[str]]:
    """Return the module edges of one crate. `sources` maps a file stem to its text."""
    graph: dict[str, set[str]] = {}
    for module, text in sources.items():
        used = set(MODULE_PATH.findall(text))
        for group in MODULE_GROUP.findall(text):
            used |= {part.strip().split("::")[0] for part in group.split(",")}
        graph[module] = (used & sources.keys()) - {module}
    return graph


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


@pytest.mark.skipif(shutil.which("cargo") is None, reason="needs a Rust toolchain")
def test_the_native_workspace_keeps_the_declared_layers() -> None:
    layers = tomllib.loads((NATIVE / "layers.toml").read_text())
    assert crate_problems(layers, _metadata()) == []


def test_the_typescript_collector_adds_no_module_cycle() -> None:
    layers = tomllib.loads((NATIVE / "layers.toml").read_text())
    allowed = [
        sorted(entry["modules"])
        for entry in layers["cycles"]["archkeel-typescript-collector"]
        if entry["modules"]
    ]
    graph = module_graph(_sources(NATIVE / "typescript"))
    assert cycle_problems(graph, allowed) == []
