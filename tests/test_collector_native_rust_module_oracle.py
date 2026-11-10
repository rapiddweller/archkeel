# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-335: the module edges of the Rust collector equal the errors of `cargo check`.

Consumer: the entry criterion of slice 5b-2c. The oracle is the compiler. For a module `m` of
`native/`, delete the line `mod m;` from a copy and run `cargo check --all-features`. The files with
a name resolution error in the crate of `m` must be exactly the files with an edge into `m` or
into a module below it. A production scope is used (no `--tests`), as the request that excludes
test sources reads it. `make native-check` runs the seven modules below; a run over all 108
modules of `native/` was a one-off and is not part of the gate.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import zlib
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).parents[1]
RESOLUTION_ERRORS = {
    "E0432",
    "E0433",
    "E0412",
    "E0425",
    "E0405",
    "E0422",
    "E0423",
    "E0531",
    "E0599",
}
MODULES = [
    "archkeel_rust_collector.paths",
    "archkeel_rust_collector.tokens",
    "archkeel_rust_collector.manifest",
    "archkeel_rust_collector.resolve",
    "archkeel_rust_collector.scan",
    "archkeel_typescript_collector.kinds",
    "archkeel_typescript_collector.sites",
]


def _facts(binary: Path) -> dict[str, Any]:
    request = {
        "protocol_version": "9.0.0",
        "snapshot": {"root": str(ROOT), "git_head": "0" * 40, "dirty": False},
        "scope": {"roots": ["native"], "namespace": "native", "exclude_test_sources": True},
        "resolver": {"language": "rust"},
    }
    done = subprocess.run([str(binary)], input=json.dumps(request).encode(), capture_output=True)
    assert done.returncode == 0, done.stderr
    return json.loads(zlib.decompress(done.stdout))["facts"]  # type: ignore[no-any-return]


def _crate(module: str) -> str:
    return ".".join(module.split(".")[:2])


def _without_declaration(text: str, name: str) -> str:
    lines = text.split("\n")
    found = [
        i for i, line in enumerate(lines) if re.match(rf"\s*(pub\S*\s+)?mod\s+{name}\s*;", line)
    ]
    assert len(found) == 1, name
    start = found[0]
    while start and lines[start - 1].strip().startswith("#["):
        start -= 1
    return "\n".join(lines[:start] + lines[found[0] + 1 :])


@pytest.fixture(scope="module")
def facts(rust_binary: Path) -> dict[str, Any]:
    if shutil.which("cargo") is None:
        pytest.skip("cargo is not installed; install Rust to run the oracle.")
    return _facts(rust_binary)


@pytest.fixture(scope="module")
def target(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """One build directory for all runs: the registry crates compile once."""
    return tmp_path_factory.mktemp("target")


@pytest.mark.parametrize("name", MODULES)
def test_the_files_with_an_edge_into_a_module_are_the_files_that_fail_without_it(
    name: str, facts: dict[str, Any], tmp_path: Path, target: Path
) -> None:
    module = f"native.{name}"
    files = {item["module"]: item["rel_path"] for item in facts["files"]}
    records = [r for s in facts["sections"] if s["name"] == "imports" for r in s["records"]]

    def below(other: str) -> bool:
        return other == module or other.startswith(module + ".")

    expected = {
        files[data["source_module"]]
        for data in (record["data"] for record in records)
        if below(data["target_module"])
        and not below(data["source_module"])
        and _crate(data["source_module"]) == _crate(module)
    }
    parent = module.rsplit(".", 1)[0]
    work = tmp_path / "work"
    shutil.copytree(ROOT / "native", work / "native", ignore=shutil.ignore_patterns("target"))
    declared = work / files[parent]
    declared.write_text(_without_declaration(declared.read_text(), module.rsplit(".", 1)[1]))
    checked = subprocess.run(
        ["cargo", "check", "--offline", "--workspace", "--all-features", "--message-format=json"],
        cwd=work / "native",
        capture_output=True,
        text=True,
        env={**os.environ, "CARGO_TARGET_DIR": str(target)},
    )
    crate_dir = files[module].split("/")[1]
    failing: set[str] = set()
    for line in checked.stdout.splitlines():
        message = json.loads(line) if line.startswith("{") else {}
        if message.get("reason") != "compiler-message":
            continue
        body = message["message"]
        if body["level"] == "error" and (body.get("code") or {}).get("code") in RESOLUTION_ERRORS:
            failing |= {
                f"native/{span['file_name']}"
                for span in body["spans"]
                if span["is_primary"] and span["file_name"].split("/")[0] == crate_dir
            }

    assert expected, "the fixture module has no importer"
    assert failing == expected
