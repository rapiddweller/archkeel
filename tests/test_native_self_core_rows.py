# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-418, AD-432: the core decides each rule of the self-contract of native/ (#880).

The test runs the default `archkeel validate` on `native/` of this tree with the core of this
build. Each rule has a row: no rule names a part of the scope proof. The rows equal the pinned
file `native/expected-gaps.json`, which `make self-validate-native` checks with the same code.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import zlib
from pathlib import Path
from typing import Any

import pytest
from core_support import NATIVE, ROOT, SUFFIX, run
from frozen_native import frozen_root as frozen_root

from archkeel.cli import core_only

sys.path.insert(0, str(ROOT / "tools"))
from native_expected import expected_exit, problems  # noqa: E402


@pytest.fixture(scope="module")
def checked(built: Path, frozen_root: Path) -> tuple[int, dict[str, Any]]:
    """One default run on `native/` for the tests of this file: the exit code and the result."""
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(core_only, "locate_core", lambda: built / f"archkeel-core{SUFFIX}")
        return run("validate", "--root", str(frozen_root), "--config", "native/archkeel.toml")


def test_the_core_decides_each_rule_of_the_self_contract(
    checked: tuple[int, dict[str, Any]],
) -> None:
    code, result = checked
    frame = result["frame"]
    core = {rule: row[1] for rule, row in frame["rules"].items()}
    expected = json.loads((NATIVE / "expected-gaps.json").read_text())
    assert problems(result, expected) == []
    assert core, "the self-contract has rules"
    # No rule names a part of the scope proof: each one has a decision.
    assert result["gaps"] == []
    # AD-668: a known violation stays FAIL, as pinned (honesty rule). An UNKNOWN rule is one that
    # the pin names with its reason (AD-670: the Rust collector states no public symbol facts yet).
    assert {rule for rule, status in core.items() if status == "UNKNOWN"} == set(
        expected["unknown"]
    )
    assert core == expected["rules"]
    status = (
        "FAIL" if "FAIL" in core.values() else "UNKNOWN" if "UNKNOWN" in core.values() else "PASS"
    )
    assert (code, result["status"], frame["status"]) == (expected_exit(expected), status, status)
    assert set(frame["unknown_kinds"]) == {r for r, status in core.items() if status == "UNKNOWN"}
    # The scope follows the pin (the ratchet): a pin without gaps gives a complete scope; a pin with
    # gaps gives an incomplete one that counts at most the pinned gaps (the contract allows some).
    if not expected["gaps"]:
        assert frame["scope"] == "complete"
    else:
        found = re.fullmatch(r"incomplete scope: (\d+) gaps? .*", frame["scope"], re.DOTALL)
        assert found, frame["scope"]
        assert 0 < int(found.group(1)) <= len(expected["gaps"])


# Review B2 and B3 of #1121: `core` reaches the collector crates only through `archkeel_collect`.
# The scan lists no method in the file of its type and no trait method as a candidate (open
# classes, docs/known-limits.md), so a value of a collector type in `core` could reach one without
# a gap. The items that `collect` takes from a collector crate return only facts types and text, so
# no such value reaches `core`. The pin reads the import records of the reply, not source text: an
# alias (`extern crate ... as`) or a renamed dependency is a record too. A new record fails the
# test, and the row of `core` has to be decided again.
COLLECT = "native.archkeel_collect"
TS = "native.archkeel_typescript_collector"
# AD-450: `BUILD` is the version and code digest text of the Python collector. It stays in collect.
PY = "native.archkeel_python_collector"
# AD-468: the Dart items return a `Reply`, a `Provenance` and text, all facts types.
DART = "native.archkeel_dart_collector"
COLLECT_TO_COLLECTORS = {
    ("native.archkeel_collect", "archkeel_typescript_collector::TEST_FEATURES", TS),
    ("native.archkeel_collect.cargo_toml", "dependencies: archkeel-typescript-collector", TS),
    ("native.archkeel_collect.run", "archkeel_typescript_collector::provenance", TS),
    ("native.archkeel_collect.run", "archkeel_typescript_collector::typed_reply", TS),
    ("native.archkeel_collect", "archkeel_python_collector::TEST_FEATURES", PY),
    ("native.archkeel_collect.cargo_toml", "dependencies: archkeel-python-collector", PY),
    ("native.archkeel_collect.run", "archkeel_python_collector::BUILD", PY),
    ("native.archkeel_collect.run", "archkeel_python_collector::typed_reply", PY),
    # AD-688: the check of the collector gives the core only a refusal text.
    ("native.archkeel_collect.run", "archkeel_python_collector::check", PY),
    ("native.archkeel_collect", "archkeel_dart_collector::TEST_FEATURES", DART),
    ("native.archkeel_collect.cargo_toml", "dependencies: archkeel-dart-collector", DART),
    ("native.archkeel_collect.run", "archkeel_dart_collector::provenance", DART),
    ("native.archkeel_collect.run", "archkeel_dart_collector::typed_reply", DART),
    ("native.archkeel_collect.run", "archkeel_dart_collector::check", DART),
}


def _crate(module: str) -> str:
    return ".".join(module.split(".")[:2])


@pytest.fixture(scope="module")
def import_records(built: Path, checked: tuple[int, dict[str, Any]]) -> list[dict[str, Any]]:
    # The core states the request that it sent to its collector; the Rust collector of the same
    # build answers it again here, so the test reads the import records themselves.
    request = checked[1]["frame"]["self_test"]["collect"]["request"]
    done = subprocess.run(
        [str(built / f"archkeel-rust-collector{SUFFIX}")],
        input=json.dumps(request, sort_keys=True, separators=(",", ":")).encode(),
        capture_output=True,
        check=False,
    )
    assert done.returncode == 0, done.stderr.decode(errors="replace")
    reply = json.loads(zlib.decompress(done.stdout))
    return [
        record["data"]
        for section in reply["facts"]["sections"]
        if section["name"] == "imports"
        for record in section["records"]
    ]


def test_snapshot_io_does_not_depend_on_collector_facts(
    import_records: list[dict[str, Any]],
) -> None:
    snapshot = "native.archkeel_snapshot"
    facts = "native.archkeel_facts"
    assert any(_crate(row["source_module"]) == snapshot for row in import_records)
    assert [
        row
        for row in import_records
        if _crate(row["source_module"]) == snapshot and _crate(row["target_module"]) == facts
    ] == []


def test_collect_hands_core_no_value_of_a_collector_type(
    import_records: list[dict[str, Any]],
) -> None:
    records = import_records
    # The collector crates are the crates of the reply whose name says so; a new one (the Rust
    # collector of #1120) is in the set without a change of this test.
    modules = {data[end] for data in records for end in ("source_module", "target_module")}
    collectors = {_crate(module) for module in modules if _crate(module).endswith("_collector")}
    found = {
        (data["source_module"], data["specifier"], _crate(data["target_module"]))
        for data in records
        if _crate(data["source_module"]) == COLLECT and _crate(data["target_module"]) in collectors
    }
    assert found == COLLECT_TO_COLLECTORS
