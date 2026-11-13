# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The review-workflow fixture (#600, #601) is green, so review findings are judgment, not FAIL."""

from pathlib import Path

from archkeel.check.ports import ScanConfig

FIXTURE = Path(__file__).parents[1] / "fixtures/M-review-workflow"
CONFIG = ScanConfig(("orders",), "orders", "architecture-contract.json", "0" * 64)


def test_project_adapter_adds_domain_invariants_without_copying_the_review_process() -> None:
    adapter = (FIXTURE / "skills/orders-domain/SKILL.md").read_text().splitlines()
    canonical = set(
        (Path(__file__).parents[1] / "skills/archkeel/SKILL.md").read_text().splitlines()
    )
    copied = [line for line in adapter if len(line) > 40 and line in canonical]

    assert copied == []
    assert any("`archkeel` skill" in line for line in adapter)
    assert len(adapter) < 30
