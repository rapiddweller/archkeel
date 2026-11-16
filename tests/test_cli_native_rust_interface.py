# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-604: the core decides `interface_boundary` for Rust from the item and route of each import.

Each plant is a small Cargo workspace that rustc accepts (`cargo check`), so a FAIL is a use of a
name that the contract does not publish, not code that cannot build. A use of a public name passes,
also through a re-export or a binding of its module. A use of another name fails. A form whose name
the scan does not know (a glob), a name that a macro may publish further, and a method call whose
receiver the scan does not know are UNKNOWN, never PASS.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest
from corpus_support import commit_tree
from rust_repository import claims, component, repository, rule, statuses, validate

pytestmark = pytest.mark.skipif(shutil.which("cargo") is None, reason="rustc is the oracle")

BASE = {
    "crates/base/src/lib.rs": (
        "pub mod shapes;\npub mod relay;\nmod inner;\nmod extra;\npub mod made;\n"
        "pub use inner::Thing;\n"
        "pub fn make() {}\npub fn secret() {}\npub struct Tool;\n"
    ),
    "crates/base/src/inner.rs": "pub struct Thing;\n",
    "crates/base/src/shapes.rs": "pub struct Circle;\npub struct Square;\n",
    # AD-608: a macro whose expansion writes `pub use` may publish its name further.
    "crates/base/src/relay.rs": (
        "macro_rules! pass {\n    () => {\n        pub use std::string::String as Text;\n"
        "    };\n}\n"
        "pass!();\n"
    ),
    "crates/base/src/made.rs": (
        "macro_rules! def {\n    ($n:ident) => {\n        pub struct $n;\n    };\n}\ndef!(Gen);\n"
    ),
    "crates/base/src/extra.rs": (
        "impl crate::Tool {\n    pub fn build() -> Self {\n        crate::Tool\n    }\n}\n"
    ),
}
PUBLIC = ["native.base_crate:make", "native.base_crate:Thing", "native.base_crate.shapes:Circle"]
VIOLATION = "BOUNDARY: native.app -> {}: import outside the public interface"
# (name, source of the app crate, more public entries, status of the rule, the claim of the rule)
PLANTS = [
    ("public", "use base_crate::make;\npub fn run() { make(); }\n", [], "PASS", None),
    (
        "private",
        "use base_crate::secret;\npub fn run() { secret(); }\n",
        [],
        "FAIL",
        VIOLATION.format("native.base_crate:secret"),
    ),
    ("reexport", "use base_crate::Thing;\npub fn run() -> Thing { Thing }\n", [], "PASS", None),
    (
        "deep path",
        "pub fn run() -> base_crate::shapes::Square { base_crate::shapes::Square }\n",
        [],
        "FAIL",
        VIOLATION.format("native.base_crate.shapes:Square"),
    ),
    (
        "module binding",
        "use base_crate::shapes;\npub fn run() -> shapes::Circle { shapes::Circle }\n",
        [],
        "PASS",
        None,
    ),
    (
        "use through a module binding",
        "use base_crate::shapes;\npub fn run() -> shapes::Square { shapes::Square }\n",
        [],
        "FAIL",
        VIOLATION.format("native.base_crate.shapes:Square"),
    ),
    (
        "crate alias",
        "use base_crate as b;\npub fn run() { b::secret(); }\n",
        [],
        "FAIL",
        VIOLATION.format("native.base_crate:secret"),
    ),
    (
        "glob",
        "use base_crate::*;\npub fn run() { make(); }\n",
        [],
        "UNKNOWN",
        "BOUNDARY: incomplete scope: interface_boundary: unread import binding",
    ),
    (
        "item that a macro defines",
        "use base_crate::made::Gen;\npub fn run() -> Gen { Gen }\n",
        [],
        "FAIL",
        VIOLATION.format("native.base_crate.made:Gen"),
    ),
    (
        "item that a macro may publish further",
        "pub fn run() -> base_crate::relay::Text { base_crate::relay::Text::new() }\n",
        [],
        "UNKNOWN",
        "BOUNDARY: incomplete scope: interface_boundary: unproven publication route",
    ),
    (
        "macro item at a public hop",
        "use base_crate::made::Gen;\npub fn run() -> Gen { Gen }\n",
        ["native.base_crate.made:Gen"],
        "PASS",
        None,
    ),
    (
        "method of an unknown receiver",
        "pub fn run() -> base_crate::Tool { base_crate::Tool::build() }\n",
        ["native.base_crate:Tool", "native.base_crate.extra:Tool"],
        "UNKNOWN",
        "BOUNDARY: incomplete scope: 1 gaps between two modules that the contract does not allow: "
        "native.app -> native.base_crate.extra",
    ),
]


def _rustc_accepts(root: Path) -> None:
    manifest = root / "crates/Cargo.toml"
    env = {**os.environ, "CARGO_TARGET_DIR": str(root / "target")}
    done = subprocess.run(
        ["cargo", "check", "--quiet", "--offline", "--manifest-path", str(manifest)],
        capture_output=True,
        text=True,
        env=env,
    )
    assert done.returncode == 0, done.stderr


