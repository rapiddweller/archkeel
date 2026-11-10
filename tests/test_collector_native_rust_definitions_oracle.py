# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-351: the definitions of the Rust collector equal `rustdoc --output-format json`.

Consumer: the entry criterion of slice 5b-4a. The oracle is the compiler front end. The test runs
rustdoc on the crate `archkeel-rust-collector` of `native/` and compares its production items with
the symbols of the collector: file, name, kind, visibility and the type of a method. Two differences
are allowed, and the test states each one:

1. `build.rs` is a build script: rustdoc does not document it, and the collector reads it.
2. A method of an `impl` that is in another module than its type (`impl Builder` in `edges.rs`,
   the type in `builder.rs`). The collector places a member only when the type is a definition of
   the same module, so it gives no record. Slice 5b-4b can place them with the module index.

Not compared: fields, associated types, `extern` blocks and the visibility of a module (a `mod`
is a file fact). Rustdoc cannot tell `pub(crate)` from private at the crate root, so the test
reads `crate` there as private.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import zlib
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).parents[1]
CRATE = "native.archkeel_rust_collector"
KINDS = {
    "function": "function",
    "struct": "class",
    "union": "class",
    "enum": "class",
    "trait": "class",
    "constant": "constant",
    "static": "static_constant",
    "type_alias": "type_alias",
    "macro": "macro",
}
Row = tuple[str, str, str, str, str | None]


def _collector_rows(binary: Path) -> set[Row]:
    request = {
        "protocol_version": "9.0.0",
        "snapshot": {"root": str(ROOT), "git_head": "0" * 40, "dirty": False},
        "scope": {"roots": ["native"], "namespace": "native", "exclude_test_sources": True},
        "resolver": {"language": "rust"},
    }
    done = subprocess.run([str(binary)], input=json.dumps(request).encode(), capture_output=True)
    assert done.returncode == 0, done.stderr
    facts = json.loads(zlib.decompress(done.stdout))["facts"]
    cited = {item["id"]: item["file"] for item in facts["evidence"]}
    rows: set[Row] = set()
    for section in facts["sections"]:
        for record in section["records"] if section["name"] == "symbols" else ():
            data = record["data"]
            if not data["module"].startswith(CRATE):
                continue
            holder = data["parent"].rsplit(".", 1)[-1] if data["parent"] else None
            rows.add(
                (
                    cited[record["evidence_ids"][0]],
                    data["name"],
                    record["kind"],
                    data["visibility_detail"]["kind"],
                    holder,
                )
            )
    return rows


def _rustdoc(target: Path) -> dict[str, Any]:
    done = subprocess.run(
        [
            "cargo",
            "rustdoc",
            "--offline",
            "--package",
            "archkeel-rust-collector",
            "--bin",
            "archkeel-rust-collector",
            "--",
            "-Z",
            "unstable-options",
            "--output-format",
            "json",
            "--document-private-items",
        ],
        cwd=ROOT / "native",
        capture_output=True,
        text=True,
        env={**os.environ, "RUSTC_BOOTSTRAP": "1", "CARGO_TARGET_DIR": str(target)},
    )
    assert done.returncode == 0, done.stderr
    path = target / "doc" / "archkeel_rust_collector.json"
    return json.loads(path.read_text())  # type: ignore[no-any-return]


class _Docs:
    """The production items of one rustdoc document, as rows of the collector."""

    def __init__(self, doc: dict[str, Any]) -> None:
        self.index: dict[str, Any] = doc["index"]
        self.files: dict[str, str] = {}
        self._modules(doc["root"], [])

    def _modules(self, identifier: int, path: list[str]) -> None:
        module = self.index[str(identifier)]
        self.files[module["span"]["filename"]] = "::" + "::".join(path)
        for child in module["inner"]["module"]["items"]:
            item = self.index[str(child)]
            if "module" in item["inner"]:
                self._modules(child, [*path, item["name"]])

    def visibility(self, item: dict[str, Any]) -> str:
        value = item["visibility"]
        own = self.files.get(item["span"]["filename"])
        if value == "public":
            return "public"
        if value == "crate":
            return "private" if own == "::" else "package"
        if value == "default":
            return "private"
        return "private" if value["restricted"]["path"] == own else "package"

    def rows(self) -> set[Row]:
        found: set[Row] = set()
        members: set[int] = set()
        for item in self.index.values():
            inner = item["inner"]
            if "impl" in inner:
                members.update(inner["impl"]["items"])
                if inner["impl"]["trait"] is None:
                    found |= self._members(inner["impl"]["items"], self._impl_type(inner["impl"]))
            elif "trait" in inner:
                members.update(inner["trait"]["items"])
                found |= self._members(inner["trait"]["items"], item["name"], item)
        for identifier, item in self.index.items():
            kind = next(iter(item["inner"]))
            if int(identifier) in members or item["crate_id"] != 0 or kind not in KINDS:
                continue
            if item.get("span"):
                file = "native/" + item["span"]["filename"]
                found.add((file, item["name"], KINDS[kind], self.visibility(item), None))
        return found

    @staticmethod
    def _impl_type(impl: dict[str, Any]) -> str | None:
        target = impl["for"]
        return target["resolved_path"]["path"].split("::")[-1] if "resolved_path" in target else None

    def _members(
        self, items: list[int], holder: str | None, trait: dict[str, Any] | None = None
    ) -> set[Row]:
        rows: set[Row] = set()
        for identifier in items:
            item = self.index[str(identifier)]
            if "function" not in item["inner"]:
                continue
            visible = self.visibility(trait or item)
            file = "native/" + item["span"]["filename"]
            rows.add((file, item["name"], "method", visible, holder))
        return rows


@pytest.fixture(scope="module")
def compared(
    rust_binary: Path, tmp_path_factory: pytest.TempPathFactory
) -> tuple[set[Row], set[Row]]:
    if shutil.which("cargo") is None:
        pytest.skip("cargo is not installed; install Rust to run the oracle.")
    docs = _Docs(_rustdoc(tmp_path_factory.mktemp("rustdoc")))
    return _collector_rows(rust_binary), docs.rows()


def test_the_only_definition_that_rustdoc_lacks_is_the_build_script(
    compared: tuple[set[Row], set[Row]],
) -> None:
    collector, rustdoc = compared
    assert collector - rustdoc == {("native/rust/build.rs", "main", "function", "private", None)}


def test_the_methods_that_the_collector_lacks_are_impls_in_another_module_than_their_type(
    compared: tuple[set[Row], set[Row]],
) -> None:
    collector, rustdoc = compared
    types = {(file, name) for file, name, kind, _, holder in rustdoc if kind == "class"}
    missing = rustdoc - collector
    assert missing, "the allowed difference is gone: lower this test"
    for file, name, kind, _, holder in missing:
        assert kind == "method", (file, name)
        assert (file, holder) not in types, f"{name} of {holder} is in the file of its type"


def test_the_collector_and_rustdoc_agree_on_most_definitions(
    compared: tuple[set[Row], set[Row]],
) -> None:
    collector, rustdoc = compared
    assert len(collector & rustdoc) >= 230
    assert {row[3] for row in collector & rustdoc} == {"public", "package", "private"}
