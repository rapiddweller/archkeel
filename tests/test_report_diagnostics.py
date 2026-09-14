# Codekeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
import json
from pathlib import Path
from unittest.mock import patch

import pytest
from test_delta import _model, _record

from codekeel.check.ports import ScanConfig
from codekeel.check.report import run_report
from codekeel.ir.codec import decode_canonical_model, parse_observation
from codekeel.ir.model import Diagnostic, ObservationResult


def test_report_keeps_partial_ir_artifact_and_coverage(tmp_path: Path) -> None:
    raw = _model(git_head="a" * 40)
    failure = _record("failure", kind="parse_failure", evidence_class="UNKNOWN")
    raw["unknowns"] = [failure]
    raw["coverage"].update(status="FAIL", files_parsed=0, failures=[failure])
    model = parse_observation(raw)
    observed = ObservationResult(
        model,
        model.coverage,
        (Diagnostic("parse_error", "probe.py", "AST coverage", "Repair the syntax."),),
    )

    def producer(*args: object, **kwargs: object) -> ObservationResult:
        return observed

    with (
        patch("codekeel.check.report.resolve_commit", return_value="a" * 40),
        patch("codekeel.check.report.git_bytes", return_value=b""),
    ):
        result = run_report(
            tmp_path,
            config=ScanConfig((".",), "sample", "contract.json", "d" * 64),
            producer=producer,
        )
    assert result.exit_code == 2
    assert result.coverage == model.coverage
    assert result.diagnostics == observed.diagnostics
    assert result.artifact == "test-artifacts/architecture/architecture.json"
    assert decode_canonical_model(json.loads((tmp_path / result.artifact).read_bytes())) == raw


@pytest.mark.parametrize("outside", [False, True])
def test_report_artifact_path_is_relative_only_inside_root(tmp_path: Path, outside: bool) -> None:
    root = tmp_path / "root"
    output = tmp_path / "outside.json" if outside else root / "report.json"
    model = parse_observation(_model(git_head="a" * 40))

    def producer(*args: object, **kwargs: object) -> ObservationResult:
        return ObservationResult(model, model.coverage, ())

    with (
        patch("codekeel.check.report.resolve_commit", return_value="a" * 40),
        patch("codekeel.check.report.git_bytes", return_value=b""),
    ):
        result = run_report(
            root,
            config=ScanConfig((".",), "sample", "contract.json", "d" * 64),
            output=output,
            producer=producer,
        )
    assert result.exit_code == 0
    assert result.artifact == (str(output.resolve()) if outside else "report.json")
    assert decode_canonical_model(json.loads(output.read_bytes())) == _model(git_head="a" * 40)