def _run(root: Path, binary: Path, files: dict[str, str], parts: tuple[dict[str, Any], ...]) -> Any:
    rules = (
        rule("BOUNDARY", "interface_boundary"),
        rule("ASSIGNED", "complete_assignment", source="native"),
    )
    repository(root, binary, files, parts, rules)
    path = root / "architecture-contract.json"
    contract = json.loads(path.read_text())
    contract["schema_version"] = "3.14.0"
    path.write_text(json.dumps(contract, indent=2))
    commit_tree(root)
    _rustc_accepts(root)
    result = validate(root)
    found = [c for c in claims(result) if c.startswith("BOUNDARY")]
    return statuses(result)["BOUNDARY"], found


@pytest.mark.parametrize(("name", "source", "more", "status", "claim"), PLANTS)
def test_each_rust_form_gets_the_verdict_of_its_route(
    core_binary: Path,
    tmp_path: Path,
    name: str,
    source: str,
    more: list[str],
    status: str,
    claim: str | None,
) -> None:
    base = {**component("base", "base_crate"), "public": PUBLIC + more}
    app = component("app", "app", ("base",))
    files = {**BASE, "crates/app/src/lib.rs": source}
    found_status, found = _run(tmp_path, core_binary, files, (base, app))
    assert found_status == status, (name, found)
    assert claim is None or claim in found, (name, found)


@pytest.mark.parametrize(
    ("public", "status"), [(["native.base_crate.extra:Tool"], "PASS"), ([], "FAIL")]
)
def test_a_member_of_a_type_is_published_by_the_type_in_the_module_of_its_block(
    core_binary: Path, tmp_path: Path, public: list[str], status: str
) -> None:
    """The root calls `Tool::build`, which a block of another component defines (#953)."""
    root = {
        **component("base", "base_crate"),
        "packages": [],
        "exact_modules": ["native.base_crate"],
    }
    root["requires"] = [{"component": "extra", "rationale": "The root builds its tool."}]
    extra = {**component("extra", "base_crate.extra"), "public": public}
    manifest = {**component("manifest", "base_crate.cargo_toml")}
    app = component("app", "app", ("base",))
    files = {
        **BASE,
        "crates/base/src/lib.rs": BASE["crates/base/src/lib.rs"]
        + "pub fn tool() -> Tool {\n    Tool::build()\n}\n",
        "crates/app/src/lib.rs": "pub fn run() {}\n",
    }
    root["exact_modules"] += [
        f"native.base_crate.{m}" for m in ("shapes", "inner", "made", "relay")
    ]
    found_status, found = _run(tmp_path, core_binary, files, (root, extra, manifest, app))
    assert found_status == status, found
    if status == "FAIL":
        assert (
            VIOLATION.replace("native.app", "native.base_crate").format(
                "native.base_crate.extra:Tool"
            )
            in found
        )


ROOT_PUBLIC = ["native.base_crate:Circle", "native.base_crate:Thing", "native.base_crate:make"]
# AD-608: the root of `base` publishes `Circle`; its one public path is the root.
ROOT_PLANTS = [
    ("root path", "use base_crate::Circle;\npub fn run() -> Circle { Circle }\n", "PASS"),
    (
        "deeper path of a root name",
        "use base_crate::shapes::Circle;\npub fn run() -> Circle { Circle }\n",
        "FAIL",
    ),
    (
        "path through a module binding",
        "use base_crate::shapes;\npub fn run() -> shapes::Circle { shapes::Circle }\n",
        "FAIL",
    ),
]


@pytest.mark.parametrize(("name", "source", "status"), ROOT_PLANTS)
def test_a_name_that_a_crate_root_publishes_has_the_root_as_its_one_path(
    core_binary: Path, tmp_path: Path, name: str, source: str, status: str
) -> None:
    base = {**component("base", "base_crate"), "public": ROOT_PUBLIC}
    app = component("app", "app", ("base",))
    lib = BASE["crates/base/src/lib.rs"] + "pub use shapes::Circle;\n"
    files = {**BASE, "crates/base/src/lib.rs": lib, "crates/app/src/lib.rs": source}
    found_status, found = _run(tmp_path, core_binary, files, (base, app))
    assert found_status == status, (name, found)
    if status == "FAIL":
        assert VIOLATION.format("native.base_crate.shapes:Circle") in found, (name, found)


PUBLISHED = (
    "BOUNDARY: native.base_crate -> native.base_crate:Square: "
    "publication outside the public interface"
)
# AD-608: a `pub use` at the root of a library crate publishes its name to other crates.
PUBLICATIONS = [
    ("unlisted publication", "pub use shapes::Square;\n", [], "FAIL"),
    ("listed publication", "pub use shapes::Square;\n", ["native.base_crate:Square"], "PASS"),
    ("restricted re-export", "pub(crate) use shapes::Square;\n", [], "PASS"),
    ("published glob", "pub use shapes::*;\n", [], "UNKNOWN"),
]


@pytest.mark.parametrize(("name", "line", "more", "status"), PUBLICATIONS)
def test_a_crate_root_publishes_only_names_that_its_component_lists(
    core_binary: Path, tmp_path: Path, name: str, line: str, more: list[str], status: str
) -> None:
    base = {**component("base", "base_crate"), "public": PUBLIC + more}
    app = component("app", "app", ("base",))
    lib = BASE["crates/base/src/lib.rs"] + line
    files = {**BASE, "crates/base/src/lib.rs": lib, "crates/app/src/lib.rs": "pub fn run() {}\n"}
    found_status, found = _run(tmp_path, core_binary, files, (base, app))
    assert found_status == status, (name, found)
    assert (PUBLISHED in found) == (status == "FAIL"), (name, found)
