# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""#880: a crafted collector reply must never give a PASS. The fast subset that each PR runs.

Consumer: the host (`run_report`). One TypeScript scan and one Python scan are the base. Each probe
changes the reply of the real collector in one way (`false_pass_support.py`) and sends it as an
external producer. The expected verdict is UNKNOWN or FAIL, never PASS.
`test_collector_false_pass_full.py` runs the same probes on more rule families.

A probe with a reason is a strict xfail: the host still gives PASS today. It fails when the host
closes the gap, so the closing change must remove the reason.
"""

from __future__ import annotations

from pathlib import Path

import false_pass_support as support
import pytest

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


@pytest.mark.parametrize(("tamper", "argument"), support.probe_params(support.PYTHON))
def test_a_changed_python_reply_gives_no_pass(
    python_root: Path, tamper: str, argument: str
) -> None:
    support.assert_not_pass(python_root, "python", tamper, argument)
