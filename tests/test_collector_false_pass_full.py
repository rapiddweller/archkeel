# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""#880: a crafted collector reply must never give a PASS. The probes on every rule family.

Consumer: the host (`run_report`). `test_collector_false_pass_gate.py` runs each probe on one
base scan in each PR. This file runs the TypeScript probes on the variants of the demo catalog
that carry the other PASS-bearing rule families: interfaces and exports (`interface_boundary`)
and layering (`layer_order`). It also sends the reply of an honest collector for each rule that
the profile marks unsupported: the host must not turn that reply into a PASS.

The Rust probes run the real collector on the sources that hid an edge in the reviews of #916.
"""

from __future__ import annotations

from pathlib import Path

import false_pass_support as support
import pytest
from rust_repository import component, repository, statuses, validate

from fixtures.demo_catalog_typescript import UNSUPPORTED_RULES, VARIANTS
from fixtures.reproduce_typescript import repository as typescript_repository

FAMILIES = {
    "interfaces-and-exports": "typescript-module-interface",
    "layering": "typescript-layer-order-positive",
}
BY_ID = {variant.id: variant for variant in VARIANTS}


@pytest.fixture(scope="module", params=sorted(FAMILIES))
def family_root(request: pytest.FixtureRequest, tmp_path_factory: pytest.TempPathFactory) -> Path:
    return typescript_repository(
        tmp_path_factory.mktemp(request.param), BY_ID[FAMILIES[request.param]]
    )


@pytest.mark.parametrize(("tamper", "argument"), support.probe_params(support.TYPESCRIPT))
def test_a_changed_reply_gives_no_pass_for_each_rule_family(
    family_root: Path, tamper: str, argument: str
) -> None:
    support.assert_not_pass(family_root, "typescript", tamper, argument)


@pytest.mark.parametrize("kind", sorted(UNSUPPORTED_RULES))
def test_an_unsupported_rule_kind_gives_no_pass_with_an_honest_reply(
    tmp_path: Path, kind: str
) -> None:
    root = typescript_repository(tmp_path, BY_ID[f"typescript-unsupported-{kind}"])
    result = support.verdict(root, "typescript", support.argv_for("typescript", "honest"))
    assert result["exit"] == 2, (kind, result["diagnostics"])
    assert "rule_unsupported_by_profile" in result["diagnostics"], kind
    assert all(result["kinds"][rule] != kind for rule in support.passing(result)), kind


# The false-PASS cases of the reviews of #916 (the Rust collector). The app crate does not require
# the crate `base_crate`, so a path that names it must be a FAIL (an edge) or UNKNOWN, never a PASS.
# The sources are the ones that hid an edge in a review: each family has its own list.
SHADOWED = {
    "module": "pub mod base_crate {}\n#[cfg(test)]\nmod tests { fn t() { base_crate::make(); } }\n",
    "type": "pub struct base_crate;\nmod m { fn t() { base_crate::make(); } }\n",
    "import of a function": "use crate::util::base_crate;\nfn t() { base_crate::make(); }\n",
    "function": "fn base_crate() {}\npub fn run() { base_crate::make(); }\n",
}
MACRO_BODY = {
    "macro argument": "pub fn run() { other::call!(base_crate); }\n",
    "path in a macro": 'pub fn run() { println!("{}", base_crate::make()); }\n',
    "macro_rules": (
        "macro_rules! m { ($c:ident) => { $c::make() }; }\npub fn run() { m!(base_crate); }\n"
    ),
    "raw identifier": "pub fn run() { r#base_crate::make(); }\n",
}
ATTRIBUTE = {
    "string with a path": '#[serde(getter = "base_crate::get")]\npub struct S;\n',
    "string with a name": '#[serde(with = "base_crate")]\npub struct S;\n',
    "attribute argument": "#[other::attr(base_crate)]\npub struct S;\n",
    "doc expression": "#![doc = base_crate::readme!()]\n",
}
RUST_PROBES = {**SHADOWED, **MACRO_BODY, **ATTRIBUTE}


@pytest.mark.parametrize("source", RUST_PROBES.values(), ids=RUST_PROBES.keys())
def test_a_rust_source_that_hides_a_crate_edge_gives_no_pass(
    tmp_path: Path, rust_binary: Path, capsys: pytest.CaptureFixture[str], source: str
) -> None:
    parts = (component("base", "base_crate"), component("app", "app"))
    files = {"crates/app/src/lib.rs": source}
    result = validate(repository(tmp_path, rust_binary, files, components=parts), capsys)

    assert statuses(result).get("REQUIRES") != "PASS"
    assert result["declared_rules"] in {"FAIL", "UNKNOWN"}
