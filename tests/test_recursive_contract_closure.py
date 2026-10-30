# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Independent recursive closure checks, without depending on a loader implementation."""

import json
from pathlib import Path

import pytest
from test_analyzer import _observe
from test_recursive_inside_independent_contracts import (
    _commit_tree,
    _component_at,
    _contract,
    _write_three_levels,
)

from archkeel.check.ports import ScanConfig
from archkeel.check.run import materialize_declarations
from archkeel.check.validation import inside_diagnostics
from archkeel.ir.codec import parse_contract
from archkeel.ir.trace import trace_valid_violations


def test_deep_rule_sources_stop_at_immediate_parent_not_root_ancestor(tmp_path: Path) -> None:
    _write_three_levels(tmp_path)
    leaf = _contract(
        [_component_at("api", "sample.layer.source.api")],
        [
            {
                "id": "NO-EVAL",
                "kind": "forbidden_construct",
                "source": "sample",
                "constructs": ["eval"],
                "rationale": "No evaluation in this child.",
                "provenance": ["docs/architecture/sample.md"],
                "decided_by": "architect",
            }
        ],
    )
    second_path = tmp_path / "contracts/two.json"
    second = json.loads(second_path.read_text())
    second["components"][0]["inside"] = "contracts/leaf.json"
    second_path.write_text(json.dumps(second))
    (tmp_path / "contracts/leaf.json").write_text(json.dumps(leaf))
    for module in ("source", "target"):
        (tmp_path / f"sample/layer/{module}/api.py").write_text(
            "def run():\n    return eval('1')\n"
        )

    result = _observe(tmp_path)

    assert result.observation is not None, result.diagnostics
    findings = [
        item
        for item in trace_valid_violations(result.observation)
        if item.kind == "forbidden_construct"
    ]
    assert len(findings) == 1
    assert findings[0].subjects == ("sample.layer.source.api.run",)


@pytest.mark.parametrize("graph", ["cycle", "duplicate_mount"])
def test_symlink_alias_cannot_hide_cycle_or_duplicate_mount(tmp_path: Path, graph: str) -> None:
    _write_three_levels(tmp_path)
    real = tmp_path / "contracts/two.json"
    (tmp_path / "contracts/alias.json").symlink_to("two.json")
    if graph == "cycle":
        leaf = json.loads(real.read_text())
        leaf["components"][0]["inside"] = "contracts/alias.json"
        real.write_text(json.dumps(leaf))
    else:
        real.write_text(json.dumps(_contract([], [])))
        first_path = tmp_path / "contracts/one.json"
        first = json.loads(first_path.read_text())
        first["components"].append(
            _component_at("other", "sample.other", inside="contracts/alias.json")
        )
        first_path.write_text(json.dumps(first))

    contract = parse_contract(json.loads((tmp_path / "contract.json").read_text()))
    diagnostics = inside_diagnostics(
        tmp_path,
        contract,
        ScanConfig(("sample",), "sample", "contract.json", "0" * 64),
    )

    assert diagnostics
    if graph == "duplicate_mount":
        assert any(
            item.code == "contract.invalid" and "duplicate mount" in item.unknown_claim
            for item in diagnostics
        )
    assert _observe(tmp_path).diagnostics


def test_snapshot_discovers_recursive_tree_only_from_accepted_revision(tmp_path: Path) -> None:
    _write_three_levels(tmp_path)
    first = tmp_path / "contracts/one.json"
    leaf = tmp_path / "contracts/two.json"
    accepted_first = first.read_bytes()
    accepted_leaf = leaf.read_bytes()
    revision = _commit_tree(tmp_path)
    # Neither a candidate's severed edge nor its broken leaf can replace accepted policy.
    first.write_text(json.dumps(_contract([], [])))
    leaf.write_text("not a contract\n")
    snapshot = tmp_path / "snapshot"

    materialize_declarations(
        tmp_path,
        revision,
        ScanConfig(("sample",), "sample", "contract.json", "0" * 64),
        snapshot,
    )

    assert (snapshot / "contracts/one.json").read_bytes() == accepted_first
    assert (snapshot / "contracts/two.json").read_bytes() == accepted_leaf
