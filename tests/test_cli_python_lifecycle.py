# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-514: the interface lifecycle checks of contract hygiene on Python, against release 4.0.1.

Consumer: a CI job that reads `archkeel validate` on a Python contract with an `interface_boundary`
rule. Release 4.0.1 refuses such a contract for `interface.undeclared`, `unused`, `missing` and
`planned_built`. The core proves a use from the imports and reads no declared facade signature, so
it never clears a contract that 4.0.1 refuses, and it names `interface.usage_unknown` where it
cannot tell unused from reached by a signature.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from corpus_support import commit_tree as commit
from python_interface_plants import build
from python_lifecycle_mounts import Variant, variants
from python_lifecycle_mounts import build as build_variant
from python_lifecycle_plants import Lifecycle, lifecycles
from test_cli_native_python_imports import verdict

CASES = lifecycles()
# What the core says for what 4.0.1 says: it cannot tell these two from a reached entry.
UNREAD = {"interface.unused", "interface.missing"}


def codes(result: dict[str, object]) -> set[str]:
    rows = result["frame"]["unsupported"]["rules"]  # type: ignore[index]
    found = {re.match(r"hygiene:(interface\.\w+):", name) for name in rows}
    return {match.group(1) for match in found if match}


@pytest.mark.parametrize("case", CASES, ids=[case.plant.name for case in CASES])
def test_the_core_names_each_finding_of_4_0_1_and_never_clears_one(
    release_core: Path, tmp_path: Path, case: Lifecycle
) -> None:
    root = tmp_path / "p"
    root.mkdir()
    result = verdict(release_core, build(root, case.plant))
    core = codes(result)
    assert core == case.core, (case.plant.name, core, result["frame"]["unsupported"])
    # The differential: a finding of 4.0.1 is a finding of the core, or `usage_unknown` for the
    # two findings that need a facade signature; a code of the core that 4.0.1 lacks is
    # `usage_unknown` and has a reason.
    for code in case.four:
        assert code in core or (code in UNREAD and "interface.usage_unknown" in core), code
    for code in core - case.four:
        assert code == "interface.usage_unknown" and case.why, code
    assert "interface" not in str(result["frame"]["unsupported"]["rules"]) or core


MOUNTS = variants()


@pytest.mark.parametrize("variant", MOUNTS, ids=[variant.name for variant in MOUNTS])
def test_a_mounted_contract_counts_only_the_imports_that_each_boundary_publishes(
    release_core: Path, tmp_path: Path, variant: Variant
) -> None:
    root = build_variant(tmp_path / "p", variant)
    commit(root)
    result = verdict(release_core, root)
    rows = result["frame"]["unsupported"]["rules"]
    found = {
        (match.group(1), match.group(2))
        for name in rows
        if (match := re.match(r"hygiene:(interface\.\w+):[^:]+?(/components/\S+?):", name))
    }
    if variant.four is None:
        # 4.0.1 passes: the core decides each rule and holds no hygiene row.
        assert found == set(), found
        assert (result["status"], result["exit_code"]) == ("PASS", 0), result["frame"]["explained"]
    else:
        # 4.0.1 gives a finding at the pointer; the core gives a finding of its own code there.
        assert found == {(variant.core, variant.four[1])}, (found, variant.four)
        assert result["status"] != "PASS"
