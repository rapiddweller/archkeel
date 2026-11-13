# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""#880: a crafted collector reply must never give a PASS. The fast subset that each PR runs.

Consumer: the host (`run_report`). One TypeScript scan and one Python scan are the base. Each probe
changes the reply of the real collector in one way (`false_pass_support.py`) and sends it as a
pinned producer, so the host checks the reply (AD-344). The honest probe is an external producer.
The expected verdict is UNKNOWN or FAIL, never PASS.
`test_collector_false_pass_full.py` runs the same probes on more rule families.

A probe with a reason is a strict xfail: the host still gives PASS today. It fails when the host
closes the gap, so the closing change must remove the reason.
"""

from __future__ import annotations

from pathlib import Path

import areas
import false_pass_support as support
import pytest

from archkeel.ir import facts_validation

ROOT = Path(__file__).parents[1]


@pytest.fixture(scope="module")
def typescript_root(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return support.copy_repository(
        ROOT / "fixtures/H-typescript", tmp_path_factory.mktemp("typescript")
    )


@pytest.fixture(scope="module")
def python_root(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return support.copy_repository(
        ROOT / "fixtures/F-architecture", tmp_path_factory.mktemp("python")
    )


@pytest.mark.parametrize(("tamper", "argument"), support.probe_params(support.TYPESCRIPT))
def test_a_changed_typescript_reply_gives_no_pass(
    typescript_root: Path, tamper: str, argument: str
) -> None:
    support.assert_not_pass(typescript_root, "typescript", tamper, argument)


@pytest.mark.parametrize("section", support.UNREAD_SECTIONS)
def test_emptying_a_section_that_no_typescript_rule_reads_changes_no_verdict(
    typescript_root: Path, section: str
) -> None:
    support.assert_unchanged(typescript_root, "typescript", section)


def test_a_duplicate_record_id_fails_in_the_unique_check_too() -> None:
    # The probe `duplicate-id` is caught by an earlier check. This test pins `_unique` itself.
    with pytest.raises(ValueError, match="duplicate source record id"):
        facts_validation._unique(["a", "b", "a"], "source record id")


def test_the_full_probe_file_belongs_to_a_full_area() -> None:
    # Full runs each area (`make full-test AREA=...`); a file outside every area would not run.
    assert areas.area_of("test_collector_false_pass_full.py") == "collectors"
    assert areas.area_of("test_collector_false_pass_gate.py") == "collectors"
