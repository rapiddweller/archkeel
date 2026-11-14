# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""#619, #880: two rule kinds that the core does not port give UNKNOWN by name, never PASS.

Consumer: a CI job that reads `archkeel validate` or `report` on a contract that still holds a rule
kind of 4.0.1 (here `symbol_placement` and `boundary_types`). An unported rule has no row, and
the gap `rule_kind_not_ported` names it, so the run is UNKNOWN and exits 2. The native test
`unported_tests.rs` of `archkeel-eval` pins every unported kind at the evaluator.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from rust_repository import CRATE_RULES, claims, outcome, repository, rule, statuses

OWNERSHIP = rule(
    "PLACED",
    "symbol_placement",
    source="native",
    class_kinds=["enum"],
    allowed_sources=["native.base_crate"],
)
TYPES = rule("TYPED", "boundary_types", source="native.app")


@pytest.mark.parametrize("command", ["validate", "report"])
def test_two_unported_rule_kinds_are_unknown_by_name_and_hold_the_run(
    tmp_path: Path, core_binary: Path, command: str
) -> None:
    root = repository(tmp_path, core_binary, rules=(*CRATE_RULES, OWNERSHIP, TYPES))

    code, document = outcome(root, command)

    assert (code, document["exit_code"], document["status"]) == (2, 2, "UNKNOWN"), claims(document)
    rows = statuses(document)
    # An unported rule has no row, so no PASS row can stand for it (the gap names it below).
    assert "PLACED" not in rows and "TYPED" not in rows, rows
    for name in ("PLACED", "TYPED"):
        assert any(f"rule_kind_not_ported: {name}" in claim for claim in claims(document)), name
