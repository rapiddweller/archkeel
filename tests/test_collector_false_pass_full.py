# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""#880: a crafted collector reply must never give a PASS. The probes on every rule family.

Consumer: the host (`run_report`). `test_collector_false_pass_gate.py` runs each probe on one
base scan in each PR. This file runs the TypeScript probes on the variants of the demo catalog
that carry the other PASS-bearing rule families: interfaces and exports (`interface_boundary`)
and layering (`layer_order`). It also sends the reply of an honest collector for each rule that
the profile marks unsupported: the host must not turn that reply into a PASS.

The scan of the Rust collector is not on `main`: see `test_a_rust_reply_gives_no_pass`.
"""

from __future__ import annotations

from pathlib import Path

import false_pass_support as support
import pytest

from fixtures.demo_catalog_typescript import UNSUPPORTED_RULES, VARIANTS
from fixtures.reproduce_typescript import repository

FAMILIES = {
    "interfaces-and-exports": "typescript-module-interface",
    "layering": "typescript-layer-order-positive",
}
BY_ID = {variant.id: variant for variant in VARIANTS}


@pytest.fixture(scope="module", params=sorted(FAMILIES))
def family_root(request: pytest.FixtureRequest, tmp_path_factory: pytest.TempPathFactory) -> Path:
    return repository(tmp_path_factory.mktemp(request.param), BY_ID[FAMILIES[request.param]])


@pytest.mark.parametrize(("tamper", "argument"), support.probe_params(support.TYPESCRIPT))
def test_a_changed_reply_gives_no_pass_for_each_rule_family(
    family_root: Path, tamper: str, argument: str
) -> None:
    support.assert_not_pass(family_root, "typescript", tamper, argument)


@pytest.mark.parametrize("kind", sorted(UNSUPPORTED_RULES))
def test_an_unsupported_rule_kind_gives_no_pass_with_an_honest_reply(
    tmp_path: Path, kind: str
) -> None:
    root = repository(tmp_path, BY_ID[f"typescript-unsupported-{kind}"])
    result = support.verdict(root, "typescript", support.argv_for("typescript", "honest"))
    assert result["exit"] == 2, (kind, result["diagnostics"])
    assert "rule_unsupported_by_profile" in result["diagnostics"], kind
    assert all(result["kinds"][rule] != kind for rule in support.passing(result)), kind


# The false-PASS cases of the reviews of #916 (the Rust collector). Each case is a Rust source
# that the collector must not read as a dependency that is allowed, or as no dependency:
# 1. A local name equal to a crate name: `let serde = 1; serde::x()` is not a use of the crate.
# 2. The body of a macro: `macro_rules!` and `println!("{}", other::f())` hide or show a path.
# 3. An attribute string: `#[doc = "use forbidden::x;"]` is text, not an import.
@pytest.mark.skip(reason="the Rust collector is not on main: add these probes when #916 merges")
def test_a_rust_reply_gives_no_pass() -> None:
    raise AssertionError("#916")
