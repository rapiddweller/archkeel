# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""A gap whose evidence does not bind to its module gives no dependency scope proof."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from test_scoped_dependency_proof import _project
from test_typescript_partial_uml import _TypeScriptCollector

import archkeel.check.observation as observation
from archkeel.check.observe import Observer
from archkeel.check.report import run_report


def _receipts(
    root: Path, *, break_gap_evidence: bool, monkeypatch: pytest.MonkeyPatch
) -> list[Any]:
    """Return the requires receipts as the check leaves them, before the model is parsed."""
    config = _project(root)
    seen: list[Any] = []
    certify = observation._certify_dependency_scopes

    def spy(scan: Any, facts: Any, digest: str, declarations: Any) -> None:
        if break_gap_evidence:
            gap_evidence = {i for gap in scan.coverage["failures"] for i in gap["evidence_ids"]}
            broken = [item for item in scan.evidence if item["id"] in gap_evidence]
            assert broken
            for item in broken:
                item["file"] = "src/not_the_module.ts"  # the evidence no longer binds to the module
        certify(scan, facts, digest, declarations)
        requires = {i["id"] for i in declarations if i["kind"] == "complete_requires"}
        seen.extend(
            item
            for item in scan.scope_observations
            if item["kind"] == "rule_evaluation" and item["rule_ids"][0] in requires
        )

    monkeypatch.setattr(observation, "_certify_dependency_scopes", spy)
    try:
        run_report(root, config=config, analyzer=Observer(_TypeScriptCollector()))
    except (ValueError, KeyError):
        pass  # a broken model may fail later; this test reads the receipts before that
    return seen


def test_intact_gap_evidence_gives_a_proof(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    receipts = _receipts(tmp_path / "p", break_gap_evidence=False, monkeypatch=monkeypatch)
    assert receipts
    assert any(r["data"].get("dependency_scope_proof") for r in receipts)
    assert any(r["data"]["assessment_complete"] for r in receipts)


def test_broken_gap_evidence_gives_no_proof_and_no_complete_assessment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    receipts = _receipts(tmp_path / "p", break_gap_evidence=True, monkeypatch=monkeypatch)
    assert receipts
    assert not any("dependency_scope_proof" in r["data"] for r in receipts)
    assert [r["data"]["assessment_complete"] for r in receipts] == [False] * len(receipts)
