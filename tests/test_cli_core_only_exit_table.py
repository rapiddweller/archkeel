# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-430: the exit table of the default path, on one real project for each line of the table.

Consumer: a CI job that reads the exit code of `archkeel validate` or `archkeel report`. Code 0 is
only for a verdict that the core proved. A failure is 1. Each other result is 2: a source gap, a
rule kind that the core does not decide, and a profile that the core does not collect.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from corpus_support import commit_tree
from rust_repository import CRATE_RULES, claims, component, outcome, repository, rule, statuses

ENUMS = rule(
    "ENUMS-IN-BASE",
    "symbol_placement",
    source="native",
    class_kinds=["enum"],
    allowed_sources=["native.base_crate"],
)
# A config without `language` selects the Python profile.
PYTHON = (
    '[scan]\nroots = ["crates"]\nnamespace = "native"\ncontract = "architecture-contract.json"\n'
)
# name: (changes of the fixture, exit code, status, a text that the result must name)
TABLE: dict[str, tuple[dict[str, Any], int, str, str]] = {
    "a proven pass": ({}, 0, "PASS", ""),
    "a proven failure": (
        {"components": (component("base", "base_crate"), component("app", "app"))},
        1,
        "FAIL",
        "REQUIRES: native.app -> native.base_crate",
    ),
    "a source gap": (
        {"files": {"crates/app/src/lib.rs": 'include!("generated.rs");\n'}},
        2,
        "UNKNOWN",
        "The macro include! adds code that the scan does not read",
    ),
    "a rule kind that the core does not decide": (
        {"rules": (*CRATE_RULES, ENUMS)},
        2,
        "UNKNOWN",
        "rule_kind_not_ported: ENUMS-IN-BASE",
    ),
    "a profile that the core does not collect": (
        {"config": PYTHON},
        2,
        "UNKNOWN",
        "python",
    ),
}


@pytest.mark.parametrize("command", ["validate", "report"])
@pytest.mark.parametrize(("changes", "code", "status", "names"), TABLE.values(), ids=TABLE.keys())
def test_the_default_path_gives_the_exit_code_of_its_table(
    tmp_path: Path,
    core_binary: Path,
    command: str,
    changes: dict[str, Any],
    code: int,
    status: str,
    names: str,
) -> None:
    config = changes.get("config")
    fixture = {name: value for name, value in changes.items() if name != "config"}
    root = repository(tmp_path, core_binary, **fixture)
    if config is not None:
        (root / "archkeel.toml").write_text(config)
        commit_tree(root)

    found, document = outcome(root, command)

    assert (found, document["exit_code"], document["status"]) == (code, code, status), claims(
        document
    )
    assert not names or any(names in claim for claim in claims(document)), claims(document)
    # Code 0 needs a PASS for each rule; no other line of the table may hold only PASS rows.
    rows = set(statuses(document).values())
    assert (rows == {"PASS"}) == (code == 0), statuses(document)
