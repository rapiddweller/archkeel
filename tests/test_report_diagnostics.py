# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
import json
from pathlib import Path
from unittest.mock import patch

import pytest
from test_delta import _model, _record

from archkeel.check.ports import ScanConfig
from archkeel.check.report import run_report
from archkeel.cli import main
from archkeel.ir.codec import decode_canonical_model, parse_observation
from archkeel.ir.model import Diagnostic, ObservationResult


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
        patch("archkeel.check.report.resolve_commit", return_value="a" * 40),
        patch("archkeel.check.report.git_bytes", return_value=b""),
    ):
        result, architecture = run_report(
            tmp_path,
            config=ScanConfig((".",), "sample", "contract.json", "d" * 64),
            producer=producer,
        )
    assert result.exit_code == 2
    assert result.coverage == model.coverage
    assert result.diagnostics == observed.diagnostics
    assert result.artifact is None
    assert architecture is not None
    assert decode_canonical_model(json.loads(architecture)) == raw
    assert not (tmp_path / "test-artifacts/architecture/interactive.html").exists()


@pytest.mark.parametrize("outside", [False, True])
def test_cli_report_artifact_path_is_relative_only_inside_root(
    tmp_path: Path, outside: bool, capsys: pytest.CaptureFixture[str]
) -> None:
    root = tmp_path / "root"
    root.mkdir()
    output = tmp_path / "outside.json" if outside else root / "report.json"
    model = parse_observation(_model(git_head="a" * 40))

    def producer(*args: object, **kwargs: object) -> ObservationResult:
        return ObservationResult(model, model.coverage, ())

    with (
        patch("archkeel.check.report.resolve_commit", return_value="a" * 40),
        patch("archkeel.check.report.git_bytes", return_value=b""),
        patch(
            "archkeel.cli.load_config",
            return_value=ScanConfig((".",), "sample", "contract.json", "d" * 64),
        ),
        patch("archkeel.cli.observe", producer),
    ):
        assert main(["report", "--root", str(root), "--output", str(output)]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["artifact"] == (str(output.resolve()) if outside else "report.json")
    assert decode_canonical_model(json.loads(output.read_bytes())) == _model(git_head="a" * 40)
    assert (output.parent / "interactive.html").is_file()
