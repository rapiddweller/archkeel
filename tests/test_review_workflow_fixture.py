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
    root = _prepare_repo(tmp_path, {}, fixture=FIXTURE)
    result, _ = run_validate(root, CONFIG, observe)

    assert (result.exit_code, result.diagnostics) == (0, ())
    assert {row.status for row in result.rule_assessments or ()} == {"PASS"}
    assert len(result.rule_assessments or ()) == 12
    observed = observe(
        root,
        roots=CONFIG.roots,
        namespace=CONFIG.namespace,
        contract=CONFIG.contract,
        git_head="a" * 40,
        dirty=False,
        contract_root=root,
    ).observation
    assert observed is not None
    # Discovery is a review case only while its literal loaders stay proven dependencies.
    assert {
        record.data.get("target_module")
        for record in observed.records("imports") or ()
        if record.data.get("source_module") == "orders.storage.backends"
    } >= {
        "orders.storage.backends.memory",
        "orders.storage.backends.file",
        "orders.storage.backends.cloud",
    }


def test_project_adapter_adds_domain_invariants_without_copying_the_review_process() -> None:
    adapter = (FIXTURE / "skills/orders-domain/SKILL.md").read_text().splitlines()
    canonical = set(
        (Path(__file__).parents[1] / "skills/archkeel/SKILL.md").read_text().splitlines()
    )
    copied = [line for line in adapter if len(line) > 40 and line in canonical]

    assert copied == []
    assert any("`archkeel` skill" in line for line in adapter)
    assert len(adapter) < 30
