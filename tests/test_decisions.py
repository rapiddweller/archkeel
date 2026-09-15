# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-15: open_decisions derives undecided component pairs from one observation alone."""

import json
from pathlib import Path

from test_architecture_demo import _prepare_repo

from archkeel.analyzer import observe
from archkeel.check.ports import ScanConfig
from archkeel.check.report import run_report
from archkeel.check.validation import closed_world_diagnostics
from archkeel.ir.codec import decode_canonical_model, decode_json, parse_contract, parse_observation
from archkeel.ir.decisions import open_decisions
from fixtures.demo_catalog_support import contract_without_rule

CONFIG = ScanConfig(("shop",), "shop", "architecture-contract.json", "0" * 64)


def test_open_decisions_reports_the_pair_left_undecided_by_a_removed_allowed_rule(
    tmp_path: Path,
) -> None:
    root = _prepare_repo(
        tmp_path, {"architecture-contract.json": contract_without_rule("DEP-STORE-ALLOWS-MODEL")}
    )
    _, architecture = run_report(root, config=CONFIG, analyzer=observe)
    assert architecture is not None
    observation = parse_observation(decode_canonical_model(json.loads(architecture)))

    decisions = open_decisions(observation)

    assert [(item.source, item.target) for item in decisions] == [("store", "model")]
    assert decisions[0].observed is True
    assert decisions[0].import_sites == 1


def test_validation_and_open_decisions_agree_on_undecided_pairs(tmp_path: Path) -> None:
    root = _prepare_repo(
        tmp_path, {"architecture-contract.json": contract_without_rule("DEP-STORE-ALLOWS-MODEL")}
    )
    _, architecture = run_report(root, config=CONFIG, analyzer=observe)
    assert architecture is not None
    observation = parse_observation(decode_canonical_model(json.loads(architecture)))
    contract = parse_contract(decode_json((root / "architecture-contract.json").read_bytes()))

    decisions = open_decisions(observation)
    diagnostics = closed_world_diagnostics(contract, observation)
    open_subjects = {item.subject for item in diagnostics if item.code == "decision.open"}

    assert open_subjects == {f"{item.source} -> {item.target}" for item in decisions}
    assert open_subjects == {"store -> model"}
