# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-383: rustc decides the target of each probe call; the collector gives that edge or a gap.

Consumer: the soundness of the Rust collector for a method call on `self`. Each case of
`tests/rust_receiver_probes.py` is compiled with `rustc` (no `--cfg`, so `feature = "optional"` is
off) and run: the output is the module of the method that Rust calls. The collector must give the
edge to that module or a gap of the pair, never an edge of the call to another module and never
nothing. `make native-check` runs this file; without `rustc` it skips with that reason.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import zlib
from pathlib import Path
from typing import Any

import pytest
from rust_receiver_probes import CASES, KNOWN_MISSES, LIB, TYPES, caller

MANIFEST = '[package]\nname = "app"\nversion = "0.0.0"\nedition = "2021"\n'
MAIN = 'fn main() {\n    print!("{}", app::run());\n}\n'
SOURCE = "ns.app.a"


def _crate(root: Path, files: dict[str, str]) -> Path:
    source = root / "crates" / "app" / "src"
    source.mkdir(parents=True)
    (source.parent / "Cargo.toml").write_text(MANIFEST)
    every = {"lib.rs": LIB, "c.rs": TYPES, "a.rs": caller(), "b.rs": "", "d.rs": "", "e.rs": ""}
    for name, text in {**every, **files}.items():
        (source / name).write_text(text)
    return source


def _target(root: Path, source: Path) -> str:
    """The module that the program names: the real target of the call."""
    out = root / "out"
    out.mkdir()
    common = ["rustc", "--edition", "2021", "-A", "warnings", "--out-dir", str(out)]
    library = [*common, "--crate-type", "lib", "--crate-name", "app", str(source / "lib.rs")]
    done = subprocess.run(library, capture_output=True, text=True)
    assert done.returncode == 0, done.stderr
    (root / "main.rs").write_text(MAIN)
    program = [*common, "--extern", f"app={out / 'libapp.rlib'}", str(root / "main.rs")]
    done = subprocess.run(program, capture_output=True, text=True)
    assert done.returncode == 0, done.stderr
    return subprocess.run([str(out / "main")], capture_output=True, text=True, check=True).stdout


def _records(binary: Path, root: Path) -> dict[str, list[dict[str, Any]]]:
    request = {
        "protocol_version": "9.0.0",
        "snapshot": {"root": str(root), "git_head": "0" * 40, "dirty": False},
        "scope": {"roots": ["crates"], "namespace": "ns", "exclude_test_sources": True},
        "resolver": {"language": "rust"},
    }
    done = subprocess.run([str(binary)], input=json.dumps(request).encode(), capture_output=True)
    assert done.returncode == 0, done.stderr
    facts = json.loads(zlib.decompress(done.stdout))["facts"]
    return {s["name"]: [r["data"] for r in s["records"]] for s in facts["sections"]}


def outcome(records: dict[str, list[dict[str, Any]]], target: str) -> str:
    """What the collector says about the call: `exact edge` (the call resolved), `edge` (another
    record of `a` to the target), `gap`, `scan gap`, `same module`, or the failure `wrong edge`
    or `missed`."""
    module = f"ns.app.{target}"
    imports = [d for d in records.get("imports", ()) if d["source_module"] == SOURCE]
    specifiers = ("self.", "Self::")
    resolved = {d["target_module"] for d in imports if str(d["specifier"]).startswith(specifiers)}
    if resolved - {module}:
        return "wrong edge"
    if target == "a":
        return "same module"
    if module in resolved:
        return "exact edge"
    if module in {d["target_module"] for d in imports}:
        return "edge"
    unknowns = records.get("unknowns", ())
    if any(d.get("source_module") == SOURCE and d.get("module") == module for d in unknowns):
        return "gap"
    if any(not d.get("source_module") for d in unknowns):
        return "scan gap"
    return "missed"


@pytest.fixture(scope="module")
def rustc() -> None:
    if shutil.which("rustc") is None:
        pytest.skip("rustc is not on PATH: the probes need the compiler to know the real target.")


@pytest.mark.parametrize("name", sorted(CASES))
def test_the_collector_gives_the_real_target_or_a_gap(
    name: str, rustc: None, rust_binary: Path, tmp_path: Path
) -> None:
    source = _crate(tmp_path, CASES[name])
    target = _target(tmp_path, source)
    found = outcome(_records(rust_binary, tmp_path), target)
    print(f"PROBE | {name} | {target} | {found}")
    if name in KNOWN_MISSES:
        assert found == "missed", f"{name}: {found}; remove it from KNOWN_MISSES"
        return
    assert found not in ("wrong edge", "missed"), f"{name}: Rust calls {target}, collector {found}"


def test_there_are_at_least_thirty_cases() -> None:
    assert len(CASES) >= 30
