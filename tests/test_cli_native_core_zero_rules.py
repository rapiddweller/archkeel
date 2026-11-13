# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-416: an empty contract keeps the shipped result through the real CLI fallback."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest
import rust_repository as rr
from test_cli_native_core import (
    NATIVE,
    SUFFIX,
    _record,
    built,
    core_notes,
    install,
    report,
    repository,
    without_core_notes,
)
from test_cli_native_core_check import check, protocol, without_notes

from archkeel.analyzer.runtime import package_version
from tools.dual_run_corpus import corpus_cases, materialized

__all__ = ["built", "install"]


def test_declaration_only_report_keeps_the_python_result_through_fallback(
    install: Path,
    tmp_path: Path,
) -> None:
    declaration = rr.rule("ALLOW", "allowed_dependency", source="native", target="native")
    root = repository(tmp_path / "repo", install, rules=(declaration,))
    off = report(root)
    code, result, written = report(root, "--native-core")
    assert (off[0], off[1]["declared_rules"]) == (0, "PASS")
    assert (code, result["declared_rules"]) == (off[0], off[1]["declared_rules"])
    assert written == off[2]
    assert without_core_notes(result) == off[1]
    assert "contract has no decided rule" in core_notes(result)[0]


@pytest.fixture(scope="module")
def typescript(built: Path) -> Path:
    done = subprocess.run(
        [
            "cargo",
            "build",
            "--locked",
            "-q",
            "-p",
            "archkeel-typescript-collector",
            "--target-dir",
            str(built.parent),
        ],
        cwd=NATIVE,
        env={**os.environ, "ARCHKEEL_VERSION": package_version()},
        capture_output=True,
        text=True,
        check=False,
    )
    assert done.returncode == 0, done.stderr
    return built / f"archkeel-typescript-collector{SUFFIX}"


@pytest.mark.parametrize(
    "case_id",
    [
        "golden/typescript-excalidraw-laser-pointer",
        "s4/a-contract-without-rules-passes",
    ],
)
def test_zero_rule_corpus_report_has_the_same_exit_and_verdict_with_the_switch(
    install: Path,
    typescript: Path,
    case_id: str,
) -> None:
    shutil.copy2(typescript, install / typescript.name)
    _record(install, "archkeel-typescript-collector")
    case = next(case for case in corpus_cases() if case.id == case_id)
    with materialized(case) as root:
        off = report(root)
        code, result, written = report(root, "--native-core")
    assert (off[0], off[1]["declared_rules"]) == (0, "PASS")
    assert (code, result["declared_rules"]) == (off[0], off[1]["declared_rules"])
    assert written == off[2]
    assert without_core_notes(result) == off[1]
    assert "contract has no decided rule" in core_notes(result)[0]


def test_zero_rule_check_falls_back_without_changing_the_product_result(
    install: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, arguments = protocol(tmp_path, install, monkeypatch, rules=())
    off = check(arguments)
    code, result = check(arguments, "--native-core")
    assert (code, result["declared_rules"]) == (off[0], "PASS")
    assert without_notes(result) == without_notes(off[1])
    assert "contract has no decided rule" in core_notes(result)[0]
