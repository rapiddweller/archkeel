# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-373: the pairs of contract trees of the parity test of the Rust widening comparison.

A pair is a name, the tree before and the tree after. A tree is the root path and the bytes of
each path that it reads. The pairs come from the 15 recorded `demo--against-*` cases, from one
changed key of each role of each repository contract (in both directions), from two changed keys
together and from changed inside contracts.
"""

from __future__ import annotations

import copy
import gzip
import json
import random
from pathlib import Path
from typing import Any

from rust_contract_tree_cases import hostile_trees as inside_trees
from rust_contract_tree_cases import identity
from test_rust_contract_parity import (
    GATED,
    OPTIONAL_KEYS,
    VALUES,
    _at,
    _paths,
    _python,
    _role,
    repository_contracts,
)

from archkeel.ir.codec import load_inside_contract_tree, parse_contract
from archkeel.ir.codec_wire import decode_json

ROOT = Path(__file__).parents[1]
ROOT_PATH = "architecture-contract.json"
# The accepted values of one key of one role. More values give the same change kinds.
PER_KEY = 6
Files = dict[str, bytes]
Tree = tuple[str, Files]
Pair = tuple[str, Tree, Tree]

# More values that a widening classifier names, so that each branch sees a change.
EXTRA_VALUES: list[Any] = [
    "agent",
    "exact",
    "import_namespace",
    "migration",
    "module",
    ["a.b", "a.b:C"],
    ["p.a", "p.b"],
    [{"source_module": "a.b", "target_module": "a.d"}],
    [{"qualified_name": "a.c", "line": 2, "statement": "s", "tag": "t"}],
    [{"component": "a", "rationale": "r", "through": ["p.a.x"]}],
    [{"component": "a", "rationale": "r", "decided_by": "agent"}],
    False,
    0,
    5,
    ["read", "write"],
]


def _encode(value: object) -> bytes:
    return (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode()


def _closure(base: Path, overlay: dict[str, str | None], root_path: str) -> Files | None:
    """The bytes that the tree of `root_path` reads, from a directory with an overlay."""

    def raw(path: str) -> bytes | None:
        if path in overlay:
            text = overlay[path]
            return None if text is None else text.encode()
        target = base / path
        return target.read_bytes() if target.is_file() else None

    root = raw(root_path)
    if root is None:
        return None
    files: Files = {root_path: root}

    def read(reference: str) -> tuple[bytes, str]:
        key = identity(reference)
        data = raw(key) if key is not None else None
        if key is None or data is None:
            raise ValueError("missing")
        files[key] = data
        return data, reference

    load_inside_contract_tree(root_path, parse_contract(decode_json(root)), "", root_path, read)
    return files


def recorded_pairs() -> list[Pair]:
    """Each recorded `demo--against-*` case: the base revision, then the changed files."""
    pairs = []
    for path in sorted((ROOT / "tests/dual_run").glob("demo--against-*.json.gz")):
        case = json.loads(gzip.decompress(path.read_bytes()))["case"]
        base = ROOT / case["fixture"]
        before = _closure(base, case["base_files"], ROOT_PATH)
        after = _closure(base, {**case["base_files"], **case["files"]}, ROOT_PATH)
        if before is not None and after is not None:
            pairs.append((path.name, (ROOT_PATH, before), (ROOT_PATH, after)))
    return pairs


def _single(document: dict[str, Any]) -> Tree:
    return ROOT_PATH, {ROOT_PATH: _encode(document)}


def _changed(sources: list[dict[str, Any]]) -> list[tuple[str, dict[str, Any], dict[str, Any]]]:
    """One changed key of each role of each source; only changes that Python accepts."""
    done: set[str] = set()
    changes = []
    for source in sorted(sources, key=lambda value: len(_encode(value))):
        for path in _paths(source):
            role = _role(source, path)
            if role in done:
                continue
            done.add(role)
            keys = dict.fromkeys([*_at(source, path), *OPTIONAL_KEYS.get(role, ())])
            for key in keys:
                kept = 0
                for value in ["<delete>", *VALUES, *EXTRA_VALUES]:
                    if kept == PER_KEY:
                        break
                    mutated = copy.deepcopy(source)
                    if key in GATED:
                        mutated["schema_version"] = "3.14.0"
                    target = _at(mutated, path)
                    if value == "<delete>":
                        target.pop(key, None)
                    else:
                        target[key] = value
                    if mutated != source and _python(_encode(mutated))["kind"] == "accept":
                        changes.append((f"{role}.{key}={value!r}", source, mutated))
                        kept += 1
        components = source["components"]
        for index in range(len(source["rules"])):
            removed = {**source, "rules": source["rules"][:index] + source["rules"][index + 1 :]}
            changes.append((f"rule {index} removed", source, removed))
        if components:
            renamed = copy.deepcopy(source)
            renamed["components"][0]["id"] = "C-RENAMED"
            if _python(_encode(renamed))["kind"] == "accept":
                changes.append(("component id changed", source, renamed))
    return changes


def _without_mounts(document: dict[str, Any]) -> dict[str, Any]:
    """A root alone: a mount would need the bytes of its inside contract."""
    for component in document["components"]:
        component.pop("inside", None)
    return document


def mutated_pairs(seed: int = 367) -> list[Pair]:
    """Each change in both directions, and two changes of one source together."""
    sources = [
        _without_mounts(json.loads(raw))
        for _, raw in repository_contracts()
        if _python(raw)["kind"] == "accept"
    ]
    changes = _changed(sources)
    pairs: list[Pair] = []
    for name, source, mutated in changes:
        pairs.append((f"{name} (after)", _single(source), _single(mutated)))
        pairs.append((f"{name} (before)", _single(mutated), _single(source)))
    generator = random.Random(seed)
    by_source: dict[int, list[dict[str, Any]]] = {}
    for _, source, mutated in changes:
        by_source.setdefault(id(source), []).append(mutated)
    for index, group in enumerate(by_source.values()):
        for _ in range(min(20, len(group))):
            first, second = generator.sample(group, 2) if len(group) > 1 else (group[0], group[0])
            pairs.append((f"combined {index}", _single(first), _single(second)))
    return pairs


def inside_pairs() -> list[Pair]:
    """Each accepted hostile inside tree against the base tree, in both directions."""
    trees = inside_trees()
    base = next(files for name, _, files in trees if name == "base")
    pairs: list[Pair] = []
    for name, root_path, files in trees:
        pairs.append((f"inside {name} (after)", (ROOT_PATH, base), (root_path, files)))
        pairs.append((f"inside {name} (before)", (root_path, files), (ROOT_PATH, base)))
    budget = {"measurement_budgets": [{"name": "cycle_edges", "provenance": ["d.md"]}]}
    module = {"modules": [{"path": "src/m.py", "responsibility": "Own m."}]}
    for label, declarations in (("budget", budget), ("module", module)):
        changed = dict(base)
        inner = json.loads(base["a/x/inside.json"])
        inner["declarations"] = declarations
        changed["a/x/inside.json"] = _encode(inner)
        pairs.append((f"inside declarations {label}", (ROOT_PATH, base), (ROOT_PATH, changed)))
        pairs.append((f"inside declarations {label} gone", (ROOT_PATH, changed), (ROOT_PATH, base)))
    return pairs


def _component(label: str, **extra: Any) -> dict[str, Any]:
    item: dict[str, Any] = {
        "id": f"C-{label}",
        "label": label,
        "role": "component",
        "packages": [f"p.{label}"],
        "responsibilities": [f"Own {label}."],
        "forbidden_responsibilities": [],
        "provenance": ["d.md"],
    }
    item.update(extra)
    return item


def _rule(identity: str, kind: str, **extra: Any) -> dict[str, Any]:
    return {
        "id": identity,
        "kind": kind,
        "rationale": "r",
        "provenance": ["d.md"],
        "decided_by": "architect",
        **extra,
    }


def _hand_base() -> dict[str, Any]:
    return {
        "schema_version": "3.14.0",
        "components": [
            _component(
                "a", decided_by="architect", public=["p.a.x"], planned=["p.a.y"], namespace="p.a"
            ),
            _component("b", requires=[{"component": "a", "rationale": "r", "through": ["p.a.x"]}]),
        ],
        "rules": [
            _rule(
                "R-DEP",
                "forbidden_dependency",
                source="p.b",
                target="p.a",
                include_type_checking=True,
            ),
            _rule(
                "R-OWN",
                "source_ownership",
                source="p",
                mode="confined",
                symbols=["p.a.x._f"],
                owner="p.a.x",
                roles=["definition", "read"],
            ),
            _rule(
                "R-NUM",
                "bounded_numeric_operand",
                source="p.a",
                form="binary",
                terminal_suffix="ms",
                minimum_value=10,
            ),
            _rule("R-IFACE", "interface_boundary", include_type_checking=True),
            _rule("R-CON", "forbidden_construct", source="p", constructs=["getattr", "eval"]),
        ],
        "declarations": {
            "compat": [{"module": "p.old", "target": "p.a", "lifetime": "migration"}],
            "measurement_budgets": [{"name": "cycle_edges", "provenance": ["d.md"]}],
            "facade_budgets": [{"component": "a", "max_names": 3, "provenance": ["d.md"]}],
            "coupling_budgets": [
                {"source": "b", "target": "a", "max_names": 2, "provenance": ["d.md"]}
            ],
        },
    }


def _edit(path: list[str | int], value: Any) -> Any:
    def apply(document: dict[str, Any]) -> None:
        target = _at(document, path[:-1])
        if value == "<delete>":
            target.pop(path[-1])
        else:
            target[path[-1]] = value

    return apply


HAND_EDITS: dict[str, list[Any]] = {
    "rule kind changed": [
        _edit(["rules", 0], _rule("R-DEP", "allowed_dependency", source="p.b", target="p.a"))
    ],
    "compat target changed": [_edit(["declarations", "compat", 0, "target"], "p.b")],
    "compat permanent": [_edit(["declarations", "compat", 0, "lifetime"], "permanent")],
    "compat removed": [_edit(["declarations", "compat"], [])],
    "budget lost": [_edit(["declarations", "measurement_budgets"], [])],
    "facade raised": [_edit(["declarations", "facade_budgets", 0, "max_names"], 4)],
    "facade removed": [_edit(["declarations", "facade_budgets"], [])],
    "coupling raised": [_edit(["declarations", "coupling_budgets", 0, "max_names"], 9)],
    "coupling removed": [_edit(["declarations", "coupling_budgets"], "<delete>")],
    "schema added": [_edit(["$schema"], "https://example.invalid/s.json")],
    "planned promoted": [
        _edit(["components", 0, "public"], ["p.a.x", "p.a.y"]),
        _edit(["components", 0, "planned"], []),
    ],
    "public moved": [_edit(["components", 0, "public"], ["p.a.z.x"])],
    "author inherited": [_edit(["components", 1, "decided_by"], "agent")],
    "requires symbol": [_edit(["components", 1, "requires", 0, "through"], ["p.a.x:K"])],
    "requires wider": [_edit(["components", 1, "requires", 0, "through"], ["p.a"])],
    "requires gone": [_edit(["components", 1, "requires"], [])],
    "requires replaced": [
        _edit(
            ["components", 1, "requires"],
            [{"component": "a", "rationale": "r", "through": ["p.a.x.y"]}],
        )
    ],
    "roles changed": [_edit(["rules", 1, "roles"], ["definition", "write"])],
    "mode changed": [_edit(["rules", 1, "mode"], "retired")],
    "minimum lowered": [_edit(["rules", 2, "minimum_value"], 5)],
    "minimum raised": [_edit(["rules", 2, "minimum_value"], 50)],
    "form changed": [_edit(["rules", 2, "form"], "both")],
    "rule rationale": [_edit(["rules", 2, "rationale"], "other")],
    "declarations removed": [_edit(["declarations"], "<delete>")],
    # The five pairs that the review of #1060 found without a killing test.
    "requires partial segment": [_edit(["components", 1, "requires", 0, "through"], ["p.a.xy"])],
    "planned also public": [_edit(["components", 0, "public"], ["p.a.x", "p.a.y"])],
    "construct lost": [_edit(["rules", 4, "constructs"], ["getattr"])],
    "minimum lowered by one": [_edit(["rules", 2, "minimum_value"], 9)],
    "namespace removed": [_edit(["components", 0, "namespace"], "<delete>")],
    # A message with a raw U+2028: the probe output must be split on line feeds only.
    "rule ID with a line separator": [_edit(["rules", 2, "id"], "R-NUM\u2028X")],
}

# Texts that Python `repr` writes with escapes or as they are (L-28): each named code point of
# the review of #1060 and the other classes of `str.isprintable` (C0, C1, Cf, Zs, Zl, Zp, Co, Cn,
# and printable letters, marks and symbols of each plane).
REPR_PROBES = [
    "\x00",
    "\x07",
    "\x1b",
    "\x7f",
    "\x85",
    "\x9f",
    "\xa0",
    "\xad",
    "\u0378",
    "\u0600",
    "\u061c",
    "\u070f",
    "\u115f",
    "\u1680",
    "\u180e",
    "\u2000",
    "\u200b",
    "\u200f",
    "\u2028",
    "\u2029",
    "\u202e",
    "\u2060",
    "\u2066",
    "\u3000",
    "\ud7ff",
    "\ue000",
    "\uf8ff",
    "\ufeff",
    "\ufff9",
    "\ufffe",
    "\U0001d173",
    "\U0001fae8",
    "\U000e0001",
    "\U000f0000",
    "\u00e9",
    "\u0301",
    "\u4e2d",
    "\U0001f600",
    "\U00010348",
    "'\"",
]
for _index, _probe in enumerate(REPR_PROBES):
    HAND_EDITS[f"repr probe {_index} layer"] = [_edit(["components", 0, "layer"], f"L{_probe}")]
    HAND_EDITS[f"repr probe {_index} responsibilities"] = [
        _edit(["components", 0, "responsibilities"], [f"Own {_probe}."])
    ]


def hand_pairs() -> list[Pair]:
    """Each hand-written change of a small contract, in both directions."""
    pairs: list[Pair] = []
    for name, edits in HAND_EDITS.items():
        before = _hand_base()
        after = copy.deepcopy(before)
        for edit in edits:
            edit(after)
        pairs.append((f"hand {name} (after)", _single(before), _single(after)))
        pairs.append((f"hand {name} (before)", _single(after), _single(before)))
    return pairs


def all_pairs() -> list[Pair]:
    return [*recorded_pairs(), *hand_pairs(), *mutated_pairs(), *inside_pairs()]
