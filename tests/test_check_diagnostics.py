# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
import json
from contextlib import nullcontext
from hashlib import sha256
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from test_delta import _model, _record
from test_expectation import _expectation_payload
from test_git_lock import _lock

from archkeel.check.ports import ScanConfig
from archkeel.check.report import render_result
from archkeel.check.run import run_check
from archkeel.check.snapshot import ArchivedSnapshot
from archkeel.ir.codec import parse_observation
from archkeel.ir.model import Diagnostic, ObservationResult


@pytest.mark.parametrize("stage", ["accepted", "candidate"])
def test_check_keeps_partial_observation_on_exit_two(tmp_path: Path, stage: str) -> None:
    raw = _model(git_head="a" * 40)
    lock_bytes = _lock(raw)
    complete = parse_observation(raw)
    failure = _record("partial", kind="parse_failure", evidence_class="UNKNOWN")
    raw["unknowns"] = [failure]
    raw["coverage"].update(status="FAIL", files_parsed=0, failures=[failure])
    partial = parse_observation(raw)
    observed = ObservationResult(
        partial,
        partial.coverage,
        (Diagnostic("parse_error", "probe.py", "AST coverage", "Repair the syntax."),),
    )
    results = (
        [observed]
        if stage == "accepted"
        else [ObservationResult(complete, complete.coverage, ()), observed]
    )
    analyzer = Mock(side_effect=results)
    expected = _expectation_payload()
    expected.update(accepted_digest=sha256(lock_bytes).hexdigest(), baseline_commit="b" * 40)
    expected_bytes = json.dumps(expected).encode()
    contract_bytes = json.dumps({"schema_version": "2.1.0", "components": [], "rules": []}).encode()

    def read_blob(root: Path, commit: str, path: str) -> bytes:
        if path == "expectation.json":
            return expected_bytes
        if path == "contract.json":
            return contract_bytes
        return lock_bytes

    with (
        patch("archkeel.check.run.remote_tip", return_value="b" * 40),
        patch("archkeel.check.run.read_blob", side_effect=read_blob),
        patch("archkeel.check.run.parents", return_value=["a" * 40]),
        patch("archkeel.check.run.changed_paths", return_value={"architecture-accepted.json"}),
        patch("archkeel.check.run.package_digest", return_value="c" * 64),
        patch("archkeel.check.run.check_git_order", return_value=()),
        patch("archkeel.check.run.check_order", return_value=()),
        patch("archkeel.check.run.materialize_declarations"),
        patch(
            "archkeel.check.run.materialize_git_snapshot",
            side_effect=lambda *args, **kwargs: nullcontext(ArchivedSnapshot(tmp_path, "a" * 40)),
        ),
    ):
        result = run_check(
            tmp_path,
            config=ScanConfig((".",), "sample", "contract.json", "b" * 64),
            baseline="b" * 40,
            expectation_commit="e" * 40,
            head="f" * 40,
            expected_path="expectation.json",
            expected_digest=sha256(expected_bytes).hexdigest(),
            branch="candidate",
            accepted_branch="main",
            host_records_path=None,
            environ={},
            host=Mock(return_value=()),
            analyzer=analyzer,
        )
    assert result.exit_code == 2
    assert result.observation == partial
    assert result.coverage == partial.coverage
    assert result.diagnostics == observed.diagnostics
    assert parse_observation(json.loads(render_result(result))["observation"]) == partial
