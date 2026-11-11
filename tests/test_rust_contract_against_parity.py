# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-373: the Rust contract crate compares two contract trees as `validate --against` does.

For each pair of `rust_contract_against_cases` the list of changes must be equal: each widening
of `contract_widening_changes` and `_inside_declaration_widenings`, then each narrowing of
`contract_narrowing_changes`, with direction, subject, field and message, in the same order. A
widening that Rust misses is a false PASS of a CI gate, so the decision (any widening) is
counted on its own. When a tree cannot be assembled, both sides must refuse the pair. Rust is
stricter only in the named cases of AD-364 and AD-366 (`STRICTER`).

The messages are byte-equal, also where Python writes the `repr` of a value. The oracle is
Python 3.11: `repr` escapes each character that `str.isprintable` refuses, and the Rust crate holds
that table from Python 3.11 (Unicode 14, L-28). On Python 3.12 or later a code point assigned after
Unicode 14 gives other message bytes, so the tests that compare messages run on 3.11 only.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import pytest
from filelock import FileLock
from rust_contract_against_cases import Tree, all_pairs, recorded_pairs
from rust_contract_tree_cases import identity

from archkeel.check.validation import _inside_declaration_widenings
from archkeel.ir.codec import InsideContractTree, load_inside_contract_tree, parse_contract
from archkeel.ir.codec_wire import decode_json
from archkeel.ir.widening import contract_narrowing_changes, contract_widening_changes

NATIVE = Path(__file__).parents[1] / "native"
# The named stricter cases of AD-364 and AD-366 that the pairs reach: Rust refuses a JSON object
# with one key two times, and a mount deeper than 900 levels.
STRICTER = ("inside with duplicate key", "inside chain one level deeper")


def _probe() -> Path:
    cargo = shutil.which("cargo")
    if cargo is None and os.environ.get("CI"):
        pytest.fail("CI must provide cargo for the native contract comparison parity test.")
    if cargo is None:
        pytest.skip("cargo is not installed; install Rust to test changes in native/.")
    (NATIVE / "target").mkdir(exist_ok=True)
    name = "contract_against_dump"
    command = [cargo, "build", "--locked", "--release", "-p", "archkeel-contract"]
    command += ["--example", name]
    with FileLock(str(NATIVE / "target" / ".pytest-native-build.lock")):
        built = subprocess.run(command, cwd=NATIVE, capture_output=True, text=True, check=False)
    assert built.returncode == 0, built.stderr
    # A release build: the corpus has 4 000 pairs, and a debug build reads them ten times slower.
    return NATIVE / "target/release/examples" / (name + (".exe" if os.name == "nt" else ""))


def _sources(tree: Tree) -> list[list[str]]:
    root_path, files = tree
    return [[root_path, files[root_path].hex()]] + [
        [path, data.hex()] for path, data in files.items() if path != root_path
    ]


def _rust(probe: Path, pairs: list[tuple[Tree, Tree]]) -> list[dict[str, Any]]:
    text = "".join(
        json.dumps({"before": _sources(before), "after": _sources(after)}) + "\n"
        for before, after in pairs
    )
    run = subprocess.run([probe], input=text.encode(), capture_output=True, check=True)
    # Split on line feeds only: a message may hold U+2028, which `splitlines` also splits on.
    return [json.loads(line) for line in run.stdout.decode().split("\n") if line]


def _tree(tree: Tree, read_paths: set[str] | None = None) -> InsideContractTree | None:
    root_path, files = tree

    def read(reference: str) -> tuple[bytes, str]:
        key = identity(reference)
        if key is None or key not in files:
            raise ValueError("missing")
        if read_paths is not None:
            read_paths.add(key)
        return files[key], reference

    root_bytes = files[root_path]
    try:
        contract = parse_contract(decode_json(root_bytes))
        digest = hashlib.sha256(root_bytes).hexdigest()
        loaded = load_inside_contract_tree(root_path, contract, digest, root_path, read)
    except ValueError:
        return None
    return None if loaded.issues else loaded


def _load(tree: Tree) -> tuple[InsideContractTree | None, Tree]:
    """The Python tree, and the bytes that the shell sends: the root and each file that the tree
    reads. Rust refuses bytes that no mount reads (AD-366)."""
    root_path, files = tree
    read_paths = {root_path}
    loaded = _tree(tree, read_paths)
    if loaded is None:
        return None, tree
    return loaded, (root_path, {path: data for path, data in files.items() if path in read_paths})


def _python(old: InsideContractTree | None, new: InsideContractTree | None) -> dict[str, Any]:
    if old is None or new is None:
        return {"kind": "refused"}
    widened = [
        *contract_widening_changes(old.comparison_contract, new.comparison_contract),
        *_inside_declaration_widenings(old, new, None),
    ]
    narrowed = contract_narrowing_changes(old.comparison_contract, new.comparison_contract)
    changes = [
        {"direction": direction, "subject": item.subject, "field": item.field, "message": text}
        for direction, items in (("widened", widened), ("narrowed", narrowed))
        for item in items
        for text in [item.message]
    ]
    return {"kind": "compared", "widened": bool(widened), "changes": changes}


@pytest.mark.requires_python(below=12)
def test_the_printable_table_is_the_table_of_python_3_11() -> None:
    tool = Path(__file__).parents[1] / "tools/contract_printable.py"
    checked = subprocess.run([sys.executable, str(tool), "--check"], check=False)
    assert checked.returncode == 0, "run python3.11 tools/contract_printable.py"


@pytest.mark.requires_python(below=12)
def test_the_rust_comparison_is_the_python_comparison() -> None:
    probe = _probe()
    pairs = all_pairs()
    loaded = [(_load(before), _load(after)) for _, before, after in pairs]
    python = [_python(old[0], new[0]) for old, new in loaded]
    rust = _rust(probe, [(old[1], new[1]) for old, new in loaded])
    tally: Counter[str] = Counter()
    for (name, _, _), expected, actual in zip(pairs, python, rust, strict=True):
        if any(case in name for case in STRICTER):
            assert actual == {"kind": "refused"}, name
            tally["stricter"] += 1
            continue
        assert actual.get("widened") == expected.get("widened"), (name, expected, actual)
        assert actual == expected, name
        kind = expected["kind"]
        tally[kind if kind != "compared" else ("widened" if expected["widened"] else "same")] += 1
        for item in expected.get("changes", []):
            tally[f"{item['direction']} {item['field']}"] += 1
    print(dict(tally))
    assert tally["widened"] >= 2000, tally
    assert tally["same"] >= 500, tally
    assert tally["refused"] >= 20, tally
    assert tally["narrowed requires"] >= 1, tally


def test_the_recorded_against_cases_are_compared() -> None:
    pairs = recorded_pairs()
    assert len(pairs) == 15
    results = [_python(_tree(before), _tree(after)) for _, before, after in pairs]
    assert all(item["kind"] == "compared" for item in results)
    assert sum(item["widened"] for item in results) >= 8
