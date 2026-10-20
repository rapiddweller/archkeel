# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The review-workflow fixture (#600, #601) is green, so review findings are judgment, not FAIL."""

from pathlib import Path

from test_architecture_demo import _prepare_repo

from archkeel.check.ports import ScanConfig
from archkeel.check.validation import run_validate
from archkeel.cli.observe import observe

FIXTURE = Path(__file__).parents[1] / "fixtures/M-review-workflow"
CONFIG = ScanConfig(("orders",), "orders", "architecture-contract.json", "0" * 64)


def test_review_fixture_is_green_with_proven_discovery_loaders(tmp_path: Path) -> None:
    result, _ = run_validate(_prepare_repo(tmp_path, {}, fixture=FIXTURE), CONFIG, observe)

    assert (result.exit_code, result.diagnostics) == (0, ())
    assert {row.status for row in result.rule_assessments or ()} == {"PASS"}
    assert len(result.rule_assessments or ()) == 12
