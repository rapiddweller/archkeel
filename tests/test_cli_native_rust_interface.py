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
from hashlib import sha256
from pathlib import Path
from typing import Any

import pytest
from corpus_support import commit_tree
from rust_repository import (
    CRATE_RULES,
    claims,
    component,
    report,
    repository,
    rule,
    statuses,
    validate,
)

pytestmark = pytest.mark.skipif(shutil.which("cargo") is None, reason="rustc is the oracle")

BASE = {
    "crates/base/src/lib.rs": (
        "pub mod shapes;\npub mod relay;\npub mod gated;\nmod inner;\nmod extra;\npub mod made;\n"
        "pub use inner::Thing;\n"
        "pub fn make() {}\npub fn secret() {}\npub struct Tool;\n"
    ),
    "crates/base/src/inner.rs": "pub struct Thing;\n",
    "crates/base/src/shapes.rs": "pub struct Circle;\npub struct Square;\n",
    # AD-614: one name, two definitions under `cfg`: each is a definition of `gated`.
    "crates/base/src/gated.rs": (
        "#[cfg(test)]\npub fn skip() -> bool {\n    true\n}\n"
        "#[cfg(not(test))]\npub fn skip() -> bool {\n    false\n}\n"
    ),
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
        "name with two definitions under cfg",
        "pub fn run() -> bool { base_crate::gated::skip() }\n",
        [],
        "FAIL",
        VIOLATION.format("native.base_crate.gated:skip"),
    ),
    (
        "listed name with two definitions under cfg",
        "pub fn run() -> bool { base_crate::gated::skip() }\n",
        ["native.base_crate.gated:skip"],
        "PASS",
        None,
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
        "BOUNDARY: incomplete scope: 1 module pair with gaps that the contract does not allow: "
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
        f"native.base_crate.{m}" for m in ("shapes", "inner", "made", "relay", "gated")
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


# AD-604: the Rust collector names the item and the route of each import, so the core decides the
# rule. `make` is a definition of the root of `base`; a glob names no known name.
INTERFACE_PLANTS = [
    ("the whole root is public", ["native.base_crate"], "use base_crate::make;\n", "PASS"),
    ("the name is public", ["native.base_crate:make"], "use base_crate::make;\n", "PASS"),
    ("another name is public", ["native.base_crate:other"], "use base_crate::make;\n", "FAIL"),
    ("a glob", ["native.base_crate:make"], "use base_crate::*;\n", "UNKNOWN"),
]


@pytest.mark.parametrize(("name", "public", "head", "status"), INTERFACE_PLANTS)
def test_the_core_decides_interface_boundary_from_the_item_of_each_import(
    tmp_path: Path,
    core_binary: Path,
    name: str,
    public: list[str],
    head: str,
    status: str,
) -> None:
    base = {**component("base", "base_crate"), "public": public}
    parts = (base, component("app", "app", ("base",)))
    boundary = rule("INTERFACE", "interface_boundary")
    source = {"crates/app/src/lib.rs": head + "pub fn run() { make(); }\n"}
    result = validate(repository(tmp_path, core_binary, source, parts, (*CRATE_RULES, boundary)))

    assert statuses(result).get("INTERFACE") == status, (name, claims(result))
    if status == "FAIL":
        assert (
            "INTERFACE: native.app -> native.base_crate:make: import outside the public interface"
            in claims(result)
        )


@pytest.mark.parametrize(
    ("body", "status"),
    [
        ("base_crate::extra::allowed();", "PASS"),
        ("value.touch(); base_crate::extra::allowed();", "FAIL"),
        ("let r = if true { value } else { value }; r.touch();", "UNKNOWN"),
        (
            "let r = if true { value } else { value }; r.touch(); base_crate::extra::allowed();",
            "UNKNOWN",
        ),
        (
            "base_crate::extra::allowed(); let r = if true { value } else { value }; r.touch();",
            "UNKNOWN",
        ),
    ],
    ids=["allowed", "exact-unlisted", "unread", "unread-first", "listed-first"],
)
def test_a_listed_import_does_not_prove_a_different_method(
    release_core: Path, tmp_path: Path, body: str, status: str
) -> None:
    base = {
        **component("base", "base_crate"),
        "packages": [],
        "exact_modules": ["native.base_crate", "native.base_crate.cargo_toml"],
        "public": ["native.base_crate:Tool"],
    }
    extra = {
        **component("extra", "base_crate.extra", ("base",)),
        "public": ["native.base_crate.extra:allowed"],
    }
    app = component("app", "app", ("base", "extra"))
    files = {
        "crates/base/src/lib.rs": "pub mod extra;\npub struct Tool;\n",
        "crates/base/src/extra.rs": (
            "impl crate::Tool { pub fn touch(&self) {} }\npub fn allowed() {}\n"
        ),
        "crates/app/src/lib.rs": f"pub fn run(value: &base_crate::Tool) {{ {body} }}\n",
    }
    found, messages = _run(tmp_path, release_core, files, (base, extra, app))
    assert found == status, messages
    if status == "FAIL":
        assert VIOLATION.format("native.base_crate.extra:Tool") in messages


@pytest.mark.parametrize(
    ("return_type", "body", "status"),
    [
        ("impl Sized", "drop(base_crate::make());", "PASS"),
        ("impl Sized", "base_crate::hidden::secret(); drop(base_crate::make());", "FAIL"),
        (
            "hidden::Hidden",
            "let r = if true { base_crate::make() } else { base_crate::make() }; r.touch();",
            "UNKNOWN",
        ),
    ],
    ids=["execution-only", "unlisted-name", "mixed-method-and-execution"],
)
def test_impl_execution_does_not_hide_an_unread_named_use(
    release_core: Path, tmp_path: Path, return_type: str, body: str, status: str
) -> None:
    base = {
        **component("base", "base_crate", ("hidden",)),
        "packages": [],
        "exact_modules": ["native.base_crate", "native.base_crate.cargo_toml"],
        "public": ["native.base_crate:make"],
    }
    hidden = {
        **component("hidden", "base_crate.hidden"),
        "public": ["native.base_crate.hidden:make", "native.base_crate.hidden:Hidden"],
    }
    app = component("app", "app", ("base", "hidden"))
    files = {
        "crates/base/src/lib.rs": (
            f"pub mod hidden;\npub fn make() -> {return_type} {{ hidden::make() }}\n"
        ),
        "crates/base/src/hidden.rs": (
            "pub struct Hidden;\n"
            "impl Drop for Hidden { fn drop(&mut self) {} }\n"
            "impl Hidden { pub fn touch(&self) {} }\n"
            "pub fn make() -> Hidden { Hidden }\n"
            "pub fn secret() {}\n"
        ),
        "crates/app/src/lib.rs": f"pub fn run() {{ {body} }}\n",
    }
    found, messages = _run(tmp_path, release_core, files, (base, hidden, app))
    assert found == status, messages


@pytest.mark.parametrize(
    ("receiver", "publish_scopes", "expected"),
    [
        ("Scopes::qualified(&kept.scopes, at)", True, "PASS"),
        ("Scopes::qualified(&kept.scopes, at)", False, "FAIL"),
        ("kept.scopes.qualified(at)", True, "UNKNOWN"),
    ],
    ids=["listed-type", "unlisted-type", "open-receiver"],
)
def test_a_scope_read_uses_the_written_receiver_type_when_present(
    tmp_path: Path, release_core: Path, receiver: str, publish_scopes: bool, expected: str
) -> None:
    public = ["native.app.scope_store:Kept"]
    if publish_scopes:
        public.append("native.app.scope_store:Scopes")
    store = {**component("scope-store", "app.scope_store"), "public": public}
    app = {
        **component("app", "app", ("base", "scope-store")),
        "packages": [],
        "exact_modules": ["native.app", "native.app.cargo_toml"],
    }
    files = {
        "crates/app/src/scope_store.rs": (
            "pub struct Kept { pub scopes: Scopes }\n"
            "pub struct Scopes;\n"
            "impl Scopes { pub fn qualified(&self, at: u32) -> u32 { at } }\n"
        ),
        "crates/app/src/lib.rs": (
            "pub mod scope_store;\n"
            "use crate::scope_store::Scopes;\n"
            "pub fn run(kept: &scope_store::Kept, site: Option<u32>) -> Option<u32> {\n"
            "    let kept = if site.is_some() { kept } else { kept };\n"
            f"    site.map(|at| {receiver})\n"
            "}\n"
        ),
    }
    status, found = _run(
        tmp_path, release_core, files, (component("base", "base_crate"), store, app)
    )
    assert status == expected, found
    if expected == "FAIL":
        assert VIOLATION.format("native.app.scope_store:Scopes") in found


@pytest.mark.parametrize("separator", [" ", "\n    "], ids=["same-line", "separate-lines"])
def test_a_glob_keeps_both_trait_call_positions(
    release_core: Path, tmp_path: Path, separator: str
) -> None:
    child = "crates/app/src/child.rs"
    source = (
        "use super::*;\nuse crate::api::allowed;\n"
        f"pub fn run(value: u8) {{ allowed(); value.touch();{separator}value.touch(); }}\n"
    )
    repository(
        tmp_path,
        release_core,
        {
            "crates/app/src/lib.rs": "pub mod api;\nmod child;\nuse api::Touch;\n",
            "crates/app/src/api.rs": (
                "pub trait Touch { fn touch(&self) {} }\n"
                "impl Touch for u8 {}\npub fn allowed() {}\n"
            ),
            child: source,
        },
    )
    _rustc_accepts(tmp_path)
    locations = report(tmp_path)["frame"]["locations"]
    expected = {}
    for line, text in enumerate(source.splitlines(), 1):
        for column in range(len(text)):
            if text.startswith("touch()", column):
                identity = f"{child}\x1f{line}\x1f{line}\x1f{column}"
                evidence = f"EVD-{sha256(identity.encode()).hexdigest()[:16]}"
                expected[evidence] = {"path": child, "line": line}
    assert len(expected) == 2
    assert {evidence: locations.get(evidence) for evidence in expected} == expected
